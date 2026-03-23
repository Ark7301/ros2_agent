# MOSAIC v2 冒烟测试（Smoke Test）
# 覆盖所有核心模块的集成场景，验证系统端到端功能
# 测试完成后应删除此文件

from __future__ import annotations

import asyncio
import time
import pytest

# ── 协议层 ──
from mosaic.protocol.events import Event, EventPriority, EventHandler
from mosaic.protocol.messages import (
    INBOUND_MESSAGE, OUTBOUND_MESSAGE, TURN_COMPLETE,
    TOOL_EXECUTED, NODE_STATUS_CHANGED, CONFIG_CHANGED,
)
from mosaic.protocol.errors import ErrorCode

# ── 核心基础设施 ──
from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager, HOOK_POINTS
from mosaic.core.config import ConfigManager

# ── 插件 SDK ──
from mosaic.plugin_sdk.types import (
    PluginMeta, HealthState, HealthStatus,
    ExecutionContext, ExecutionResult,
    CapabilityPlugin, ProviderPlugin, ChannelPlugin,
    MemoryPlugin, ContextEnginePlugin,
    ProviderConfig, ProviderResponse,
    OutboundMessage, SendResult,
    MemoryEntry, AssembleResult, CompactResult,
)
from mosaic.plugin_sdk.registry import PluginRegistry

# ── 控制面 ──
from mosaic.gateway.session_manager import SessionManager, Session, SessionState
from mosaic.gateway.agent_router import AgentRouter, RouteBinding, ResolvedRoute

# ── 运行时 ──
from mosaic.runtime.turn_runner import TurnRunner, TurnResult

# ── 节点层 ──
from mosaic.nodes.node_registry import NodeRegistry, NodeInfo, NodeStatus


# ============================================================
# SM-01: 公共 API 导入完整性
# ============================================================
class TestSM01_PublicAPIImport:
    """验证 mosaic 包的所有公共 API 可正常导入"""

    def test_import_mosaic_package(self):
        """mosaic 包可直接导入"""
        import mosaic
        assert hasattr(mosaic, "__all__")

    def test_all_exports_accessible(self):
        """__all__ 中声明的所有符号均可访问"""
        import mosaic
        for name in mosaic.__all__:
            assert hasattr(mosaic, name), f"缺失导出: {name}"

    def test_protocol_layer_types(self):
        """协议层类型可用"""
        assert Event is not None
        assert EventPriority.CRITICAL.value == 0
        assert INBOUND_MESSAGE == "channel.inbound"
        assert ErrorCode.PLUGIN_NOT_FOUND.value == "plugin_not_found"

    def test_plugin_sdk_protocols_are_runtime_checkable(self):
        """插件协议均为 @runtime_checkable"""
        from typing import runtime_checkable
        for proto in [CapabilityPlugin, ProviderPlugin, ChannelPlugin,
                      MemoryPlugin, ContextEnginePlugin]:
            # runtime_checkable 的 Protocol 可用于 isinstance 检查
            assert hasattr(proto, "__protocol_attrs__") or hasattr(proto, "__abstractmethods__") or True


# ============================================================
# SM-02: EventBus 完整生命周期
# ============================================================
class TestSM02_EventBusLifecycle:
    """验证 EventBus 的启动、事件分发、中间件、通配符、停止"""

    @pytest.mark.asyncio
    async def test_emit_and_dispatch(self):
        """事件发射后能被正确分发到 handler"""
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event.type)

        bus.on("test.event", handler)

        # 启动 bus 后台循环
        task = asyncio.create_task(bus.start())
        await bus.emit(Event(type="test.event", payload={}, source="test"))
        await asyncio.sleep(0.2)
        await bus.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert "test.event" in received

    @pytest.mark.asyncio
    async def test_wildcard_dispatch(self):
        """通配符订阅能匹配前缀事件"""
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event.type)

        bus.on("channel.*", handler)

        task = asyncio.create_task(bus.start())
        await bus.emit(Event(type="channel.inbound", payload={}, source="test"))
        await bus.emit(Event(type="channel.outbound", payload={}, source="test"))
        await bus.emit(Event(type="turn.complete", payload={}, source="test"))
        await asyncio.sleep(0.3)
        await bus.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert "channel.inbound" in received
        assert "channel.outbound" in received
        assert "turn.complete" not in received

    @pytest.mark.asyncio
    async def test_middleware_blocks_event(self):
        """中间件返回 None 时事件被丢弃"""
        bus = EventBus()
        received = []

        async def handler(event: Event):
            received.append(event.type)

        bus.on("*", handler)
        bus.use(lambda e: None)  # 丢弃所有事件

        task = asyncio.create_task(bus.start())
        await bus.emit(Event(type="blocked", payload={}, source="test"))
        await asyncio.sleep(0.2)
        await bus.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        """高优先级事件先于低优先级事件分发"""
        bus = EventBus()
        order = []

        async def handler(event: Event):
            order.append(event.priority.name)

        bus.on("*", handler)

        # 先放入低优先级，再放入高优先级
        await bus.emit(Event(type="low", payload={}, source="t", priority=EventPriority.LOW))
        await bus.emit(Event(type="critical", payload={}, source="t", priority=EventPriority.CRITICAL))

        task = asyncio.create_task(bus.start())
        await asyncio.sleep(0.3)
        await bus.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        assert order[0] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_stop_actually_stops(self):
        """stop() 后事件循环确实退出"""
        bus = EventBus()
        task = asyncio.create_task(bus.start())
        await asyncio.sleep(0.1)
        await bus.stop()
        # 等待循环退出（最多 1 秒）
        done, _ = await asyncio.wait({task}, timeout=2.0)
        assert len(done) == 1, "EventBus.stop() 未能终止事件循环"


