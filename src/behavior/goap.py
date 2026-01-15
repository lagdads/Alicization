"""文件职责：GOAP 规划器与动作执行辅助。
简明实现逻辑：基于动作效果搜索满足目标的路径，生成并执行计划。
输入输出：输入为动作集合/当前状态/目标；输出为动作序列与执行结果。"""

import heapq
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Action:
    """GOAP 动作定义。"""

    name: str
    preconditions: Dict[str, Any]
    effects: Dict[str, Any]
    cost: float


class GOAPPlanner:
    """GOAP 规划器，支持生成与执行计划。"""

    def __init__(self, actions: Optional[List[Action]] = None) -> None:
        """初始化动作列表与当前状态。"""
        self.actions = actions or []
        self.current_state: Dict[str, Any] = {}

    def set_actions(self, actions: List[Action]) -> None:
        """替换动作列表。"""
        self.actions = actions

    def set_state(self, state: Dict[str, Any]) -> None:
        """设置当前状态。"""
        self.current_state = state

    def plan(self, current_state: Dict[str, Any], goal: Dict[str, Any]) -> List[Action]:
        """从当前状态规划到目标状态的动作序列。"""
        if self._goal_satisfied(current_state, goal):
            return []
        frontier: List[Tuple[float, Dict[str, Any], List[Action]]] = []
        heapq.heappush(frontier, (0.0, current_state, []))
        visited = set()
        while frontier:
            cost, state, plan = heapq.heappop(frontier)
            state_key = self._state_key(state)
            if state_key in visited:
                continue
            visited.add(state_key)
            if self._goal_satisfied(state, goal):
                return plan
            for action in self.actions:
                if not self._preconditions_met(state, action.preconditions):
                    continue
                new_state = self._apply_effects(state, action.effects)
                heapq.heappush(frontier, (cost + action.cost, new_state, plan + [action]))
        return []

    def execute_plan(
        self,
        plan: List[Action],
        current_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """按顺序执行动作计划并更新状态。"""
        state = current_state or self.current_state
        for action in plan:
            if not self._preconditions_met(state, action.preconditions):
                return False
            state.update(action.effects)
        return True

    def _preconditions_met(self, state: Dict[str, Any], preconditions: Dict[str, Any]) -> bool:
        """判断动作前置条件是否满足。"""
        return all(state.get(key) == value for key, value in preconditions.items())

    def _goal_satisfied(self, state: Dict[str, Any], goal: Dict[str, Any]) -> bool:
        """判断目标条件是否已满足。"""
        return all(state.get(key) == value for key, value in goal.items())

    def _apply_effects(self, state: Dict[str, Any], effects: Dict[str, Any]) -> Dict[str, Any]:
        """应用动作效果并返回新状态。"""
        new_state = dict(state)
        new_state.update(effects)
        return new_state

    def _state_key(self, state: Dict[str, Any]) -> Tuple[Tuple[str, Any], ...]:
        """将状态转换为可哈希的键。"""
        return tuple(sorted(state.items()))
