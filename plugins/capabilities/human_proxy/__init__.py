from __future__ import annotations

import asyncio
from typing import Any

from mosaic.plugin_sdk.types import (
    ExecutionContext,
    ExecutionResult,
    HealthState,
    HealthStatus,
    PluginMeta,
)

from mosaic.runtime.operator_console import OperatorConsoleState


class HumanProxyCapability:
    """Capability that publishes steps to an operator console and waits for human input."""

    def __init__(
        self,
        console_state: OperatorConsoleState | None = None,
        timeout_s: float = 180.0,
        enabled: bool = True,
    ) -> None:
        self.meta = PluginMeta(
            id="human-proxy",
            name="Human Proxy",
            version="0.1.0",
            description="Forward movement instructions to a human operator console.",
            kind="capability",
            author="MOSAIC",
        )
        self._state = console_state or OperatorConsoleState()
        self._timeout = timeout_s
        self._enabled = enabled

    def get_supported_intents(self) -> list[str]:
        return ["request_human_move"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        if not self._enabled:
            return []
        return [
            {
                "name": "request_human_move",
                "description": "请求真人代理执行移动指令。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "instruction_text": {
                            "type": "string",
                            "description": "需要下达人员执行的移动指令文本。",
                        },
                    },
                    "required": ["instruction_text"],
                },
            }
        ]

    async def execute(
        self, intent: str, params: dict[str, Any], ctx: ExecutionContext
    ) -> ExecutionResult:
        if not self._enabled:
            return ExecutionResult(success=False, error="human proxy disabled")
        if intent != "request_human_move":
            return ExecutionResult(success=False, error=f"不支持的意图: {intent}")

        step_id = ctx.metadata.get("step_id", "step-missing")
        payload = {
            "step_id": step_id,
            "instruction_text": params.get("instruction_text", ""),
            "params": params,
        }
        self._state.publish_step(payload)

        try:
            result = await self._state.wait_for_result(step_id, self._timeout)
        except asyncio.TimeoutError:
            return ExecutionResult(success=False, error="等待真人代机回传超时")

        operator_result = result.get("operator_result")
        is_completed = operator_result == "completed"
        if is_completed:
            images = result.get("images", {}) or {}
            required_views = {"front", "left", "right", "back"}
            missing_views = required_views - set(images.keys())
            if missing_views:
                return ExecutionResult(
                    success=False,
                    data=result,
                    error=f"缺少视角图像: {', '.join(sorted(missing_views))}",
                )
            return ExecutionResult(success=True, data=result, message="真人代机已完成操作")
        return ExecutionResult(success=False, data=result, error="真人代机执行失败")

    async def cancel(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, message="Human proxy console ready")


def create_plugin(
    console_state: OperatorConsoleState | None = None,
    timeout_s: float = 180.0,
    enabled: bool = True,
) -> HumanProxyCapability:
    return HumanProxyCapability(
        console_state=console_state,
        timeout_s=timeout_s,
        enabled=enabled,
    )
