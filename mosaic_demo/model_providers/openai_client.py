from __future__ import annotations

"""
OpenAI API 异步客户端

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


class OpenAIClientError(Exception):
    """OpenAI 客户端异常基类"""
    pass


class OpenAIClient:
    """OpenAI API 异步客户端

    支持：
    - httpx 异步 HTTP 调用
    - 指数退避重试（最多 max_retries 次）
    - 从 YAML 配置读取 API 参数，从环境变量读取 API 密钥
    """

    def __init__(
        self,
        model: str = "gpt-4",
        api_base: str = "https://api.openai.com/v1",
        temperature: float = 0.1,
        timeout: int = 30,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        config: Optional[dict[str, Any]] = None,
    ):
        """初始化 OpenAI 客户端

        可通过关键字参数逐个传入，也可通过 config 字典一次性传入。
        config 字典中的值会覆盖默认值，但显式传入的关键字参数优先级最高。

        Args:
            model: 模型名称
            api_base: API 基础 URL
            temperature: 生成温度
            timeout: 请求超时秒数
            max_retries: 最大重试次数
            backoff_base: 指数退避基数
            config: 可选的配置字典，键与上述参数同名
        """
        # 如果提供了 config 字典，用它填充默认值
        if config:
            model = config.get("model", model)
            api_base = config.get("api_base", api_base)
            temperature = config.get("temperature", temperature)
            timeout = config.get("timeout", timeout)
            max_retries = config.get("max_retries", max_retries)
            backoff_base = config.get("backoff_base", backoff_base)

        self.model = model
        self.api_base = api_base.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

        # 从环境变量读取 API 密钥，禁止硬编码
        self.api_key = os.environ.get("OPENAI_API_KEY", "")

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        functions: Optional[list[dict]] = None,
        **kwargs: Any,
    ) -> dict:
        """调用 ChatCompletion API

        构建请求 payload，使用 httpx 异步发送，失败时指数退避重试。

        Args:
            messages: 消息列表
            functions: 可选的 Function Calling 函数定义列表
            **kwargs: 其他传递给 API 的参数

        Returns:
            API 响应的 JSON 字典

        Raises:
            OpenAIClientError: 重试耗尽后仍然失败
        """
        # 构建请求 payload
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if functions:
            payload["functions"] = functions
        # 合并额外参数
        payload.update(kwargs)

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url, json=payload, headers=headers
                    )
                    response.raise_for_status()
                    return response.json()
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                # 最后一次尝试不需要等待
                if attempt < self.max_retries - 1:
                    wait_time = self.backoff_base ** attempt
                    logger.warning(
                        "OpenAI API 调用失败（第 %d/%d 次），%s 秒后重试: %s",
                        attempt + 1,
                        self.max_retries,
                        wait_time,
                        exc,
                    )
                    await asyncio.sleep(wait_time)

        # 重试耗尽，抛出异常
        raise OpenAIClientError(
            f"OpenAI API 调用失败，已重试 {self.max_retries} 次: {last_error}"
        ) from last_error
