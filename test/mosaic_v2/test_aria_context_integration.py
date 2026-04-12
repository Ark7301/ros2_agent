import pytest

from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.gateway.session_manager import SessionManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.plugin_sdk.types import PluginMeta, ProviderResponse, AssembleResult
from mosaic.runtime.scene_graph import SceneNode, SceneEdge, NodeType, EdgeType
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.turn_runner import TurnRunner
from mosaic.runtime.world_state_manager import (
    WorkingMemory, SemanticMemory, EpisodicMemory, WorldStateManager, TaskEpisode,
    PlanningContext,
)


@pytest.mark.asyncio
async def test_turn_runner_prefers_world_state_manager_context():
    captured_messages = []

    class CapturingProvider:
        def __init__(self):
            self.meta = PluginMeta(id="prov", name="Provider", version="0.1.0", description="", kind="provider")

        async def chat(self, messages, tools, config):
            captured_messages.append(messages)
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(id="ce", name="ContextEngine", version="0.1.0", description="", kind="context-engine")

        async def ingest(self, session_id, message):
            return None

        async def assemble(self, session_id, token_budget):
            return AssembleResult(messages=[], token_count=0)

        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    registry = PluginRegistry()
    registry.register("prov", CapturingProvider, "provider")
    registry.set_default_provider("prov")
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")

    sgm = SceneGraphManager()
    sgm._graph.add_node(SceneNode("living_room", NodeType.ROOM, "客厅", position=(0.0, 0.0)))
    sgm._graph.add_node(SceneNode("robot", NodeType.AGENT, "机器人", position=(0.0, 0.0)))
    sgm._graph.add_edge(SceneEdge("robot", "living_room", EdgeType.AT))

    wm = WorkingMemory()
    wm.update_robot_state(x=1.5, y=-0.5)
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    em.record_episode(TaskEpisode(task_description="去客厅找用户", success=True))
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    runner = TurnRunner(
        registry=registry,
        event_bus=EventBus(),
        hooks=HookManager(),
        system_prompt="BASE",
        scene_graph_mgr=sgm,
        world_state_mgr=wsm,
    )

    smgr = SessionManager()
    session = await smgr.create_session("default", "cli")
    await smgr.run_turn(session.session_id, "去客厅", runner)

    system_content = captured_messages[0][0]["content"]
    assert "BASE" in system_content
    assert "[ARIA]" in system_content
    assert "机器人状态" in system_content
    assert "相似经验" in system_content
    assert "\"task_description\"" in system_content
    assert "- 去客厅找用户" not in system_content


@pytest.mark.asyncio
async def test_turn_runner_refreshes_aria_context_after_tool_execution():
    captured_messages = []
    call_count = 0

    class CapturingProvider:
        def __init__(self):
            self.meta = PluginMeta(id="prov", name="Provider", version="0.1.0", description="", kind="provider")

        async def chat(self, messages, tools, config):
            nonlocal call_count
            captured_messages.append(messages)
            if call_count == 0:
                call_count += 1
                return ProviderResponse(
                    content="",
                    tool_calls=[{"id": "tool-1", "name": "dummy", "arguments": {}}],
                    usage={},
                )
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class DummyCapability:
        def __init__(self):
            self.meta = PluginMeta(id="cap", name="Capability", version="0.1.0", description="", kind="capability")

        def get_tool_definitions(self):
            return [{"name": "dummy", "description": "", "parameters": {"type": "object", "properties": {}}}]

        async def execute(self, name, args, ctx):
            from mosaic.plugin_sdk.types import ExecutionResult
            return ExecutionResult(success=True, message="ok")

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(id="ce", name="ContextEngine", version="0.1.0", description="", kind="context-engine")

        async def ingest(self, session_id, message):
            return None

        async def assemble(self, session_id, token_budget):
            return AssembleResult(messages=[{"role": "system", "content": "EXTERNAL SYSTEM"}], token_count=0)

        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    registry = PluginRegistry()
    registry.register("prov", CapturingProvider, "provider")
    registry.set_default_provider("prov")
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")
    registry.register("cap", DummyCapability, "capability")

    sgm = SceneGraphManager()
    sgm._graph.add_node(SceneNode("living_room", NodeType.ROOM, "客厅", position=(0.0, 0.0)))
    sgm._graph.add_node(SceneNode("robot", NodeType.AGENT, "机器人", position=(0.0, 0.0)))
    sgm._graph.add_edge(SceneEdge("robot", "living_room", EdgeType.AT))

    wm = WorkingMemory()
    wm.update_robot_state(x=1.5, y=-0.5)
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    em.record_episode(TaskEpisode(task_description="去客厅找用户", success=True))
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    runner = TurnRunner(
        registry=registry,
        event_bus=EventBus(),
        hooks=HookManager(),
        system_prompt="BASE",
        scene_graph_mgr=sgm,
        world_state_mgr=wsm,
    )

    smgr = SessionManager()
    session = await smgr.create_session("default", "cli")
    await smgr.run_turn(session.session_id, "去客厅", runner)

    assert "_turn_runner_system" not in captured_messages[0][0]
    assert len(captured_messages) >= 2
    system_content = captured_messages[1][0]["content"]
    assert "BASE" in system_content
    assert "[ARIA]" in system_content
    assert captured_messages[1][1]["content"] == "EXTERNAL SYSTEM"


