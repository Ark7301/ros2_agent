"""异步事件总线 — 优先级队列 + 通配符订阅 + 中间件"""
from __future__ import annotations

import asyncio
from typing import Callable

from mosaic.protocol.events import Event, EventHandler


class EventBus:
    """异步事件总线 — 优先级队列 + 通配符订阅 + 中间件

    所有组件通过事件解耦通信，支持：
    - 优先级队列：CRITICAL 事件优先分发
    - 通配符订阅：'*' 匹配所有，'a.*' 匹配 'a.' 开头的事件
    - 中间件链：按注册顺序执行，返回 None 则丢弃事件
    """

    def __init__(self, max_queue_size: int = 10000):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self._running = False
        self._middlewares: list[Callable[[Event], Event | None]] = []

    def on(self, event_type: str, handler: EventHandler) -> Callable:
        """订阅事件，支持通配符 'capability.*'

        返回取消订阅的回调函数。
        """
        self._handlers.setdefault(event_type, []).append(handler)
        return lambda: self._handlers[event_type].remove(handler)

    async def emit(self, event: Event) -> None:
        """发射事件（经过中间件链）

        中间件按注册顺序依次执行，任一中间件返回 None 则丢弃事件。
        """
        for mw in self._middlewares:
            event = mw(event)
            if event is None:
                return
        await self._queue.put(event)

    def use(self, middleware: Callable[[Event], Event | None]):
        """注册中间件"""
        self._middlewares.append(middleware)

    async def start(self):
        """启动事件分发循环"""
        self._running = True
        while self._running:
            try:
                # 使用短超时轮询，避免 stop() 后永远阻塞在 get()
                event = await asyncio.wait_for(self._queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            await self._dispatch(event)

    async def stop(self):
        """停止事件分发循环"""
        self._running = False

    async def _dispatch(self, event: Event):
        """分发到匹配的 handler，支持通配符匹配"""
        tasks = []
        for pattern, handlers in self._handlers.items():
            if self._matches(pattern, event.type):
                tasks.extend(handler(event) for handler in handlers)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        """通配符匹配规则：
        - '*' 匹配所有事件类型
        - 'a.*' 匹配所有以 'a.' 开头的事件类型
        - 精确匹配
        """
        if pattern == "*":
            return True
        if pattern.endswith(".*"):
            return event_type.startswith(pattern[:-1])
        return pattern == event_type
