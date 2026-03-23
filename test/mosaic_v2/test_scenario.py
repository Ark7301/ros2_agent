# MOSAIC v2 使用场景测试
# 模拟真实用户使用场景，验证系统在实际工作流下的表现
# 测试完成后应删除此文件

from __future__ import annotations

import asyncio
import time
import pytest

from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.core.config import ConfigManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.plugin_sdk.types import (
    PluginMeta, ExecutionContext, ExecutionResult,
    ProviderConfig, ProviderResponse, AssembleResult, CompactResult,
    HealthStatus, HealthState, OutboundMessage, SendResult,
)
from mosaic.gateway.session_manager import SessionManager, Session, SessionState
from mosaic.gateway.agent_router import AgentRouter, RouteBinding, ResolvedRoute
from mosaic.gateway.server import GatewayServer
from mosaic.runtime.turn_runner import TurnRunner, TurnResult
from mosaic.nodes.node_registry import NodeRegistry, NodeInfo, NodeStatus
from mosaic.protocol.events import Event, EventPriority
from mosaic.protocol.messages import INBOUND_MESSAGE, OUTBOUND_MESSAGE


# ── 共用 Mock 工厂 ──

def make_mock_context_engine():
    """创建带持久化存储的 Mock 上下文引擎"""
    class MockContextEngine:
        def __init__(self):
            self.meta = PluginMeta(
                id="mock-ce", name="Mock CE", version="0.1.0",
                description="", kind="context-engine",
            )
            self._store: dict[str, list[dict]] = {}

        async def ingest(self, session_id, message):
            self._store.setdefault(session_id, []).append(message)

        async def assemble(self, session_id, token_budget):
            msgs = self._store.get(session_id, [])
            return AssembleResult(messages=list(msgs), token_count=len(msgs) * 10)

        async def compact(self, session_id, force=False):
            msgs = self._store.get(session_id, [])
            if force and len(msgs) > 2:
                half = len(msgs) // 2
                self._store[session_id] = msgs[half:]
                return CompactResult(removed_count=half, remaining_count=len(msgs) - half)
            return CompactResult(removed_count=0, remaining_count=len(msgs))

    return MockContextEngine()


def make_scripted_provider(script: list[ProviderResponse]):
    """创建按脚本顺序返回响应的 Mock Provider"""
    idx = [0]

    class ScriptedProvider:
        def __init__(self):
            self.meta = PluginMeta(
                id="mock-prov", name="Mock Provider", version="0.1.0",
                description="", kind="provider",
            )

        async def chat(self, messages, tools, config):
            i = min(idx[0], len(script) - 1)
            idx[0] += 1
            resp = script[i]
            if isinstance(resp, Exception):
                raise resp
            return resp

        async def stream(self, messages, tools, config):
            yield script[0]

        async def validate_auth(self):
            return True

    return ScriptedProvider()


def make_nav_capability():
    """创建导航能力 Mock"""
    class NavCap:
        def __init__(self):
            self.meta = PluginMeta(
                id="navigation", name="Navigation", version="0.1.0",
                description="", kind="capability",
            )
            self.call_log = []

        def get_supported_intents(self):
            return ["navigate_to", "patrol"]

        def get_tool_definitions(self):
            return [
                {"name": "navigate_to", "description": "导航到目标",
                 "parameters": {"type": "object", "properties": {
                     "target": {"type": "string"}}}},
                {"name": "patrol", "description": "巡逻",
                 "parameters": {"type": "object", "properties": {
                     "waypoints": {"type": "array", "items": {"type": "string"}}}}},
            ]

        async def execute(self, intent, params, ctx):
            self.call_log.append({"intent": intent, "params": params})
            if intent == "navigate_to":
                return ExecutionResult(
                    success=True,
                    data={"target": params.get("target", ""), "arrived": True},
                    message=f"已到达 {params.get('target', '')}",
                )
            elif intent == "patrol":
                return ExecutionResult(
                    success=True,
                    data={"waypoints": params.get("waypoints", []), "completed": True},
                    message=f"巡逻完成",
                )
            return ExecutionResult(success=False, error=f"未知意图: {intent}")

        async def cancel(self):
            return True

        async def health_check(self):
            return HealthStatus(state=HealthState.HEALTHY)

    return NavCap()


