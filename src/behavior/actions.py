"""文件职责：行为节点与具体动作定义。
简明实现逻辑：以 Action 数据结构描述 tick 级动作，解析与执行。
输入输出：输入为动作参数；输出为可执行的 Action 实例或执行结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class Action:
    """tick 级动作定义。"""

    name: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionResult:
    """动作执行结果。"""

    success: bool
    info: Optional[Dict[str, Any]] = None


ALLOWED_ACTIONS: Dict[str, Tuple[str, ...]] = {
    "move_to": ("x", "y"),
    "scan_nearby": ("tag",),
    "find_item": ("item_type",),
    "pickup": ("object_id",),
    "attack": ("target_id",),
    "talk": ("target_id", "topic"),
    "gather": ("resource_id",),
    "wait": ("ticks",),
}


def move_to(x: int, y: int) -> Action:
    """移动到指定坐标。"""
    return Action(name="move_to", params={"x": x, "y": y})


def scan_nearby(tag: str) -> Action:
    """扫描附近对象标签。"""
    return Action(name="scan_nearby", params={"tag": tag})


def find_item(item_type: str) -> Action:
    """寻找指定类型物品。"""
    return Action(name="find_item", params={"item_type": item_type})


def pickup(object_id: str) -> Action:
    """拾取指定对象。"""
    return Action(name="pickup", params={"object_id": object_id})


def attack(target_id: str) -> Action:
    """攻击指定目标。"""
    return Action(name="attack", params={"target_id": target_id})


def talk(target_id: str, topic: str) -> Action:
    """与目标交谈并传递主题。"""
    return Action(name="talk", params={"target_id": target_id, "topic": topic})


def gather(resource_id: str) -> Action:
    """采集资源。"""
    return Action(name="gather", params={"resource_id": resource_id})


def wait(ticks: int) -> Action:
    """等待指定 tick。"""
    return Action(name="wait", params={"ticks": ticks})


def parse_action_signature(signature: str) -> Optional[Action]:
    """解析动作函数签名字符串。"""
    if not signature:
        return None
    match = re.fullmatch(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?:\((.*)\))?\s*", signature)
    if not match:
        return None
    name = match.group(1)
    params_raw = match.group(2)
    if name not in ALLOWED_ACTIONS:
        return None
    params: Dict[str, Any] = {}
    if params_raw:
        for segment in _split_params(params_raw):
            if not segment:
                continue
            if "=" not in segment:
                return None
            key, raw_value = segment.split("=", 1)
            key = key.strip()
            if key not in ALLOWED_ACTIONS[name]:
                return None
            params[key] = _parse_value(raw_value.strip())
    return Action(name=name, params=params)


def parse_action_plan(plan: Dict[str, Any]) -> List[Action]:
    """解析 LLM 返回的动作计划。"""
    if not isinstance(plan, dict):
        return []
    raw_actions = plan.get("actions", [])
    if not isinstance(raw_actions, Iterable):
        return []
    actions: List[Action] = []
    for entry in raw_actions:
        if not isinstance(entry, str):
            continue
        action = parse_action_signature(entry)
        if action:
            actions.append(action)
    return actions


def execute_action(action: Action, state: Dict[str, Any]) -> ActionResult:
    """执行动作并更新状态。"""
    params = _resolve_placeholders(action.params, state)
    if action.name == "move_to":
        position = {"x": int(params.get("x", 0)), "y": int(params.get("y", 0))}
        state["position"] = position
        return ActionResult(True, {"position": position})
    if action.name == "scan_nearby":
        tag = str(params.get("tag", "unknown"))
        info = f"扫描到附近的 {tag}"
        state["last_scan"] = tag
        return ActionResult(True, {"observation": info})
    if action.name == "find_item":
        item_type = str(params.get("item_type", "item"))
        found_id = f"{item_type}_001"
        _set_placeholder(state, f"{item_type}_id", found_id)
        state["last_found"] = found_id
        return ActionResult(True, {"found_object_id": found_id})
    if action.name == "pickup":
        object_id = str(params.get("object_id", "unknown"))
        inventory = state.setdefault("inventory", [])
        inventory.append(object_id)
        state["last_pickup"] = object_id
        return ActionResult(True, {"inventory": list(inventory)})
    if action.name == "attack":
        target_id = str(params.get("target_id", "unknown"))
        state["last_target"] = target_id
        return ActionResult(True, {"target": target_id})
    if action.name == "talk":
        target_id = str(params.get("target_id", "unknown"))
        topic = str(params.get("topic", ""))
        state["last_talk"] = {"target_id": target_id, "topic": topic}
        return ActionResult(True, {"target": target_id, "topic": topic})
    if action.name == "gather":
        resource_id = str(params.get("resource_id", "resource"))
        inventory = state.setdefault("inventory", [])
        inventory.append(resource_id)
        if "wood" in resource_id:
            state["has_wood"] = True
        return ActionResult(True, {"resource": resource_id, "inventory": list(inventory)})
    if action.name == "wait":
        ticks = int(params.get("ticks", 1))
        state["last_wait"] = ticks
        return ActionResult(True, {"waited": ticks})
    return ActionResult(False, {"error": "unknown_action"})


def _split_params(param_block: str) -> List[str]:
    """按逗号拆分参数，忽略字符串中的逗号。"""
    params: List[str] = []
    buffer: List[str] = []
    quote: Optional[str] = None
    escape = False
    for char in param_block:
        if escape:
            buffer.append(char)
            escape = False
            continue
        if char == "\\":
            buffer.append(char)
            escape = True
            continue
        if quote:
            buffer.append(char)
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            buffer.append(char)
            quote = char
            continue
        if char == ",":
            params.append("".join(buffer).strip())
            buffer = []
            continue
        buffer.append(char)
    if buffer:
        params.append("".join(buffer).strip())
    return params


def _parse_value(raw_value: str) -> Any:
    """解析参数值，支持数字、字符串与占位符。"""
    if not raw_value:
        return ""
    if raw_value.startswith("$"):
        return raw_value
    if (raw_value.startswith('"') and raw_value.endswith('"')) or (
        raw_value.startswith("'") and raw_value.endswith("'")
    ):
        return raw_value[1:-1]
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def _resolve_placeholders(params: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    """用状态中的占位符替换参数值。"""
    placeholders = state.get("placeholders", {})
    resolved: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("$"):
            resolved[key] = placeholders.get(value[1:], value)
        else:
            resolved[key] = value
    return resolved


def _set_placeholder(state: Dict[str, Any], key: str, value: Any) -> None:
    """写入占位符。"""
    placeholders = state.setdefault("placeholders", {})
    placeholders[key] = value
