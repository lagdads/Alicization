"""文件职责：行为子系统包标识。
简明实现逻辑：提供行为树与 GOAP 的命名空间分组。
输入输出：无直接输入输出。"""

from src.behavior.actions import Action
from src.behavior.behavior_tree import BehaviorTree

__all__ = ["Action", "BehaviorTree"]
