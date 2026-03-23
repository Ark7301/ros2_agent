"""属性测试 — TurnRunner ReAct 循环终止

属性 9: Turn ReAct 循环终止
对于任意 Turn 执行，ReAct 循环在以下条件之一满足时终止：
(a) Provider 返回无工具调用的响应
(b) 迭代次数达到 max_iterations
(c) 超时 turn_timeout_s

**Validates: Requirements 5.3, 5.5, 5.6, 5.7**
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from hypothesis import given, settings, strategies as st, assume

from mosaic.runtime.turn_runner import TurnRunner, TurnResult
from mosaic.plugin_sdk.types import (
    ProviderConfig,
    ProviderResponse,
    ExecutionContext,
    ExecutionResult,
    AssembleResult,
    PluginMeta,
)


# ── 辅助函数 ──

def run_async(coro):
    """在新的事件循环中运行协程，避免循环复用问题"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Mock 对象 ──

class MockSession:
    """模拟 Session 对象"""
    def __init__(self, session_id: str = "test-session-001", turn_count: int = 0):
        self.session_id = session_id
        self.turn_count = turn_count


class MockContextEngine:
    """模拟 ContextEnginePlugin — 返回空上下文，记录 ingest 调用"""
    def __init__(self):
        self.ingested: list[dict] = []

    async def assemble(self, session_id: str, token_budget: int) -> AssembleResult:
        return AssembleResult(messages=[], token_count=0)

    async def ingest(self, session_id: str, message: dict) -> None:
        self.ingested.append(message)

    async def compact(self, session_id: str, force: bool = False):
        pass


class MockHookManager:
    """模拟 HookManager — 记录钩子触发，不拦截"""
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    async def emit(self, point: str, context: dict) -> bool:
        self.emitted.append((point, context))
        return True


class MockCapabilityPlugin:
    """模拟 CapabilityPlugin — 返回固定工具定义和执行结果"""
    def __init__(self, tool_names: list[str]):
        self._tool_names = tool_names
        self.meta = PluginMeta(
            id="mock-cap", name="MockCap", version="1.0",
            description="测试用能力插件", kind="capability",
        )

    def get_supported_intents(self) -> list[str]:
        return self._tool_names

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [{"name": name, "description": f"工具 {name}"} for name in self._tool_names]

    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult:
        return ExecutionResult(success=True, data={"tool": intent})

    async def cancel(self) -> bool:
        return True


class MockProvider:
    """模拟 ProviderPlugin — 可配置每次调用返回的响应序列

    responses: 按顺序返回的 ProviderResponse 列表。
    当调用次数超过列表长度时，循环最后一个响应。
    """
    def __init__(self, responses: list[ProviderResponse]):
        self._responses = responses
        self._call_count = 0

    async def chat(self, messages, tools, config=None) -> ProviderResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]

    async def stream(self, messages, tools, config=None):
        raise NotImplementedError

    async def validate_auth(self) -> bool:
        return True


class SlowProvider:
    """模拟慢速 Provider — 每次调用都会 sleep，用于超时测试"""
    def __init__(self, delay: float):
        self._delay = delay

    async def chat(self, messages, tools, config=None) -> ProviderResponse:
        await asyncio.sleep(self._delay)
        return ProviderResponse(content="慢速响应", tool_calls=[])

    async def stream(self, messages, tools, config=None):
        raise NotImplementedError

    async def validate_auth(self) -> bool:
        return True


class AlwaysToolCallProvider:
    """模拟始终返回工具调用的 Provider — 用于测试 max_iterations 终止"""
    def __init__(self, tool_name: str = "test_tool"):
        self._tool_name = tool_name
        self.call_count = 0

    async def chat(self, messages, tools, config=None) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            content="",
            tool_calls=[{"id": f"call_{self.call_count}", "name": self._tool_name, "arguments": {}}],
            usage={"total_tokens": 10},
        )

    async def stream(self, messages, tools, config=None):
        raise NotImplementedError

    async def validate_auth(self) -> bool:
        return True


