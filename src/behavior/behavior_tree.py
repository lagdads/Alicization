"""文件职责：行为树节点类型与执行逻辑。
简明实现逻辑：递归遍历节点并传递 SUCCESS/FAILURE/RUNNING 状态。
输入输出：输入为动作/条件回调与子节点；输出为状态字符串。"""

import inspect
from typing import Any, Awaitable, Callable, List, Optional


class Status:
    """行为树节点返回状态枚举。"""

    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RUNNING = "RUNNING"


def _maybe_await(result: Any) -> Awaitable[Any]:
    """将同步结果包装为协程以统一 await 调用。"""
    if inspect.isawaitable(result):
        return result
    async def _wrapper() -> Any:
        """包装同步结果为可 await 协程。"""
        return result
    return _wrapper()


class Node:
    """行为树节点基类。"""

    async def tick(self) -> str:
        """执行节点逻辑并返回状态。"""
        raise NotImplementedError


class Sequence(Node):
    """顺序节点，子节点全部成功才成功。"""

    def __init__(self, children: List[Node]) -> None:
        """初始化子节点列表。"""
        self.children = children

    async def tick(self) -> str:
        """按顺序执行子节点。"""
        for child in self.children:
            result = await child.tick()
            if result != Status.SUCCESS:
                return result
        return Status.SUCCESS


class Selector(Node):
    """选择节点，子节点任一成功即成功。"""

    def __init__(self, children: List[Node]) -> None:
        """初始化子节点列表。"""
        self.children = children

    async def tick(self) -> str:
        """按顺序选择可成功的子节点。"""
        for child in self.children:
            result = await child.tick()
            if result == Status.SUCCESS:
                return Status.SUCCESS
            if result == Status.RUNNING:
                return Status.RUNNING
        return Status.FAILURE


class Condition(Node):
    """条件节点，根据断言结果返回状态。"""

    def __init__(self, predicate: Callable[[], Any]) -> None:
        """初始化断言回调。"""
        self.predicate = predicate

    async def tick(self) -> str:
        """执行条件判断。"""
        result = await _maybe_await(self.predicate())
        return Status.SUCCESS if result else Status.FAILURE


class Action(Node):
    """动作节点，执行回调并映射返回状态。"""

    def __init__(self, action: Callable[[], Any]) -> None:
        """初始化动作回调。"""
        self.action = action

    async def tick(self) -> str:
        """执行动作并转换为状态。"""
        result = await _maybe_await(self.action())
        if result is None:
            return Status.SUCCESS
        if result in (Status.SUCCESS, Status.FAILURE, Status.RUNNING):
            return result
        return Status.SUCCESS if bool(result) else Status.FAILURE


class BehaviorTree:
    """行为树容器，持有根节点。"""

    def __init__(self, root: Node) -> None:
        """初始化根节点。"""
        self.root = root

    async def tick(self) -> str:
        """执行行为树一次 tick。"""
        return await self.root.tick()
