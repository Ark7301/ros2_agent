"""
Mock 导航能力 — 模拟 navigate_to 和 patrol 意图

内部通过 LocationService 解析语义地名，
execute() 模拟异步延迟后返回成功/失败结果。
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
from mosaic_demo.capabilities.location_service import LocationService


class MockNavigationCapability(Capability):
    """Mock 导航能力 — 模拟 navigate_to 和 patrol 意图

    通过 LocationService 解析语义地名为坐标，
    模拟异步延迟后返回执行结果。
    地名无法解析时返回错误 ExecutionResult。
    """

    def __init__(self, location_service: LocationService):
        """初始化导航能力

        Args:
            location_service: 语义地名服务实例，用于解析地名到坐标
        """
        self._location_service = location_service

    def get_name(self) -> str:
        """返回能力名称"""
        return "navigation"

    def get_supported_intents(self) -> list[str]:
        """返回支持的意图列表：navigate_to 和 patrol"""
        return ["navigate_to", "patrol"]

    async def execute(
        self, task: Task, feedback_callback: Callable = None
    ) -> ExecutionResult:
        """模拟导航执行

        从 task.params 获取 target 参数，通过 LocationService 解析地名。
        地名无法解析时返回错误结果，否则模拟异步延迟后返回成功结果。

        Args:
            task: 待执行的任务，params 中应包含 "target" 字段
            feedback_callback: 可选的反馈回调函数

        Returns:
            包含执行状态和消息的 ExecutionResult
        """
        target = task.params.get("target")

        # 通过 LocationService 解析地名
        coords = self._location_service.resolve_location(target)

        # 地名无法解析时返回错误
        if coords is None:
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                message=f"无法解析目标地名: {target}",
                status=TaskStatus.FAILED,
                error=f"地名 '{target}' 未在 LocationService 中注册",
            )

        # 模拟异步导航延迟
        await asyncio.sleep(0.1)

        return ExecutionResult(
            task_id=task.task_id,
            success=True,
            message=f"已到达{target}",
            status=TaskStatus.SUCCEEDED,
            data={"target": target, "coordinates": coords},
        )

    async def cancel(self) -> bool:
        """取消当前导航任务"""
        return True

    async def get_status(self) -> CapabilityStatus:
        """获取当前能力状态"""
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        """返回导航能力的自然语言描述"""
        return "导航能力：支持导航到指定地点（navigate_to）和巡逻（patrol）"