def make_motion_capability():
    """创建运动控制能力 Mock"""
    class MotionCap:
        def __init__(self):
            self.meta = PluginMeta(
                id="motion", name="Motion", version="0.1.0",
                description="", kind="capability",
            )
            self.call_log = []

        def get_supported_intents(self):
            return ["rotate", "stop"]

        def get_tool_definitions(self):
            return [
                {"name": "rotate", "description": "旋转",
                 "parameters": {"type": "object", "properties": {
                     "angle": {"type": "number"}}}},
                {"name": "stop", "description": "紧急停止",
                 "parameters": {"type": "object", "properties": {}}},
            ]

        async def execute(self, intent, params, ctx):
            self.call_log.append({"intent": intent, "params": params})
            if intent == "rotate":
                return ExecutionResult(
                    success=True,
                    data={"angle": params.get("angle", 0)},
                    message=f"已旋转 {params.get('angle', 0)} 度",
                )
            elif intent == "stop":
                return ExecutionResult(success=True, message="已停止")
            return ExecutionResult(success=False, error=f"未知意图: {intent}")

        async def cancel(self):
            return True

        async def health_check(self):
            return HealthStatus(state=HealthState.HEALTHY)

    return MotionCap()


def build_test_system(provider_script, nav=None, motion=None, max_concurrent=10):
    """构建完整测试系统"""
    reg = PluginRegistry()
    bus = EventBus()
    hooks = HookManager()

    ce = make_mock_context_engine()
    prov = make_scripted_provider(provider_script)
    nav = nav or make_nav_capability()
    motion = motion or make_motion_capability()

    reg.register("mock-ce", lambda: ce, "context-engine")
    reg.set_slot("context-engine", "mock-ce")
    reg.register("mock-prov", lambda: prov, "provider")
    reg.set_default_provider("mock-prov")
    reg.register("navigation", lambda: nav, "capability")
    reg.register("motion", lambda: motion, "capability")

    sm = SessionManager(max_concurrent=max_concurrent)
    runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks,
                        max_iterations=10, turn_timeout_s=10)

    return {
        "registry": reg, "bus": bus, "hooks": hooks,
        "session_manager": sm, "turn_runner": runner,
        "context_engine": ce, "provider": prov,
        "nav": nav, "motion": motion,
    }


# ============================================================
# 场景 1: 用户与机器人的单轮导航对话
# "去厨房" → LLM 调用 navigate_to → 返回结果
# ============================================================
class TestScenario01_SingleTurnNavigation:
    """用户发出导航指令，机器人执行导航并返回结果"""

    @pytest.mark.asyncio
    async def test_user_says_go_to_kitchen(self):
        """用户: '去厨房' → 机器人导航到厨房并回复"""
        sys = build_test_system([
            # LLM 第一次调用：决定调用 navigate_to 工具
            ProviderResponse(content="", tool_calls=[
                {"id": "tc1", "name": "navigate_to",
                 "arguments": {"target": "厨房"}},
            ], usage={}),
            # LLM 第二次调用：看到工具结果后生成最终回复
            ProviderResponse(
                content="好的，我已经到达厨房了。请问还需要什么帮助？",
                tool_calls=[], usage={"total_tokens": 50},
            ),
        ])

        sm = sys["session_manager"]
        runner = sys["turn_runner"]

        session = await sm.create_session("default", "cli")
        result = await sm.run_turn(session.session_id, "去厨房", runner)

        assert result.success
        assert "厨房" in result.response
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "navigate_to"
        # 验证导航能力确实被调用
        assert len(sys["nav"].call_log) == 1
        assert sys["nav"].call_log[0]["params"]["target"] == "厨房"

    @pytest.mark.asyncio
    async def test_user_says_patrol(self):
        """用户: '巡逻 A B C' → 机器人执行巡逻"""
        sys = build_test_system([
            ProviderResponse(content="", tool_calls=[
                {"id": "tc1", "name": "patrol",
                 "arguments": {"waypoints": ["A区", "B区", "C区"]}},
            ], usage={}),
            ProviderResponse(
                content="巡逻任务完成，已依次经过 A区、B区、C区。",
                tool_calls=[], usage={"total_tokens": 40},
            ),
        ])

        sm = sys["session_manager"]
        runner = sys["turn_runner"]

        session = await sm.create_session("default", "cli")
        result = await sm.run_turn(session.session_id, "巡逻 A区 B区 C区", runner)

        assert result.success
        assert "巡逻" in result.response
        assert sys["nav"].call_log[0]["intent"] == "patrol"
        assert sys["nav"].call_log[0]["params"]["waypoints"] == ["A区", "B区", "C区"]


