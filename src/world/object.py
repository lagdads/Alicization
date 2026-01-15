"""文件职责：世界对象与组件定义（ECS 组合）。
简明实现逻辑：通过组件组合能力，表达位置/权限/持有等信息。
输入输出：输入为组件数据；输出为组合后的对象实例。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.core.entity import Entity


@dataclass
class Position:
    """世界坐标组件。"""

    x: int
    y: int


@dataclass
class Destiny:
    """天命值组件。"""

    value: float


@dataclass
class Holdable:
    """可持有组件。"""

    required_level: int


@dataclass
class HolderPermission:
    """持有权限组件。"""

    level: int


@dataclass
class AccessPermission:
    """系统指令访问权限组件。"""

    level: int


class Object(Entity):
    """世界对象，基于 ECS 组合组件。"""

    def __init__(self, object_id: str) -> None:
        """初始化对象。"""
        super().__init__(object_id)

    def set_position(self, x: int, y: int) -> None:
        """更新对象位置。"""
        self.add_component("position", Position(x=x, y=y))

    def get_position(self) -> Optional[Position]:
        """获取对象位置组件。"""
        component = self.get_component("position")
        if isinstance(component, Position):
            return component
        return None

    def set_destiny(self, value: float) -> None:
        """设置天命值。"""
        self.add_component("destiny", Destiny(value=value))

    def adjust_destiny(self, delta: float) -> None:
        """调整天命值（可用于消耗）。"""
        destiny = self.get_component("destiny")
        if isinstance(destiny, Destiny):
            destiny.value += delta
        else:
            self.add_component("destiny", Destiny(value=delta))

    def get_destiny(self) -> Optional[Destiny]:
        """获取天命值组件。"""
        component = self.get_component("destiny")
        if isinstance(component, Destiny):
            return component
        return None

    def set_holdable(self, required_level: int) -> None:
        """设置可持有组件。"""
        self.add_component("holdable", Holdable(required_level=required_level))

    def set_holder_permission(self, level: int) -> None:
        """设置持有权限组件。"""
        self.add_component("holder_permission", HolderPermission(level=level))

    def set_access_permission(self, level: int) -> None:
        """设置访问权限组件。"""
        self.add_component("access_permission", AccessPermission(level=level))

    def can_be_held_by(self, holder: "Object") -> bool:
        """判断是否可被指定对象持有。"""
        holdable = self.get_component("holdable")
        permission = holder.get_component("holder_permission")
        if not isinstance(holdable, Holdable):
            return False
        if not isinstance(permission, HolderPermission):
            return False
        return permission.level >= holdable.required_level
