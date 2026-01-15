"""文件职责：项目启动入口，提供多 Agent CLI 交互与行为演示。
简明实现逻辑：解析参数→加载配置→初始化认知/行为模块→进入 CLI 或 demo。
输入输出：输入为 CLI 参数/用户输入；输出为对话与行动结果。"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.behavior.goap import Action, GOAPPlanner
from src.cognitive.knowledge.interceptor import KnowledgeInterceptor
from src.cognitive.knowledge.tree import KnowledgeBase
from src.cognitive.knowledge.worldview import WorldviewKnowledge
from src.cognitive.llm_interface import LLMInterface, build_llm_group
from src.cognitive.memory.store import MemoryManager

DEFAULT_AGENT_NAMES = ["Alice", "Boris", "Celia"]
DEFAULT_AGENT_STATE: Dict[str, Any] = {
    "has_wood": False,
    "has_fire": False,
    "has_map": False,
}
DEFAULT_ACTIONS = [
    Action("gather_wood", {}, {"has_wood": True}, cost=1.0),
    Action("make_fire", {"has_wood": True}, {"has_fire": True}, cost=2.0),
    Action("explore_ruins", {}, {"has_map": True}, cost=1.5),
]
MEMORY_DIR = Path("data/memory")
KNOWLEDGE_DIR = Path("data/knowledge")
SAVE_DIR = Path("data/saves")
DEFAULT_APP_CONFIG_PATH = "config/app_config.toml"

HELP_TEXT = """命令帮助:
  /help               显示帮助
  /list               列出角色
  /use <name>         进入与该角色的对话
  /exit               退出当前对话
  /state [name]       查看角色状态
  /lore [name]        查看世界观概要
  /act <goal>         触发当前角色行动 (goal: action 名称或 key=value)
  /save [label]       保存当前进度
  /quit               退出程序
"""


@dataclass
class ActionResult:
    """单次行动执行结果。"""

    action: Optional[Action]
    success: bool
    reason: str


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
        intent_llm: LLMInterface,
    ) -> None:
        """初始化代理的状态与依赖模块。"""
        self.name = name
        self.description = description
        self.memory = memory
        self.knowledge_base = knowledge_base
        self.worldview = worldview
        self.planner = planner
        self.state = state
        self.intent_llm = intent_llm

    def introduce(self) -> str:
        """返回含世界观摘要的自我介绍。"""
        intro = self.worldview.intro()
        if intro:
            return f"我是 {self.name}，{self.description}。\n世界观: {intro}"
        return f"我是 {self.name}，{self.description}。"

    async def respond(self, message: str) -> str:
        """基于记忆检索与意图生成回应。"""
        await self.memory.add_sensory_input(
            f"User: {message}", force_consolidate=True
        )
        memories = self.memory.retrieve_and_reinforce(message, top_k=3)
        memory_texts = [fragment.content for fragment in memories]
        intent = await self.intent_llm.generate_intent(
            {"goal": "respond"}, memory_texts
        )
        knowledge_hint = self._knowledge_hint(message)
        worldview_hint = self._worldview_hint(message)

        lines = [f"身份: {self.description}"]
        if worldview_hint:
            lines.append(f"世界观: {worldview_hint}")
        if knowledge_hint:
            lines.append(f"知识: {knowledge_hint}")
        lines.append(f"意图: {intent}")
        if memory_texts:
            lines.append(f"记忆: {' / '.join(memory_texts)}")
        return "\n".join(lines)

    async def act_once(self, goal_token: str) -> ActionResult:
        """为目标执行一次行动并返回结果。"""
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
        return ActionResult(action, success, reason)

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


def _load_config(path: str) -> Dict[str, Any]:
    """从 JSON/TOML 文件加载配置内容。"""
    suffix = Path(path).suffix.lower()
    if suffix == ".toml":
        with open(path, "rb") as handle:
            return tomllib.load(handle)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_app_config(path: str) -> Dict[str, Any]:
    """加载应用配置文件，不存在时返回空配置。"""
    try:
        return _load_config(path)
    except FileNotFoundError:
        return {}


def _setup_logging() -> None:
    """配置全局日志格式。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


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


def _memory_path_for_agent(name: str) -> Path:
    """为指定角色生成记忆文件基准路径。"""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not safe:
        safe = "npc"
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return MEMORY_DIR / f"{safe}-{digest}.json"


def _knowledge_path_for_agent(name: str) -> Path:
    """为指定角色生成知识向量库路径。"""
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip()).strip("_")
    if not safe:
        safe = "npc"
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()[:8]
    return KNOWLEDGE_DIR / f"{safe}-{digest}.chroma"


def _parse_goal_token(token: str, actions: List[Action]) -> Dict[str, Any]:
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


