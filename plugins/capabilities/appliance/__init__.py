# 家电操作能力插件 — 操作家用电器/设备
# 实现 CapabilityPlugin Protocol，提供 operate_appliance 和 wait_appliance 意图
# 当前为模拟实现（stub），后续将连接 ROS2 IoT Bridge

from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ExecutionContext,
    ExecutionResult,
    HealthStatus,
    HealthState,
)


class ApplianceCapability:
    """家电操作能力插件 — 支持 operate_appliance 和 wait_appliance 意图

    实现 CapabilityPlugin Protocol，提供：
    - operate_appliance: 操作指定家电（启动/停止/设置参数）
    - wait_appliance: 等待家电完成当前任务

    当前为模拟实现，返回成功结果。
    后续将通过 NodeRegistry 查找 ROS2 IoT Bridge 节点执行真实设备控制。
    """

    def __init__(self) -> None:
        self.meta = PluginMeta(
            id="appliance",
            name="Appliance",
            version="0.1.0",
            description="家电操作能力，支持操作和等待家用电器",
            kind="capability",
            author="MOSAIC",
        )
        self._cancelled = False

    def get_supported_intents(self) -> list[str]:
        """返回支持的意图列表"""
        return ["operate_appliance", "wait_appliance"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """返回工具定义，供 LLM 调用时使用"""
        return [
            {
                "name": "operate_appliance",
                "description": (
                    "操作家用电器或设备。"
                    "例如：启动咖啡机制作咖啡、打开微波炉加热、开关灯、启动扫地机器人等。"
                    "必须先导航到设备所在位置再调用此工具。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appliance_name": {
                            "type": "string",
                            "description": "设备名称（如：咖啡机、微波炉、洗碗机、空调、灯）",
                        },
                        "action": {
                            "type": "string",
                            "description": "操作动作（如：启动、停止、开、关、设置温度）",
                        },
                        "parameters": {
                            "type": "string",
                            "description": "操作参数（可选，如：制作拿铁、加热3分钟、设置26度）",
                            "default": "",
                        },
                    },
                    "required": ["appliance_name", "action"],
                },
            },
            {
                "name": "wait_appliance",
                "description": (
                    "等待家电完成当前任务。"
                    "例如：等待咖啡机制作完成、等待微波炉加热完成。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "appliance_name": {
                            "type": "string",
                            "description": "等待的设备名称",
                        },
                    },
                    "required": ["appliance_name"],
                },
            },
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext,
    ) -> ExecutionResult:
        """执行家电操作意图"""
        self._cancelled = False

        if intent == "operate_appliance":
            return self._execute_operate(params)
        elif intent == "wait_appliance":
            return self._execute_wait(params)
        else:
            return ExecutionResult(
                success=False,
                error=f"不支持的意图: {intent}",
            )

    def _execute_operate(self, params: dict) -> ExecutionResult:
        """执行 operate_appliance 意图（模拟）"""
        name = params.get("appliance_name", "")
        action = params.get("action", "")
        extra = params.get("parameters", "")
        msg = f"已对 {name} 执行操作: {action}"
        if extra:
            msg += f"（参数: {extra}）"
        return ExecutionResult(
            success=True,
            data={
                "intent": "operate_appliance",
                "appliance_name": name,
                "action": action,
                "parameters": extra,
            },
            message=msg,
        )

    def _execute_wait(self, params: dict) -> ExecutionResult:
        """执行 wait_appliance 意图（模拟）"""
        name = params.get("appliance_name", "")
        return ExecutionResult(
            success=True,
            data={"intent": "wait_appliance", "appliance_name": name},
            message=f"{name} 已完成任务",
        )

    async def cancel(self) -> bool:
        """取消当前操作"""
        self._cancelled = True
        return True

    async def health_check(self) -> HealthStatus:
        """健康检查"""
        return HealthStatus(state=HealthState.HEALTHY, message="家电操作插件正常")


def create_plugin() -> ApplianceCapability:
    """工厂函数 — 返回 ApplianceCapability 实例"""
    return ApplianceCapability()
