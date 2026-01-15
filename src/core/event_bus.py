"""文件职责：异步事件总线，负责发布/订阅与事件等待。
简明实现逻辑：将事件入队，分发给订阅者，并支持按类型或任意事件等待。
输入输出：输入为事件类型与数据；输出为 Event 对象与处理结果。"""

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional


@dataclass(frozen=True)
class Event:
    """事件对象，包含类型、数据与时间戳。"""

    event_type: str
    data: Dict[str, Any]
    timestamp: float


def _maybe_await(result: Any) -> Awaitable[None]:
    """将同步结果包装为可 await 的协程。"""
    if inspect.isawaitable(result):
        return result
    async def _noop() -> None:
        """空协程占位。"""
        return None
    return _noop()


class EventBus:
    """异步事件总线，支持发布、订阅与等待事件。"""

    def __init__(self) -> None:
        """初始化事件队列与订阅表。"""
        self._subscribers: Dict[str, List[Callable[[Event], Any]]] = {}
        self._queues: Dict[str, asyncio.Queue[Event]] = {}
        self._any_queue: asyncio.Queue[Event] = asyncio.Queue()

    async def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        """发布事件并通知订阅者。"""
        event = Event(event_type=event_type, data=data, timestamp=time.time())
        self._get_queue(event_type).put_nowait(event)
        self._any_queue.put_nowait(event)
        for handler in self._subscribers.get(event_type, []):
            await _maybe_await(handler(event))

    async def subscribe(self, event_type: str, handler: Callable[[Event], Any]) -> None:
        """订阅指定类型事件。"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    async def wait_for_event(
        self,
        event_type: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Event]:
        """等待指定类型事件或任意事件。"""
        queue = self._any_queue if event_type in (None, "*") else self._get_queue(event_type)
        try:
            if timeout is None:
                return await queue.get()
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def _get_queue(self, event_type: str) -> asyncio.Queue[Event]:
        """获取或创建指定类型的事件队列。"""
        if event_type not in self._queues:
            self._queues[event_type] = asyncio.Queue()
        return self._queues[event_type]