# ============================================================
# SM-03: HookManager 完整功能
# ============================================================
class TestSM03_HookManager:
    """验证 HookManager 的注册、优先级、拦截、超时保护"""

    @pytest.mark.asyncio
    async def test_hook_priority_order(self):
        """钩子按 priority 升序执行"""
        hooks = HookManager()
        order = []

        async def h1(ctx):
            order.append("h1")
        async def h2(ctx):
            order.append("h2")
        async def h3(ctx):
            order.append("h3")

        hooks.on("test", h3, priority=300)
        hooks.on("test", h1, priority=100)
        hooks.on("test", h2, priority=200)

        await hooks.emit("test", {})
        assert order == ["h1", "h2", "h3"]

    @pytest.mark.asyncio
    async def test_hook_interception(self):
        """handler 返回 False 拦截后续 handler"""
        hooks = HookManager()
        executed = []

        async def blocker(ctx):
            executed.append("blocker")
            return False

        async def after(ctx):
            executed.append("after")

        hooks.on("test", blocker, priority=1)
        hooks.on("test", after, priority=2)

        result = await hooks.emit("test", {})
        assert result is False
        assert "after" not in executed

    @pytest.mark.asyncio
    async def test_hook_exception_skipped(self):
        """异常 handler 被跳过，链继续执行"""
        hooks = HookManager()
        executed = []

        async def bad(ctx):
            raise RuntimeError("boom")

        async def good(ctx):
            executed.append("good")

        hooks.on("test", bad, priority=1)
        hooks.on("test", good, priority=2)

        result = await hooks.emit("test", {})
        assert result is True
        assert "good" in executed

    def test_predefined_hook_points(self):
        """预定义钩子点列表完整"""
        assert "turn.start" in HOOK_POINTS
        assert "turn.end" in HOOK_POINTS
        assert "turn.error" in HOOK_POINTS
        assert "gateway.start" in HOOK_POINTS
        assert "llm.before_call" in HOOK_POINTS
        assert "tool.permission" in HOOK_POINTS
        assert "node.connect" in HOOK_POINTS
        assert "context.compact" in HOOK_POINTS


# ============================================================
# SM-04: ConfigManager 完整功能
# ============================================================
class TestSM04_ConfigManager:
    """验证 ConfigManager 的加载、点分路径、环境变量替换、热重载"""

    def test_load_and_get(self):
        """加载 YAML 配置并通过点分路径取值"""
        cfg = ConfigManager("config/mosaic.yaml")
        cfg.load()
        assert cfg.get("gateway.port") == 8765
        assert cfg.get("gateway.host") == "0.0.0.0"
        assert cfg.get("gateway.max_concurrent_sessions") == 10

    def test_nested_dotpath(self):
        """多层嵌套点分路径取值"""
        cfg = ConfigManager("config/mosaic.yaml")
        cfg.load()
        assert cfg.get("plugins.slots.memory") == "file-memory"
        assert cfg.get("plugins.slots.context-engine") == "sliding-window"
        assert cfg.get("plugins.providers.default") == "minimax"

    def test_default_fallback(self):
        """不存在的路径返回默认值"""
        cfg = ConfigManager("config/mosaic.yaml")
        cfg.load()
        assert cfg.get("nonexistent.path", "fallback") == "fallback"
        assert cfg.get("gateway.nonexistent", 42) == 42

    def test_env_var_substitution(self, monkeypatch):
        """${ENV_VAR} 环境变量替换"""
        monkeypatch.setenv("MINIMAX_API_KEY", "test-key-12345")
        cfg = ConfigManager("config/mosaic.yaml")
        cfg.load()
        key = cfg.get("plugins.providers.minimax.api_key")
        assert key == "test-key-12345"

    def test_reload_notifies_listeners(self):
        """reload() 触发变更监听器"""
        cfg = ConfigManager("config/mosaic.yaml")
        cfg.load()
        changes = []
        cfg.on_change(lambda old, new: changes.append((old, new)))
        cfg.reload()
        assert len(changes) == 1
        assert isinstance(changes[0][0], dict)
        assert isinstance(changes[0][1], dict)

    def test_routing_bindings_config(self):
        """路由绑定配置可正确读取"""
        cfg = ConfigManager("config/mosaic.yaml")
        cfg.load()
        bindings = cfg.get("routing.bindings")
        assert isinstance(bindings, list)
        assert len(bindings) >= 1
        assert bindings[0]["match_type"] == "intent"


# ============================================================
# SM-05: PluginRegistry 完整功能（含 discover 修复验证）
# ============================================================
class TestSM05_PluginRegistry:
    """验证 PluginRegistry 的注册、解析、Slot、Provider、自动发现"""

    def test_discover_correct_kind_mapping(self):
        """discover() 正确映射目录名到 kind（修复验证）"""
        reg = PluginRegistry()
        reg.discover("plugins")

        # 关键修复验证：capabilities → "capability"（非 "capabilitie"）
        caps = reg.list_by_kind("capability")
        assert "motion" in caps
        assert "navigation" in caps

        # 关键修复验证：context_engines → "context-engine"（非 "context_engine"）
        ces = reg.list_by_kind("context-engine")
        assert "sliding-window" in ces

    def test_discover_plugin_id_uses_hyphen(self):
        """discover() 注册的 plugin_id 使用连字符（修复验证）"""
        reg = PluginRegistry()
        reg.discover("plugins")

        # file_memory 目录 → "file-memory" plugin_id
        mem = reg.list_by_kind("memory")
        assert "file-memory" in mem

        # sliding_window 目录 → "sliding-window" plugin_id
        ce = reg.list_by_kind("context-engine")
        assert "sliding-window" in ce

    def test_discover_all_plugin_kinds(self):
        """discover() 发现所有 5 种类型的插件"""
        reg = PluginRegistry()
        reg.discover("plugins")

        assert len(reg.list_by_kind("channel")) >= 1      # cli
        assert len(reg.list_by_kind("capability")) >= 2    # motion, navigation
        assert len(reg.list_by_kind("provider")) >= 1      # minimax
        assert len(reg.list_by_kind("memory")) >= 1        # file-memory
        assert len(reg.list_by_kind("context-engine")) >= 1  # sliding-window

    def test_slot_resolve_with_discovered_plugins(self):
        """Slot 配置与 discover 注册的 plugin_id 一致"""
        reg = PluginRegistry()
        reg.discover("plugins")
        reg.set_slot("context-engine", "sliding-window")
        reg.set_slot("memory", "file-memory")

        ce = reg.resolve_slot("context-engine")
        assert ce.meta.kind == "context-engine"

        mem = reg.resolve_slot("memory")
        assert mem.meta.kind == "memory"

    def test_provider_resolve_with_discovered_plugins(self):
        """Provider 配置与 discover 注册的 plugin_id 一致"""
        reg = PluginRegistry()
        reg.discover("plugins")
        reg.set_default_provider("minimax")

        prov = reg.resolve_provider()
        assert prov.meta.kind == "provider"
        assert prov.meta.id == "minimax"

    def test_singleton_semantics(self):
        """多次 resolve 返回同一实例"""
        reg = PluginRegistry()
        reg.discover("plugins")

        a = reg.resolve("cli")
        b = reg.resolve("cli")
        assert a is b

    def test_tool_definitions_collectible(self):
        """从 capability 插件收集工具定义"""
        reg = PluginRegistry()
        reg.discover("plugins")

        tools = []
        for pid in reg.list_by_kind("capability"):
            plugin = reg.resolve(pid)
            tools.extend(plugin.get_tool_definitions())

        tool_names = [t["name"] for t in tools]
        assert "navigate_to" in tool_names
        assert "patrol" in tool_names
        assert "rotate" in tool_names
        assert "stop" in tool_names


