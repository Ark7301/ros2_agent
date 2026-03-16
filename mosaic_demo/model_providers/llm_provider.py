from __future__ import annotations

"""
LLMProvider — 基于美的 AIMP Claude API 的 ModelProvider 实现

从 CapabilityRegistry 动态获取意图列表，自动生成工具定义，
将 Tool Use 响应解析为 TaskResult。
"""

import json
import logging
from typing import Any

from mosaic_demo.interfaces_abstract.model_provider import ModelProvider
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import TaskContext, TaskResult
from mosaic_demo.model_providers.midea_client import MideaClient, MideaClientError

logger = logging.getLogger(__name__)

# 系统提示词，引导 LLM 使用 Tool Use 解析用户意图
_SYSTEM_PROMPT = (
    "你是一个机器人任务调度助手。根据用户的自然语言指令，"
    "调用合适的工具来执行对应的机器人能力。"
    "请始终通过 tool_use 返回结构化结果。"
)


class LLMProvider(ModelProvider):
    """基于美的 AIMP Claude API 的 ModelProvider 实现

    从 CapabilityRegistry 动态获取意图列表，自动生成工具定义，
    将 Tool Use 响应解析为 TaskResult。
    """

    def __init__(self, client: MideaClient, registry: CapabilityRegistry):
        """初始化 LLMProvider

        Args:
            client: 美的 AIMP API 异步客户端
            registry: 能力注册中心，用于动态获取意图列表
        """
        self._client = client
        self._registry = registry

    async def parse_task(self, context: TaskContext) -> TaskResult:
        """通过 Tool Use 解析自然语言指令

        构建工具定义和消息列表，调用美的 AIMP Claude API，
        将响应解析为 TaskResult。

        Args:
            context: 任务上下文，包含用户原始输入

        Returns:
            解析后的 TaskResult
        """
        try:
            # 从 registry 动态生成工具定义
            tools = self._build_tool_definitions()

            # 构建消息列表（美的 AIMP 格式）
            messages = [
                {
                    "role": "user",
                    "content": [{"text": context.raw_input}],
                },
            ]

            # 系统提示词
            system = [{"text": _SYSTEM_PROMPT}]

            # 调用美的 AIMP Claude API
            response = await self._client.chat_completion(
                messages=messages,
                system=system,
                tools=tools if tools else None,
            )

            # 解析响应为 TaskResult
            return self._parse_response(response)

        except MideaClientError as exc:
            logger.error("LLM 调用失败: %s", exc)
            return TaskResult(
                intent="",
                params={"error": f"LLM 调用失败: {exc}"},
                confidence=0.0,
            )

    def get_supported_intents(self) -> list[str]:
        """从 registry 获取所有支持的意图列表"""
        intents: list[str] = []
        for cap_info in self._registry.list_capabilities():
            intents.extend(cap_info.supported_intents)
        return intents

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        """从 Registry 动态生成美的 AIMP toolConfig 格式的工具定义

        Returns:
            toolConfig.tools 格式的工具定义列表
        """
        tools: list[dict[str, Any]] = []
        for cap_info in self._registry.list_capabilities():
            for intent in cap_info.supported_intents:
                tool_def: dict[str, Any] = {
                    "toolSpec": {
                        "name": intent,
                        "description": cap_info.description or f"执行 {intent} 操作",
                        "inputSchema": {
                            "json": {
                                "type": "object",
                                "properties": {
                                    "target": {
                                        "type": "string",
                                        "description": "目标参数",
                                    }
                                },
                                "required": [],
                            }
                        },
                    }
                }
                tools.append(tool_def)
        return tools

    def _parse_response(self, response: dict) -> TaskResult:
        """从美的 AIMP API 响应中提取 tool_use 并解析为 TaskResult

        响应格式示例：
        {
            "output": {
                "message": {
                    "content": [
                        {"text": "..."},
                        {"toolUse": {"name": "...", "input": {...}, "toolUseId": "..."}}
                    ],
                    "role": "assistant"
                }
            },
            "stopReason": "tool_use" | "end_turn",
            "usage": {...}
        }

        Args:
            response: 美的 AIMP API 返回的 JSON 字典

        Returns:
            解析后的 TaskResult
        """
        try:
            message = response["output"]["message"]
            content_blocks = message.get("content", [])

            # 遍历 content blocks，查找 toolUse
            for block in content_blocks:
                if "toolUse" in block:
                    tool_use = block["toolUse"]
                    intent = tool_use["name"]
                    params = tool_use.get("input", {})

                    return TaskResult(
                        intent=intent,
                        params=params,
                        confidence=1.0,
                        raw_response=json.dumps(tool_use, ensure_ascii=False),
                    )

            # 没有 toolUse，提取纯文本响应
            text_parts = []
            for block in content_blocks:
                if "text" in block:
                    text_parts.append(block["text"])

            content = "\n".join(text_parts) if text_parts else ""
            return TaskResult(
                intent="",
                params={"error": "LLM 未返回 tool_use"},
                confidence=0.0,
                raw_response=content,
            )

        except (KeyError, IndexError, TypeError) as exc:
            logger.error("解析 LLM 响应失败: %s", exc)
            return TaskResult(
                intent="",
                params={"error": f"解析 LLM 响应失败: {exc}"},
                confidence=0.0,
                raw_response=str(response),
            )