@pytest.mark.asyncio
async def test_turn_runner_world_state_failure_falls_back_to_scene_graph():
    captured_messages = []

    class CapturingProvider:
        def __init__(self):
            self.meta = PluginMeta(id="prov", name="Provider", version="0.1.0", description="", kind="provider")

        async def chat(self, messages, tools, config):
            captured_messages.append(messages)
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(id="ce", name="ContextEngine", version="0.1.0", description="", kind="context-engine")

        async def ingest(self, session_id, message):
            return None

        async def assemble(self, session_id, token_budget):
            return AssembleResult(messages=[], token_count=0)

        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    registry = PluginRegistry()
    registry.register("prov", CapturingProvider, "provider")
    registry.set_default_provider("prov")
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")

    sgm = SceneGraphManager()
    sgm._graph.add_node(SceneNode("living_room", NodeType.ROOM, "客厅", position=(0.0, 0.0)))
    sgm._graph.add_node(SceneNode("robot", NodeType.AGENT, "机器人", position=(0.0, 0.0)))
    sgm._graph.add_edge(SceneEdge("robot", "living_room", EdgeType.AT))

    wm = WorkingMemory()
    wm.update_robot_state(x=1.5, y=-0.5)
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    em.record_episode(TaskEpisode(task_description="去客厅找用户", success=True))
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    def broken_assemble_context(_user_input):
        raise RuntimeError("boom")

    wsm.assemble_context = broken_assemble_context

    runner = TurnRunner(
        registry=registry,
        event_bus=EventBus(),
        hooks=HookManager(),
        system_prompt="BASE",
        scene_graph_mgr=sgm,
        world_state_mgr=wsm,
    )

    smgr = SessionManager()
    session = await smgr.create_session("default", "cli")
    await smgr.run_turn(session.session_id, "去客厅", runner)

    system_content = captured_messages[0][0]["content"]
    assert "BASE" in system_content
    assert "[场景图]" in system_content
    assert "[ARIA]" not in system_content