# ============================================================
# 场景 2: 多轮对话 — 上下文保持
# 用户连续发多条消息，验证上下文引擎正确积累历史
# ============================================================
class TestScenario02_MultiTurnConversation:
    """多轮对话场景，验证上下文持久化和历史积累"""

    @pytest.mark.asyncio
    async def test_three_turn_conversation(self):
        """三轮对话，每轮上下文正确积累"""
        call_count = [0]
        responses = [
            ProviderResponse(content="你好！我是 MOSAIC 机器人助手。", tool_calls=[], usage={}),
            ProviderResponse(content="好的，正在导航到客厅。", tool_calls=[
                {"id": "tc1", "name": "navigate_to", "arguments": {"target": "客厅"}},
            ], usage={}),
            ProviderResponse(content="已到达客厅，请问还需要什么？", tool_calls=[], usage={}),
            ProviderResponse(content="好的，正在旋转 90 度。", tool_calls=[
                {"id": "tc2", "name": "rotate", "arguments": {"angle": 90}},
            ], usage={}),
            ProviderResponse(content="已旋转完成。", tool_calls=[], usage={}),
        ]

        sys = build_test_system(responses)
        sm = sys["session_manager"]
        runner = sys["turn_runner"]
        ce = sys["context_engine"]

        session = await sm.create_session("default", "cli")

        # Turn 1: 打招呼
        r1 = await sm.run_turn(session.session_id, "你好", runner)
        assert r1.success
        assert "你好" in r1.response

        # 验证上下文引擎存储了 Turn 1 的消息
        ctx1 = await ce.assemble(session.session_id, 10000)
        assert len(ctx1.messages) == 2  # user + assistant

        # Turn 2: 导航指令
        r2 = await sm.run_turn(session.session_id, "去客厅", runner)
        assert r2.success

        # 验证上下文引擎存储了 Turn 1 + Turn 2 的消息
        ctx2 = await ce.assemble(session.session_id, 10000)
        assert len(ctx2.messages) == 4  # 2 from turn1 + 2 from turn2

        # Turn 3: 运动控制
        r3 = await sm.run_turn(session.session_id, "向右转 90 度", runner)
        assert r3.success

        # 验证上下文引擎存储了全部 3 轮消息
        ctx3 = await ce.assemble(session.session_id, 10000)
        assert len(ctx3.messages) == 6  # 2 * 3 turns

        # 验证 session 状态
        assert session.turn_count == 3
        assert session.state == SessionState.WAITING

    @pytest.mark.asyncio
    async def test_context_passed_to_provider(self):
        """验证历史上下文确实传递给了 Provider"""
        captured_messages = []

        class CapturingProvider:
            def __init__(self):
                self.meta = PluginMeta(
                    id="cap-prov", name="Capturing", version="0.1.0",
                    description="", kind="provider",
                )

            async def chat(self, messages, tools, config):
                captured_messages.append(list(messages))
                return ProviderResponse(content="ok", tool_calls=[], usage={})

            async def stream(self, messages, tools, config):
                yield ProviderResponse(content="ok", tool_calls=[], usage={})

            async def validate_auth(self):
                return True

        reg = PluginRegistry()
        bus = EventBus()
        hooks = HookManager()

        ce = make_mock_context_engine()
        prov = CapturingProvider()

        reg.register("ce", lambda: ce, "context-engine")
        reg.set_slot("context-engine", "ce")
        reg.register("prov", lambda: prov, "provider")
        reg.set_default_provider("prov")

        sm = SessionManager()
        runner = TurnRunner(registry=reg, event_bus=bus, hooks=hooks)

        session = await sm.create_session("default", "cli")

        await sm.run_turn(session.session_id, "第一条消息", runner)
        await sm.run_turn(session.session_id, "第二条消息", runner)

        # 第二次 Provider 调用应包含第一轮的历史
        assert len(captured_messages) == 2
        # 第一次调用：只有当前 user 消息
        assert captured_messages[0][-1]["content"] == "第一条消息"
        # 第二次调用：包含历史 + 当前 user 消息
        assert len(captured_messages[1]) > 1
        assert captured_messages[1][-1]["content"] == "第二条消息"
        # 历史中应包含第一轮的 user 和 assistant 消息
        roles = [m["role"] for m in captured_messages[1]]
        assert "user" in roles
        assert "assistant" in roles


