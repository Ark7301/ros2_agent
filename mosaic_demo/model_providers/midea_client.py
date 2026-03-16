from __future__ import annotations

"""
美的 AIMP Claude API 异步客户端

- 对接美的 AIMP 平台的 Claude API（非流式）
- 使用 httpx 异步 HTTP 调用
- 指数退避重试（最多 3 次）
- API 参数通过 YAML 配置，密钥通过环境变量注入
"""

import asyncio
import os
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class MideaClientError(Exception):
    """美的 AIMP 客户端异常基类"""
    pass


class MideaClient:
    """美的 AIMP Claude API 异步客户端

    支持：
    - httpx 异步 HTTP 调用
    - 指数退避重试
    - 从 YAML 配置读取 API 参数，从环境变量读取 API 密钥
    """

    def __init__(
        self,
        model: str = "anthropic.claude-opus-4-20250514-v1:0",
        api_base: str = "https://aimpapi.midea.com/t-aigc/mip-chat-app/claude/official/standard/sync/v3/chat/completions",
        aigc_user: str = "",
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: int = 60,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        enable_thinking: bool = False,
        thinking_budget: int = 8000,
        config: Optional[dict[str, Any]] = None,
    ):
        """初始化美的 AIMP 客户端

        Args:
            model: 模型 ID
            api_base: API 完整 URL
            aigc_user: AIGC 用户账号
            temperature: 生成温度
            max_tokens: 最大输出 token 数
            timeout: 请求超时秒数
            max_retries: 最大重试次数
            backoff_base: 指数退避基数
            enable_thinking: 是否启用思考模式
            thinking_budget: 思考 token 预算
            config: 可选的配置字典
        """
        if config:
            model = config.get("model", model)
            api_base = config.get("api_base", api_base)
            aigc_user = config.get("aigc_user", aigc_user)
            temperature = config.get("temperature", temperature)
            max_tokens = config.get("max_tokens", max_tokens)
            timeout = config.get("timeout", timeout)
            max_retries = config.get("max_retries", max_retries)
            backoff_base = config.get("backoff_base", backoff_base)
            enable_thinking = config.get("enable_thinking", enable_thinking)
            thinking_budget = config.get("thinking_budget", thinking_budget)

        self.model = model
        self.api_base = api_base
        self.aigc_user = aigc_user
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

        # 从环境变量读取 API 密钥，优先环境变量
        self.api_key = os.environ.get("MIDEA_API_KEY", "")

    async def chat_completion(
        self,
        messages: list[dict[str, Any]],
        system: Optional[list[dict[str, str]]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> dict:
        """调用美的 AIMP Claude API（非流式）

        Args:
            messages: 消息列表，格式为 [{"role": "user", "content": [{"text": "..."}]}]
            system: 系统提示词列表，格式为 [{"text": "..."}]
            tools: 工具定义列表（toolConfig 格式）
            **kwargs: 其他传递给 API 的参数

        Returns:
            API 响应的 JSON 字典

        Raises:
            MideaClientError: 重试耗尽后仍然失败
        """
        # 构建请求 payload
        payload: dict[str, Any] = {
            "modelId": self.model,
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
            },
        }

        # 非思考模式下才传 temperature
        if not self.enable_thinking:
            payload["inferenceConfig"]["temperature"] = self.temperature

        if system:
            payload["system"] = system

        if tools:
            payload["toolConfig"] = {"tools": tools}

        # 启用思考模式
        if self.enable_thinking:
            payload["additionalModelRequestFields"] = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": self.thinking_budget,
                }
            }

        payload.update(kwargs)

        headers = {
            "Content-Type": "application/json",
            "Authorization": self.api_key,
            "Aimp-Biz-Id": self.model,
            "AIGC-USER": self.aigc_user,
        }

        # 调试：打印实际发送的 headers（隐藏 key 中间部分）
        masked_key = self.api_key[:8] + "****" + self.api_key[-4:] if len(self.api_key) > 12 else self.api_key
        logger.info(
            "请求 headers: Authorization=Bearer %s, Aimp-Biz-Id=%s, AIGC-USER=%s",
            masked_key, self.model, self.aigc_user,
        )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        self.api_base, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_base ** attempt
                    logger.warning(
                        "美的 AIMP API 调用失败（第 %d/%d 次），%s 秒后重试: %s",
                        attempt + 1,
                        self.max_retries,
                        wait_time,
                        exc,
                    )
                    await asyncio.sleep(wait_time)

        raise MideaClientError(
            f"美的 AIMP API 调用失败，已重试 {self.max_retries} 次: {last_error}"
        ) from last_error
