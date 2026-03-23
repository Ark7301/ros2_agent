# 物品操作能力插件 — 拿取与递交
# 实现 CapabilityPlugin Protocol，提供 pick_up 和 hand_over 两种物品操作意图
# 当前为模拟实现（stub），后续将连接 ROS2 机械臂控制栈

from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ExecutionContext,
    ExecutionResult,
    HealthStatus,
    HealthState,
)


class ManipulationCapability:
    """物品操作能力插件 — 支持 pick_up 和 hand_over 意图

    实现 CapabilityPlugin Protocol，提供：
    - pick_up: 拿取/抓取指定物品
    - hand_over: 将手中物品递交给用户

    当前为模拟实现，返回成功结果。
    后续将通过 NodeRegistry 查找 ROS2 Bridge 节点执行真实机械臂操作。
    """

    def __init__(self) -> None:
        self.meta = PluginMeta(
            id="manipulation",
            name="Manipulation",
            version="0.1.0",
            description="物品操作能力，支持拿取和递交物品",
            kind="capability",
            author="MOSAIC",
        )
        self._cancelled = False
        # 当前手持物品（模拟状态）
        self._holding: str | None = None

    def get_supported_intents(self) -> list[str]:
        """返回支持的意图列表"""
        return ["pick_up", "hand_over"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """返回工具定义，供 LLM 调用时使用"""
        return [
            {
                "name": "pick_up",
                "description": "拿取/抓取指定物品。必须先导航到物品所在位置再调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "object_name": {
                            "type": "string",
                            "description": "要拿取的物品名称（如：黄色毛巾、水杯、遥控器）",
                        },
                    },
                    "required": ["object_name"],
                },
            },
            {
                "name": "hand_over",
                "description": "将手中持有的物品递交给用户。必须先导航到用户所在位置再调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "object_name": {
                            "type": "string",
                            "description": "要递交的物品名称",
                        },
                    },
                    "required": ["object_name"],
                },
            },
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        """执行物品操作意图

        Args:
            intent: 意图名称（pick_up 或 hand_over）
            params: 意图参数
            ctx: 执行上下文

        Returns:
            ExecutionResult: 执行结果
        """
        self._cancelled = False

        if intent == "pick_up":
            return self._execute_pick_up(params)
        elif intent == "hand_over":
            return self._execute_hand_over(params)
        else:
            return ExecutionResult(
                success=False,
                error=f"不支持的意图: {intent}",
            )

    def _execute_pick_up(self, params: dict) -> ExecutionResult:
        """执行 pick_up 意图（模拟）"""
        obj = params.get("object_name", "")
        self._holding = obj
        return ExecutionResult(
            success=True,
            data={"intent": "pick_up", "object_name": obj},
            message=f"已拿取 {obj}",
        )

    def _execute_hand_over(self, params: dict) -> ExecutionResult:
        """执行 hand_over 意图（模拟）"""
        obj = params.get("object_name", "")
        if self._holding is None:
            return ExecutionResult(
                success=False,
                error="当前没有持有任何物品，无法递交",
            )
        handed = self._holding
        self._holding = None
        return ExecutionResult(
            success=True,
            data={"intent": "hand_over", "object_name": handed},
            message=f"已将 {handed} 递交给用户",
        )

    async def cancel(self) -> bool:
        """取消当前操作"""
        self._cancelled = True
        return True

    async def health_check(self) -> HealthStatus:
        """健康检查"""
        return HealthStatus(state=HealthState.HEALTHY, message="物品操作插件正常")


def create_plugin() -> ManipulationCapability:
    """工厂函数 — 返回 ManipulationCapability 实例"""
    return ManipulationCapability()