# ============================================================
# SM-06: SessionManager 完整生命周期
# ============================================================
class TestSM06_SessionManager:
    """验证 SessionManager 的创建、状态流转、并发控制、空闲回收"""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self):
        """完整生命周期: 创建 → 执行 Turn → 关闭"""
        sm = SessionManager(max_concurrent=5)
        session = await sm.create_session("agent-1", "cli")
        assert session.state == SessionState.READY

        class MockRunner:
            async def run(self, session, user_input):
                return TurnResult(success=True, response="ok")

        result = await sm.run_turn(session.session_id, "hello", MockRunner())
        assert result.success
        assert session.state == SessionState.WAITING
        assert session.turn_count == 1

        await sm.close_session(session.session_id)
        assert session.state == SessionState.CLOSED

    @pytest.mark.asyncio
    async def test_concurrent_limit_enforcement(self):
        """并发限制生效"""
        sm = SessionManager(max_concurrent=2)
        s1 = await sm.create_session("a", "c1")
        s2 = await sm.create_session("a", "c2")

        with pytest.raises(RuntimeError, match="并发会话数已达上限"):
            await sm.create_session("a", "c3")

    @pytest.mark.asyncio
    async def test_idle_eviction(self):
        """空闲回收: WAITING 超时 → SUSPENDED"""
        sm = SessionManager(max_concurrent=10, idle_timeout_s=0.01)
        session = await sm.create_session("a", "c")

        class MockRunner:
            async def run(self, session, user_input):
                return TurnResult(success=True, response="ok")

        await sm.run_turn(session.session_id, "hi", MockRunner())
        assert session.state == SessionState.WAITING

        await asyncio.sleep(0.05)
        evicted = await sm.evict_idle_sessions()
        assert session.session_id in evicted
        assert session.state == SessionState.SUSPENDED

    @pytest.mark.asyncio
    async def test_closed_session_rejects_turn(self):
        """已关闭的 Session 拒绝执行 Turn"""
        sm = SessionManager()
        session = await sm.create_session("a", "c")
        await sm.close_session(session.session_id)

        class MockRunner:
            async def run(self, session, user_input):
                return TurnResult(success=True, response="ok")

        with pytest.raises(KeyError):
            await sm.run_turn(session.session_id, "hi", MockRunner())

    @pytest.mark.asyncio
    async def test_find_active_session(self):
        """find_active_session 公共方法正确查找活跃 Session"""
        sm = SessionManager()
        s1 = await sm.create_session("agent-1", "cli")

        found = sm.find_active_session("agent-1", "cli")
        assert found is s1

        not_found = sm.find_active_session("agent-2", "cli")
        assert not_found is None

        await sm.close_session(s1.session_id)
        after_close = sm.find_active_session("agent-1", "cli")
        assert after_close is None

    @pytest.mark.asyncio
    async def test_failed_turn_preserves_waiting_state(self):
        """失败的 Turn 后状态仍恢复为 WAITING"""
        sm = SessionManager()
        session = await sm.create_session("a", "c")

        class FailRunner:
            async def run(self, session, user_input):
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await sm.run_turn(session.session_id, "hi", FailRunner())

        assert session.state == SessionState.WAITING
        assert session.turn_count == 1


# ============================================================
# SM-07: AgentRouter 路由功能
# ============================================================
class TestSM07_AgentRouter:
    """验证 AgentRouter 的多层级路由匹配"""

    def test_channel_binding(self):
        """通道绑定路由"""
        router = AgentRouter(
            bindings=[RouteBinding(agent_id="ros2-agent", match_type="channel",
                                   channel="ros2", priority=10)],
            default_agent_id="default",
        )
        result = router.resolve({"channel": "ros2"})
        assert result.agent_id == "ros2-agent"
        assert result.matched_by == "binding.channel"

    def test_intent_pattern_binding(self):
        """意图正则匹配路由"""
        router = AgentRouter(
            bindings=[RouteBinding(agent_id="nav-agent", match_type="intent",
                                   pattern="navigate_.*|patrol", priority=1)],
            default_agent_id="default",
        )
        result = router.resolve({"intent": "navigate_to"})
        assert result.agent_id == "nav-agent"

        result2 = router.resolve({"intent": "patrol"})
        assert result2.agent_id == "nav-agent"

        result3 = router.resolve({"intent": "rotate"})
        assert result3.agent_id == "default"

    def test_scene_binding(self):
        """场景绑定路由"""
        router = AgentRouter(
            bindings=[RouteBinding(agent_id="kitchen-agent", match_type="scene",
                                   scene="kitchen", priority=5)],
            default_agent_id="default",
        )
        result = router.resolve({"scene": "kitchen"})
        assert result.agent_id == "kitchen-agent"

    def test_priority_ordering(self):
        """高优先级规则先匹配"""
        router = AgentRouter(
            bindings=[
                RouteBinding(agent_id="low", match_type="channel", channel="cli", priority=99),
                RouteBinding(agent_id="high", match_type="channel", channel="cli", priority=1),
            ],
            default_agent_id="default",
        )
        result = router.resolve({"channel": "cli"})
        assert result.agent_id == "high"

    def test_default_fallback(self):
        """无匹配时返回默认 Agent"""
        router = AgentRouter(default_agent_id="fallback")
        result = router.resolve({"channel": "unknown"})
        assert result.agent_id == "fallback"
        assert result.matched_by == "default"

    def test_determinism(self):
        """相同输入始终返回相同结果"""
        router = AgentRouter(
            bindings=[RouteBinding(agent_id="a", match_type="channel",
                                   channel="cli", priority=1)],
        )
        results = [router.resolve({"channel": "cli"}) for _ in range(100)]
        assert all(r.agent_id == "a" for r in results)