# ============================================================
# 场景 3: 复合工具调用 — 导航 + 旋转
# LLM 在一次响应中调用多个工具
# ============================================================
class TestScenario03_CompoundToolCalls:
    """LLM 在一次响应中调用多个工具（并行执行）"""

    @pytest.mark.asyncio
    async def test_navigate_then_rotate_in_one_response(self):
        """LLM 同时调用 navigate_to 和 rotate"""
        sys = build_test_system([
            ProviderResponse(content="", tool_calls=[
                {"id": "tc1", "name": "navigate_to", "arguments": {"target": "门口"}},
                {"id": "tc2", "name": "rotate", "arguments": {"angle": 180}},
            ], usage={}),
            ProviderResponse(
                content="已到达门口并转身面向出口。",
                tool_calls=[], usage={"total_tokens": 30},
            ),
        ])

        sm = sys["session_manager"]
        runner = sys["turn_runner"]

        session = await sm.create_session("default", "cli")
        result = await sm.run_turn(session.session_id, "去门口然后转身", runner)

        assert result.success
        assert len(result.tool_calls) == 2
        # 两个能力都被调用
        assert len(sys["nav"].call_log) == 1
        assert len(sys["motion"].call_log) == 1
        assert sys["nav"].call_log[0]["params"]["target"] == "门口"
        assert sys["motion"].call_log[0]["params"]["angle"] == 180

    @pytest.mark.asyncio
    async def test_multi_step_tool_calls(self):
        """LLM 分两步调用工具：先导航，再停止"""
        sys = build_test_system([
            # 第一步：导航
            ProviderResponse(content="", tool_calls=[
                {"id": "tc1", "name": "navigate_to", "arguments": {"target": "仓库"}},
            ], usage={}),
            # 第二步：看到导航结果后，决定停止
            ProviderResponse(content="", tool_calls=[
                {"id": "tc2", "name": "stop", "arguments": {}},
            ], usage={}),
            # 最终回复
            ProviderResponse(
                content="已到达仓库并停止运动。",
                tool_calls=[], usage={"total_tokens": 25},
            ),
        ])

        sm = sys["session_manager"]
        runner = sys["turn_runner"]

        session = await sm.create_session("default", "cli")
        result = await sm.run_turn(session.session_id, "去仓库然后停下", runner)

        assert result.success
        assert len(result.tool_calls) == 2
        assert result.tool_calls[0]["name"] == "navigate_to"
        assert result.tool_calls[1]["name"] == "stop"


# ============================================================
# 场景 4: 多 Agent 路由 — 不同意图路由到不同 Agent
# ============================================================
class TestScenario04_MultiAgentRouting:
    """不同用户意图路由到不同 Agent"""

    def test_navigation_intent_routes_to_nav_agent(self):
        """导航意图路由到导航 Agent"""
        router = AgentRouter(
            bindings=[
                RouteBinding(agent_id="nav-agent", match_type="intent",
                             pattern="navigate_.*|patrol", priority=1),
                RouteBinding(agent_id="motion-agent", match_type="intent",
                             pattern="rotate|stop", priority=2),
            ],
            default_agent_id="general-agent",
        )

        r1 = router.resolve({"intent": "navigate_to"})
        assert r1.agent_id == "nav-agent"

        r2 = router.resolve({"intent": "patrol"})
        assert r2.agent_id == "nav-agent"

        r3 = router.resolve({"intent": "rotate"})
        assert r3.agent_id == "motion-agent"

        r4 = router.resolve({"intent": "stop"})
        assert r4.agent_id == "motion-agent"

        r5 = router.resolve({"intent": "chat"})
        assert r5.agent_id == "general-agent"

    def test_channel_based_routing(self):
        """不同通道路由到不同 Agent"""
        router = AgentRouter(
            bindings=[
                RouteBinding(agent_id="ros2-agent", match_type="channel",
                             channel="ros2_topic", priority=1),
                RouteBinding(agent_id="web-agent", match_type="channel",
                             channel="websocket", priority=2),
            ],
            default_agent_id="cli-agent",
        )

        assert router.resolve({"channel": "ros2_topic"}).agent_id == "ros2-agent"
        assert router.resolve({"channel": "websocket"}).agent_id == "web-agent"
        assert router.resolve({"channel": "cli"}).agent_id == "cli-agent"

    def test_scene_based_routing(self):
        """场景绑定路由"""
        router = AgentRouter(
            bindings=[
                RouteBinding(agent_id="kitchen-bot", match_type="scene",
                             scene="kitchen", priority=1),
                RouteBinding(agent_id="warehouse-bot", match_type="scene",
                             scene="warehouse", priority=2),
            ],
            default_agent_id="default-bot",
        )

        assert router.resolve({"scene": "kitchen"}).agent_id == "kitchen-bot"
        assert router.resolve({"scene": "warehouse"}).agent_id == "warehouse-bot"
        assert router.resolve({"scene": "hallway"}).agent_id == "default-bot"

    @pytest.mark.asyncio
    async def test_routed_sessions_are_isolated(self):
        """不同 Agent 的 Session 相互隔离"""
        router = AgentRouter(
            bindings=[
                RouteBinding(agent_id="nav-agent", match_type="channel",
                             channel="ros2", priority=1),
            ],
            default_agent_id="general-agent",
        )

        sm = SessionManager(max_concurrent=10)

        # 两个不同通道的请求
        route1 = router.resolve({"channel": "ros2"})
        route2 = router.resolve({"channel": "cli"})

        s1 = await sm.create_session(route1.agent_id, "ros2")
        s2 = await sm.create_session(route2.agent_id, "cli")

        assert s1.agent_id == "nav-agent"
        assert s2.agent_id == "general-agent"
        assert s1.session_id != s2.session_id