class MockRegistry:
    """模拟 PluginRegistry — 管理 slot、provider 和 capability 插件"""
    def __init__(self, context_engine, provider, capabilities: list | None = None):
        self._context_engine = context_engine
        self._provider = provider
        self._capabilities = capabilities or []
        self._cap_ids = [f"cap-{i}" for i in range(len(self._capabilities))]

    def resolve_slot(self, slot_key: str):
        if slot_key == "context-engine":
            return self._context_engine
        raise KeyError(f"Slot 未配置: {slot_key}")

    def resolve_provider(self, plugin_id: str | None = None):
        return self._provider

    def resolve(self, plugin_id: str):
        for cid, cap in zip(self._cap_ids, self._capabilities):
            if cid == plugin_id:
                return cap
        raise KeyError(f"插件未注册: {plugin_id}")

    def list_by_kind(self, kind: str) -> list[str]:
        if kind == "capability":
            return self._cap_ids
        return []


# ── Hypothesis 策略 ──

# 用户输入策略
user_input_st = st.text(
    min_size=1, max_size=30,
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
)

# max_iterations 策略（小范围以加速测试）
max_iterations_st = st.integers(min_value=1, max_value=8)

# Provider 在第 N 次调用后停止返回工具调用的迭代次数
stop_at_iteration_st = st.integers(min_value=0, max_value=7)

# 工具名策略
tool_name_st = st.from_regex(r"[a-z][a-z0-9_]{1,10}", fullmatch=True)

# 响应内容策略
response_content_st = st.text(min_size=1, max_size=30)


# ── 属性 9: Turn ReAct 循环终止 ──


