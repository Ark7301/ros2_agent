from __future__ import annotations

"""
核心数据模型 — MOSAIC Demo 管道数据流基础

包含所有核心数据结构：枚举、dataclass 及其序列化方法。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import uuid
from datetime import datetime


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CapabilityStatus(Enum):
    """能力状态枚举"""
    IDLE = "idle"
    BUSY = "busy"
    ERROR = "error"


@dataclass
class TaskContext:
    """任务上下文 — 在整个管道中传递"""
    raw_input: str
    language: str = "zh"
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """任务解析结果"""
    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    sub_tasks: list['TaskResult'] = field(default_factory=list)
    confidence: float = 1.0
    raw_response: Optional[str] = None

    def to_dict(self) -> dict:
        """将实例序列化为字典，递归处理 sub_tasks"""
        return {
            "intent": self.intent,
            "params": self.params,
            "sub_tasks": [st.to_dict() for st in self.sub_tasks],
            "confidence": self.confidence,
            "raw_response": self.raw_response,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TaskResult':
        """从字典反序列化为实例，递归处理 sub_tasks"""
        return cls(
            intent=data.get("intent", ""),
            params=data.get("params", {}),
            sub_tasks=[cls.from_dict(st) for st in data.get("sub_tasks", [])],
            confidence=data.get("confidence", 1.0),
            raw_response=data.get("raw_response"),
        )


@dataclass
class Task:
    """可执行任务"""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    intent: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    priority: int = 1
    status: TaskStatus = TaskStatus.PENDING
    context: Optional[TaskContext] = None
    created_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0


@dataclass
class PlannedAction:
    """计划中的单个动作"""
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    capability_name: str = ""
    task: Optional[Task] = None
    description: str = ""


@dataclass
class ExecutionPlan:
    """有序动作序列"""
    plan_id: str
    actions: list[PlannedAction]
    original_task: Optional[TaskResult] = None
    current_index: int = 0

    def peek_next(self) -> Optional[PlannedAction]:
        """返回当前索引的动作，如果已完成返回 None"""
        if self.is_complete():
            return None
        return self.actions[self.current_index]

    def advance(self) -> None:
        """将 current_index 加 1"""
        self.current_index += 1

    def is_complete(self) -> bool:
        """判断是否所有动作已执行完毕"""
        return self.current_index >= len(self.actions)


@dataclass
class ExecutionResult:
    """执行结果 — 沿管道回传"""
    task_id: str
    success: bool
    message: str
    status: TaskStatus = TaskStatus.SUCCEEDED
    data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class CapabilityInfo:
    """能力信息"""
    name: str
    supported_intents: list[str]
    status: CapabilityStatus = CapabilityStatus.IDLE
    description: str = ""
