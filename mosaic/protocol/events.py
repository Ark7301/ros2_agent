"""协议层 — 事件优先级、不可变事件对象、事件处理函数类型"""
from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from datetime import datetime
import uuid


class EventPriority(Enum):
    """事件优先级"""
    CRITICAL = 0   # 安全/紧急停止
    HIGH = 1       # 执行结果
    NORMAL = 2     # 常规消息
    LOW = 3        # 日志/遥测


@dataclass(frozen=True)
class Event:
    """不可变事件对象"""
    type: str
    payload: dict[str, Any]
    source: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: str | None = None
    session_id: str | None = None

    def __lt__(self, other: Event) -> bool:
        """支持 PriorityQueue 比较"""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.timestamp < other.timestamp


# 事件处理函数类型别名
EventHandler = Callable[[Event], Awaitable[None]]