class TestTurnReActLoopTermination:
    """属性 9: Turn ReAct 循环终止 **Validates: Requirements 5.3, 5.5, 5.6, 5.7**"""

    @given(
        user_input=user_input_st,
        response_content=response_content_st,
    )
    @settings(max_examples=100)
    def test_terminates_when_provider_returns_no_tool_calls(
        self, user_input: str, response_content: str,
    ):
        """(a) Provider 返回无工具调用 → 循环终止，返回最终响应

        Validates: Requirement 5.3
        当 Provider 返回的 ProviderResponse.tool_calls 为空时，
        ReAct 循环应立即终止并返回成功的 TurnResult。
        """
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        # Provider 直接返回无工具调用的响应
        provider = MockProvider([
            ProviderResponse(content=response_content, tool_calls=[], usage={"total_tokens": 42}),
        ])
        registry = MockRegistry(context_engine, provider)
        runner = TurnRunner(registry, event_bus=None, hooks=hooks, max_iterations=10)
        session = MockSession()

        async def _verify():
            result = await runner.run(session, user_input)
            # 循环应终止并返回成功结果
            assert result.success is True, "Provider 无工具调用时应返回成功"
            assert result.response == response_content, (
                f"响应内容应为 '{response_content}'，实际为 '{result.response}'"
            )
            # 不应有工具调用记录
            assert result.tool_calls == [], "无工具调用时 tool_calls 应为空"
            # 应触发 turn.start 和 turn.end 钩子
            hook_points = [h[0] for h in hooks.emitted]
            assert "turn.start" in hook_points, "应触发 turn.start 钩子"
            assert "turn.end" in hook_points, "应触发 turn.end 钩子"

        run_async(_verify())

    @given(
        user_input=user_input_st,
        max_iterations=max_iterations_st,
        tool_name=tool_name_st,
    )
    @settings(max_examples=80)
    def test_terminates_when_max_iterations_exceeded(
        self, user_input: str, max_iterations: int, tool_name: str,
    ):
        """(b) 迭代次数达到 max_iterations → 抛出 RuntimeError

        Validates: Requirement 5.6
        当 Provider 始终返回工具调用，迭代次数达到 max_iterations 时，
        ReAct 循环应抛出 RuntimeError 终止。
        """
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        cap = MockCapabilityPlugin([tool_name])
        # Provider 始终返回工具调用，永不终止
        provider = AlwaysToolCallProvider(tool_name=tool_name)
        registry = MockRegistry(context_engine, provider, capabilities=[cap])
        runner = TurnRunner(
            registry, event_bus=None, hooks=hooks,
            max_iterations=max_iterations,
        )
        session = MockSession()

        async def _verify():
            with pytest.raises(RuntimeError, match="最大迭代次数"):
                await runner.run(session, user_input)
            # Provider 应被调用恰好 max_iterations 次
            assert provider.call_count == max_iterations, (
                f"Provider 应被调用 {max_iterations} 次，"
                f"实际调用 {provider.call_count} 次"
            )
            # 应触发 turn.error 钩子
            hook_points = [h[0] for h in hooks.emitted]
            assert "turn.start" in hook_points, "应触发 turn.start 钩子"
            assert "turn.error" in hook_points, "应触发 turn.error 钩子"

        run_async(_verify())

    @given(user_input=user_input_st)
    @settings(max_examples=30)
    def test_terminates_when_timeout_exceeded(self, user_input: str):
        """(c) 超时 turn_timeout_s → 抛出 asyncio.TimeoutError

        Validates: Requirement 5.7
        当 Turn 执行时间超过 turn_timeout_s 时，
        asyncio.wait_for 应抛出 TimeoutError 终止循环。
        """
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        # 慢速 Provider：每次调用 sleep 较长时间
        provider = SlowProvider(delay=5.0)
        registry = MockRegistry(context_engine, provider)
        # 设置极短超时以触发超时
        runner = TurnRunner(
            registry, event_bus=None, hooks=hooks,
            max_iterations=10, turn_timeout_s=0.05,
        )
        session = MockSession()

        async def _verify():
            with pytest.raises(asyncio.TimeoutError):
                await runner.run(session, user_input)
            # 应触发 turn.error 钩子
            hook_points = [h[0] for h in hooks.emitted]
            assert "turn.start" in hook_points, "应触发 turn.start 钩子"
            assert "turn.error" in hook_points, "超时后应触发 turn.error 钩子"

        run_async(_verify())

    @given(
        user_input=user_input_st,
        max_iterations=st.integers(min_value=2, max_value=8),
        stop_at=stop_at_iteration_st,
        tool_name=tool_name_st,
        final_content=response_content_st,
    )
    @settings(max_examples=100)
    def test_terminates_after_multiple_iterations_with_tool_calls(
        self,
        user_input: str,
        max_iterations: int,
        stop_at: int,
        tool_name: str,
        final_content: str,
    ):
        """多次迭代后 Provider 停止返回工具调用 → 正常终止

        Validates: Requirements 5.3, 5.5
        Provider 先返回 stop_at 次带工具调用的响应，
        然后返回无工具调用的最终响应，循环应正常终止。
        """
        # 确保 stop_at < max_iterations，这样循环能在限制内正常终止
        assume(stop_at < max_iterations)

        context_engine = MockContextEngine()
        hooks = MockHookManager()
        cap = MockCapabilityPlugin([tool_name])

        # 构建响应序列：前 stop_at 次返回工具调用，最后一次返回纯文本
        responses: list[ProviderResponse] = []
        for i in range(stop_at):
            responses.append(ProviderResponse(
                content="",
                tool_calls=[{"id": f"call_{i}", "name": tool_name, "arguments": {}}],
                usage={"total_tokens": 10},
            ))
        # 最终响应：无工具调用
        responses.append(ProviderResponse(
            content=final_content, tool_calls=[], usage={"total_tokens": 20},
        ))

        provider = MockProvider(responses)
        registry = MockRegistry(context_engine, provider, capabilities=[cap])
        runner = TurnRunner(
            registry, event_bus=None, hooks=hooks,
            max_iterations=max_iterations,
        )
        session = MockSession()

        async def _verify():
            result = await runner.run(session, user_input)
            # 应成功终止
            assert result.success is True, (
                f"经过 {stop_at} 次工具调用后应正常终止"
            )
            assert result.response == final_content, (
                f"最终响应应为 '{final_content}'，实际为 '{result.response}'"
            )
            # 应记录 stop_at 次工具调用
            assert len(result.tool_calls) == stop_at, (
                f"应有 {stop_at} 次工具调用，实际 {len(result.tool_calls)} 次"
            )
            # Provider 应被调用 stop_at + 1 次（stop_at 次工具调用 + 1 次最终响应）
            assert provider._call_count == stop_at + 1, (
                f"Provider 应被调用 {stop_at + 1} 次，"
                f"实际 {provider._call_count} 次"
            )
            # 应触发 turn.start 和 turn.end 钩子
            hook_points = [h[0] for h in hooks.emitted]
            assert "turn.start" in hook_points
            assert "turn.end" in hook_points

        run_async(_verify())