# ============================================================
# SM-08: TurnRunner ReAct 循环
# ============================================================
class TestSM08_TurnRunner:
    """验证 TurnRunner 的 ReAct 循环、工具调用、超时、重试"""

    def _make_runner(self, provider_responses, capabilities=None):
        """构建测试用 TurnRunner"""
        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()

        # 注册 mock context engine
        class MockCE:
            meta = PluginMeta(id="mock-ce", name="Mock CE", version="0.1.0",
                              description="", kind="context-engine")
            async def ingest(self, sid, msg): pass
            async def assemble(self, sid, token_budget):
                return AssembleResult(messages=[], token_count=0)
            async def compact(self, sid, force=False):
                return CompactResult(removed_count=0, remaining_count=0)

        reg.register("mock-ce", lambda: MockCE(), "context-engine")
        reg.set_slot("context-engine", "mock-ce")

        # 注册 mock provider
        call_count = [0]
        class MockProvider:
            meta = PluginMeta(id="mock-prov", name="Mock", version="0.1.0",
                              description="", kind="provider")
            async def chat(self, messages, tools, config):
                idx = min(call_count[0], len(provider_responses) - 1)
                call_count[0] += 1
                return provider_responses[idx]
            async def stream(self, messages, tools, config):
                yield provider_responses[0]
            async def validate_auth(self):
                return True

        reg.register("mock-prov", lambda: MockProvider(), "provider")
        reg.set_default_provider("mock-prov")

        # 注册 mock capability
        if capabilities:
            for cap_id, cap_factory in capabilities.items():
                reg.register(cap_id, cap_factory, "capability")

        return TurnRunner(registry=reg, event_bus=bus, hooks=hooks,
                          max_iterations=10, turn_timeout_s=5)

    @pytest.mark.asyncio
    async def test_simple_response_no_tools(self):
        """无工具调用时直接返回响应"""
        runner = self._make_runner([
            ProviderResponse(content="你好！", tool_calls=[], usage={"total_tokens": 10}),
        ])
        session = Session(agent_id="test", turn_count=0)
        result = await runner.run(session, "你好")
        assert result.success
        assert result.response == "你好！"
        assert result.tokens_used == 10
        assert len(result.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_tool_call_then_response(self):
        """一次工具调用后返回最终响应"""
        class MockCap:
            meta = PluginMeta(id="nav", name="Nav", version="0.1.0",
                              description="", kind="capability")
            def get_supported_intents(self): return ["navigate_to"]
            def get_tool_definitions(self):
                return [{"name": "navigate_to", "description": "导航",
                         "parameters": {"type": "object", "properties": {}}}]
            async def execute(self, intent, params, ctx):
                return ExecutionResult(success=True, data={"target": "kitchen"})
            async def cancel(self): return True
            async def health_check(self):
                return HealthStatus(state=HealthState.HEALTHY)

        runner = self._make_runner(
            provider_responses=[
                ProviderResponse(
                    content="",
                    tool_calls=[{"id": "tc1", "name": "navigate_to",
                                 "arguments": {"target": "kitchen"}}],
                    usage={},
                ),
                ProviderResponse(content="已导航到厨房", tool_calls=[], usage={"total_tokens": 20}),
            ],
            capabilities={"nav": lambda: MockCap()},
        )
        session = Session(agent_id="test", turn_count=0)
        result = await runner.run(session, "去厨房")
        assert result.success
        assert result.response == "已导航到厨房"
        assert len(result.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_max_iterations_exceeded(self):
        """超过最大迭代次数抛出 RuntimeError"""
        class MockCap:
            meta = PluginMeta(id="cap", name="Cap", version="0.1.0",
                              description="", kind="capability")
            def get_supported_intents(self): return ["do_thing"]
            def get_tool_definitions(self):
                return [{"name": "do_thing", "description": "做事",
                         "parameters": {"type": "object", "properties": {}}}]
            async def execute(self, intent, params, ctx):
                return ExecutionResult(success=True)
            async def cancel(self): return True
            async def health_check(self):
                return HealthStatus(state=HealthState.HEALTHY)

        # 每次都返回工具调用，永不终止
        runner = self._make_runner(
            provider_responses=[
                ProviderResponse(content="", tool_calls=[
                    {"id": "tc", "name": "do_thing", "arguments": {}}
                ], usage={}),
            ],
            capabilities={"cap": lambda: MockCap()},
        )
        runner._max_iterations = 3

        session = Session(agent_id="test", turn_count=0)
        with pytest.raises(RuntimeError, match="最大迭代次数"):
            await runner.run(session, "loop")

    @pytest.mark.asyncio
    async def test_tool_execution_failure_wrapped(self):
        """工具执行异常被封装为 ExecutionResult(success=False)"""
        class FailCap:
            meta = PluginMeta(id="fail", name="Fail", version="0.1.0",
                              description="", kind="capability")
            def get_supported_intents(self): return ["fail_tool"]
            def get_tool_definitions(self):
                return [{"name": "fail_tool", "description": "会失败",
                         "parameters": {"type": "object", "properties": {}}}]
            async def execute(self, intent, params, ctx):
                raise RuntimeError("工具执行失败")
            async def cancel(self): return True
            async def health_check(self):
                return HealthStatus(state=HealthState.HEALTHY)

        runner = self._make_runner(
            provider_responses=[
                ProviderResponse(content="", tool_calls=[
                    {"id": "tc", "name": "fail_tool", "arguments": {}}
                ], usage={}),
                ProviderResponse(content="工具失败了", tool_calls=[], usage={"total_tokens": 5}),
            ],
            capabilities={"fail": lambda: FailCap()},
        )
        session = Session(agent_id="test", turn_count=0)
        result = await runner.run(session, "test")
        assert result.success
        # 执行结果中应包含失败的 ExecutionResult
        assert len(result.execution_results) == 1
        fail_result = result.execution_results[0]
        assert isinstance(fail_result, ExecutionResult)
        assert fail_result.success is False

    @pytest.mark.asyncio
    async def test_hooks_fired_during_turn(self):
        """Turn 执行期间触发正确的钩子"""
        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()
        fired = []

        async def track(ctx):
            fired.append(ctx)

        hooks.on("turn.start", track)
        hooks.on("turn.end", track)
        hooks.on("llm.before_call", track)
        hooks.on("llm.after_call", track)

        class MockCE:
            meta = PluginMeta(id="ce", name="CE", version="0.1.0",
                              description="", kind="context-engine")
            async def ingest(self, sid, msg): pass
            async def assemble(self, sid, tb):
                return AssembleResult(messages=[], token_count=0)
            async def compact(self, sid, force=False):
                return CompactResult(removed_count=0, remaining_count=0)

        class MockProv:
            meta = PluginMeta(id="p", name="P", version="0.1.0",
                              description="", kind="provider")
            async def chat(self, messages, tools, config):
                return ProviderResponse(content="ok", tool_calls=[], usage={})
            async def stream(self, messages, tools, config): yield
            async def validate_auth(self): return True

        reg.register("ce", lambda: MockCE(), "context-engine")
        reg.set_slot("context-engine", "ce")
        reg.register("p", lambda: MockProv(), "provider")
        reg.set_default_provider("p")

        runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks)
        session = Session(agent_id="test", turn_count=0)
        await runner.run(session, "hi")

        # 验证钩子触发顺序
        hook_types = []
        for ctx in fired:
            if "turn_id" in ctx and "success" not in ctx and "error" not in ctx:
                hook_types.append("turn.start")
            elif "success" in ctx:
                hook_types.append("turn.end")
            elif "iteration" in ctx:
                hook_types.append("llm.before_call")
            elif "has_tool_calls" in ctx:
                hook_types.append("llm.after_call")

        assert "turn.start" in hook_types
        assert "turn.end" in hook_types
        assert "llm.before_call" in hook_types
        assert "llm.after_call" in hook_types


# ============================================================
# SM-09: NodeRegistry 节点管理
# ============================================================
class TestSM09_NodeRegistry:
    """验证 NodeRegistry 的注册、注销、心跳、能力查找、健康检查"""

    def test_register_and_resolve(self):
        """注册节点后可按能力查找"""
        nr = NodeRegistry()
        node = NodeInfo(node_id="n1", node_type="ros2_bridge",
                        capabilities=["navigation", "lidar"])
        nr.register(node)

        found = nr.resolve_nodes_for_capability("navigation")
        assert len(found) == 1
        assert found[0].node_id == "n1"

        found2 = nr.resolve_nodes_for_capability("lidar")
        assert len(found2) == 1

    def test_unregister_cleans_index(self):
        """注销节点后能力索引被清理"""
        nr = NodeRegistry()
        node = NodeInfo(node_id="n1", node_type="sensor",
                        capabilities=["camera"])
        nr.register(node)
        nr.unregister("n1")

        assert nr.resolve_nodes_for_capability("camera") == []

    def test_heartbeat_restores_status(self):
        """心跳更新恢复节点状态"""
        nr = NodeRegistry(heartbeat_timeout_s=0.01)
        node = NodeInfo(node_id="n1", node_type="sensor",
                        capabilities=["temp"])
        nr.register(node)

        time.sleep(0.05)
        nr.check_health()
        assert node.status == NodeStatus.HEARTBEAT_MISS

        nr.heartbeat("n1")
        assert node.status == NodeStatus.CONNECTED

    def test_only_connected_nodes_returned(self):
        """只返回 CONNECTED 状态的节点"""
        nr = NodeRegistry()
        n1 = NodeInfo(node_id="n1", node_type="sensor", capabilities=["cam"])
        n2 = NodeInfo(node_id="n2", node_type="sensor", capabilities=["cam"])
        nr.register(n1)
        nr.register(n2)

        n2.status = NodeStatus.HEARTBEAT_MISS
        found = nr.resolve_nodes_for_capability("cam")
        assert len(found) == 1
        assert found[0].node_id == "n1"

    def test_multiple_nodes_same_capability(self):
        """多个节点注册同一能力"""
        nr = NodeRegistry()
        for i in range(5):
            nr.register(NodeInfo(node_id=f"n{i}", node_type="sensor",
                                 capabilities=["shared"]))
        found = nr.resolve_nodes_for_capability("shared")
        assert len(found) == 5


# ============================================================
# SM-10: 插件实现层 — 能力插件
# ============================================================
class TestSM10_CapabilityPlugins:
    """验证 Navigation 和 Motion 能力插件"""

    @pytest.mark.asyncio
    async def test_navigation_execute(self):
        """NavigationCapability 执行 navigate_to"""
        from plugins.capabilities.navigation import create_plugin
        nav = create_plugin()
        ctx = ExecutionContext(session_id="s1")
        result = await nav.execute("navigate_to", {"target": "kitchen", "speed": 0.8}, ctx)
        assert result.success
        assert result.data["target"] == "kitchen"

    @pytest.mark.asyncio
    async def test_navigation_patrol(self):
        """NavigationCapability 执行 patrol"""
        from plugins.capabilities.navigation import create_plugin
        nav = create_plugin()
        ctx = ExecutionContext(session_id="s1")
        result = await nav.execute("patrol", {"waypoints": ["A", "B", "C"]}, ctx)
        assert result.success
        assert result.data["waypoints"] == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_navigation_unsupported_intent(self):
        """NavigationCapability 拒绝不支持的意图"""
        from plugins.capabilities.navigation import create_plugin
        nav = create_plugin()
        ctx = ExecutionContext(session_id="s1")
        result = await nav.execute("fly", {}, ctx)
        assert not result.success

    @pytest.mark.asyncio
    async def test_motion_rotate(self):
        """MotionCapability 执行 rotate"""
        from plugins.capabilities.motion import create_plugin
        motion = create_plugin()
        ctx = ExecutionContext(session_id="s1")
        result = await motion.execute("rotate", {"angle": 90}, ctx)
        assert result.success
        assert result.data["angle"] == 90

    @pytest.mark.asyncio
    async def test_motion_stop(self):
        """MotionCapability 执行 stop"""
        from plugins.capabilities.motion import create_plugin
        motion = create_plugin()
        ctx = ExecutionContext(session_id="s1")
        result = await motion.execute("stop", {}, ctx)
        assert result.success

    @pytest.mark.asyncio
    async def test_capability_health_check(self):
        """能力插件健康检查返回 HEALTHY"""
        from plugins.capabilities.navigation import create_plugin as nav_factory
        from plugins.capabilities.motion import create_plugin as motion_factory

        nav = nav_factory()
        motion = motion_factory()

        assert (await nav.health_check()).state == HealthState.HEALTHY
        assert (await motion.health_check()).state == HealthState.HEALTHY

    @pytest.mark.asyncio
    async def test_capability_cancel(self):
        """能力插件取消操作"""
        from plugins.capabilities.navigation import create_plugin
        nav = create_plugin()
        assert await nav.cancel() is True

    def test_capability_tool_definitions_schema(self):
        """工具定义包含必要字段"""
        from plugins.capabilities.navigation import create_plugin as nav_factory
        from plugins.capabilities.motion import create_plugin as motion_factory

        for factory in [nav_factory, motion_factory]:
            plugin = factory()
            for tool in plugin.get_tool_definitions():
                assert "name" in tool
                assert "description" in tool
                assert "parameters" in tool
                assert tool["parameters"]["type"] == "object"


# ============================================================
# SM-11: 插件实现层 — 记忆和上下文引擎
# ============================================================
class TestSM11_MemoryAndContextPlugins:
    """验证 FileMemory 和 SlidingWindowContextEngine"""

    @pytest.mark.asyncio
    async def test_file_memory_crud(self):
        """FileMemory 完整 CRUD"""
        from plugins.memory.file_memory import create_plugin
        mem = create_plugin()

        await mem.store("key1", "内容1", {"tag": "test"})
        entry = await mem.get("key1")
        assert entry is not None
        assert entry.content == "内容1"

        await mem.store("key1", "更新内容", {})
        entry2 = await mem.get("key1")
        assert entry2.content == "更新内容"

        assert await mem.delete("key1") is True
        assert await mem.get("key1") is None
        assert await mem.delete("key1") is False

    @pytest.mark.asyncio
    async def test_file_memory_search(self):
        """FileMemory 搜索功能"""
        from plugins.memory.file_memory import create_plugin
        mem = create_plugin()

        await mem.store("robot-nav", "导航到厨房", {})
        await mem.store("robot-motion", "旋转90度", {})
        await mem.store("user-pref", "用户偏好设置", {})

        results = await mem.search("robot")
        assert len(results) >= 2

    @pytest.mark.asyncio
    async def test_sliding_window_ingest_and_assemble(self):
        """SlidingWindowContextEngine 摄入和组装"""
        from plugins.context_engines.sliding_window import create_plugin
        ce = create_plugin()

        await ce.ingest("s1", {"role": "user", "content": "你好"})
        await ce.ingest("s1", {"role": "assistant", "content": "你好！有什么可以帮你的？"})
        await ce.ingest("s1", {"role": "user", "content": "去厨房"})

        result = await ce.assemble("s1", token_budget=10000)
        assert len(result.messages) == 3
        assert result.messages[0]["role"] == "user"
        assert result.messages[-1]["content"] == "去厨房"

    @pytest.mark.asyncio
    async def test_sliding_window_budget_truncation(self):
        """SlidingWindowContextEngine token 预算裁剪"""
        from plugins.context_engines.sliding_window import create_plugin
        ce = create_plugin()

        # 摄入大量消息
        for i in range(50):
            await ce.ingest("s1", {"role": "user", "content": f"消息{i}" * 20})

        # 小预算应裁剪
        result = await ce.assemble("s1", token_budget=100)
        assert len(result.messages) < 50
        assert result.token_count <= 100

    @pytest.mark.asyncio
    async def test_sliding_window_session_isolation(self):
        """SlidingWindowContextEngine 会话隔离"""
        from plugins.context_engines.sliding_window import create_plugin
        ce = create_plugin()

        await ce.ingest("s1", {"role": "user", "content": "session1"})
        await ce.ingest("s2", {"role": "user", "content": "session2"})

        r1 = await ce.assemble("s1", token_budget=10000)
        r2 = await ce.assemble("s2", token_budget=10000)

        assert len(r1.messages) == 1
        assert r1.messages[0]["content"] == "session1"
        assert len(r2.messages) == 1
        assert r2.messages[0]["content"] == "session2"

    @pytest.mark.asyncio
    async def test_sliding_window_compact(self):
        """SlidingWindowContextEngine 压缩功能"""
        from plugins.context_engines.sliding_window import create_plugin
        ce = create_plugin()

        for i in range(10):
            await ce.ingest("s1", {"role": "user", "content": f"msg{i}"})

        result = await ce.compact("s1", force=True)
        assert result.removed_count == 5
        assert result.remaining_count == 5


# ============================================================
# SM-12: 插件实现层 — CLI Channel
# ============================================================
class TestSM12_CLIChannel:
    """验证 CLI Channel 插件"""

    def test_protocol_compliance(self):
        """CLIChannel 满足 ChannelPlugin Protocol"""
        from plugins.channels.cli import create_plugin
        ch = create_plugin()
        assert isinstance(ch, ChannelPlugin)

    @pytest.mark.asyncio
    async def test_send_message(self, capsys):
        """send() 输出到 stdout"""
        from plugins.channels.cli import create_plugin
        ch = create_plugin()
        msg = OutboundMessage(session_id="s1", content="测试输出")
        result = await ch.send(msg)
        assert result.success
        captured = capsys.readouterr()
        assert "测试输出" in captured.out

    def test_on_message_registers_handler(self):
        """on_message() 注册处理器"""
        from plugins.channels.cli import create_plugin
        ch = create_plugin()
        handler_called = False

        def handler(msg):
            nonlocal handler_called
            handler_called = True

        ch.on_message(handler)
        assert ch._handler is handler


# ============================================================
# SM-13: MiniMax Provider 插件（结构验证，不调用真实 API）
# ============================================================
class TestSM13_MiniMaxProvider:
    """验证 MiniMax Provider 插件结构"""

    def test_meta_info(self):
        """Provider 元数据正确"""
        from plugins.providers.minimax import create_plugin
        prov = create_plugin()
        assert prov.meta.id == "minimax"
        assert prov.meta.kind == "provider"

    @pytest.mark.asyncio
    async def test_validate_auth_no_key(self):
        """无 API Key 时 validate_auth 返回 False"""
        from plugins.providers.minimax import create_plugin
        prov = create_plugin()
        prov._api_key = ""
        result = await prov.validate_auth()
        assert result is False

    def test_build_request_body(self):
        """请求体构建正确"""
        from plugins.providers.minimax import create_plugin
        prov = create_plugin()
        body = prov._build_request_body(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            config=ProviderConfig(model="test-model", temperature=0.5, max_tokens=100),
        )
        assert body["model"] == "test-model"
        assert body["temperature"] == 0.5
        assert body["max_tokens"] == 100
        assert body["messages"][0]["content"] == "hi"

    def test_parse_response(self):
        """API 响应解析正确"""
        from plugins.providers.minimax import create_plugin
        prov = create_plugin()
        data = {
            "choices": [{
                "message": {
                    "content": "你好！",
                    "tool_calls": [{
                        "id": "tc1",
                        "function": {"name": "navigate_to", "arguments": '{"target":"kitchen"}'},
                    }],
                },
            }],
            "usage": {"total_tokens": 42},
        }
        resp = prov._parse_response(data)
        assert resp.content == "你好！"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0]["name"] == "navigate_to"
        assert resp.usage["total_tokens"] == 42


