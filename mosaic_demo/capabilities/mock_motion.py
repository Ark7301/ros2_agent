from __future__ import annotations

"""
Mock 运动能力 — 模拟 rotate 和 stop 意图

模拟异步执行并返回成功 ExecutionResult。
"""

import asyncio
from typing import Callable

from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus,
    ExecutionResult,
    Task,
    TaskStatus,
)


class MockMotionCapability(Capability):
    """Mock 运动能力 — 模拟 rotate 和 stop 意图

    模拟异步延迟后返回成功的 ExecutionResult。
    """

    def get_name(self) -> str:
        """返回能力名称"""
        return "motion"

    def get_supported_intents(self) -> list[str]:
        """返回支持的意图列表：rotate 和 stop"""
        return ["rotate", "stop"]

    async def execute(
        self, task: Task, feedback_callback: Callable = None
    ) -> ExecutionResult:
        """模拟运动执行

        Args:
            task: 待执行的任务实例
            feedback_callback: 可选的反馈回调函数

        Returns:
            包含执行状态和消息的 ExecutionResult
        """
        # 模拟异步执行延迟
        await asyncio.sleep(0.05)

        return ExecutionResult(
            task_id=task.task_id,
            success=True,
            message="运动完成",
            status=TaskStatus.SUCCEEDED,
        )

    async def cancel(self) -> bool:
        """取消当前运动任务"""
        return True

    async def get_status(self) -> CapabilityStatus:
        """获取当前能力状态"""
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        """返回运动能力的自然语言描述"""
        return "运动能力：支持旋转（rotate）和停止（stop）"
