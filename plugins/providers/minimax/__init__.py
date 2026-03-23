# MiniMax Provider 插件
# 通过 httpx 异步调用 MiniMax API，实现 ProviderPlugin Protocol
# API 密钥从环境变量 MINIMAX_API_KEY 读取

from __future__ import annotations

import os
from typing import Any, AsyncIterator

try:
    import httpx
except ImportError:
    httpx = None  # type: ignore[assignment]

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ProviderConfig,
    ProviderResponse,
)

# 默认配置
_DEFAULT_API_BASE = "https://api.minimax.chat/v1"
_DEFAULT_MODEL = "MiniMax-Text-01"
_CHAT_ENDPOINT = "/text/chatcompletion_v2"


def _require_httpx() -> None:
    """检查 httpx 是否可用，不可用时抛出明确错误"""
    if httpx is None:
        raise ImportError(
            "MiniMax Provider 需要 httpx 库。"
            "请运行 `pip install httpx` 安装。"
        )


class MiniMaxProvider:
    """MiniMax LLM Provider 插件

    通过 httpx.AsyncClient 异步调用 MiniMax API，
    支持同步聊天（chat）和流式输出（stream）。
    API 密钥从环境变量 MINIMAX_API_KEY 读取，
    API 地址从 MINIMAX_API_BASE 读取（可选，有默认值）。
    """

    def __init__(self) -> None:
        _require_httpx()

        self.meta = PluginMeta(
            id="minimax",
            name="MiniMax Provider",
            version="0.1.0",
            description="MiniMax LLM Provider，支持 chat 和 stream 调用",
            kind="provider",
            author="MOSAIC",
        )

        # 从环境变量读取配置
        self._api_key: str = os.environ.get("MINIMAX_API_KEY", "")
        self._api_base: str = os.environ.get("MINIMAX_API_BASE", _DEFAULT_API_BASE)

        # 延迟创建 httpx 客户端（在首次请求时初始化）
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 异步客户端"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._api_base,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0),
            )
        return self._client

    def _build_request_body(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        config: ProviderConfig,
        stream: bool = False,
    ) -> dict[str, Any]:
        """构建 API 请求体"""
        model = config.model or _DEFAULT_MODEL
        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "stream": stream,
        }
        # 附加工具定义
        if tools:
            body["tools"] = tools
        # 合并额外参数
        if config.extra:
            body.update(config.extra)
        return body

    def _parse_response(self, data: dict[str, Any]) -> ProviderResponse:
        """解析 API 响应为 ProviderResponse"""
        # 提取第一个 choice
        choices = data.get("choices", [])
        if not choices:
            return ProviderResponse(
                content="",
                usage=data.get("usage", {}),
                raw_content=data,
            )

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "") or ""

        # 解析工具调用
        tool_calls: list[dict[str, Any]] = []
        raw_tool_calls = message.get("tool_calls", [])
        for tc in raw_tool_calls:
            tool_calls.append({
                "id": tc.get("id", ""),
                "name": tc.get("function", {}).get("name", ""),
                "arguments": tc.get("function", {}).get("arguments", ""),
            })

        return ProviderResponse(
            content=content,
            tool_calls=tool_calls,
            usage=data.get("usage", {}),
            raw_content=data,
        )

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        config: ProviderConfig,
    ) -> ProviderResponse:
        """同步聊天调用 — POST /text/chatcompletion_v2

        发送消息列表和工具定义到 MiniMax API，
        返回解析后的 ProviderResponse。
        """
        client = self._get_client()
        body = self._build_request_body(messages, tools, config, stream=False)

        response = await client.post(_CHAT_ENDPOINT, json=body)
        response.raise_for_status()

        data = response.json()
        return self._parse_response(data)

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        config: ProviderConfig,
    ) -> AsyncIterator:
        """流式聊天调用 — POST /text/chatcompletion_v2 (stream=True)

        以 SSE 方式逐块返回响应内容，
        每个 chunk 解析为 ProviderResponse 并 yield。
        """
        client = self._get_client()
        body = self._build_request_body(messages, tools, config, stream=True)

        async with client.stream("POST", _CHAT_ENDPOINT, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                # SSE 格式：以 "data: " 开头
                if not line.startswith("data: "):
                    continue
                payload = line[6:]  # 去掉 "data: " 前缀
                # 流结束标记
                if payload.strip() == "[DONE]":
                    break
                # 解析 JSON chunk
                import json
                try:
                    chunk_data = json.loads(payload)
                    yield self._parse_response(chunk_data)
                except (json.JSONDecodeError, KeyError):
                    # 跳过无法解析的 chunk
                    continue

    async def validate_auth(self) -> bool:
        """验证 API 密钥是否有效

        发送一个最小请求来检测认证状态，
        成功返回 True，失败返回 False。
        """
        if not self._api_key:
            return False

        try:
            client = self._get_client()
            # 发送最小请求验证密钥
            body = {
                "model": _DEFAULT_MODEL,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }
            response = await client.post(_CHAT_ENDPOINT, json=body)
            return response.status_code == 200
        except Exception:
            return False


def create_plugin() -> MiniMaxProvider:
    """工厂函数 — 返回 MiniMaxProvider 实例"""
    return MiniMaxProvider()
