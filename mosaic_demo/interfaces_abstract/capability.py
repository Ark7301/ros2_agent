from __future__ import annotations

"""
Capability 抽象基类 — 机器人能力接口

定义 Agent 核心与机器人能力模块之间的抽象契约，
具体实现（如 MockNavigationCapability）需继承此基类。
"""

from abc import ABC, abstractmethod
from typing import Callable, Optional

from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus,
    ExecutionResult,
    Task,
)


class Capability(ABC):
    """机器人能力抽象接口

    所有能力模块（导航、运动等）必须继承此基类并实现所有抽象方法。
    Agent 核心仅依赖此抽象接口，不直接依赖具体实现。
    """

    @abstractmethod
    def get_name(self) -> str:
        """返回能力名称

        Returns:
            能力的唯一标识名称
        """
        pass

    @abstractmethod
    def get_supported_intents(self) -> list[str]:
        """返回支持的意图类型列表

        Returns:
            该能力支持处理的意图名称列表
        """
        pass

    @abstractmethod
    async def execute(
        self, task: Task, feedback_callback: Callable = None
    ) -> ExecutionResult:
        """执行任务

        Args:
            task: 待执行的任务实例
            feedback_callback: 可选的反馈回调函数，用于报告执行进度

        Returns:
            执行结果
        """
        pass

    @abstractmethod
    async def cancel(self) -> bool:
        """取消当前正在执行的任务

        Returns:
            取消是否成功
        """
        pass

    @abstractmethod
    async def get_status(self) -> CapabilityStatus:
        """获取当前能力状态

        Returns:
            当前能力的状态（IDLE / BUSY / ERROR）
        """
        pass

    @abstractmethod
    def get_capability_description(self) -> str:
        """返回能力的自然语言描述（供 LLM 理解能力边界）

        Returns:
            描述该能力功能范围的自然语言文本
        """
        pass