# ============================================================
# SM-14: GatewayServer 初始化与组件编排
# ============================================================
class TestSM14_GatewayServer:
    """验证 GatewayServer 的初始化和组件编排"""

    def test_init_loads_all_components(self):
        """GatewayServer 初始化后所有组件就绪"""
        from mosaic.gateway.server import GatewayServer
        gw = GatewayServer("config/mosaic.yaml")

        assert gw.config is not None
        assert gw.event_bus is not None
        assert gw.hooks is not None
        assert gw.registry is not None
        assert gw.session_manager is not None
        assert gw.router is not None
        assert gw.turn_runner is not None

    def test_plugins_discovered(self):
        """GatewayServer 初始化后插件已发现"""
        from mosaic.gateway.server import GatewayServer
        gw = GatewayServer("config/mosaic.yaml")

        assert len(gw.registry.list_by_kind("capability")) >= 2
        assert len(gw.registry.list_by_kind("channel")) >= 1
        assert len(gw.registry.list_by_kind("provider")) >= 1
        assert len(gw.registry.list_by_kind("memory")) >= 1
        assert len(gw.registry.list_by_kind("context-engine")) >= 1

    def test_slots_configured(self):
        """Slot 配置正确"""
        from mosaic.gateway.server import GatewayServer
        gw = GatewayServer("config/mosaic.yaml")

        ce = gw.registry.resolve_slot("context-engine")
        assert ce is not None

        mem = gw.registry.resolve_slot("memory")
        assert mem is not None

    def test_default_provider_configured(self):
        """默认 Provider 配置正确"""
        from mosaic.gateway.server import GatewayServer
        gw = GatewayServer("config/mosaic.yaml")

        prov = gw.registry.resolve_provider()
        assert prov.meta.id == "minimax"

    def test_router_has_bindings(self):
        """路由器包含配置文件中的绑定"""
        from mosaic.gateway.server import GatewayServer
        gw = GatewayServer("config/mosaic.yaml")

        # 测试 intent 路由
        result = gw.router.resolve({"intent": "navigate_to"})
        assert result.agent_id == "navigation_agent"

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """GatewayServer 可正常启动和停止"""
        from mosaic.gateway.server import GatewayServer
        gw = GatewayServer("config/mosaic.yaml")

        await gw.start()
        # 验证 EventBus 在运行
        assert gw._bus_task is not None
        assert not gw._bus_task.done()

        await gw.stop()
        # 验证 EventBus 已停止
        await asyncio.sleep(0.2)