# ── 属性 16 辅助 Mock ──


class ConfigurableCapabilityPlugin:
    """可配置成功/失败模式的 CapabilityPlugin

    通过 failure_indices 指定哪些工具调用会抛出异常，
    其余调用返回成功的 ExecutionResult。
    """

    def __init__(self, tool_names: list[str], failure_indices: set[int] | None = None):
        self._tool_names = tool_names
        self._failure_indices = failure_indices or set()
        self._call_order: list[str] = []  # 记录调用顺序
        self.meta = PluginMeta(
            id="configurable-cap", name="ConfigurableCap", version="1.0",
            description="可配置失败模式的测试能力插件", kind="capability",
        )
        self._call_count = 0

    def get_supported_intents(self) -> list[str]:
        return self._tool_names

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [{"name": name, "description": f"工具 {name}"} for name in self._tool_names]

    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult:
        """根据 call_index 参数决定成功或失败"""
        call_index = params.get("call_index", -1)
        self._call_order.append(intent)
        if call_index in self._failure_indices:
            raise RuntimeError(f"工具 {intent} 执行失败 (index={call_index})")
        return ExecutionResult(
            success=True,
            data={"tool": intent, "call_index": call_index},
        )

    async def cancel(self) -> bool:
        return True


# ── Hypothesis 策略（属性 16）──

# 工具调用数量策略
num_tools_st = st.integers(min_value=1, max_value=20)


# ── 属性 16: 工具并行执行结果完整性 ──


