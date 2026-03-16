from __future__ import annotations

"""
MiniMax Anthropic API 异步客户端

- 使用 Anthropic SDK 对接 MiniMax API（Anthropic 兼容格式）
- 支持 Tool Use / Function Calling
- 支持 Thinking（推理链）
- 指数退避重试
"""

import asyncio
import os
import logging
from typing import Any, Optional

import anthropic

logger = logging.getLogger(__name__)


class MiniMaxClientError(Exception):
    """MiniMax 客户端异常基类"""
    pass


class MiniMaxClient:
    """MiniMax Anthropic API 客户端

    通过 Anthropic SDK 调用 MiniMax API，支持：
    - Tool Use（工具调用）
    - Thinking（推理链）
    - 指数退避重试
    """

    def __init__(
        self,
        model: str = "MiniMax-M2.5",
        api_base: str = "https://api.minimaxi.com/anthropic",
        temperature: float = 1.0,
        max_tokens: int = 4096,
        timeout: int = 60,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        enable_thinking: bool = False,
        thinking_budget: int = 8000,
        config: Optional[dict[str, Any]] = None,
    ):
        if config:
            model = config.get("model", model)
            api_base = config.get("api_base", api_base)
            temperature = config.get("temperature", temperature)
            max_tokens = config.get("max_tokens", max_tokens)
            timeout = config.get("timeout", timeout)
            max_retries = config.get("max_retries", max_retries)
            backoff_base = config.get("backoff_base", backoff_base)
            enable_thinking = config.get("enable_thinking", enable_thinking)
            thinking_budget = config.get("thinking_budget", thinking_budget)

        self.model = model
        self.api_base = api_base.rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

        # 从环境变量读取 API 密钥
        api_key = os.environ.get("MINIMAX_API_KEY", "")

        self._client = anthropic.Anthropic(
            api_key=api_key,
            base_url=self.api_base,
        )

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        system: Optional[str] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> anthropic.types.Message:
        """调用 MiniMax API（Anthropic 兼容格式）

        Args:
            messages: Anthropic 格式消息列表
            system: 系统提示词（字符串）
            tools: Anthropic 格式工具定义列表
            **kwargs: 其他传递给 API 的参数

        Returns:
            Anthropic Message 对象

        Raises:
            MiniMaxClientError: 重试耗尽后仍然失败
        """
        create_params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": messages,
        }

        if system:
            create_params["system"] = system

        if tools:
            create_params["tools"] = tools

        # 非思考模式下传 temperature
        if not self.enable_thinking:
            create_params["temperature"] = self.temperature

        # 启用思考模式
        if self.enable_thinking:
            create_params["thinking"] = {
                "type": "enabled",
                "budget_tokens": self.thinking_budget,
            }

        create_params.update(kwargs)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                # Anthropic SDK 是同步的，用 asyncio 包装
                response = await asyncio.to_thread(
                    self._client.messages.create, **create_params
                )
                return response
            except (anthropic.APIError, anthropic.APIConnectionError) as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_base ** attempt
                    logger.warning(
                        "MiniMax API 调用失败（第 %d/%d 次），%s 秒后重试: %s",
                        attempt + 1,
                        self.max_retries,
                        wait_time,
                        exc,
                    )
                    await asyncio.sleep(wait_time)

        raise MiniMaxClientError(
            f"MiniMax API 调用失败，已重试 {self.max_retries} 次: {last_error}"
        ) from last_error