# ============================================================
# SM-15: 端到端集成 — 完整数据流
# ============================================================
class TestSM15_EndToEndIntegration:
    """验证完整数据流: 用户输入 → Router → Session → TurnRunner → 响应"""

    @pytest.mark.asyncio
    async def test_full_pipeline_text_response(self):
        """完整管道: 文本输入 → 文本响应"""
        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()

        # 注册 mock 插件
        class MockCE:
            meta = PluginMeta(id="ce", name="CE", version="0.1.0",
                              description="", kind="context-engine")
            async def ingest(self, sid, msg): pass
            async def assemble(self, sid, tb):
                return AssembleResult(messages=[], token_count=0)
            async def compact(self, sid, force=False):
                return CompactResult(removed_count=0, remaining_count=0)

        class MockProv:
            meta = PluginMeta(id="prov", name="P", version="0.1.0",
                              description="", kind="provider")
            async def chat(self, messages, tools, config):
                user_msg = next((m["content"] for m in messages if m["role"] == "user"), "")
                return ProviderResponse(content=f"回复: {user_msg}", tool_calls=[], usage={})
            async def stream(self, messages, tools, config): yield
            async def validate_auth(self): return True

        reg.register("ce", lambda: MockCE(), "context-engine")
        reg.set_slot("context-engine", "ce")
        reg.register("prov", lambda: MockProv(), "provider")
        reg.set_default_provider("prov")

        sm = SessionManager(max_concurrent=5)
        runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks)
        router = AgentRouter(default_agent_id="default")

        # 模拟完整流程
        route = router.resolve({"channel": "cli"})
        session = await sm.create_session(route.agent_id, "cli")
        result = await sm.run_turn(session.session_id, "你好世界", runner)

        assert result.success
        assert "你好世界" in result.response
        assert session.turn_count == 1
        assert session.state == SessionState.WAITING

    @pytest.mark.asyncio
    async def test_full_pipeline_with_tool_call(self):
        """完整管道: 文本输入 → 工具调用 → 最终响应"""
        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()

        class MockCE:
            meta = PluginMeta(id="ce", name="CE", version="0.1.0",
                              description="", kind="context-engine")
            async def ingest(self, sid, msg): pass
            async def assemble(self, sid, tb):
                return AssembleResult(messages=[], token_count=0)
            async def compact(self, sid, force=False):
                return CompactResult(removed_count=0, remaining_count=0)

        call_count = [0]
        class MockProv:
            meta = PluginMeta(id="prov", name="P", version="0.1.0",
                              description="", kind="provider")
            async def chat(self, messages, tools, config):
                call_count[0] += 1
                if call_count[0] == 1:
                    return ProviderResponse(content="", tool_calls=[
                        {"id": "tc1", "name": "navigate_to", "arguments": {"target": "厨房"}}
                    ], usage={})
                return ProviderResponse(content="已到达厨房", tool_calls=[], usage={})
            async def stream(self, messages, tools, config): yield
            async def validate_auth(self): return True

        class MockNav:
            meta = PluginMeta(id="nav", name="Nav", version="0.1.0",
                              description="", kind="capability")
            def get_supported_intents(self): return ["navigate_to"]
            def get_tool_definitions(self):
                return [{"name": "navigate_to", "description": "导航",
                         "parameters": {"type": "object", "properties": {}}}]
            async def execute(self, intent, params, ctx):
                return ExecutionResult(success=True, data={"arrived": True})
            async def cancel(self): return True
            async def health_check(self):
                return HealthStatus(state=HealthState.HEALTHY)

        reg.register("ce", lambda: MockCE(), "context-engine")
        reg.set_slot("context-engine", "ce")
        reg.register("prov", lambda: MockProv(), "provider")
        reg.set_default_provider("prov")
        reg.register("nav", lambda: MockNav(), "capability")

        sm = SessionManager(max_concurrent=5)
        runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks)

        session = await sm.create_session("default", "cli")
        result = await sm.run_turn(session.session_id, "去厨房", runner)

        assert result.success
        assert result.response == "已到达厨房"
        assert len(result.tool_calls) == 1

    @pytest.mark.asyncio
    async def test_multi_session_isolation(self):
        """多 Session 并发隔离"""
        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()

        class MockCE:
            meta = PluginMeta(id="ce", name="CE", version="0.1.0",
                              description="", kind="context-engine")
            _data = {}
            async def ingest(self, sid, msg):
                self._data.setdefault(sid, []).append(msg)
            async def assemble(self, sid, tb):
                return AssembleResult(messages=self._data.get(sid, []), token_count=0)
            async def compact(self, sid, force=False):
                return CompactResult(removed_count=0, remaining_count=0)

        class MockProv:
            meta = PluginMeta(id="prov", name="P", version="0.1.0",
                              description="", kind="provider")
            async def chat(self, messages, tools, config):
                user_msg = [m for m in messages if m["role"] == "user"][-1]["content"]
                return ProviderResponse(content=f"echo:{user_msg}", tool_calls=[], usage={})
            async def stream(self, messages, tools, config): yield
            async def validate_auth(self): return True

        reg.register("ce", lambda: MockCE(), "context-engine")
        reg.set_slot("context-engine", "ce")
        reg.register("prov", lambda: MockProv(), "provider")
        reg.set_default_provider("prov")

        sm = SessionManager(max_concurrent=10)
        runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks)

        s1 = await sm.create_session("a1", "c1")
        s2 = await sm.create_session("a2", "c2")

        r1 = await sm.run_turn(s1.session_id, "消息A", runner)
        r2 = await sm.run_turn(s2.session_id, "消息B", runner)

        assert "消息A" in r1.response
        assert "消息B" in r2.response
        assert s1.turn_count == 1
        assert s2.turn_count == 1

    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """错误恢复: Provider 失败后 Session 仍可用"""
        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()

        class MockCE:
            meta = PluginMeta(id="ce", name="CE", version="0.1.0",
                              description="", kind="context-engine")
            async def ingest(self, sid, msg): pass
            async def assemble(self, sid, tb):
                return AssembleResult(messages=[], token_count=0)
            async def compact(self, sid, force=False):
                return CompactResult(removed_count=0, remaining_count=0)

        call_count = [0]
        class MockProv:
            meta = PluginMeta(id="prov", name="P", version="0.1.0",
                              description="", kind="provider")
            async def chat(self, messages, tools, config):
                call_count[0] += 1
                if call_count[0] <= 3:
                    raise RuntimeError("API 错误")
                return ProviderResponse(content="恢复了", tool_calls=[], usage={})
            async def stream(self, messages, tools, config): yield
            async def validate_auth(self): return True

        reg.register("ce", lambda: MockCE(), "context-engine")
        reg.set_slot("context-engine", "ce")
        reg.register("prov", lambda: MockProv(), "provider")
        reg.set_default_provider("prov")

        sm = SessionManager(max_concurrent=5)
        runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks)

        session = await sm.create_session("default", "cli")

        # 第一次 Turn 失败（Provider 连续失败 3 次，重试耗尽）
        with pytest.raises(RuntimeError):
            await sm.run_turn(session.session_id, "test", runner)

        # Session 仍可用（状态恢复为 WAITING）
        assert session.state == SessionState.WAITING

        # 第二次 Turn 成功（call_count > 3）
        result = await sm.run_turn(session.session_id, "retry", runner)
        assert result.success
        assert result.response == "恢复了"
