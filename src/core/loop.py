"""文件职责：双循环调度器，分别驱动环境高频与认知低频任务。
简明实现逻辑：按固定间隔执行 fast tick，并按事件/间隔执行 slow tick。
输入输出：输入为任务回调与 EventBus 事件；输出为任务执行节奏。"""

import asyncio
import logging
import time
from typing import Awaitable, Callable, List, Optional

from src.core.event_bus import Event, EventBus


class WorldLoop:
    """双循环调度器，运行 fast/slow 任务列表。"""

    def __init__(
        self,
        event_bus: EventBus,
        fast_hz: float = 30.0,
        slow_hz: float = 0.1,
        slow_event_type: Optional[str] = "*",
    ) -> None:
        """初始化调度器与任务队列。"""
        self.event_bus = event_bus
        self.fast_interval = 1.0 / fast_hz
        self.slow_interval = 1.0 / slow_hz if slow_hz > 0 else 0.0
        self.slow_event_type = slow_event_type
        self._fast_tasks: List[Callable[[], Awaitable[None]]] = []
        self._slow_tasks: List[Callable[[Optional[Event]], Awaitable[None]]] = []
        self._stop = asyncio.Event()
        self._logger = logging.getLogger(__name__)

    def register_fast_task(self, task: Callable[[], Awaitable[None]]) -> None:
        """注册高频任务。"""
        self._fast_tasks.append(task)

    def register_slow_task(self, task: Callable[[Optional[Event]], Awaitable[None]]) -> None:
        """注册低频任务。"""
        self._slow_tasks.append(task)

    async def fast_loop(self) -> None:
        """运行 fast tick 循环。"""
        while not self._stop.is_set():
            start = time.monotonic()
            await self._run_fast_tasks()
            elapsed = time.monotonic() - start
            sleep_for = max(0.0, self.fast_interval - elapsed)
            await asyncio.sleep(sleep_for)

    async def slow_loop(self) -> None:
        """运行 slow tick 循环。"""
        while not self._stop.is_set():
            event = await self.event_bus.wait_for_event(
                event_type=self.slow_event_type,
                timeout=self.slow_interval if self.slow_interval > 0 else None,
            )
            await self._run_slow_tasks(event)

    async def run(self) -> None:
        """并发运行 fast/slow 两个循环。"""
        await asyncio.gather(self.fast_loop(), self.slow_loop())

    def stop(self) -> None:
        """请求停止循环。"""
        self._stop.set()

    async def _run_fast_tasks(self) -> None:
        """执行所有 fast 任务并捕获异常。"""
        for task in self._fast_tasks:
            try:
                await task()
            except Exception:
                self._logger.exception("Fast task failed")

    async def _run_slow_tasks(self, event: Optional[Event]) -> None:
        """执行所有 slow 任务并捕获异常。"""
        for task in self._slow_tasks:
            try:
                await task(event)
            except Exception:
                self._logger.exception("Slow task failed")
