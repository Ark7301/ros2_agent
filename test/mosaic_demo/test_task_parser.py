"""
TaskParser 属性测试 — 空意图拒绝

Property 4: 对于任意 intent 为空字符串的 TaskResult，
TaskParser 的校验逻辑应拒绝该结果并返回错误。

Validates: Requirements 3.2, 3.3
"""

import pytest
import pytest_asyncio
from hypothesis import given, strategies as st

from mosaic_demo.interfaces_abstract.model_provider import ModelProvider
from mosaic_demo.interfaces_abstract.data_models import TaskContext, TaskResult


class EmptyIntentModelProvider(ModelProvider):
    """Mock ModelProvider — 始终返回 intent 为空的 TaskResult"""

    def __init__(self, empty_intent: str):
        """初始化，接收一个空意图字符串（空字符串或纯空白）"""
        self._empty_intent = empty_intent

    async def parse_task(self, context: TaskContext) -> TaskResult:
        """返回 intent 为空的解析结果"""
        return TaskResult(
            intent=self._empty_intent,
            params={"raw": context.raw_input},
            confidence=0.5,
        )

    def get_supported_intents(self) -> list[str]:
        return []


# 生成空意图策略：空字符串或纯空白字符串
empty_intent_strategy = st.one_of(
    st.just(""),
    st.text(alphabet=" \t\n\r", min_size=1, max_size=20),
)


@pytest.mark.asyncio
class TestTaskParserEmptyIntentRejection:
    """**Validates: Requirements 3.2, 3.3**"""

    @given(
        empty_intent=empty_intent_strategy,
        raw_input=st.text(min_size=1, max_size=100),
    )
    async def test_property4_empty_intent_rejected(self, empty_intent: str, raw_input: str):
        """Property 4: TaskParser 验证 — 空意图拒绝

        对于任意 intent 为空字符串或纯空白字符串的 TaskResult，
        TaskParser.parse() 应返回 intent 为 "error" 的结果。

        **Validates: Requirements 3.2, 3.3**
        """
        from mosaic_demo.agent_core.task_parser import TaskParser

        # 构造返回空意图的 Mock Provider
        provider = EmptyIntentModelProvider(empty_intent)
        parser = TaskParser(model_provider=provider)

        context = TaskContext(raw_input=raw_input)
        result = await parser.parse(context)

        # 校验：空意图应被拒绝，返回 error
        assert result.intent == "error", (
            f"空意图 '{empty_intent!r}' 应被拒绝，但返回了 intent='{result.intent}'"
        )
        assert result.confidence == 0.0, "错误结果的 confidence 应为 0.0"
        assert "message" in result.params, "错误结果应包含 message 字段"