@pytest.mark.asyncio
async def test_turn_runner_scene_graph_fallback_keeps_system_prompt():
    captured_messages = []

    class CapturingProvider:
        def __init__(self):
            self.meta = PluginMeta(id="prov", name="Provider", version="0.1.0", description="", kind="provider")

        async def chat(self, messages, tools, config):
            captured_messages.append(messages)
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(id="ce", name="ContextEngine", version="0.1.0", description="", kind="context-engine")

        async def ingest(self, session_id, message):
            return None

        async def assemble(self, session_id, token_budget):
            return AssembleResult(messages=[], token_count=0)

        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    registry = PluginRegistry()
    registry.register("prov", CapturingProvider, "provider")
    registry.set_default_provider("prov")
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")

    sgm = SceneGraphManager()
    sgm._graph.add_node(SceneNode("living_room", NodeType.ROOM, "客厅", position=(0.0, 0.0)))
    sgm._graph.add_node(SceneNode("robot", NodeType.AGENT, "机器人", position=(0.0, 0.0)))
    sgm._graph.add_edge(SceneEdge("robot", "living_room", EdgeType.AT))

    runner = TurnRunner(
        registry=registry,
        event_bus=EventBus(),
        hooks=HookManager(),
        system_prompt="BASE",
        scene_graph_mgr=sgm,
        world_state_mgr=None,
    )

    smgr = SessionManager()
    session = await smgr.create_session("default", "cli")
    await smgr.run_turn(session.session_id, "去客厅", runner)

    system_content = captured_messages[0][0]["content"]
    assert "BASE" in system_content
    assert "[场景图]" in system_content
    assert "客厅" in system_content


@pytest.mark.asyncio
async def test_turn_runner_does_not_overwrite_system_with_empty_refresh():
    captured_messages = []
    call_count = 0
    assemble_calls = 0

    class CapturingProvider:
        def __init__(self):
            self.meta = PluginMeta(id="prov", name="Provider", version="0.1.0", description="", kind="provider")

        async def chat(self, messages, tools, config):
            nonlocal call_count
            captured_messages.append([msg.copy() for msg in messages])
            if call_count == 0:
                call_count += 1
                return ProviderResponse(
                    content="",
                    tool_calls=[{"id": "tool-1", "name": "dummy", "arguments": {}}],
                    usage={},
                )
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class DummyCapability:
        def __init__(self):
            self.meta = PluginMeta(id="cap", name="Capability", version="0.1.0", description="", kind="capability")

        def get_tool_definitions(self):
            return [{"name": "dummy", "description": "", "parameters": {"type": "object", "properties": {}}}]

        async def execute(self, name, args, ctx):
            from mosaic.plugin_sdk.types import ExecutionResult
            return ExecutionResult(success=True, message="ok")

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(id="ce", name="ContextEngine", version="0.1.0", description="", kind="context-engine")

        async def ingest(self, session_id, message):
            return None

        async def assemble(self, session_id, token_budget):
            return AssembleResult(messages=[], token_count=0)

        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    registry = PluginRegistry()
    registry.register("prov", CapturingProvider, "provider")
    registry.set_default_provider("prov")
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")
    registry.register("cap", DummyCapability, "capability")

    sgm = SceneGraphManager()
    sgm._graph.add_node(SceneNode("living_room", NodeType.ROOM, "客厅", position=(0.0, 0.0)))
    sgm._graph.add_node(SceneNode("robot", NodeType.AGENT, "机器人", position=(0.0, 0.0)))
    sgm._graph.add_edge(SceneEdge("robot", "living_room", EdgeType.AT))

    wm = WorkingMemory()
    wm.update_robot_state(x=1.5, y=-0.5)
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    em.record_episode(TaskEpisode(task_description="去客厅找用户", success=True))
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    def flaky_assemble_context(_user_input, top_k=3):
        nonlocal assemble_calls
        assemble_calls += 1
        if assemble_calls == 1:
            return PlanningContext(
                subgraph=sgm._graph,
                scene_text="场景",
                similar_episodes=[TaskEpisode(task_description="去客厅找用户", success=True)],
            )
        raise RuntimeError("boom")

    wsm.assemble_context = flaky_assemble_context

    runner = TurnRunner(
        registry=registry,
        event_bus=EventBus(),
        hooks=HookManager(),
        system_prompt="",
        scene_graph_mgr=None,
        world_state_mgr=wsm,
    )

    smgr = SessionManager()
    session = await smgr.create_session("default", "cli")
    await smgr.run_turn(session.session_id, "去客厅", runner)

    assert len(captured_messages) >= 2
    system_content = captured_messages[1][0]["content"]
    assert system_content
    assert "[ARIA]" in system_content
