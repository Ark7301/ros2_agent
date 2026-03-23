# 导航能力插件 — Nav2 导航
# 实现 CapabilityPlugin Protocol，提供 navigate_to 和 patrol 两种导航意图
# 当前为模拟实现（stub），后续将连接 ROS2 导航栈

from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ExecutionContext,
    ExecutionResult,
    HealthStatus,
    HealthState,
)


class NavigationCapability:
    """导航能力插件 — 支持 navigate_to 和 patrol 意图

    实现 CapabilityPlugin Protocol，提供：
    - navigate_to: 导航到指定目标位置
    - patrol: 按路径点列表巡逻

    当前为模拟实现，返回成功结果。
    后续将通过 NodeRegistry 查找 ROS2 Bridge 节点执行真实导航。
    """

    def __init__(self) -> None:
        self.meta = PluginMeta(
            id="navigation",
            name="Navigation",
            version="0.1.0",
            description="Nav2 导航能力，支持目标导航和巡逻",
            kind="capability",
            author="MOSAIC",
        )
        # 取消标志，用于中断正在执行的导航任务
        self._cancelled = False

    def get_supported_intents(self) -> list[str]:
        """返回支持的意图列表"""
        return ["navigate_to", "patrol"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """返回工具定义，供 LLM 调用时使用"""
        return [
            {
                "name": "navigate_to",
                "description": "导航到指定位置",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "目标位置名称",
                        },
                        "speed": {
                            "type": "number",
                            "description": "导航速度（0.0-1.0），默认 0.5",
                            "default": 0.5,
                        },
                    },
                    "required": ["target"],
                },
            },
            {
                "name": "patrol",
                "description": "按路径点列表巡逻",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "waypoints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "巡逻路径点列表",
                        },
                        "repeat": {
                            "type": "boolean",
                            "description": "是否循环巡逻，默认 false",
                            "default": False,
                        },
                    },
                    "required": ["waypoints"],
                },
            },
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        """执行导航意图

        当前为模拟实现，返回包含意图和参数的成功结果。
        后续将通过 NodeRegistry 查找 ROS2 Bridge 节点执行真实导航。

        Args:
            intent: 意图名称（navigate_to 或 patrol）
            params: 意图参数
            ctx: 执行上下文

        Returns:
            ExecutionResult: 执行结果
        """
        # 重置取消标志
        self._cancelled = False

        if intent == "navigate_to":
            return self._execute_navigate_to(params)
        elif intent == "patrol":
            return self._execute_patrol(params)
        else:
            return ExecutionResult(
                success=False,
                error=f"不支持的意图: {intent}",
            )

    def _execute_navigate_to(self, params: dict) -> ExecutionResult:
        """执行 navigate_to 意图（模拟）"""
        target = params.get("target", "")
        speed = params.get("speed", 0.5)
        return ExecutionResult(
            success=True,
            data={"intent": "navigate_to", "target": target, "speed": speed},
            message=f"已导航到 {target}（速度: {speed}）",
        )

    def _execute_patrol(self, params: dict) -> ExecutionResult:
        """执行 patrol 意图（模拟）"""
        waypoints = params.get("waypoints", [])
        repeat = params.get("repeat", False)
        return ExecutionResult(
            success=True,
            data={
                "intent": "patrol",
                "waypoints": waypoints,
                "repeat": repeat,
            },
            message=f"巡逻完成，路径点: {waypoints}，循环: {repeat}",
        )

    async def cancel(self) -> bool:
        """取消当前导航任务

        设置取消标志，后续真实导航实现中将检查此标志中断执行。

        Returns:
            bool: 取消是否成功
        """
        self._cancelled = True
        return True

    async def health_check(self) -> HealthStatus:
        """健康检查

        当前模拟实现始终返回 HEALTHY。
        后续将检查 ROS2 导航栈连接状态。

        Returns:
            HealthStatus: 健康状态
        """
        return HealthStatus(state=HealthState.HEALTHY, message="导航插件正常")


def create_plugin() -> NavigationCapability:
    """工厂函数 — 返回 NavigationCapability 实例"""
    return NavigationCapability()
