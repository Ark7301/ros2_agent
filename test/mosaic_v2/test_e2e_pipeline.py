"""端到端管道集成测试 — 验证完整数据流

测试完整管道: 用户输入 → Router → Session → TurnRunner → Provider → Capability → 响应
使用真实组件 + Mock 插件，验证各组件协作和错误处理路径。

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 11.2, 11.3
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.plugin_sdk.types import (
    AssembleResult,
    CompactResult,
    ExecutionContext,
    ExecutionResult,
    HealthState,
    HealthStatus,
    PluginMeta,
    ProviderConfig,
    ProviderResponse,
)
from mosaic.gateway.agent_router import AgentRouter, RouteBinding
from mosaic.gateway.session_manager import SessionManager, SessionState
from mosaic.runtime.turn_runner import TurnRunner, TurnResult


# ── Mock 插件 ──


class MockContextEngine:
    """Mock 上下文引擎 — 返回空上下文，记录 ingest 调用"""

    meta = PluginMeta(
        id="mock-context-engine",
        name="MockContextEngine",
        version="1.0",
        description="测试用上下文引擎",
        kind="context-engine",
    )

    def __init__(self):
        self.ingested: list[tuple[str, dict]] = []

    async def ingest(self, session_id: str, message: dict) -> None:
        self.ingested.append((session_id, message))

    async def assemble(self, session_id: str, token_budget: int) -> AssembleResult:
        return AssembleResult(messages=[], token_count=0)

    async def compact(self, session_id: str, force: bool = False) -> CompactResult:
        return CompactResult(removed_count=0, remaining_count=0)


class MockProvider:
    """Mock Provider — 可配置响应序列

    responses: 按顺序返回的 ProviderResponse 列表。
    超出列表长度时循环最后一个响应。
    """

    meta = PluginMeta(
        id="mock-provider",
        name="MockProvider",
        version="1.0",
        description="测试用 Provider",
        kind="provider",
    )

    def __init__(self, responses: list[ProviderResponse]):
        self._responses = responses
        self.call_count = 0

    async def chat(
        self, messages: list[dict], tools: list[dict] | None, config: ProviderConfig
    ) -> ProviderResponse:
        idx = min(self.call_count, len(self._responses) - 1)
        self.call_count += 1
        return self._responses[idx]

    async def stream(self, messages, tools, config):
        raise NotImplementedError

    async def validate_auth(self) -> bool:
        return True


class FailingProvider:
    """Mock Provider — 始终抛出异常，用于测试重试和错误处理"""

    meta = PluginMeta(
        id="failing-provider",
        name="FailingProvider",
        version="1.0",
        description="始终失败的 Provider",
        kind="provider",
    )

    def __init__(self):
        self.call_count = 0

    async def chat(self, messages, tools, config) -> ProviderResponse:
        self.call_count += 1
        raise ConnectionError("Provider API 连接失败")

    async def stream(self, messages, tools, config):
        raise NotImplementedError

    async def validate_auth(self) -> bool:
        return False


class MockCapability:
    """Mock 能力插件 — 返回成功的执行结果"""

    def __init__(self, plugin_id: str, tool_names: list[str]):
        self.meta = PluginMeta(
            id=plugin_id,
            name=f"MockCap-{plugin_id}",
            version="1.0",
            description=f"测试用能力插件 {plugin_id}",
            kind="capability",
        )
        self._tool_names = tool_names
        self.executed: list[tuple[str, dict]] = []

    def get_supported_intents(self) -> list[str]:
        return self._tool_names

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "description": f"工具 {name}"}
            for name in self._tool_names
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        self.executed.append((intent, params))
        return ExecutionResult(success=True, data={"tool": intent, "result": "ok"})

    async def cancel(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY)


class FailingCapability:
    """Mock 能力插件 — 执行时抛出异常"""

    def __init__(self, plugin_id: str, tool_names: list[str]):
        self.meta = PluginMeta(
            id=plugin_id,
            name=f"FailCap-{plugin_id}",
            version="1.0",
            description=f"始终失败的能力插件 {plugin_id}",
            kind="capability",
        )
        self._tool_names = tool_names

    def get_supported_intents(self) -> list[str]:
        return self._tool_names

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "description": f"工具 {name}"}
            for name in self._tool_names
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        raise RuntimeError(f"能力 {intent} 执行失败: 硬件不可用")

    async def cancel(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.UNHEALTHY, message="硬件离线")


# ── 辅助函数 ──


def build_pipeline(
    provider_factory,
    capability_factories: list | None = None,
    max_concurrent: int = 10,
    max_iterations: int = 10,
    turn_timeout_s: float = 30,
):
    """构建完整管道组件，返回 (session_manager, router, turn_runner, registry, hooks)

    使用真实的 PluginRegistry、SessionManager、AgentRouter、TurnRunner、HookManager。
    通过工厂函数注册 Mock 插件。
    """
    # 真实组件
    event_bus = EventBus()
    hooks = HookManager()
    registry = PluginRegistry()

    # 注册 Mock 上下文引擎
    context_engine = MockContextEngine()
    registry.register("mock-context-engine", lambda: context_engine, "context-engine")
    registry.set_slot("context-engine", "mock-context-engine")

    # 注册 Mock Provider
    registry.register("mock-provider", provider_factory, "provider")
    registry.set_default_provider("mock-provider")

    # 注册 Mock 能力插件
    for cap_factory in (capability_factories or []):
        cap_instance = cap_factory()
        registry.register(cap_instance.meta.id, lambda c=cap_instance: c, "capability")

    # 构建控制面和运行时
    session_manager = SessionManager(
        max_concurrent=max_concurrent, idle_timeout_s=300,
    )
    router = AgentRouter(default_agent_id="default-agent")
    turn_runner = TurnRunner(
        registry=registry,
        event_bus=event_bus,
        hooks=hooks,
        max_iterations=max_iterations,
        turn_timeout_s=turn_timeout_s,
    )

    return session_manager, router, turn_runner, registry, hooks, context_engine


# ── 测试场景 ──


class TestHappyPath:
    """场景 1: 正常路径 — 用户输入 → Provider 返回文本 → 响应交付"""

    @pytest.mark.asyncio
    async def test_simple_text_response(self):
        """用户输入 → Provider 直接返回文本响应 → 成功返回 TurnResult"""
        provider = MockProvider([
            ProviderResponse(
                content="你好！我是 MOSAIC 助手。",
                tool_calls=[],
                usage={"total_tokens": 50},
            ),
        ])
        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
        )

        # 路由解析
        route = router.resolve({"channel": "cli"})
        assert route.agent_id == "default-agent"

        # 创建会话
        session = await sm.create_session(route.agent_id, "cli")
        assert session.state == SessionState.READY

        # 执行 Turn
        result = await sm.run_turn(session.session_id, "你好", runner)

        # 验证结果
        assert isinstance(result, TurnResult)
        assert result.success is True
        assert result.response == "你好！我是 MOSAIC 助手。"
        assert result.tool_calls == []
        assert result.tokens_used == 50

        # 验证会话状态
        assert session.state == SessionState.WAITING
        assert session.turn_count == 1

        # 验证上下文引擎记录了消息
        assert len(ctx_engine.ingested) == 2  # user + assistant
        assert ctx_engine.ingested[0][1]["role"] == "user"
        assert ctx_engine.ingested[1][1]["role"] == "assistant"


class TestToolCallPath:
    """场景 2: 工具调用路径 — 用户输入 → Provider 返回工具调用 → 工具执行 → 最终响应"""

    @pytest.mark.asyncio
    async def test_single_tool_call_then_response(self):
        """Provider 先返回工具调用，工具执行后 Provider 返回最终文本"""
        provider = MockProvider([
            # 第一次调用：返回工具调用
            ProviderResponse(
                content="",
                tool_calls=[{
                    "id": "call_1",
                    "name": "navigate_to",
                    "arguments": {"target": "厨房"},
                }],
                usage={"total_tokens": 30},
            ),
            # 第二次调用：返回最终响应
            ProviderResponse(
                content="已导航到厨房。",
                tool_calls=[],
                usage={"total_tokens": 40},
            ),
        ])
        nav_cap = MockCapability("nav-cap", ["navigate_to"])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
            capability_factories=[lambda: nav_cap],
        )

        session = await sm.create_session("default-agent", "cli")
        result = await sm.run_turn(session.session_id, "去厨房", runner)

        # 验证最终响应
        assert result.success is True
        assert result.response == "已导航到厨房。"
        # 验证工具调用记录
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "navigate_to"
        # 验证能力插件被调用
        assert len(nav_cap.executed) == 1
        assert nav_cap.executed[0][0] == "navigate_to"

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(self):
        """Provider 多次返回工具调用，最终返回文本响应"""
        provider = MockProvider([
            # 第一次：导航
            ProviderResponse(
                content="",
                tool_calls=[{"id": "c1", "name": "navigate_to", "arguments": {}}],
                usage={"total_tokens": 20},
            ),
            # 第二次：旋转
            ProviderResponse(
                content="",
                tool_calls=[{"id": "c2", "name": "rotate", "arguments": {}}],
                usage={"total_tokens": 20},
            ),
            # 第三次：最终响应
            ProviderResponse(
                content="任务完成：已导航并旋转。",
                tool_calls=[],
                usage={"total_tokens": 30},
            ),
        ])
        nav_cap = MockCapability("nav-cap", ["navigate_to"])
        motion_cap = MockCapability("motion-cap", ["rotate"])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
            capability_factories=[lambda: nav_cap, lambda: motion_cap],
        )

        session = await sm.create_session("default-agent", "cli")
        result = await sm.run_turn(session.session_id, "去厨房然后转身", runner)

        assert result.success is True
        assert result.response == "任务完成：已导航并旋转。"
        assert len(result.tool_calls) == 2


class TestProviderFailure:
    """场景 3: Provider 失败 — Provider 抛出异常 → 重试 → 错误处理

    Validates: Requirements 10.1, 10.2
    """

    @pytest.mark.asyncio
    async def test_provider_failure_after_retries(self):
        """Provider 始终失败 → 重试 3 次后异常传播"""
        failing_provider = FailingProvider()

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: failing_provider,
        )

        session = await sm.create_session("default-agent", "cli")

        # Provider 失败应传播为异常
        with pytest.raises(ConnectionError, match="Provider API 连接失败"):
            await sm.run_turn(session.session_id, "你好", runner)

        # 验证重试了 3 次（指数退避）
        assert failing_provider.call_count == 3

        # 验证会话状态恢复为 WAITING（而非 RUNNING）
        assert session.state == SessionState.WAITING
        # turn_count 仍然增加了 1
        assert session.turn_count == 1


class TestToolExecutionFailure:
    """场景 3b: 工具执行失败 — Capability 抛出异常 → 封装为 ExecutionResult(success=False)

    Validates: Requirement 10.3
    """

    @pytest.mark.asyncio
    async def test_capability_failure_wrapped_as_error_result(self):
        """能力插件执行失败 → 异常被封装，Provider 收到错误信息后返回最终响应"""
        provider = MockProvider([
            # 第一次：返回工具调用
            ProviderResponse(
                content="",
                tool_calls=[{"id": "c1", "name": "broken_tool", "arguments": {}}],
                usage={"total_tokens": 20},
            ),
            # 第二次：收到工具错误后返回最终响应
            ProviderResponse(
                content="抱歉，工具执行失败了。",
                tool_calls=[],
                usage={"total_tokens": 30},
            ),
        ])
        fail_cap = FailingCapability("fail-cap", ["broken_tool"])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
            capability_factories=[lambda: fail_cap],
        )

        session = await sm.create_session("default-agent", "cli")
        result = await sm.run_turn(session.session_id, "执行任务", runner)

        # 管道应正常完成（异常被封装，不中断流程）
        assert result.success is True
        assert result.response == "抱歉，工具执行失败了。"
        # 工具调用记录中应有 1 个调用
        assert len(result.tool_calls) == 1
        # 执行结果中应有 1 个失败结果
        assert len(result.execution_results) == 1
        failed_result = result.execution_results[0]
        assert isinstance(failed_result, ExecutionResult)
        assert failed_result.success is False


class TestSessionConcurrentLimit:
    """场景 4: Session 并发限制 — 达到上限后拒绝新 Session

    Validates: Requirements 10.4, 11.3
    """

    @pytest.mark.asyncio
    async def test_max_concurrent_sessions_enforced(self):
        """创建 max_concurrent 个 Session 后，下一个创建应失败"""
        max_concurrent = 3
        provider = MockProvider([
            ProviderResponse(content="ok", tool_calls=[], usage={}),
        ])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
            max_concurrent=max_concurrent,
        )

        # 创建 max_concurrent 个 Session（全部为 READY 状态）
        sessions = []
        for i in range(max_concurrent):
            s = await sm.create_session(f"agent-{i}", "cli")
            sessions.append(s)
            assert s.state == SessionState.READY

        # 第 max_concurrent + 1 个应失败
        with pytest.raises(RuntimeError, match="并发会话数已达上限"):
            await sm.create_session("agent-overflow", "cli")

    @pytest.mark.asyncio
    async def test_closed_session_frees_slot(self):
        """关闭一个 Session 后，可以创建新的 Session"""
        max_concurrent = 2
        provider = MockProvider([
            ProviderResponse(content="ok", tool_calls=[], usage={}),
        ])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
            max_concurrent=max_concurrent,
        )

        s1 = await sm.create_session("agent-1", "cli")
        s2 = await sm.create_session("agent-2", "cli")

        # 已满，创建失败
        with pytest.raises(RuntimeError):
            await sm.create_session("agent-3", "cli")

        # 关闭一个 Session
        await sm.close_session(s1.session_id)

        # 现在可以创建新 Session
        s3 = await sm.create_session("agent-3", "cli")
        assert s3.state == SessionState.READY


class TestMultiSessionIsolation:
    """场景 5: 多 Session 隔离 — 两个 Session 互不干扰

    Validates: Requirements 11.2, 11.3
    """

    @pytest.mark.asyncio
    async def test_sessions_do_not_interfere(self):
        """两个 Session 各自执行 Turn，结果互不影响"""
        # 为两个 Session 准备不同的 Provider 响应
        # 由于共享同一个 Provider 实例，用调用计数区分
        provider = MockProvider([
            ProviderResponse(content="响应-1", tool_calls=[], usage={"total_tokens": 10}),
            ProviderResponse(content="响应-2", tool_calls=[], usage={"total_tokens": 20}),
        ])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
        )

        # 创建两个独立 Session
        session_a = await sm.create_session("agent-a", "cli")
        session_b = await sm.create_session("agent-b", "websocket")

        # Session A 执行 Turn
        result_a = await sm.run_turn(session_a.session_id, "问题A", runner)
        assert result_a.success is True
        assert result_a.response == "响应-1"

        # Session B 执行 Turn
        result_b = await sm.run_turn(session_b.session_id, "问题B", runner)
        assert result_b.success is True
        assert result_b.response == "响应-2"

        # 验证两个 Session 状态独立
        assert session_a.state == SessionState.WAITING
        assert session_b.state == SessionState.WAITING
        assert session_a.turn_count == 1
        assert session_b.turn_count == 1

        # 验证 agent_id 和 channel_id 隔离
        assert session_a.agent_id == "agent-a"
        assert session_b.agent_id == "agent-b"
        assert session_a.channel_id == "cli"
        assert session_b.channel_id == "websocket"

    @pytest.mark.asyncio
    async def test_concurrent_turns_on_different_sessions(self):
        """两个不同 Session 可以并发执行 Turn"""
        # 使用独立的 Provider 实例避免共享状态问题
        provider_a = MockProvider([
            ProviderResponse(content="并发响应A", tool_calls=[], usage={}),
        ])
        provider_b = MockProvider([
            ProviderResponse(content="并发响应B", tool_calls=[], usage={}),
        ])

        # 构建两套独立管道（共享 SessionManager）
        event_bus = EventBus()
        hooks = HookManager()
        registry_a = PluginRegistry()
        registry_b = PluginRegistry()

        ctx_a = MockContextEngine()
        ctx_b = MockContextEngine()

        # 注册 Provider 和 ContextEngine 到各自的 registry
        registry_a.register("ctx-a", lambda: ctx_a, "context-engine")
        registry_a.set_slot("context-engine", "ctx-a")
        registry_a.register("prov-a", lambda: provider_a, "provider")
        registry_a.set_default_provider("prov-a")

        registry_b.register("ctx-b", lambda: ctx_b, "context-engine")
        registry_b.set_slot("context-engine", "ctx-b")
        registry_b.register("prov-b", lambda: provider_b, "provider")
        registry_b.set_default_provider("prov-b")

        sm = SessionManager(max_concurrent=10)
        runner_a = TurnRunner(registry_a, event_bus, hooks)
        runner_b = TurnRunner(registry_b, event_bus, hooks)

        session_a = await sm.create_session("agent-a", "cli")
        session_b = await sm.create_session("agent-b", "ws")

        # 并发执行
        result_a, result_b = await asyncio.gather(
            sm.run_turn(session_a.session_id, "输入A", runner_a),
            sm.run_turn(session_b.session_id, "输入B", runner_b),
        )

        assert result_a.success is True
        assert result_a.response == "并发响应A"
        assert result_b.success is True
        assert result_b.response == "并发响应B"


class TestRouterIntegration:
    """路由器集成 — 验证 Router 正确将请求路由到不同 Agent"""

    @pytest.mark.asyncio
    async def test_router_directs_to_correct_agent(self):
        """不同 channel 的请求被路由到不同 Agent"""
        bindings = [
            RouteBinding(
                agent_id="robot-agent",
                match_type="channel",
                channel="ros2",
                priority=10,
            ),
            RouteBinding(
                agent_id="chat-agent",
                match_type="channel",
                channel="cli",
                priority=20,
            ),
        ]
        router = AgentRouter(bindings=bindings, default_agent_id="fallback")

        # ROS2 通道 → robot-agent
        route_ros2 = router.resolve({"channel": "ros2"})
        assert route_ros2.agent_id == "robot-agent"

        # CLI 通道 → chat-agent
        route_cli = router.resolve({"channel": "cli"})
        assert route_cli.agent_id == "chat-agent"

        # 未知通道 → fallback
        route_unknown = router.resolve({"channel": "unknown"})
        assert route_unknown.agent_id == "fallback"


class TestHookIntegration:
    """钩子集成 — 验证 Turn 执行过程中钩子被正确触发"""

    @pytest.mark.asyncio
    async def test_hooks_fired_during_turn(self):
        """Turn 执行过程中应触发 turn.start / llm.before_call / llm.after_call / turn.end"""
        provider = MockProvider([
            ProviderResponse(content="钩子测试响应", tool_calls=[], usage={}),
        ])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
        )

        # 注册钩子记录器
        hook_log: list[str] = []

        async def log_hook(ctx):
            return True

        hooks.on("turn.start", lambda ctx: _async_log(hook_log, "turn.start"))
        hooks.on("turn.end", lambda ctx: _async_log(hook_log, "turn.end"))
        hooks.on("llm.before_call", lambda ctx: _async_log(hook_log, "llm.before_call"))
        hooks.on("llm.after_call", lambda ctx: _async_log(hook_log, "llm.after_call"))

        session = await sm.create_session("default-agent", "cli")
        result = await sm.run_turn(session.session_id, "测试钩子", runner)

        assert result.success is True
        # 验证钩子触发顺序
        assert "turn.start" in hook_log
        assert "llm.before_call" in hook_log
        assert "llm.after_call" in hook_log
        assert "turn.end" in hook_log
        # turn.start 应在 llm.before_call 之前
        assert hook_log.index("turn.start") < hook_log.index("llm.before_call")

    @pytest.mark.asyncio
    async def test_error_hook_fired_on_failure(self):
        """Provider 失败时应触发 turn.error 钩子"""
        failing_provider = FailingProvider()

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: failing_provider,
        )

        hook_log: list[str] = []
        hooks.on("turn.start", lambda ctx: _async_log(hook_log, "turn.start"))
        hooks.on("turn.error", lambda ctx: _async_log(hook_log, "turn.error"))

        session = await sm.create_session("default-agent", "cli")

        with pytest.raises(ConnectionError):
            await sm.run_turn(session.session_id, "触发错误", runner)

        assert "turn.start" in hook_log
        assert "turn.error" in hook_log


class TestSessionErrorPaths:
    """Session 错误路径 — 不存在的 Session 和已关闭的 Session"""

    @pytest.mark.asyncio
    async def test_run_turn_on_nonexistent_session(self):
        """对不存在的 session_id 执行 Turn 应抛出 KeyError"""
        provider = MockProvider([
            ProviderResponse(content="ok", tool_calls=[], usage={}),
        ])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
        )

        with pytest.raises(KeyError, match="会话不存在"):
            await sm.run_turn("nonexistent-id", "你好", runner)

    @pytest.mark.asyncio
    async def test_run_turn_on_closed_session(self):
        """对已关闭的 Session 执行 Turn 应抛出异常

        close_session 会从管理器中移除 Session，
        因此后续 run_turn 会抛出 KeyError（会话不存在）。
        """
        provider = MockProvider([
            ProviderResponse(content="ok", tool_calls=[], usage={}),
        ])

        sm, router, runner, registry, hooks, ctx_engine = build_pipeline(
            provider_factory=lambda: provider,
        )

        session = await sm.create_session("default-agent", "cli")
        await sm.close_session(session.session_id)

        # close_session 会 pop 掉 session，所以 run_turn 抛出 KeyError
        with pytest.raises(KeyError, match="会话不存在"):
            await sm.run_turn(session.session_id, "你好", runner)


# ── 辅助异步函数 ──


async def _async_log(log_list: list[str], name: str):
    """异步记录钩子名称到列表"""
    log_list.append(name)
    return True
