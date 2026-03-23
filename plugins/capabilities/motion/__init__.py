# 运动控制能力插件 — 旋转与紧急停止
# 实现 CapabilityPlugin Protocol，提供 rotate 和 stop 两种运动控制意图
# 当前为模拟实现（stub），后续将连接 ROS2 运动控制栈

from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ExecutionContext,
    ExecutionResult,
    HealthStatus,
    HealthState,
)


class MotionCapability:
    """运动控制能力插件 — 支持 rotate 和 stop 意图

    实现 CapabilityPlugin Protocol，提供：
    - rotate: 原地旋转指定角度
    - stop: 紧急停止所有运动

    当前为模拟实现，返回成功结果。
    后续将通过 NodeRegistry 查找 ROS2 Bridge 节点执行真实运动控制。
    """

    def __init__(self) -> None:
        self.meta = PluginMeta(
            id="motion",
            name="Motion",
            version="0.1.0",
            description="运动控制能力，支持旋转和紧急停止",
            kind="capability",
            author="MOSAIC",
        )
        # 取消标志，用于中断正在执行的运动任务
        self._cancelled = False

    def get_supported_intents(self) -> list[str]:
        """返回支持的意图列表"""
        return ["rotate", "stop"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """返回工具定义，供 LLM 调用时使用"""
        return [
            {
                "name": "rotate",
                "description": "原地旋转指定角度",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "angle": {
                            "type": "number",
                            "description": "旋转角度（度），正值为逆时针，负值为顺时针",
                        },
                        "speed": {
                            "type": "number",
                            "description": "旋转速度（rad/s），默认 0.3",
                            "default": 0.3,
                        },
                    },
                    "required": ["angle"],
                },
            },
            {
                "name": "stop",
                "description": "紧急停止所有运动",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        """执行运动控制意图

        当前为模拟实现，返回包含意图和参数的成功结果。
        后续将通过 NodeRegistry 查找 ROS2 Bridge 节点执行真实运动控制。

        Args:
            intent: 意图名称（rotate 或 stop）
            params: 意图参数
            ctx: 执行上下文

        Returns:
            ExecutionResult: 执行结果
        """
        # 重置取消标志
        self._cancelled = False

        if intent == "rotate":
            return self._execute_rotate(params)
        elif intent == "stop":
            return self._execute_stop()
        else:
            return ExecutionResult(
                success=False,
                error=f"不支持的意图: {intent}",
            )

    def _execute_rotate(self, params: dict) -> ExecutionResult:
        """执行 rotate 意图（模拟）"""
        angle = params.get("angle", 0.0)
        speed = params.get("speed", 0.3)
        return ExecutionResult(
            success=True,
            data={"intent": "rotate", "angle": angle, "speed": speed},
            message=f"已旋转 {angle} 度（速度: {speed} rad/s）",
        )

    def _execute_stop(self) -> ExecutionResult:
        """执行 stop 意图（模拟） — 紧急停止"""
        return ExecutionResult(
            success=True,
            data={"intent": "stop"},
            message="已紧急停止所有运动",
        )

    async def cancel(self) -> bool:
        """取消当前运动任务

        设置取消标志，后续真实运动控制实现中将检查此标志中断执行。

        Returns:
            bool: 取消是否成功
        """
        self._cancelled = True
        return True

    async def health_check(self) -> HealthStatus:
        """健康检查

        当前模拟实现始终返回 HEALTHY。
        后续将检查 ROS2 运动控制栈连接状态。

        Returns:
            HealthStatus: 健康状态
        """
        return HealthStatus(state=HealthState.HEALTHY, message="运动控制插件正常")


def create_plugin() -> MotionCapability:
    """工厂函数 — 返回 MotionCapability 实例"""
    return MotionCapability()