def _save_game_snapshot(
    agents: Dict[str, ChatAgent], label: Optional[str] = None
) -> Path:
    """保存当前进度到本地文件。"""
    SAVE_DIR.mkdir(parents=True, exist_ok=True)
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
    path = SAVE_DIR / filename
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
            vector_store_path=_knowledge_path_for_agent(name),
        )
        knowledge_base.load_from_json(knowledge_path)
        for node_id in persona.get("initial_knowledge", []):
            knowledge_base.learn(node_id)

        memory_path = _memory_path_for_agent(name)
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
            intent_llm=intent_llm,
        )
    return agents


async def _run_cli(agents: Dict[str, ChatAgent]) -> None:
    """运行多 Agent 交互式 CLI。"""
    names = list(agents.keys())
    if not names:
        print("未配置角色。")
        return
    active_name: Optional[str] = None

    print("命令行已启动。输入 /help 查看命令。")

    while True:
        prompt_label = f"[{active_name}]> " if active_name else "> "
        raw = (await _prompt(prompt_label)).strip()
        if not raw:
            continue
        if raw.startswith("/"):
            parts = raw.split(maxsplit=1)
            command = parts[0]
            arg = parts[1].strip() if len(parts) > 1 else ""
            if command == "/quit":
                print("已退出。")
                break
            if command == "/exit":
                if active_name is None:
                    print("未在对话中。")
                else:
                    active_name = None
                continue
            if command == "/help":
                print(HELP_TEXT)
                continue
            if command == "/list":
                print(", ".join(names))
                continue
            if command == "/use":
                if not arg:
                    print("用法: /use <name>")
                    continue
                if arg in agents:
                    active_name = arg
                else:
                    print(f"未知角色: {arg}")
                continue
            if command == "/state":
                target = arg or active_name
                if not target:
                    print("未选择角色。")
                    continue
                agent = agents.get(target)
                if not agent:
                    print(f"未知角色: {target}")
                    continue
                prefix = "状态" if target == active_name else f"{agent.name} 状态"
                print(f"{prefix}: {_format_state(agent.state)}")
                continue
            if command == "/lore":
                target = arg or active_name
                if not target:
                    print("未选择角色。")
                    continue
                agent = agents.get(target)
                if not agent:
                    print(f"未知角色: {target}")
                    continue
                intro = agent.worldview.intro()
                if intro:
                    prefix = "世界观" if target == active_name else f"{agent.name} 世界观"
                    print(f"{prefix}: {intro}")
                else:
                    print("世界观为空。")
                continue
            if command == "/act":
                if not active_name:
                    print("未选择角色。")
                    continue
                if not arg:
                    print("用法: /act <goal>")
                    continue
                agent = agents[active_name]
                result = await agent.act_once(arg)
                if result.action:
                    line = f"行动: {result.action.name} | {result.reason}"
                else:
                    line = f"行动失败: {result.reason}"
                line += f" | 状态: {_format_state(agent.state)}"
                print(line)
                continue
            if command == "/save":
                path = _save_game_snapshot(agents, arg or None)
                print(f"已存档: {path.as_posix()}")
                continue
            print("未知命令。")
            continue

        if active_name is None:
            print("请先 /use <name>。")
            continue
        agent = agents[active_name]
        response = await agent.respond(raw)
        print(response)


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
    knowledge_path = app_config.get("knowledge_path", "data/knowledge_graph.json")
    worldview_path = app_config.get("worldview_path", "data/world_lore.json")
    llm_config_path = app_config.get("llm_config_path", "data/llm_config.json")
    persona_path = app_config.get("persona_path", "data/personas/default.json")

    persona = _load_config(persona_path)
    llm_config = _load_config(llm_config_path)
    llm_group = build_llm_group(llm_config)

    memory_llm = llm_group.for_module("memory")
    intent_llm = llm_group.for_module("behavior")
    worldview = _load_worldview(worldview_path, logger)

    agent_names = _resolve_agent_names(app_config.get("agents"))
    agents = _build_agents(
        agent_names=agent_names,
        persona=persona,
        knowledge_path=knowledge_path,
        worldview=worldview,
        llm_config=llm_config,
        memory_llm=memory_llm,
        intent_llm=intent_llm,
        embed_api=llm_group.embed_api,
    )

    memory_test = bool(app_config.get("memory_test", False))
    if args.memory_test:
        memory_test = True
    run_seconds = app_config.get("run_seconds", 0)
    if args.run_seconds is not None:
        run_seconds = args.run_seconds
    if memory_test:
        await _run_memory_test(agents)
    elif run_seconds:
        await _run_demo(agents, int(run_seconds))
    else:
        await _run_cli(agents)


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
    return parser.parse_args()


def main() -> None:
    """程序入口，支持 Web UI 模式。"""
    args = parse_args()
    if args.webui:
        from web.server import run_server

        app_config = _load_app_config(args.app_config_path)
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
