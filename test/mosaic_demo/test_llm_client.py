"""
OpenAIClient 属性测试

使用 hypothesis 验证 OpenAIClient 的重试行为。
"""

import pytest
import httpx
from hypothesis import given, strategies as st, settings

from mosaic_demo.model_providers.openai_client import OpenAIClient, OpenAIClientError

# 保存原始的 AsyncClient 类，避免 monkeypatch 后丢失引用
_OriginalAsyncClient = httpx.AsyncClient


class TestOpenAIClientRetryLimit:
    """
    Property 17: OpenAIClient 重试次数上限

    **Validates: Requirements 9.2, 9.3**

    对于任意持续失败的 API 调用，OpenAIClient 的重试次数不应超过配置的最大重试次数。
    """

    @given(max_retries=st.integers(min_value=1, max_value=5))
    @settings(max_examples=30, deadline=None)
    @pytest.mark.asyncio
    async def test_retry_count_equals_max_retries(self, max_retries: int):
        """
        **Validates: Requirements 9.2, 9.3**

        对于任意 max_retries (1-5)，当 API 持续失败时，
        实际 HTTP 调用次数应恰好等于 max_retries，
        且最终抛出 OpenAIClientError。
        """
        # 记录实际调用次数
        call_count = 0

        # 创建始终返回 500 错误的 mock transport
        async def mock_handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                status_code=500,
                json={"error": {"message": "Internal Server Error"}},
            )

        transport = httpx.MockTransport(mock_handler)

        # 创建客户端，backoff_base 设为极小值以加速测试
        client = OpenAIClient(
            model="gpt-4",
            api_base="https://api.openai.com/v1",
            max_retries=max_retries,
            backoff_base=0.001,
        )

        # 替换 httpx.AsyncClient，使其始终使用 mock transport
        original_init = _OriginalAsyncClient.__init__

        def patched_init(self_client, *args, **kwargs):
            kwargs.pop("timeout", None)
            kwargs["transport"] = transport
            original_init(self_client, *args, **kwargs)

        httpx.AsyncClient.__init__ = patched_init
        try:
            # 调用应抛出 OpenAIClientError
            with pytest.raises(OpenAIClientError):
                await client.chat_completion(
                    messages=[{"role": "user", "content": "test"}]
                )
        finally:
            # 恢复原始 __init__
            httpx.AsyncClient.__init__ = original_init

        # 验证：实际调用次数恰好等于 max_retries
        assert call_count == max_retries, (
            f"期望调用 {max_retries} 次，实际调用 {call_count} 次"
        )


import json
from unittest.mock import MagicMock

from mosaic_demo.model_providers.llm_provider import LLMProvider
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry


# 用于生成合法 JSON 值的策略（不含 NaN/Inf 等非法 JSON 值）
_json_values = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-1000, max_value=1000),
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),
            min_size=0,
            max_size=20,
        ),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=3),
        st.dictionaries(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("L", "N"),
                    min_codepoint=ord("a"),
                    max_codepoint=ord("z"),
                ),
                min_size=1,
                max_size=8,
            ),
            children,
            max_size=3,
        ),
    ),
    max_leaves=10,
)

# 生成合法的 function_call 参数字典
_params_strategy = st.dictionaries(
    st.text(
        alphabet=st.characters(
            whitelist_categories=("L", "N"),
            min_codepoint=ord("a"),
            max_codepoint=ord("z"),
        ),
        min_size=1,
        max_size=10,
    ),
    _json_values,
    min_size=0,
    max_size=5,
)

# 生成非空的 function name（仅含字母和下划线，模拟真实意图名）
_intent_name_strategy = st.from_regex(r"[a-z][a-z_]{0,19}", fullmatch=True)


class TestFunctionCallingResponseParsing:
    """
    Property 19: Function Calling 响应解析

    **Validates: Requirements 3.5**

    对于任意合法的 OpenAI Function Calling 响应（包含 function_call.name 和
    function_call.arguments），LLMProvider 应将其正确解析为 TaskResult，
    其中 intent 等于 function_call.name，params 等于解析后的 arguments 字典。
    """

    @given(
        intent_name=_intent_name_strategy,
        params=_params_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_parse_response_extracts_intent_and_params(
        self, intent_name: str, params: dict
    ):
        """
        **Validates: Requirements 3.5**

        对于任意合法的 function_call.name 和 function_call.arguments，
        _parse_response 应正确解析为 TaskResult，
        intent 等于 name，params 等于 arguments 解析后的字典。
        """
        # 构造 Mock 依赖
        mock_client = MagicMock()
        registry = CapabilityRegistry()
        provider = LLMProvider(client=mock_client, registry=registry)

        # 构造合法的 OpenAI API 响应
        response = {
            "choices": [
                {
                    "message": {
                        "function_call": {
                            "name": intent_name,
                            "arguments": json.dumps(params, ensure_ascii=False),
                        }
                    }
                }
            ]
        }

        # 调用 _parse_response
        result = provider._parse_response(response)

        # 验证 intent 等于 function_call.name
        assert result.intent == intent_name, (
            f"期望 intent={intent_name!r}，实际 intent={result.intent!r}"
        )

        # 验证 params 等于解析后的 arguments 字典
        assert result.params == params, (
            f"期望 params={params!r}，实际 params={result.params!r}"
        )

        # 验证 confidence 为 1.0（成功解析）
        assert result.confidence == 1.0
