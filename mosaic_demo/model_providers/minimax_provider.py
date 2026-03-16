from __future__ import annotations

"""
MiniMaxProvider — 基于 MiniMax Anthropic API 的 ModelProvider 实现

使用 Anthropic SDK 格式的 Tool Use 解析用户意图，
将响应解析为 TaskResult。
支持多轮 Function Call 对话（完整回传 response.content 保持思维链连续性）。
"""

import json
import logging
from typing import Any, Optional

from mosaic_demo.interfaces_abstract.model_provider import ModelProvider
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import TaskContext, TaskResult
from mosaic_demo.model_providers.minimax_client import MiniMaxClient, MiniMaxClientError

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是一个机器人任务调度助手。根据用户的自然语言指令，"
    "调用合适的工具来执行对应的机器人能力。"
    "请始终通过 tool_use 返回结构化结果。"
)

# 多轮 tool call 最大循环次数，防止无限循环
_MAX_TOOL_CALL_ROUNDS = 5


class MiniMaxProvider(ModelProvider):
    """基于 MiniMax Anthropic API 的 ModelProvider 实现"""

    def __init__(self, client: MiniMaxClient, registry: CapabilityRegistry):
        self._client = client
        self._registry = registry

    async def parse_task(self, context: TaskContext) -> TaskResult:
        """通过 Anthropic Tool Use 解析自然语言指令

        支持多轮 tool call：当模型返回 tool_use 且 stop_reason 为 "tool_use" 时，
        将完整的 response.content 回传到对话历史，附加 tool_result 后继续调用，
        直到模型返回最终结果或达到最大轮次。
        """
        try:
            tools = self._build_tool_definitions()

            messages: list[dict[str, Any]] = [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": context.raw_input}],
                },
            ]

            # 首次调用
            logger.info("📡 正在调用 MiniMax API (model=%s)...", self._client.model)
            response = await self._client.chat_completion(
                messages=messages,
                system=_SYSTEM_PROMPT,
                tools=tools if tools else None,
            )

            # 打印 LLM 返回的所有 content blocks
            logger.info("📨 LLM 响应 (stop_reason=%s, blocks=%d):",
                        response.stop_reason, len(response.content))
            for i, block in enumerate(response.content):
                if block.type == "thinking":
                    logger.info("  [%d] 🧠 Thinking:\n%s", i, block.thinking)
                elif block.type == "text":
                    logger.info("  [%d] 💬 Text: %s", i, block.text)
                elif block.type == "tool_use":
                    logger.info("  [%d] 🔧 Tool Use: name=%s, input=%s",
                                i, block.name, block.input)

            # 提取 tool_use — 只要有就直接返回（Demo 模式下不做真正的多轮执行）
            tool_use_block = self._extract_first_tool_use(response)
            if tool_use_block:
                logger.info("✅ 意图解析成功: intent=%s, params=%s",
                            tool_use_block.name, tool_use_block.input)
                return self._tool_use_to_result(tool_use_block)

            # 没有 tool_use，解析文本响应
            logger.info("⚠️  LLM 未返回 tool_use，回退到文本解析")
            return self._parse_final_response(response)

        except MiniMaxClientError as exc:
            logger.error("MiniMax LLM 调用失败: %s", exc)
            return TaskResult(
                intent="",
                params={"error": f"MiniMax LLM 调用失败: {exc}"},
                confidence=0.0,
            )

    def get_supported_intents(self) -> list[str]:
        intents: list[str] = []
        for cap_info in self._registry.list_capabilities():
            intents.extend(cap_info.supported_intents)
        return intents

    def _build_tool_definitions(self) -> list[dict[str, Any]]:
        """生成 Anthropic 格式的工具定义"""
        tools: list[dict[str, Any]] = []
        for cap_info in self._registry.list_capabilities():
            for intent in cap_info.supported_intents:
                tool_def = {
                    "name": intent,
                    "description": cap_info.description or f"执行 {intent} 操作",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "description": "目标参数",
                            }
                        },
                        "required": [],
                    },
                }
                tools.append(tool_def)
        return tools

    def _extract_first_tool_use(self, response: Any) -> Optional[Any]:
        """从响应中提取第一个 tool_use block"""
        for block in response.content:
            if block.type == "tool_use":
                return block
        return None

    def _tool_use_to_result(self, tool_use_block: Any) -> TaskResult:
        """将 tool_use block 转换为 TaskResult"""
        return TaskResult(
            intent=tool_use_block.name,
            params=tool_use_block.input if isinstance(tool_use_block.input, dict) else {},
            confidence=1.0,
            raw_response=json.dumps(
                {"name": tool_use_block.name, "input": tool_use_block.input},
                ensure_ascii=False,
            ),
        )

    def _simulate_tool_result(self, tool_use_block: Any) -> str:
        """模拟工具执行结果（demo 用途）

        在实际系统中，这里应该调用真正的 capability 执行工具并返回结果。
        """
        return json.dumps(
            {"status": "success", "tool": tool_use_block.name, "message": "工具调用已确认"},
            ensure_ascii=False,
        )

    def _parse_final_response(self, response: Any) -> TaskResult:
        """解析最终响应（可能包含 tool_use 或纯文本）"""
        # 优先提取 tool_use
        tool_use_block = self._extract_first_tool_use(response)
        if tool_use_block:
            return self._tool_use_to_result(tool_use_block)

        # 提取文本
        text_parts = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                logger.debug("Thinking: %s", block.thinking)

        content = "\n".join(text_parts) if text_parts else ""
        return TaskResult(
            intent="",
            params={"error": "LLM 未返回 tool_use"},
            confidence=0.0,
            raw_response=content,
        )
