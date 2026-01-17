"""文件职责：项目启动入口，提供多 Agent CLI 交互与行为演示。
简明实现逻辑：解析参数→加载配置→初始化认知/行为模块→进入 CLI 或 demo。
输入输出：输入为 CLI 参数/用户输入；输出为对话与行动结果。"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
import time
import toml
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.behavior.actions import (
    Action as BehaviorAction,
    ActionResult as BehaviorActionResult,
    execute_action,
    expand_action_chain,
    parse_action_plan,
)
from src.behavior.goap import Action as GoapAction, GOAPPlanner
from src.cognitive.knowledge.interceptor import KnowledgeInterceptor
from src.cognitive.knowledge.tree import KnowledgeBase
from src.cognitive.knowledge.worldview import WorldviewKnowledge
from src.cognitive.llm_interface import LLMInterface, build_llm_group
from src.cognitive.memory.store import MemoryManager
from src.world.environment import Environment
from src.world.survival_war import SurvivalWarSession

DEFAULT_AGENT_NAMES = ["Alice"]
DEFAULT_AGENT_STATE: Dict[str, Any] = {
    "has_wood": False,
    "has_fire": False,
    "has_map": False,
}
DEFAULT_ACTIONS = [
    GoapAction("gather_wood", {}, {"has_wood": True}, cost=1.0),
    GoapAction("make_fire", {"has_wood": True}, {"has_fire": True}, cost=2.0),
    GoapAction("explore_ruins", {}, {"has_map": True}, cost=1.5),
]
DEFAULT_APP_CONFIG_PATH = "config/app_config.toml"

HELP_TEXT = """命令帮助:
  /help               显示帮助
  /list               列出角色
  /use <name>         进入与该角色的对话
  /exit               退出当前对话
  /state [name]       查看角色状态
  /lore [name]        查看世界观概要
  /act <goal>         规划当前角色行动 (goal: action 名称或 key=value)
  /tick               进入下一 tick 并执行行动
  /save [label]       保存当前进度
  /quit               退出程序
