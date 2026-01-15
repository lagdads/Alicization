"""文件职责：世界子系统包标识。
简明实现逻辑：作为环境与规则模块的命名空间分组。
输入输出：无直接输入输出。"""

from src.world.environment import Environment
from src.world.map import LAND, SEA, WorldMap
from src.world.object import (
    AccessPermission,
    Destiny,
    Holdable,
    HolderPermission,
    Object,
    Position,
)

__all__ = [
    "AccessPermission",
    "Destiny",
    "Environment",
    "Holdable",
    "HolderPermission",
    "LAND",
    "Object",
    "Position",
    "SEA",
    "WorldMap",
]
