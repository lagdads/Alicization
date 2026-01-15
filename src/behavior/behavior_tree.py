"""文件职责：行为树定义与 tick 执行。
简明实现逻辑：以组合节点选择动作，每 tick 输出一个动作。
输入输出：输入为当前状态与目标；输出为 Action 或 None。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional

from src.behavior.actions import Action


@dataclass
class Node:
    """行为树节点基类。"""

    def tick(self, current_state: Dict[str, object], goal: Dict[str, object]) -> Optional[Action]:
        """执行一次 tick，返回动作或 None。"""
        raise NotImplementedError


@dataclass
class Sequence(Node):
    """顺序节点，按顺序返回第一个可执行动作。"""

    children: List[Node] = field(default_factory=list)

    def tick(self, current_state: Dict[str, object], goal: Dict[str, object]) -> Optional[Action]:
        for child in self.children:
            action = child.tick(current_state, goal)
            if action is not None:
                return action
        return None


@dataclass
class Selector(Node):
    """选择节点，返回第一个成功的动作。"""

    children: List[Node] = field(default_factory=list)

    def tick(self, current_state: Dict[str, object], goal: Dict[str, object]) -> Optional[Action]:
        for child in self.children:
            action = child.tick(current_state, goal)
            if action is not None:
                return action
        return None


@dataclass
class Condition(Node):
    """条件节点，满足条件时返回子节点的动作。"""

    key: str
    expected: object
    child: Node

    def tick(self, current_state: Dict[str, object], goal: Dict[str, object]) -> Optional[Action]:
        if current_state.get(self.key) == self.expected:
            return self.child.tick(current_state, goal)
        return None


@dataclass
class GoalAction(Node):
    """当目标满足某一条件时输出动作。"""

    key: str
    expected: object
    action: Action

    def tick(self, current_state: Dict[str, object], goal: Dict[str, object]) -> Optional[Action]:
        if goal.get(self.key) == self.expected:
            return self.action
        return None


class BehaviorTree:
    """行为树执行器。"""

    def __init__(self, root: Node, allowed_actions: Optional[Iterable[str]] = None) -> None:
        """初始化行为树。"""
        self.root = root
        self.allowed_actions = set(allowed_actions or [])
        self.last_action: Optional[Action] = None

    def tick(self, current_state: Dict[str, object], goal: Dict[str, object]) -> Optional[Action]:
        """执行一次 tick，返回动作。"""
        action = self.root.tick(current_state, goal)
        if action is None:
            return None
        if self.allowed_actions and action.name not in self.allowed_actions:
            return None
        self.last_action = action
        return action

    def update_state(self, result: Dict[str, object]) -> None:
        """更新行为树的最后动作结果。"""
        if self.last_action is None:
            return
        result["last_action"] = self.last_action.name