"""


@dataclass
class ActionResult:
    """单次行动执行结果。"""

    action: Optional[str]
    success: bool
    reason: str
    details: Optional[Dict[str, Any]] = None


def _default_action_executor(
    action: BehaviorAction, state: Dict[str, Any], _context: Optional[Dict[str, Any]]
) -> BehaviorActionResult:
    """兼容默认动作执行函数。"""
    return execute_action(action, state)


class ChatAgent:
    """封装记忆、知识与规划的代理对象。"""

    def __init__(
        self,
        name: str,
        description: str,
        memory: MemoryManager,
        knowledge_base: KnowledgeBase,
        worldview: WorldviewKnowledge,
        planner: GOAPPlanner,
        state: Dict[str, Any],
        behavior_llm: LLMInterface,
        action_executor: Optional[
            Callable[[BehaviorAction, Dict[str, Any], Optional[Dict[str, Any]]], BehaviorActionResult]
        ] = None,
        action_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """初始化代理的状态与依赖模块。"""
        self.name = name
        self.description = description
        self.memory = memory
        self.knowledge_base = knowledge_base
        self.worldview = worldview
        self.planner = planner
        self.state = state
        self.behavior_llm = behavior_llm
        self.action_executor = action_executor or _default_action_executor
        self.action_context = action_context or {}
        self.pending_actions: List[BehaviorAction] = []
        self.last_action: Optional[BehaviorAction] = None
        self.last_action_success: Optional[bool] = None
        self.repeat_action_count = 0

    def introduce(self) -> str:
        """返回含世界观摘要的自我介绍。"""
        intro = self.worldview.intro()
        if intro:
            return f"我是 {self.name}，{self.description}。\n世界观: {intro}"
        return f"我是 {self.name}，{self.description}。"

    async def respond(self, message: str) -> str:
        """基于记忆检索生成回应。"""
        return await self._reply_to_message(
            speaker_name="player",
            speaker_type="player",
            message=message,
            log_prefix="User",
        )

    async def respond_to_npc(self, speaker_name: str, message: str) -> str:
        """响应来自其他 NPC 的对话。"""
        return await self._reply_to_message(
            speaker_name=speaker_name,
            speaker_type="npc",
            message=message,
            log_prefix=speaker_name,
        )

    async def _reply_to_message(
        self,
        speaker_name: str,
        speaker_type: str,
        message: str,
        log_prefix: str,
    ) -> str:
        await self.memory.add_sensory_input(
            f"{log_prefix}: {message}", force_consolidate=True
        )
        memories = self.memory.retrieve_and_reinforce(message, top_k=3)
        memory_texts = [fragment.content for fragment in memories]
        knowledge_hint = self._knowledge_hint(message)
        worldview_hint = self._worldview_hint(message)
        context = {
            "message": message,
            "name": self.name,
            "description": self.description,
            "state": self.state,
            "speaker": speaker_name,
            "speaker_type": speaker_type,
        }
        if knowledge_hint:
            context["knowledge"] = knowledge_hint
        if worldview_hint:
            context["worldview"] = worldview_hint
        reply = await self.behavior_llm.generate_reply(context, memory_texts)
        reply = reply.strip() or "……"
        await self.memory.add_sensory_input(f"{self.name}: {reply}")
        if not self.pending_actions:
            await self._queue_actions("respond", message, memory_texts)
        return reply

    async def act_once(self, goal_token: str) -> ActionResult:
        """为目标执行一次行动并返回结果。"""
        memories = self.memory.retrieve_and_reinforce(goal_token, top_k=3)
        memory_texts = [fragment.content for fragment in memories]
        if not self.pending_actions:
            await self._queue_actions(goal_token, goal_token, memory_texts)
        action_outcome = await self._execute_next_action()
        if action_outcome:
            action, result = action_outcome
            reason = "执行成功" if result.success else "执行失败"
            return ActionResult(action.name, result.success, reason, result.info)
        goal_state = _parse_goal_token(goal_token, self.planner.actions)
        if not goal_state:
            return ActionResult(None, False, "目标为空")
        plan = self.planner.plan(self.state, goal_state)
        if not plan:
            return ActionResult(None, False, "未找到可行计划")
        action = plan[0]
        success = self.planner.execute_plan([action], current_state=self.state)
        reason = "执行成功" if success else "前置条件不足"
        await self.memory.add_sensory_input(
            f"Action: {action.name}, success={success}, state={self.state}",
            force_consolidate=True,
        )
        return ActionResult(action.name, success, reason, {"state": dict(self.state)})

    async def plan_actions(self, goal_token: str) -> List[BehaviorAction]:
        """为目标生成动作计划并写入队列。"""
        memories = self.memory.retrieve_and_reinforce(goal_token, top_k=3)
        memory_texts = [fragment.content for fragment in memories]
        return await self._queue_actions(goal_token, goal_token, memory_texts)

    async def _queue_actions(
        self, goal: str, message: str, memory_texts: List[str]
    ) -> List[BehaviorAction]:
        """调用 LLM 生成动作计划并写入队列。"""
        context = {"goal": goal, "message": message, "state": self.state}
        plan = await self.behavior_llm.generate_actions(context, memory_texts)
        actions = parse_action_plan(plan)
        if actions:
            expanded = expand_action_chain(actions, self.state)
            if expanded:
                self.pending_actions.extend(expanded)
                return expanded
        return []

    async def _execute_next_action(
        self,
    ) -> Optional[tuple[BehaviorAction, BehaviorActionResult]]:
        """执行队列中的下一个动作。"""
        if not self.pending_actions:
            return None
        action = self.pending_actions.pop(0)
        result = self.action_executor(action, self.state, self.action_context)
        same_action = (
            self.last_action
            and self.last_action.name == action.name
            and self.last_action.params == action.params
        )
        if same_action:
            self.repeat_action_count += 1
        else:
            self.repeat_action_count = 1
        self.last_action = action
        self.last_action_success = result.success
        self.state["last_action"] = {"name": action.name, "params": dict(action.params)}
        self.state["last_action_success"] = result.success
        self.state["last_action_repeat"] = self.repeat_action_count
        await self.memory.add_sensory_input(
            f"Action: {action.name}, params={action.params}, result={result.info}",
            force_consolidate=True,
        )
        return action, result

    def _format_action_result(
        self, action: BehaviorAction, result: BehaviorActionResult
    ) -> str:
        """格式化动作执行结果文本。"""
        summary = "成功" if result.success else "失败"
        details = result.info or {}
        if details:
            return f"{summary} | {details}"
        return summary

    def _knowledge_hint(self, message: str) -> Optional[str]:
        """匹配消息与知识节点并返回可访问内容。"""
        semantic = self.knowledge_base.semantic_query(message, {"agent": self.name})
        if semantic:
            return semantic
        topic = _match_topic(message, list(self.knowledge_base.tree.keys()))
        if not topic:
            return None
        return self.knowledge_base.query(topic, {"agent": self.name})

    def _worldview_hint(self, message: str) -> Optional[str]:
        """匹配世界观条目或显式触发词。"""
        if "世界观" in message or "world" in message.lower():
            return self.worldview.intro()
        matched = self.worldview.match_entry(message)
        if matched:
            return matched.content
        return None

    async def tick(
        self,
    ) -> Optional[tuple[BehaviorAction, BehaviorActionResult]]:
        """推进一次 tick 并执行队列动作。"""
        if not self.pending_actions:
            memories = self.memory.retrieve_and_reinforce("tick", top_k=3)
            memory_texts = [fragment.content for fragment in memories]
            message = "tick"
            if self.repeat_action_count >= 2 and self.last_action:
                message = (
                    f"连续重复了动作 {self.last_action.name}，请规划不同的下一步。"
                )
            await self._queue_actions("idle", message, memory_texts)
        if not self.pending_actions:
            self.pending_actions.append(
                BehaviorAction(name="wait", params={"ticks": 1})
            )
        return await self._execute_next_action()


@dataclass(frozen=True)
class WorldContext:
    """运行时世界路径与模式配置。"""

    world_id: str
    base_dir: Optional[Path]
    world_mode: str
    world_config: Dict[str, Any]
    worldview_path: str
    persona_path: str
    knowledge_path: str
    memory_dir: Path
    knowledge_dir: Path
    save_dir: Path


@dataclass
class SessionLog:
    """运行日志收集器（输出拷贝）。"""

    started_at: float
    lines: List[str]

    def __init__(self) -> None:
        """初始化日志收集器。"""
        self.started_at = time.time()
        self.lines = []

    def _append_lines(self, message: str) -> None:
        """追加多行日志内容。"""
        text = str(message)
        parts = text.splitlines()
        if not parts:
            self.lines.append("")
            return
        self.lines.extend(parts)

    def emit(self, message: str) -> None:
        """输出并记录日志。"""
        print(message, flush=True)
        self._append_lines(message)

    def path_for(self, save_dir: Path, world_id: str) -> Path:
        """生成日志文件路径。"""
        save_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(self.started_at))
        safe_world = re.sub(r"[^A-Za-z0-9_-]+", "_", world_id or "default").strip("_")
        if not safe_world:
            safe_world = "default"
        filename = f"run-{safe_world}-{timestamp}.log"
        return save_dir / filename

    def save(self, path: Path) -> None:
        """保存日志内容到文件。"""
        with path.open("w", encoding="utf-8") as handle:
            for line in self.lines:
                handle.write(f"{line}\n")


def _load_config(path: str) -> Dict[str, Any]:
    """从 JSON/TOML 文件加载配置内容。"""
    suffix = Path(path).suffix.lower()
    if suffix == ".toml":
        return toml.load(path)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_app_config(path: str) -> Dict[str, Any]:
    """加载应用配置文件，不存在时返回空配置。"""
    try:
        return _load_config(path)
    except FileNotFoundError:
        return {}


def _resolve_relative_path(base_dir: Optional[Path], value: Optional[str]) -> Optional[str]:
    """将相对路径解析到世界目录。"""
    if not value:
        return None
    path = Path(str(value))
    if base_dir and not path.is_absolute():
        path = base_dir / path
    return path.as_posix()


def _resolve_world_path(
    base_dir: Optional[Path],
    world_value: Optional[str],
    app_value: Optional[str],
    base_fallback: str,
    global_fallback: str,
) -> str:
    """解析世界相关路径（优先 world_config，其次 app_config）。"""
    resolved = _resolve_relative_path(base_dir, world_value)
    if resolved:
        return resolved
    if app_value:
        return str(app_value)
    if base_dir:
        return (base_dir / base_fallback).as_posix()
    return global_fallback


def _load_world_config(
    base_dir: Optional[Path],
    app_config: Dict[str, Any],
    args: argparse.Namespace,
    logger: logging.Logger,
) -> Dict[str, Any]:
    """加载世界专属配置。"""
    world_config_path = args.world_config_path or app_config.get("world_config_path")
    if not world_config_path and base_dir:
        world_config_path = base_dir / "world_config.toml"
    if not world_config_path:
        return {}
    try:
        return _load_config(str(world_config_path))
    except FileNotFoundError:
        logger.warning("World config not found: %s", world_config_path)
        return {}


def _resolve_world_context(
    app_config: Dict[str, Any],
    args: argparse.Namespace,
    logger: logging.Logger,
) -> WorldContext:
    """解析世界选择与路径配置。"""
    world_id = str(args.world_id or app_config.get("world_id") or "").strip()
    worlds_dir = Path(args.worlds_dir or app_config.get("worlds_dir", "data/worlds"))
    base_dir = worlds_dir / world_id if world_id else None
    if base_dir and world_id and not base_dir.exists():
        logger.warning("World base dir not found: %s", base_dir)
    world_config = _load_world_config(base_dir, app_config, args, logger)
    world_mode = str(world_config.get("world_mode", "default")).lower()

    worldview_path = _resolve_world_path(
        base_dir,
        world_config.get("worldview_path"),
        app_config.get("worldview_path"),
        base_fallback="world_lore.toml",
        global_fallback="data/world_lore.toml",
    )
    persona_path = _resolve_world_path(
        base_dir,
        world_config.get("persona_path"),
        app_config.get("persona_path"),
        base_fallback="personas/default.toml",
        global_fallback="data/personas/default.toml",
    )
    world_knowledge = world_config.get("knowledge_path")
    if world_knowledge:
        knowledge_path = _resolve_relative_path(base_dir, str(world_knowledge)) or str(
            world_knowledge
        )
    elif app_config.get("knowledge_path"):
        knowledge_path = str(app_config.get("knowledge_path"))
    elif base_dir and (base_dir / "knowledge_graph.toml").exists():
        knowledge_path = (base_dir / "knowledge_graph.toml").as_posix()
    else:
        knowledge_path = "config/knowledge_graph.toml"
    memory_dir = base_dir / "memory" if base_dir else Path("data/memory")
    knowledge_dir = base_dir / "knowledge" if base_dir else Path("data/knowledge")
    save_dir = base_dir / "saves" if base_dir else Path("data/saves")

    return WorldContext(
        world_id=world_id,
        base_dir=base_dir,
        world_mode=world_mode,
        world_config=world_config,
        worldview_path=worldview_path,
        persona_path=persona_path,
        knowledge_path=knowledge_path,
        memory_dir=memory_dir,
        knowledge_dir=knowledge_dir,
        save_dir=save_dir,
    )


def _setup_logging() -> None:
    """配置全局日志格式。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Suppress noisy AI client info logs during runtime.
    for logger_name in ("openai", "httpx", "httpcore", "alicization.llm"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def _parse_agent_names(raw: str) -> List[str]:
    """解析并规范化 Agent 名称列表。"""
    names = [name.strip() for name in raw.split(",") if name.strip()]
    return names or list(DEFAULT_AGENT_NAMES)


def _resolve_agent_names(value: Any) -> List[str]:
    """兼容数组或字符串的 Agent 名称配置。"""
    if value is None:
        return list(DEFAULT_AGENT_NAMES)
    if isinstance(value, list):
        names = [str(item).strip() for item in value if str(item).strip()]
        return names or list(DEFAULT_AGENT_NAMES)
    return _parse_agent_names(str(value))


def _resolve_agent_names_from_world_config(
    world_config: Dict[str, Any], fallback: List[str]
) -> List[str]:
    """从世界配置的 NPC 列表提取名称。"""
    npcs = world_config.get("npcs")
    if not isinstance(npcs, list):
        return fallback
    names: List[str] = []
    for entry in npcs:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("id")
        if name:
            names.append(str(name).strip())
    return names or fallback


def _memory_path_for_agent(name: str, memory_dir: Path) -> Path:
    """为指定角色生成记忆文件基准路径。"""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not safe:
        safe = "npc"
    agent_dir = memory_dir / safe
    return agent_dir / f"{safe}.json"


def _knowledge_path_for_agent(name: str, knowledge_dir: Path) -> Path:
    """为指定角色生成知识向量库路径。"""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not safe:
        safe = "npc"
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return knowledge_dir / f"{safe}-{digest}.chroma"


def _parse_goal_token(token: str, actions: List[GoapAction]) -> Dict[str, Any]:
    """将目标文本解析为目标状态字典。"""
    if not token:
        return {}
    if "=" in token:
        key, raw_value = token.split("=", 1)
        return {key.strip(): _parse_value(raw_value.strip())}
    for action in actions:
        if action.name == token:
            return dict(action.effects)
    return {token: True}


def _parse_value(raw_value: str) -> Any:
    """将字符串解析为 bool/int/float。"""
    lowered = raw_value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def _match_topic(message: str, topics: List[str]) -> Optional[str]:
    """在消息中匹配第一个出现的主题词。"""
    if not message:
        return None
    message_lower = message.lower()
    for topic in topics:
        if topic.lower() in message_lower:
            return topic
    return None


def _format_state(state: Dict[str, Any]) -> str:
    """将状态字典格式化为可读文本。"""
    if not state:
        return "(empty)"
    return ", ".join(f"{key}={value}" for key, value in state.items())


def _format_action_signature(action: BehaviorAction) -> str:
    """格式化动作与参数为函数签名字符串。"""
    if not action.params:
        return action.name
    params = ", ".join(f"{key}={value}" for key, value in action.params.items())
    return f"{action.name}({params})"


def _format_tick_action(
    tick_count: int,
    agent: ChatAgent,
    action: BehaviorAction,
    result: BehaviorActionResult,
) -> str:
    """格式化 tick 行动输出。"""
    signature = _format_action_signature(action)
    summary = agent._format_action_result(action, result)
    return f"[Tick {tick_count}] {agent.name} 行动: {signature} | {summary}"


def _build_talk_message(topic: str) -> str:
    """为 NPC 对话构造提示文本。"""
    cleaned = str(topic or "").strip()
    if cleaned:
        return f"关于{cleaned}，你怎么看？"
    return "能聊聊吗？"


def _resolve_action_params(
    params: Dict[str, Any], state: Dict[str, Any]
) -> Dict[str, Any]:
    """解析动作参数中的占位符。"""
    placeholders = state.get("placeholders", {})
    resolved: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("$"):
            resolved[key] = placeholders.get(value[1:], value)
        else:
            resolved[key] = value
    return resolved


def _build_survival_prompt(
    agent: ChatAgent, session: SurvivalWarSession
) -> str:
    """构造生存战争模式的 LLM 行动提示。"""
    summary = agent.worldview.intro()
    state = agent.state
    position = state.get("position") or {}
    nav_target = state.get("nav_target")
    weapon = state.get("weapon")
    destiny = state.get("destiny")
    nearby_npcs = state.get("nearby_npcs")
    nearby_weapons = state.get("nearby_weapons")
    lines = [
        "你正在进行生存战争。目标：击败其他 NPC，存活到最后。",
    ]
    if summary:
        lines.append(f"世界观提示：{summary}")
    lines.append(
        "每个 tick 只执行 1 个动作。move_to 只设置目标，系统会自动寻路逐步移动。"
    )
    lines.append(
        "可用动作: move_to(x,y), find_item(item_type=\"weapon\"), "
        "observe_nearby_npcs(radius), attack(target_id), wait(ticks=1)"
    )
    lines.append(
        f"自身状态: position=({position.get('x', 0)},{position.get('y', 0)}), "
        f"destiny={destiny}, weapon={weapon}"
    )
    if nav_target:
        lines.append(f"当前导航目标: {nav_target}")
    if nearby_npcs:
        lines.append(f"已观察到的 NPC: {nearby_npcs}")
    if nearby_weapons:
        lines.append(f"已观察到的武器: {nearby_weapons}")
    lines.append("请根据当前战局输出下一步动作计划。")
    return "\n".join(lines)


def _execute_survival_action(
    action: BehaviorAction,
    state: Dict[str, Any],
    context: Optional[Dict[str, Any]],
) -> BehaviorActionResult:
    """执行生存战争动作并同步状态。"""
    if not context:
        return BehaviorActionResult(False, {"error": "missing_context"})
    session = context.get("session")
    npc_id = context.get("npc_id")
    if not isinstance(session, SurvivalWarSession) or not isinstance(npc_id, str):
        return BehaviorActionResult(False, {"error": "invalid_context"})
    params = _resolve_action_params(action.params, state)
    if action.name == "move_to":
        target_x = int(params.get("x", 0))
        target_y = int(params.get("y", 0))
        state["nav_target"] = {"x": target_x, "y": target_y}
        return BehaviorActionResult(True, {"nav_target": {"x": target_x, "y": target_y}})
    if action.name == "move":
        dx = int(params.get("dx", 0))
        dy = int(params.get("dy", 0))
        result = session.execute_action(
            npc_id, BehaviorAction(name="move", params={"dx": dx, "dy": dy})
        )
        state.update(session.snapshot_state(npc_id))
        return result
    if action.name == "observe_nearby_npcs":
        radius = int(params.get("radius", 3))
        result = session.execute_action(
            npc_id,
            BehaviorAction(name="observe_nearby_npcs", params={"radius": radius}),
        )
        if result.info and "observations" in result.info:
            state["nearby_npcs"] = result.info.get("observations", [])
        state.update(session.snapshot_state(npc_id))
        return result
    if action.name == "scan_nearby":
        tag = str(params.get("tag", ""))
        result = session.execute_action(
            npc_id, BehaviorAction(name="scan_nearby", params={"tag": tag})
        )
        if result.info and "weapons" in result.info:
            state["nearby_weapons"] = result.info.get("weapons", [])
        state.update(session.snapshot_state(npc_id))
        return result
    result = session.execute_action(npc_id, BehaviorAction(name=action.name, params=params))
    state.update(session.snapshot_state(npc_id))
    return result


def _expand_move_path(
    session: SurvivalWarSession,
    start: tuple[int, int],
    target: tuple[int, int],
    max_steps: int,
) -> List[BehaviorAction]:
    """将移动目标拆解为单步移动序列。"""
    actions: List[BehaviorAction] = []
    current = start
    for _ in range(max_steps):
        if current == target:
            break
        step = session.next_step_toward(current, target)
        dx = step[0] - current[0]
        dy = step[1] - current[1]
        if abs(dx) + abs(dy) != 1:
            break
        actions.append(BehaviorAction(name="move", params={"dx": dx, "dy": dy}))
        current = step
    return actions


def _apply_move_steps(
    start: tuple[int, int], steps: List[BehaviorAction]
) -> tuple[int, int]:
    """将 move 动作叠加到坐标。"""
    current_x, current_y = start
    for step in steps:
        current_x += int(step.params.get("dx", 0))
        current_y += int(step.params.get("dy", 0))
    return current_x, current_y


def _expand_survival_actions(
    agent: ChatAgent,
    session: SurvivalWarSession,
    actions: List[BehaviorAction],
) -> List[BehaviorAction]:
    """将高层动作拆解为 tick 级行动链。"""
    expanded: List[BehaviorAction] = []
    npc_id = agent.name
    npc_state = session.npcs.get(npc_id)
    position = agent.state.get("position") or {}
    current_pos = (int(position.get("x", 0)), int(position.get("y", 0)))
    max_steps = max(session.world_map.width, session.world_map.height) * 2
    for action in actions:
        params = _resolve_action_params(action.params, agent.state)
        if action.name == "move_to":
            target = (int(params.get("x", 0)), int(params.get("y", 0)))
            agent.state["nav_target"] = {"x": target[0], "y": target[1]}
            move_steps = _expand_move_path(session, current_pos, target, max_steps)
            if move_steps:
                expanded.extend(move_steps)
                current_pos = _apply_move_steps(current_pos, move_steps)
            continue
        if action.name == "move":
            expanded.append(BehaviorAction(name="move", params=params))
            current_pos = (
                current_pos[0] + int(params.get("dx", 0)),
                current_pos[1] + int(params.get("dy", 0)),
            )
            continue
        if action.name == "find_item":
            item_type = str(params.get("item_type", ""))
            expanded.append(BehaviorAction(name="scan_nearby", params={"tag": item_type}))
            if item_type == "weapon" and session.weapons:
                nearest = session._nearest_weapon(current_pos)
                if nearest:
                    target = nearest.position
                    agent.state["nav_target"] = {"x": target[0], "y": target[1]}
                    expanded.extend(
                        _expand_move_path(session, current_pos, target, max_steps)
                    )
                    expanded.append(
                        BehaviorAction(name="scan_nearby", params={"tag": item_type})
                    )
                    expanded.append(
                        BehaviorAction(
                            name="pickup", params={"object_id": nearest.instance_id}
                        )
                    )
            else:
                dx, dy = 1, 0
                expanded.append(BehaviorAction(name="move", params={"dx": dx, "dy": dy}))
                expanded.append(
                    BehaviorAction(name="scan_nearby", params={"tag": item_type})
                )
            continue
        if action.name == "attack":
            target_id = str(params.get("target_id", "")).strip()
            target = session.npcs.get(target_id)
            if not target:
                expanded.append(BehaviorAction(name="wait", params={"ticks": 1}))
                continue
            weapon_range = 1
            if npc_state and npc_state.weapon:
                weapon_range = max(1, npc_state.weapon.range)
            distance = abs(current_pos[0] - target.position[0]) + abs(
                current_pos[1] - target.position[1]
            )
            if distance <= weapon_range:
                expanded.append(BehaviorAction(name="attack", params={"target_id": target_id}))
                continue
            target_pos = target.position
            needed = max(0, distance - weapon_range)
            move_steps = _expand_move_path(session, current_pos, target_pos, needed)
            if move_steps:
                expanded.extend(move_steps)
                current_pos = _apply_move_steps(current_pos, move_steps)
            expanded.append(BehaviorAction(name="attack", params={"target_id": target_id}))
            continue
        if action.name in ("observe_nearby_npcs", "scan_nearby", "pickup", "wait", "talk", "gather"):
            expanded.append(BehaviorAction(name=action.name, params=params))
            continue
        expanded.append(BehaviorAction(name=action.name, params=params))
    return expanded




def _save_game_snapshot(
    agents: Dict[str, ChatAgent], save_dir: Path, label: Optional[str] = None
) -> Path:
    """保存当前进度到本地文件。"""
    save_dir.mkdir(parents=True, exist_ok=True)
    safe_label = ""
    if label:
        safe_label = re.sub(r"[^A-Za-z0-9_-]+", "_", label.strip()).strip("_")
    if safe_label:
        filename = f"{safe_label}.json"
    else:
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"save-{timestamp}.json"
    payload = {
        "format_version": 1,
        "saved_at": time.time(),
        "characters": {
            name: {
                "memory": agent.memory.snapshot(),
                "state": dict(agent.state),
            }
            for name, agent in agents.items()
        },
    }
    path = save_dir / filename
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path


async def _prompt(text: str) -> str:
    """在线程中运行阻塞式输入。"""
    # input() 是阻塞式的，因此放入线程执行。
    return await asyncio.to_thread(input, text)


def _build_agents(
    agent_names: List[str],
    persona: Dict[str, Any],
    knowledge_path: str,
    worldview: WorldviewKnowledge,
    llm_config: Dict[str, Any],
    memory_llm: LLMInterface,
    intent_llm: LLMInterface,
    embed_api: Any,
    memory_dir: Path,
    knowledge_dir: Path,
) -> Dict[str, ChatAgent]:
    """根据人设与配置构建 Agent 实例。"""
    memory_config = persona.get("memory_config", {})
    worldview_visibility = persona.get("worldview_visibility") or persona.get(
        "lore_visibility", "npc"
    )
    embedding_dim = (
        llm_config.get("providers", {})
        .get("embed_api", {})
        .get("embedding_dim", 12)
    )
    agents: Dict[str, ChatAgent] = {}
    for name in agent_names:
        knowledge_base = KnowledgeBase(
            interceptor=KnowledgeInterceptor(),
            embedder=embed_api,
            vector_store_path=_knowledge_path_for_agent(name, knowledge_dir),
        )
        knowledge_base.load_from_json(knowledge_path)
        for node_id in persona.get("initial_knowledge", []):
            knowledge_base.learn(node_id)

        memory_path = _memory_path_for_agent(name, memory_dir)
        memory = MemoryManager(
            llm_interface=memory_llm,
            embedding_api=embed_api,
            memory_path=memory_path,
            decay_rate=memory_config.get("decay_rate", 0.1),
            forget_threshold=memory_config.get("forget_threshold", 15.0),
            promotion_threshold=memory_config.get("promotion_threshold", 4.0),
            max_strength=memory_config.get("max_strength", 100.0),
            embedding_dim=embedding_dim,
        )
        memory.set_core_persona("name", name)
        memory.set_core_persona("description", persona.get("description", ""))
        memory.set_core_persona(
            "persona_profile", json.dumps(persona, ensure_ascii=False)
        )
        memory.reset_session()

        planner = GOAPPlanner(actions=list(DEFAULT_ACTIONS))
        state = dict(DEFAULT_AGENT_STATE)

        agents[name] = ChatAgent(
            name=name,
            description=persona.get("description", ""),
            memory=memory,
            knowledge_base=knowledge_base,
            worldview=worldview.with_default_visibility(str(worldview_visibility)),
            planner=planner,
            state=state,
            behavior_llm=intent_llm,
        )
    return agents


async def _run_cli(
    agents: Dict[str, ChatAgent],
    save_dir: Path,
    world_id: str,
    session_log: SessionLog,
    auto_tick: bool = False,
    tick_interval: float = 1.0,
    max_ticks: int = 0,
) -> None:
    """运行多 Agent 交互式 CLI。"""
    emit = session_log.emit
    names = list(agents.keys())
    if not names:
        emit("未配置角色。")
        return
    active_name: Optional[str] = None
    tick_count = 0
    day_tick_count = 0
    day_count = 0
    ticks_per_day = Environment.TICKS_PER_DAY
    tick_lock = asyncio.Lock()
    stop_event = asyncio.Event()

    async def _end_day(agent_list: List[ChatAgent]) -> None:
        nonlocal day_count, day_tick_count
        day_count += 1
        day_tick_count = 0
        for agent in agent_list:
            await agent.memory.consolidate()
            agent.memory.apply_decay()
        emit(f"第 {day_count} 天结束，记忆已更新。")

    async def advance_tick() -> None:
        nonlocal tick_count, day_tick_count
        async with tick_lock:
            if max_ticks > 0 and tick_count >= max_ticks:
                if auto_tick:
                    emit(f"已达到最大 tick: {max_ticks}，自动停止。")
                    stop_event.set()
                else:
                    emit(f"已达到最大 tick: {max_ticks}。")
                return
            tick_count += 1
            agent_list = [agents[name] for name in names]
            for idx, agent in enumerate(agent_list):
                if len(agent_list) <= 1:
                    continue
                target_name = agent_list[(idx + 1) % len(agent_list)].name
                placeholders = agent.state.setdefault("placeholders", {})
                placeholders["npc_id"] = target_name
                placeholders["target_id"] = target_name
            outcomes = await asyncio.gather(
                *(agent.tick() for agent in agent_list), return_exceptions=True
            )
            for agent, outcome in zip(agent_list, outcomes):
                if isinstance(outcome, Exception):
                    logging.getLogger("alicization").exception(
                        "Tick failed for %s", agent.name, exc_info=outcome
                    )
                    continue
                if not outcome:
                    continue
                action, result = outcome
                emit(_format_tick_action(tick_count, agent, action, result))
                if action.name == "talk" and result.success:
                    info = result.info or {}
                    target = str(info.get("target", "")).strip()
                    if target and target in agents and target != agent.name:
                        topic = str(info.get("topic", "")).strip()
                        message = _build_talk_message(topic)
                        reply = await agents[target].respond_to_npc(
                            agent.name, message
                        )
                        emit(f"{target}: {reply}")
            day_tick_count += 1
            if ticks_per_day > 0 and day_tick_count >= ticks_per_day:
                await _end_day(agent_list)

    async def auto_tick_loop() -> None:
        while not stop_event.is_set():
            await advance_tick()
            if tick_interval > 0:
                await asyncio.sleep(tick_interval)

    auto_task = None
    if auto_tick:
        auto_task = asyncio.create_task(auto_tick_loop())

    emit("命令行已启动。输入 /help 查看命令。")

    async def _cleanup() -> None:
        stop_event.set()
        if auto_task:
            auto_task.cancel()
            with suppress(asyncio.CancelledError):
                await auto_task

    if auto_tick:
        emit("自动 tick 模式已启动，不接收命令行指令。按 Ctrl+C 退出。")
        try:
            await stop_event.wait()
        finally:
            await _cleanup()
        log_path = session_log.path_for(save_dir, world_id)
        emit(f"运行日志已保存: {log_path.as_posix()}")
        session_log.save(log_path)
        return

    try:
        while True:
            prompt_label = f"[{active_name}]> " if active_name else "> "
            try:
                raw = (await _prompt(prompt_label)).strip()
            except EOFError:
                    emit("检测到输入结束，退出交互模式。")
                    break
            if not raw:
                continue
            if raw.startswith("/"):
                parts = raw.split(maxsplit=1)
                command = parts[0]
                arg = parts[1].strip() if len(parts) > 1 else ""
                if command == "/quit":
                    emit("已退出。")
                    break
                if command == "/exit":
                    if active_name is None:
                        emit("未在对话中。")
                    else:
                        active_name = None
                    continue
                if command == "/help":
                    emit(HELP_TEXT)
                    continue
                if command == "/list":
                    emit(", ".join(names))
                    continue
                if command == "/use":
                    if not arg:
                        emit("用法: /use <name>")
                        continue
                    if arg in agents:
                        active_name = arg
                    else:
                        emit(f"未知角色: {arg}")
                    continue
                if command == "/state":
                    target = arg or active_name
                    if not target:
                        emit("未选择角色。")
                        continue
                    agent = agents.get(target)
                    if not agent:
                        emit(f"未知角色: {target}")
                        continue
                    prefix = "状态" if target == active_name else f"{agent.name} 状态"
                    emit(f"{prefix}: {_format_state(agent.state)}")
                    continue
                if command == "/lore":
                    target = arg or active_name
                    if not target:
                        emit("未选择角色。")
                        continue
                    agent = agents.get(target)
                    if not agent:
                        emit(f"未知角色: {target}")
                        continue
                    intro = agent.worldview.intro()
                    if intro:
                        prefix = "世界观" if target == active_name else f"{agent.name} 世界观"
                        emit(f"{prefix}: {intro}")
                    else:
                        emit("世界观为空。")
                    continue
                if command == "/act":
                    if not active_name:
                        emit("未选择角色。")
                        continue
                    if not arg:
                        emit("用法: /act <goal>")
                        continue
                    agent = agents[active_name]
                    actions = await agent.plan_actions(arg)
                    if actions:
                        emit(f"行动计划已加入队列（{len(actions)}）")
                    else:
                        emit("未生成可执行行动。")
                    continue
                if command == "/tick":
                    await advance_tick()
                    continue
                if command == "/save":
                    path = _save_game_snapshot(agents, save_dir, arg or None)
                    emit(f"已存档: {path.as_posix()}")
                    continue
                emit("未知命令。")
                continue

            if active_name is None:
                emit("请先 /use <name>。")
                continue
            agent = agents[active_name]
            response = await agent.respond(raw)
            emit(response)
    finally:
        await _cleanup()
        log_path = session_log.path_for(save_dir, world_id)
        emit(f"运行日志已保存: {log_path.as_posix()}")
        session_log.save(log_path)


async def _run_post_game_dialogue(
    agents: Dict[str, ChatAgent],
    session: SurvivalWarSession,
    emit: Callable[[str], None],
) -> None:
    """赛后对话环节。"""
    emit("比赛结束，进入赛后对话。")
    summary = session.summary()
    for agent in agents.values():
        await agent.memory.add_sensory_input(
            f"战斗总结: {summary}", force_consolidate=True
        )
    names = [npc_id for npc_id in session.npc_ids() if npc_id in agents]
    if len(names) < 2:
        emit("参赛者不足，跳过对话。")
        return
    topics = ["策略选择", "关键战斗", "复盘改进"]
    for topic in topics:
        for idx, speaker in enumerate(names):
            target = names[(idx + 1) % len(names)]
            message = f"赛后复盘：{topic}，你怎么看？"
            emit(f"{speaker} -> {target}: {message}")
            reply = await agents[target].respond_to_npc(speaker, message)
            emit(f"{target}: {reply}")


async def _run_survival_war_cli(
    agents: Dict[str, ChatAgent],
    session: SurvivalWarSession,
    save_dir: Path,
    world_id: str,
    session_log: SessionLog,
    auto_tick: bool = False,
    tick_interval: float = 1.0,
    max_ticks: int = 0,
) -> None:
    """生存战争模式 CLI。"""
    emit = session_log.emit
    names = [npc_id for npc_id in session.npc_ids() if npc_id in agents]
    if not names:
        emit("未配置生存战争 NPC。")
        return
    active_name: Optional[str] = None
    tick_count = 0
    tick_lock = asyncio.Lock()
    stop_event = asyncio.Event()

    def _sync_agent_states() -> None:
        for npc_id in names:
            snapshot = session.snapshot_state(npc_id)
            nav_target = agents[npc_id].state.get("nav_target")
            agents[npc_id].state.update(snapshot)
            if nav_target and snapshot.get("position") != nav_target:
                agents[npc_id].state["nav_target"] = nav_target
            else:
                agents[npc_id].state.pop("nav_target", None)

    async def advance_tick() -> None:
        nonlocal tick_count
        async with tick_lock:
            if session.game_over:
                stop_event.set()
                return
            if max_ticks > 0 and tick_count >= max_ticks:
                if auto_tick:
                    emit(f"已达到最大 tick: {max_ticks}，自动停止。")
                    stop_event.set()
                else:
                    emit(f"已达到最大 tick: {max_ticks}。")
                return
            tick_count += 1
            session.begin_tick()
            for npc_id in names:
                npc_state = session.npcs.get(npc_id)
                if not npc_state or not npc_state.alive:
                    continue
                agent = agents[npc_id]
                placeholders = agent.state.setdefault("placeholders", {})
                target_id = session.nearest_enemy_id(npc_id)
                if target_id:
                    placeholders["target_id"] = target_id
                    placeholders["npc_id"] = target_id
                if not agent.pending_actions:
                    prompt = _build_survival_prompt(agent, session)
                    memories = agent.memory.retrieve_and_reinforce(
                        "survival_war_tick", top_k=3
                    )
                    memory_texts = [fragment.content for fragment in memories]
                    context = {
                        "goal": "survival_war",
                        "message": prompt,
                        "state": agent.state,
                    }
                    plan = await agent.behavior_llm.generate_actions(
                        context, memory_texts
                    )
                    raw_actions = parse_action_plan(plan)
                    expanded = _expand_survival_actions(agent, session, raw_actions)
                    if not expanded:
                        expanded = [BehaviorAction(name="wait", params={"ticks": 1})]
                    agent.pending_actions = expanded
                action, result = await agent._execute_next_action()
                if not result.success:
                    agent.pending_actions.clear()
                signature = _format_action_signature(action)
                summary = agent._format_action_result(action, result)
                emit(f"[Tick {tick_count}] {agent.name} 行动: {signature} | {summary}")
            session.end_tick()
            _sync_agent_states()
            if session.game_over:
                await _run_post_game_dialogue(agents, session, emit)
                stop_event.set()

    async def auto_tick_loop() -> None:
        while not stop_event.is_set():
            await advance_tick()
            if tick_interval > 0:
                await asyncio.sleep(tick_interval)

    auto_task = None
    if auto_tick:
        auto_task = asyncio.create_task(auto_tick_loop())

    emit("生存战争模式已启动。输入 /help 查看命令。")
    for npc_id in names:
        agent = agents[npc_id]
        agent.action_executor = _execute_survival_action
        agent.action_context = {"session": session, "npc_id": npc_id}
    _sync_agent_states()

    async def _cleanup() -> None:
        stop_event.set()
        if auto_task:
            auto_task.cancel()
            with suppress(asyncio.CancelledError):
                await auto_task

    if auto_tick:
        emit("自动 tick 模式已启动，不接收命令行指令。按 Ctrl+C 退出。")
        try:
            await stop_event.wait()
        finally:
            await _cleanup()
        log_path = session_log.path_for(save_dir, world_id)
        emit(f"运行日志已保存: {log_path.as_posix()}")
        session_log.save(log_path)
        return

    try:
        while True:
            prompt_label = f"[{active_name}]> " if active_name else "> "
            try:
                raw = (await _prompt(prompt_label)).strip()
            except EOFError:
                    emit("检测到输入结束，退出交互模式。")
                    break
            if not raw:
                continue
            if raw.startswith("/"):
                parts = raw.split(maxsplit=1)
                command = parts[0]
                arg = parts[1].strip() if len(parts) > 1 else ""
                if command == "/quit":
                    emit("已退出。")
                    break
                if command == "/exit":
                    if active_name is None:
                        emit("未在对话中。")
                    else:
                        active_name = None
                    continue
                if command == "/help":
                    emit(HELP_TEXT)
                    continue
                if command == "/list":
                    emit(", ".join(names))
                    continue
                if command == "/use":
                    if not arg:
                        emit("用法: /use <name>")
                        continue
                    if arg in agents:
                        active_name = arg
                    else:
                        emit(f"未知角色: {arg}")
                    continue
                if command == "/state":
                    target = arg or active_name
                    if not target:
                        emit("未选择角色。")
                        continue
                    agent = agents.get(target)
                    if not agent:
                        emit(f"未知角色: {target}")
                        continue
                    prefix = "状态" if target == active_name else f"{agent.name} 状态"
                    emit(f"{prefix}: {_format_state(agent.state)}")
                    continue
                if command == "/lore":
                    target = arg or active_name
                    if not target:
                        emit("未选择角色。")
                        continue
                    agent = agents.get(target)
                    if not agent:
                        emit(f"未知角色: {target}")
                        continue
                    intro = agent.worldview.intro()
                    if intro:
                        prefix = "世界观" if target == active_name else f"{agent.name} 世界观"
                        emit(f"{prefix}: {intro}")
                    else:
                        emit("世界观为空。")
                    continue
                if command == "/act":
                    emit("生存战争模式不支持 /act。")
                    continue
                if command == "/tick":
                    await advance_tick()
                    if session.game_over:
                        break
                    continue
                if command == "/save":
                    path = _save_game_snapshot(agents, save_dir, arg or None)
                    emit(f"已存档: {path.as_posix()}")
                    continue
                emit("未知命令。")
                continue

            if active_name is None:
                emit("请先 /use <name>。")
                continue
            agent = agents[active_name]
            response = await agent.respond(raw)
            emit(response)
    finally:
        await _cleanup()
        log_path = session_log.path_for(save_dir, world_id)
        emit(f"运行日志已保存: {log_path.as_posix()}")
        session_log.save(log_path)


async def _run_demo(agents: Dict[str, ChatAgent], run_seconds: int) -> None:
    """运行指定时长的脚本化演示。"""
    logger = logging.getLogger("alicization")
    prompts = ["介绍一下世界观", "我们下一步该做什么？", "执行 make_fire"]
    start = time.monotonic()
    step = 0
    while time.monotonic() - start < run_seconds:
        prompt = prompts[step % len(prompts)]
        for agent in agents.values():
            response = await agent.respond(prompt)
            logger.info("[Demo] %s: %s", agent.name, response.replace("\n", " | "))
        step += 1
        await asyncio.sleep(1.0)


async def _run_memory_test(agents: Dict[str, ChatAgent]) -> None:
    """运行脚本化输入并输出记忆检索结果。"""
    dialogue_batches = [
        [
            ("User", "我想找木头和火。"),
            ("Agent", "我会去森林收集木头，并尝试生火。"),
        ],
        [
            ("User", "我们去探索遗迹吧。"),
            ("Agent", "好的，我会记录遗迹的路线与风险。"),
        ],
        [
            ("User", "记住我喜欢剑技训练。"),
            ("Agent", "已记录你偏好剑技训练。"),
        ],
    ]
    queries = ["火", "遗迹", "剑技"]

    for agent in agents.values():
        print(f"\n[{agent.name}] Memory Test")
        if agent.memory.promotion_threshold > 1.0:
            agent.memory.promotion_threshold = 1.0
        for batch in dialogue_batches:
            for speaker, text in batch:
                await agent.memory.add_sensory_input(f"{speaker}: {text}")
            await agent.memory.consolidate()

        fragments = agent.memory.episodic_store.list_all()
        if not fragments:
            print("No episodic memories stored.")
        else:
            print("Stored episodic memories:")
            for fragment in fragments:
                print(
                    f"- {fragment.content} (importance={fragment.importance_score:.1f})"
                )

        for query in queries:
            hits = agent.memory.retrieve_and_reinforce(query, top_k=3)
            if not hits:
                print(f'Query "{query}": no matches')
                continue
            joined = " / ".join(fragment.content for fragment in hits)
            print(f'Query "{query}": {joined}')


def _load_worldview(path: str, logger: logging.Logger) -> WorldviewKnowledge:
    """加载世界观数据，缺失时记录警告。"""
    worldview = WorldviewKnowledge()
    try:
        worldview.load_from_json(path)
    except FileNotFoundError:
        logger.warning("Worldview file not found: %s", path)
    return worldview


async def main_async(args: argparse.Namespace) -> None:
    """CLI/脚本运行的异步入口。"""
    _setup_logging()
    logger = logging.getLogger("alicization")

    app_config = _load_app_config(args.app_config_path)
    llm_config_path = app_config.get("llm_config_path", "data/llm_config.json")
    world_context = _resolve_world_context(app_config, args, logger)
    knowledge_path = world_context.knowledge_path
    worldview_path = world_context.worldview_path
    persona_path = world_context.persona_path

    persona = _load_config(persona_path)
    llm_config = _load_config(llm_config_path)
    llm_group = build_llm_group(llm_config)

    memory_llm = llm_group.for_module("memory")
    intent_llm = llm_group.for_module("behavior")
    worldview = _load_worldview(worldview_path, logger)

    agent_names = _resolve_agent_names(app_config.get("agents"))
    agent_names = _resolve_agent_names_from_world_config(
        world_context.world_config, agent_names
    )
    agents = _build_agents(
        agent_names=agent_names,
        persona=persona,
        knowledge_path=knowledge_path,
        worldview=worldview,
        llm_config=llm_config,
        memory_llm=memory_llm,
        intent_llm=intent_llm,
        embed_api=llm_group.embed_api,
        memory_dir=world_context.memory_dir,
        knowledge_dir=world_context.knowledge_dir,
    )

    memory_test = bool(app_config.get("memory_test", False))
    if args.memory_test:
        memory_test = True
    auto_tick = bool(app_config.get("auto_tick", False))
    if args.auto_tick:
        auto_tick = True
    tick_interval = app_config.get("tick_interval", 1.0)
    if args.tick_interval is not None:
        tick_interval = args.tick_interval
    max_ticks = app_config.get("max_ticks", 0)
    if args.max_ticks is not None:
        max_ticks = args.max_ticks
    try:
        max_ticks = int(max_ticks)
    except (TypeError, ValueError):
        max_ticks = 0
    try:
        tick_interval = float(tick_interval)
    except (TypeError, ValueError):
        tick_interval = 1.0
    if tick_interval <= 0:
        tick_interval = 1.0
    run_seconds = app_config.get("run_seconds", 0)
    if args.run_seconds is not None:
        run_seconds = args.run_seconds
    if memory_test:
        await _run_memory_test(agents)
    elif run_seconds:
        await _run_demo(agents, int(run_seconds))
    else:
        if world_context.world_mode == "survival_war":
            session = SurvivalWarSession.from_config(
                world_context.world_config,
                base_dir=world_context.base_dir,
                logger=logger,
            )
            await _run_survival_war_cli(
                agents,
                session,
                save_dir=world_context.save_dir,
                world_id=world_context.world_id,
                session_log=SessionLog(),
                auto_tick=auto_tick,
                tick_interval=tick_interval,
                max_ticks=max_ticks,
            )
        else:
            await _run_cli(
                agents,
                save_dir=world_context.save_dir,
                world_id=world_context.world_id,
                session_log=SessionLog(),
                auto_tick=auto_tick,
                tick_interval=tick_interval,
                max_ticks=max_ticks,
            )


def parse_args() -> argparse.Namespace:
    """定义并解析 CLI 参数。"""
    parser = argparse.ArgumentParser(description="Alicization World MVP")
    parser.add_argument(
        "--app-config-path",
        default=DEFAULT_APP_CONFIG_PATH,
        help="Path to app config JSON",
    )
    parser.add_argument(
        "--run-seconds",
        type=int,
        default=None,
        help="Override demo run seconds",
    )
    parser.add_argument(
        "--memory-test",
        action="store_true",
        help="Override to run memory test",
    )
    parser.add_argument(
        "--auto-tick",
        action="store_true",
        help="Enable automatic tick loop in CLI mode",
    )
    parser.add_argument(
        "--tick-interval",
        type=float,
        default=None,
        help="Override auto tick interval in seconds",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Stop the auto tick loop after the given number of ticks",
    )
    parser.add_argument(
        "--webui",
        action="store_true",
        help="Start the local Web UI server instead of running CLI",
    )
    parser.add_argument(
        "--webui-host",
        default=None,
        help="Override Web UI host address",
    )
    parser.add_argument(
        "--webui-port",
        type=int,
        default=None,
        help="Override Web UI port",
    )
    parser.add_argument(
        "--world-id",
        default=None,
        help="World ID under the worlds directory",
    )
    parser.add_argument(
        "--worlds-dir",
        default=None,
        help="Base directory for world definitions",
    )
    parser.add_argument(
        "--world-config-path",
        default=None,
        help="Override world config path",
    )
    return parser.parse_args()


def main() -> None:
    """程序入口，支持 Web UI 模式。"""
    args = parse_args()
    app_config = _load_app_config(args.app_config_path)
    mode = str(app_config.get("mode", "cli")).lower()
    if args.webui:
        mode = "webui"
    if mode == "webui":
        from web.server import run_server

        webui_config = app_config.get("webui", {})
        host = args.webui_host or webui_config.get("host", "127.0.0.1")
        port = args.webui_port or webui_config.get("port", 8000)
        run_server(host=host, port=int(port))
        return
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logging.getLogger("alicization").info("Shutdown requested")


if __name__ == "__main__":
    main()
