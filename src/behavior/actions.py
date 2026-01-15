"""文件职责：行为节点与具体动作定义。
简明实现逻辑：以 Action 数据结构描述 tick 级动作。
输入输出：输入为动作参数；输出为可执行的 Action 实例。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


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


def move_to(x: int, y: int) -> Action:
    """移动到指定坐标。"""
    return Action(name="move_to", params={"x": x, "y": y})


def collect(object_id: str) -> Action:
    """收集指定对象。"""
    return Action(name="collect", params={"object_id": object_id})


def attack(target_id: str) -> Action:
    """攻击指定目标。"""
    return Action(name="attack", params={"target_id": target_id})


def talk(target_id: str, message: str) -> Action:
    """与目标交谈并传递消息。"""
    return Action(name="talk", params={"target_id": target_id, "message": message})