class TestToolParallelExecutionCompleteness:
    """属性 16: 工具并行执行结果完整性

    对于任意 N 个工具调用，_execute_tools 返回恰好 N 个结果，
    顺序与输入一致，异常被封装为 ExecutionResult(success=False)。

    **Validates: Requirements 5.10, 5.11, 10.3**
    """

    @given(
        n=num_tools_st,
    )
    @settings(max_examples=100)
    def test_result_count_equals_tool_call_count(self, n: int):
        """对于 N 个工具调用，返回恰好 N 个结果（完整性）

        **Validates: Requirements 5.10**
        """
        # 生成 N 个工具名
        tool_names = [f"tool_{i}" for i in range(n)]
        cap = ConfigurableCapabilityPlugin(tool_names)
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        # Provider 不会被调用，直接测试 _execute_tools
        provider = MockProvider([ProviderResponse(content="", tool_calls=[])])
        registry = MockRegistry(context_engine, provider, capabilities=[cap])
        runner = TurnRunner(registry, event_bus=None, hooks=hooks)
        session = MockSession()

        # 构建 N 个工具调用
        tool_calls = [
            {"id": f"call_{i}", "name": f"tool_{i}", "arguments": {"call_index": i}}
            for i in range(n)
        ]

        async def _verify():
            results = await runner._execute_tools(tool_calls, session)
            # 核心断言：结果数量 == 工具调用数量
            assert len(results) == n, (
                f"期望 {n} 个结果，实际得到 {len(results)} 个"
            )

        run_async(_verify())

    @given(
        n=num_tools_st,
        failure_mask=st.lists(st.booleans(), min_size=1, max_size=20),
    )
    @settings(max_examples=100)
    def test_failure_pattern_preserved_in_results(
        self, n: int, failure_mask: list[bool],
    ):
        """失败的工具产生 ExecutionResult(success=False)，成功的产生 success=True

        **Validates: Requirements 5.11, 10.3**
        """
        # 对齐 failure_mask 长度与 n
        mask = (failure_mask * ((n // len(failure_mask)) + 1))[:n]
        failure_indices = {i for i, should_fail in enumerate(mask) if should_fail}

        tool_names = [f"tool_{i}" for i in range(n)]
        cap = ConfigurableCapabilityPlugin(tool_names, failure_indices=failure_indices)
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        provider = MockProvider([ProviderResponse(content="", tool_calls=[])])
        registry = MockRegistry(context_engine, provider, capabilities=[cap])
        runner = TurnRunner(registry, event_bus=None, hooks=hooks)
        session = MockSession()

        tool_calls = [
            {"id": f"call_{i}", "name": f"tool_{i}", "arguments": {"call_index": i}}
            for i in range(n)
        ]

        async def _verify():
            results = await runner._execute_tools(tool_calls, session)
            # 结果数量完整性
            assert len(results) == n

            for i, result in enumerate(results):
                if i in failure_indices:
                    # 失败的工具应被封装为 ExecutionResult(success=False)
                    assert isinstance(result, ExecutionResult), (
                        f"索引 {i} 应为 ExecutionResult，实际为 {type(result)}"
                    )
                    assert result.success is False, (
                        f"索引 {i} 应为失败结果，实际 success={result.success}"
                    )
                    assert result.error is not None, (
                        f"索引 {i} 失败结果应包含 error 信息"
                    )
                else:
                    # 成功的工具应返回 ExecutionResult(success=True)
                    assert isinstance(result, ExecutionResult), (
                        f"索引 {i} 应为 ExecutionResult，实际为 {type(result)}"
                    )
                    assert result.success is True, (
                        f"索引 {i} 应为成功结果，实际 success={result.success}"
                    )

        run_async(_verify())

    @given(
        n=st.integers(min_value=2, max_value=15),
        fail_index=st.integers(min_value=0, max_value=14),
    )
    @settings(max_examples=100)
    def test_single_failure_does_not_affect_others(
        self, n: int, fail_index: int,
    ):
        """单个工具失败不影响其他工具完成

        **Validates: Requirements 5.11, 10.3**
        """
        assume(fail_index < n)

        tool_names = [f"tool_{i}" for i in range(n)]
        cap = ConfigurableCapabilityPlugin(tool_names, failure_indices={fail_index})
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        provider = MockProvider([ProviderResponse(content="", tool_calls=[])])
        registry = MockRegistry(context_engine, provider, capabilities=[cap])
        runner = TurnRunner(registry, event_bus=None, hooks=hooks)
        session = MockSession()

        tool_calls = [
            {"id": f"call_{i}", "name": f"tool_{i}", "arguments": {"call_index": i}}
            for i in range(n)
        ]

        async def _verify():
            results = await runner._execute_tools(tool_calls, session)
            # 所有结果都应返回（完整性）
            assert len(results) == n

            # 失败的那个应为 success=False
            assert isinstance(results[fail_index], ExecutionResult)
            assert results[fail_index].success is False

            # 其他所有工具应成功完成
            for i, result in enumerate(results):
                if i != fail_index:
                    assert isinstance(result, ExecutionResult)
                    assert result.success is True, (
                        f"索引 {i} 不应受索引 {fail_index} 失败的影响"
                    )

        run_async(_verify())

    @given(
        n=num_tools_st,
    )
    @settings(max_examples=100)
    def test_results_order_matches_tool_calls_order(self, n: int):
        """结果顺序与工具调用顺序一致

        **Validates: Requirements 5.10**
        """
        tool_names = [f"tool_{i}" for i in range(n)]
        cap = ConfigurableCapabilityPlugin(tool_names)
        context_engine = MockContextEngine()
        hooks = MockHookManager()
        provider = MockProvider([ProviderResponse(content="", tool_calls=[])])
        registry = MockRegistry(context_engine, provider, capabilities=[cap])
        runner = TurnRunner(registry, event_bus=None, hooks=hooks)
        session = MockSession()

        tool_calls = [
            {"id": f"call_{i}", "name": f"tool_{i}", "arguments": {"call_index": i}}
            for i in range(n)
        ]

        async def _verify():
            results = await runner._execute_tools(tool_calls, session)
            assert len(results) == n

            # 验证每个结果的 data.call_index 与位置一致
            for i, result in enumerate(results):
                assert isinstance(result, ExecutionResult)
                assert result.data.get("call_index") == i, (
                    f"索引 {i} 的结果 call_index 应为 {i}，"
                    f"实际为 {result.data.get('call_index')}"
                )

        run_async(_verify())
