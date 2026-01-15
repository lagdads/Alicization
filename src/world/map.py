"""文件职责：2D 世界地图矩阵与地形查询。
简明实现逻辑：维护矩阵与坐标转换，提供地形设置与读取。
输入输出：输入为坐标/地形；输出为地形类型或布尔结果。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TerrainType:
    """地形类型定义。"""

    name: str


LAND = TerrainType(name="land")
SEA = TerrainType(name="sea")


class WorldMap:
    """世界地图，使用二维矩阵表示。"""

    def __init__(self, width: int, height: int, default: TerrainType = LAND) -> None:
        """初始化地图矩阵。"""
        if width <= 0 or height <= 0:
            raise ValueError("地图尺寸必须为正数")
        self.width = width
        self.height = height
        self._grid: List[List[TerrainType]] = [
            [default for _ in range(width)] for _ in range(height)
        ]

    def in_bounds(self, x: int, y: int) -> bool:
        """判断坐标是否在地图范围内。"""
        row, col = self._to_index(x, y)
        return 0 <= row < self.height and 0 <= col < self.width

    def get_terrain(self, x: int, y: int) -> TerrainType:
        """读取指定坐标的地形类型。"""
        row, col = self._to_index(x, y)
        return self._grid[row][col]

    def set_terrain(self, x: int, y: int, terrain: TerrainType) -> None:
        """设置指定坐标的地形类型。"""
        row, col = self._to_index(x, y)
        self._grid[row][col] = terrain

    def _to_index(self, x: int, y: int) -> tuple[int, int]:
        """世界坐标转换为矩阵索引（中心点为 0,0）。"""
        col = x + self.width // 2
        row = (self.height // 2) - y
        if not (0 <= row < self.height and 0 <= col < self.width):
            raise IndexError("坐标超出地图范围")
        return row, col
