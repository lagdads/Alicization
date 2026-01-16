"""文件职责：世界环境状态容器与时间推进。
简明实现逻辑：维护实体集合、世界地图并按 tick 推进时间。
输入输出：输入为实体/地图/时间步长；输出为更新后的环境状态。"""

from typing import Callable, Dict, List, Optional

from src.core.entity import Entity
from src.world.map import WorldMap
from src.world.object import Destiny, Object


class Environment:
    """世界环境容器，维护实体与时间。"""

    TICKS_PER_DAY = 24

    def __init__(self, world_map: Optional[WorldMap] = None) -> None:
        """初始化环境状态。"""
        self.time = 0.0
        self.tick_count = 0
        self.day_count = 0
        self.entities: Dict[str, Entity] = {}
        self.world_map = world_map
        self._day_end_callbacks: List[Callable[[int], None]] = []

    def add_entity(self, entity: Entity) -> None:
        """添加实体到环境。"""
        self.entities[entity.id] = entity

    def remove_entity(self, entity_id: str) -> None:
        """移除指定实体。"""
        self.entities.pop(entity_id, None)

    def update(self, dt: float) -> None:
        """推进环境时间。"""
        self.time += dt

    def register_day_end_callback(self, callback: Callable[[int], None]) -> None:
        """注册日终回调（用于记忆整理等）。"""
        self._day_end_callbacks.append(callback)

    def tick(self) -> None:
        """执行一个时间 tick 并清理命运值耗尽的对象。"""
        self.tick_count += 1
        self.time += 1.0
        self._cleanup_expired_objects()
        if self.tick_count >= self.TICKS_PER_DAY:
            self.tick_count = 0
            self.day_count += 1
            for callback in self._day_end_callbacks:
                callback(self.day_count)

    def _cleanup_expired_objects(self) -> None:
        """移除天命值归零的对象。"""
        expired_ids: List[str] = []
        for entity_id, entity in self.entities.items():
            if not isinstance(entity, Object):
                continue
            destiny = entity.get_component("destiny")
            if isinstance(destiny, Destiny) and destiny.value <= 0:
                expired_ids.append(entity_id)
        for entity_id in expired_ids:
            self.remove_entity(entity_id)
