"""
LLMProvider — 基于 OpenAI Function Calling 的 ModelProvider 实现

从 CapabilityRegistry 动态获取意图列表，自动生成函数定义，
将 Function Calling 响应解析为 TaskResult。
"""

import json
import logging
from typing import Any

from mosaic_demo.interfaces_abstract.model_provider import ModelProvider
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import TaskContext, TaskResult
from mosaic_demo.model_providers.openai_client import OpenAIClient, OpenAIClientError

logger = logging.getLogger(__name__)

# 系统提示词，引导 LLM 使用 Function Calling 解析用户意图
_SYSTEM_PROMPT = (
    "你是一个机器人任务调度助手。根据用户的自然语言指令，"
    "调用合适的函数来执行对应的机器人能力。"
    "请始终通过 function_call 返回结构化结果。"
)


class LLMProvider(ModelProvider):
    """基于 OpenAI Function Calling 的 ModelProvider 实现

    从 CapabilityRegistry 动态获取意图列表，自动生成函数定义，
    将 Function Calling 响应解析为 TaskResult。
    """

    def __init__(self, client: OpenAIClient, registry: CapabilityRegistry):
        """初始化 LLMProvider

        Args:
            client: OpenAI API 异步客户端
            registry: 能力注册中心，用于动态获取意图列表
        """
        self._client = client
        self._registry = registry

    async def parse_task(self, context: TaskContext) -> TaskResult:
        """通过 Function Calling 解析自然语言指令

        构建 function 定义和消息列表，调用 OpenAI API，
        将响应解析为 TaskResult。

        Args:
            context: 任务上下文，包含用户原始输入

        Returns:
            解析后的 TaskResult
        """
        try:
            # 从 registry 动态生成 Function Calling schema
            functions = self._build_function_definitions()

            # 构建消息列表
            messages = [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": context.raw_input},
            ]

            # 调用 OpenAI API
            response = await self._client.chat_completion(
                messages=messages,
                functions=functions,
            )

            # 解析响应为 TaskResult
            return self._parse_response(response)

        except OpenAIClientError as exc:
            # 重试耗尽后返回包含 "LLM 调用失败" 信息的 TaskResult
            logger.error("LLM 调用失败: %s", exc)
            return TaskResult(
                intent="",
                params={"error": f"LLM 调用失败: {exc}"},
                confidence=0.0,
            )

    def get_supported_intents(self) -> list[str]:
        """从 registry 获取所有支持的意图列表

        Returns:
            所有已注册 Capability 支持的意图名称列表
        """
        intents: list[str] = []
        for cap_info in self._registry.list_capabilities():
            intents.extend(cap_info.supported_intents)
        return intents

    def _build_function_definitions(self) -> list[dict[str, Any]]:
        """从 Registry 动态生成 Function Calling schema

        遍历所有已注册的 Capability，为每个意图生成一个 function 定义。

        Returns:
            Function Calling 函数定义列表
        """
        functions: list[dict[str, Any]] = []
        for cap_info in self._registry.list_capabilities():
            for intent in cap_info.supported_intents:
                func_def: dict[str, Any] = {
                    "name": intent,
                    "description": cap_info.description or f"执行 {intent} 操作",
                    "parameters": {
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
                functions.append(func_def)
        return functions

    def _parse_response(self, response: dict) -> TaskResult:
        """从 API 响应中提取 function_call 并解析为 TaskResult

        Args:
            response: OpenAI API 返回的 JSON 字典

        Returns:
            解析后的 TaskResult
        """
        try:
            # 从响应中提取 choices[0].message
            message = response["choices"][0]["message"]

            # 提取 function_call
            function_call = message.get("function_call")
            if not function_call:
                # 没有 function_call，返回纯文本响应
                content = message.get("content", "")
                return TaskResult(
                    intent="",
                    params={"error": "LLM 未返回 function_call"},
                    confidence=0.0,
                    raw_response=content,
                )

            # 解析 function_call 的 name 和 arguments
            intent = function_call["name"]
            arguments_str = function_call.get("arguments", "{}")

            # 将 arguments JSON 字符串解析为 dict
            try:
                params = json.loads(arguments_str)
            except (json.JSONDecodeError, TypeError):
                params = {}

            return TaskResult(
                intent=intent,
                params=params,
                confidence=1.0,
                raw_response=json.dumps(function_call, ensure_ascii=False),
            )

        except (KeyError, IndexError, TypeError) as exc:
            # 响应格式异常
            logger.error("解析 LLM 响应失败: %s", exc)
            return TaskResult(
                intent="",
                params={"error": f"解析 LLM 响应失败: {exc}"},
                confidence=0.0,
                raw_response=str(response),
            )
