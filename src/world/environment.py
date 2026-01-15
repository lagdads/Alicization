"""文件职责：世界环境状态容器与时间推进。
简明实现逻辑：维护实体集合并累积时间。
输入输出：输入为实体与时间步长；输出为更新后的环境状态。"""

from typing import Dict

from src.core.entity import Entity


class Environment:
    """世界环境容器，维护实体与时间。"""

    def __init__(self) -> None:
        """初始化环境状态。"""
        self.time = 0.0
        self.entities: Dict[str, Entity] = {}

    def add_entity(self, entity: Entity) -> None:
        """添加实体到环境。"""
        self.entities[entity.id] = entity

    def remove_entity(self, entity_id: str) -> None:
        """移除指定实体。"""
        self.entities.pop(entity_id, None)

    def update(self, dt: float) -> None:
        """推进环境时间。"""
        self.time += dt
