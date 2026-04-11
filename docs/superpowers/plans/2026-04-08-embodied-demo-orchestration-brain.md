# Embodied Demo Orchestration Brain Implementation Plan

- title: Embodied Demo Orchestration Brain Implementation Plan
- status: active
- owner: repository-maintainers
- updated: 2026-04-08
- tags: docs, plan, aria, demo, embodied-agent, orchestration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a mature MOSAIC demo where ARIA acts as the decision-and-orchestration brain for fine-grained embodied tasks, with VLM-assisted information acquisition, replanning as the core product differentiator, shared world state, and operator-visible execution traces even when full ROS2 infrastructure is incomplete.

**Architecture:** Deepen the existing `Gateway -> TurnRunner -> Capability` loop instead of introducing a second planner stack. Make `WorldStateManager / ARIA` the primary planning context source, insert a VLM observation capability into the decision loop, define an atomic action schema aligned with future base capabilities, upgrade the stub capabilities into scene-aware mock executors, add a deterministic demo director for runtime failures and perception mismatches, and ship a scripted demo runner with canonical replanning scenarios. Real ROS2, SLAM, and full online VLM infrastructure remain optional integration slots, not prerequisites for the demo milestone.

**Tech Stack:** Python, pytest, Hypothesis-compatible test style, Markdown, YAML config, existing MOSAIC plugin SDK, SceneGraph / ARIA runtime

---

## Demo Acceptance Criteria

The milestone is done when all of the following are true:

- A single MOSAIC process can run a mock-first demo with no ROS2 requirement.
- At least one canonical scenario requires VLM observation before action choice or goal confirmation.
- Canonical scenarios are decomposed into explicit atomic tool calls rather than coarse macro-steps.
- `TurnRunner` builds its planning prompt from ARIA rather than only from `SceneGraphManager`.
- The system can complete at least three canonical scenarios:
  - `coffee_delivery`: observe kitchen scene, confirm coffee machine and cup, navigate, operate appliance, wait, pick up, deliver
  - `towel_fetch`: observe bedroom scene, confirm yellow towel, navigate, pick up, navigate to user, hand over
  - `blocked_route_replan`: detect a runtime navigation blockage or perception mismatch, refresh world state, and replan to an alternate route
- At least one scenario demonstrates runtime failure followed by successful replanning.
- At least one scenario demonstrates perception feedback forcing recovery or replanning.
- The operator can see turn-level trace output: ARIA context summary, tool calls, tool results, world updates, recalled episodes.
- Missing real infrastructure is represented by typed placeholders or blank adapters, not by crashes or undocumented gaps.

## Out Of Scope

- Real Nav2 execution as a release blocker
- Live SLAM map building as a release blocker
- Full online multi-camera VLM perception infrastructure as a release blocker
- True vector retrieval as a release blocker
- Multi-process or distributed multi-agent orchestration

## File Structure

### Create

- `mosaic/runtime/atomic_action_schema.py`
- `mosaic/runtime/planning_context_formatter.py`
- `mosaic/runtime/demo_director.py`
- `plugins/capabilities/vlm_observe/__init__.py`
- `plugins/capabilities/world_query/__init__.py`
- `config/environments/demo_home.yaml`
- `config/demo/embodied_brain.yaml`
- `config/demo/observation_frames/README.md`
- `scripts/run_embodied_demo.py`
- `docs/dev/runbooks/embodied-demo.md`
- `test/mosaic_v2/test_atomic_action_schema.py`
- `test/mosaic_v2/test_aria_context_integration.py`
- `test/mosaic_v2/test_vlm_observe_capability.py`
- `test/mosaic_v2/test_scene_aware_mock_capabilities.py`
- `test/mosaic_v2/test_world_query_capability.py`
- `test/mosaic_v2/test_turn_runner_episodic_loop.py`
- `test/mosaic_v2/test_embodied_demo_e2e.py`

### Modify

- `mosaic/gateway/server.py`
- `mosaic/runtime/scene_analyzer.py`
- `mosaic/runtime/turn_runner.py`
- `mosaic/runtime/world_state_manager.py`
- `plugins/capabilities/navigation/__init__.py`
- `plugins/capabilities/manipulation/__init__.py`
- `plugins/capabilities/appliance/__init__.py`
- `config/mosaic.yaml`
- `docs/dev/README.md`

---

## CTO Review Priority Changes

The current plan is revised by three non-negotiable priority changes:

1. **VLM must participate in the decision loop**
The demo may keep infrastructure mock-first, but it may not remain information-mock-only. Use fixture-backed or cached VLM observations if live camera streaming is unavailable.

2. **Task orchestration must be atomic**
The planner must operate on fine-grained capability units that align with future base abilities, not opaque high-level macros.

3. **Replanning is the hero capability**
The flagship scenario is no longer “basic happy-path completion”, but “failure feedback -> context refresh -> successful recovery”.

## Atomic Orchestration Contract

All canonical scenarios should be decomposed into explicit atomic actions. The minimum atomic catalog for this phase is:

- `observe_scene`
- `confirm_object`
- `locate_target`
- `navigate_to`
- `rotate`
- `operate_appliance`
- `wait_appliance`
- `pick_up`
- `hand_over`
- `verify_goal`

The first execution slices should therefore be interpreted in this order:

1. define the atomic action schema
2. add the VLM observation capability
3. make ARIA the primary context source
4. make mock capabilities world-aware
5. harden feedback-driven replanning

---

### Task 1: Make ARIA The Primary Planning Context Source

**Files:**
- Create: `mosaic/runtime/planning_context_formatter.py`
- Modify: `mosaic/runtime/world_state_manager.py`
- Modify: `mosaic/runtime/turn_runner.py`
- Modify: `mosaic/gateway/server.py`
- Test: `test/mosaic_v2/test_aria_context_integration.py`

- [ ] **Step 1: Write the failing integration test for ARIA prompt assembly**

Add this exact test to `test/mosaic_v2/test_aria_context_integration.py`:

```python
import pytest

from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.gateway.session_manager import SessionManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.plugin_sdk.types import (
    PluginMeta, ProviderResponse, AssembleResult,
)
from mosaic.runtime.scene_graph import SceneNode, SceneEdge, NodeType, EdgeType
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.turn_runner import TurnRunner
from mosaic.runtime.world_state_manager import (
    WorkingMemory, SemanticMemory, EpisodicMemory, WorldStateManager, TaskEpisode,
)


@pytest.mark.asyncio
async def test_turn_runner_prefers_world_state_manager_context():
    captured_messages = []

    class CapturingProvider:
        def __init__(self):
            self.meta = PluginMeta(
                id="prov", name="Provider", version="0.1.0",
                description="", kind="provider",
            )

        async def chat(self, messages, tools, config):
            captured_messages.append(messages)
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(
                id="ce", name="ContextEngine", version="0.1.0",
                description="", kind="context-engine",
            )

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
    assert "[ARIA]" in system_content
    assert "机器人状态" in system_content
    assert "相似经验" in system_content
```

- [ ] **Step 2: Run the test and confirm it fails for the right reason**

Run:

```bash
pytest test/mosaic_v2/test_aria_context_integration.py -q
```

Expected: FAIL because `TurnRunner` does not yet accept `world_state_mgr` and does not render ARIA-specific context.

- [ ] **Step 3: Add a dedicated formatter for ARIA planning context**

Create `mosaic/runtime/planning_context_formatter.py` with this exact code:

```python
from __future__ import annotations

from mosaic.runtime.world_state_manager import PlanningContext, RobotState


class PlanningContextFormatter:
    """将 ARIA 规划上下文稳定渲染为 LLM 可读文本。"""

    def render(self, robot_state: RobotState, context: PlanningContext) -> str:
        if context.similar_episodes:
            episode_lines = [
                f"- {ep.task_description} | {'成功' if ep.success else '失败'}"
                for ep in context.similar_episodes
            ]
            similar_text = "\n".join(episode_lines)
        else:
            similar_text = "- 无"

        return (
            "[ARIA]\n"
            "机器人状态:\n"
            f"- position=({robot_state.x:.2f}, {robot_state.y:.2f})\n"
            "场景上下文:\n"
            f"{context.scene_text}\n"
            "相似经验:\n"
            f"{similar_text}"
        )
```

- [ ] **Step 4: Wire `TurnRunner` and `GatewayServer` to use `WorldStateManager` first**

Update `mosaic/runtime/turn_runner.py` constructor and prompt assembly to this shape:

```python
from mosaic.runtime.planning_context_formatter import PlanningContextFormatter


class TurnRunner:
    def __init__(
        self,
        registry,
        event_bus,
        hooks,
        max_iterations: int = 10,
        turn_timeout_s: float = 120,
        system_prompt: str = "",
        scene_graph_mgr=None,
        world_state_mgr=None,
    ):
        self._registry = registry
        self._event_bus = event_bus
        self._hooks = hooks
        self._max_iterations = max_iterations
        self._turn_timeout_s = turn_timeout_s
        self._system_prompt = system_prompt
        self._scene_graph_mgr = scene_graph_mgr
        self._world_state_mgr = world_state_mgr
        self._context_formatter = PlanningContextFormatter()

    def _build_system_content(self, user_input: str) -> str:
        if self._world_state_mgr:
            planning_context = self._world_state_mgr.assemble_context(user_input)
            robot_state = self._world_state_mgr.working.get_robot_state()
            aria_text = self._context_formatter.render(robot_state, planning_context)
            return f"{self._system_prompt}\n\n{aria_text}" if self._system_prompt else aria_text
        if self._scene_graph_mgr:
            scene_text = self._scene_graph_mgr.get_scene_prompt(user_input)
            return f"{self._system_prompt}\n\n{scene_text}" if self._system_prompt else scene_text
        return self._system_prompt
```

Update `mosaic/gateway/server.py` to pass `world_state_mgr=self._world_state_mgr` into `TurnRunner(...)`.

- [ ] **Step 5: Run the focused tests to verify ARIA prompt integration**

Run:

```bash
pytest test/mosaic_v2/test_aria_context_integration.py test/mosaic_v2/test_gateway_scene_init.py -q
```

Expected: PASS, including the new ARIA prompt test and the existing gateway injection tests.

- [ ] **Step 6: Commit the slice**

Run:

```bash
git add \
  mosaic/runtime/planning_context_formatter.py \
  mosaic/runtime/turn_runner.py \
  mosaic/gateway/server.py \
  test/mosaic_v2/test_aria_context_integration.py
git commit -m "feat: make aria the primary planning context source"
```

---

### Task 2: Upgrade Mock Capabilities Into A Shared Demo World Layer

**Files:**
- Create: `mosaic/runtime/demo_director.py`
- Modify: `plugins/capabilities/navigation/__init__.py`
- Modify: `plugins/capabilities/manipulation/__init__.py`
- Modify: `plugins/capabilities/appliance/__init__.py`
- Modify: `mosaic/gateway/server.py`
- Modify: `config/mosaic.yaml`
- Test: `test/mosaic_v2/test_scene_aware_mock_capabilities.py`

- [ ] **Step 1: Write failing tests for scene-aware mock behavior**

Add these exact tests to `test/mosaic_v2/test_scene_aware_mock_capabilities.py`:

```python
import pytest

from mosaic.plugin_sdk.types import ExecutionContext
from mosaic.runtime.scene_graph import SceneNode, SceneEdge, NodeType, EdgeType
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from plugins.capabilities.manipulation import ManipulationCapability
from plugins.capabilities.navigation import NavigationCapability
from mosaic.runtime.demo_director import DemoDirector, DirectedFailure
from mosaic.runtime.spatial_provider import SpatialProvider


def _build_scene():
    sgm = SceneGraphManager()
    g = sgm.get_full_graph()
    g.add_node(SceneNode("living_room", NodeType.ROOM, "客厅", position=(0.0, 0.0)))
    g.add_node(SceneNode("kitchen", NodeType.ROOM, "厨房", position=(5.0, 0.0)))
    g.add_edge(SceneEdge("living_room", "kitchen", EdgeType.REACHABLE))
    g.add_edge(SceneEdge("kitchen", "living_room", EdgeType.REACHABLE))
    g.add_node(SceneNode("robot", NodeType.AGENT, "机器人"))
    g.add_edge(SceneEdge("robot", "living_room", EdgeType.AT))
    g.add_node(SceneNode("cup", NodeType.OBJECT, "水杯", affordances=["graspable"]))
    g.add_edge(SceneEdge("kitchen", "cup", EdgeType.CONTAINS))
    return sgm


@pytest.mark.asyncio
async def test_pick_up_fails_when_robot_is_not_with_object():
    sgm = _build_scene()
    cap = ManipulationCapability(scene_graph_mgr=sgm)
    result = await cap.execute(
        "pick_up",
        {"object_name": "水杯"},
        ExecutionContext(session_id="s1"),
    )
    assert result.success is False
    assert "同一位置" in (result.error or "")


@pytest.mark.asyncio
async def test_navigation_can_fail_once_via_demo_director():
    sgm = _build_scene()
    director = DemoDirector([
        DirectedFailure(
            tool_name="navigate_to",
            match_params={"target": "厨房"},
            error="厨房门口临时被箱子堵住",
            remaining_hits=1,
            replan_hint="改走客厅东侧通道",
        )
    ])
    cap = NavigationCapability(
        spatial_provider=SpatialProvider(sgm.get_full_graph()),
        scene_graph_mgr=sgm,
        demo_director=director,
    )
    first = await cap.execute("navigate_to", {"target": "厨房"}, ExecutionContext(session_id="s1"))
    second = await cap.execute("navigate_to", {"target": "厨房"}, ExecutionContext(session_id="s1"))
    assert first.success is False
    assert second.success is True
```

- [ ] **Step 2: Run the test and confirm current stubs are too shallow**

Run:

```bash
pytest test/mosaic_v2/test_scene_aware_mock_capabilities.py -q
```

Expected: FAIL because the capability constructors do not yet accept scene/demo dependencies and currently return unconditional success.

- [ ] **Step 3: Add a deterministic demo director for runtime failures**

Create `mosaic/runtime/demo_director.py` with this exact code:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DirectedFailure:
    tool_name: str
    match_params: dict[str, Any]
    error: str
    remaining_hits: int = 1
    replan_hint: str = ""
    scene_patch: dict[str, Any] = field(default_factory=dict)


class DemoDirector:
    def __init__(self, failures: list[DirectedFailure] | None = None) -> None:
        self._failures = failures or []

    def maybe_fail(self, tool_name: str, params: dict[str, Any]) -> DirectedFailure | None:
        for failure in self._failures:
            if failure.tool_name != tool_name:
                continue
            if all(params.get(k) == v for k, v in failure.match_params.items()) and failure.remaining_hits > 0:
                failure.remaining_hits -= 1
                return failure
        return None
```

- [ ] **Step 4: Make navigation, manipulation, and appliance mocks scene-aware**

Update the capability constructors and mock execution paths to this exact shape:

```python
class NavigationCapability:
    def __init__(
        self,
        ros_node=None,
        spatial_provider=None,
        scene_graph_mgr=None,
        demo_director=None,
    ) -> None:
        self._ros_node = ros_node
        self._spatial = spatial_provider
        self._scene_graph_mgr = scene_graph_mgr
        self._demo_director = demo_director

    async def _execute_navigate_to(self, params: dict) -> ExecutionResult:
        target = params.get("target", "")
        directed_failure = self._demo_director.maybe_fail("navigate_to", params) if self._demo_director else None
        if directed_failure is not None:
            return ExecutionResult(
                success=False,
                error=directed_failure.error,
                data={
                    "replan_hint": directed_failure.replan_hint,
                    "scene_patch": directed_failure.scene_patch,
                },
            )
        if not self._is_nav2_mode:
            return ExecutionResult(success=True, data={"target": target}, message=f"已导航到 {target}")
        ...
```

```python
class ManipulationCapability:
    def __init__(self, scene_graph_mgr=None) -> None:
        self._scene_graph_mgr = scene_graph_mgr

    def _execute_pick_up(self, params: dict) -> ExecutionResult:
        obj = params.get("object_name", "")
        if self._scene_graph_mgr:
            graph = self._scene_graph_mgr.get_full_graph()
            agent_loc = graph.get_agent_location()
            obj_nodes = graph.find_by_label(obj)
            obj_loc = graph.get_location_of(obj_nodes[0].node_id) if obj_nodes else None
            if not agent_loc or not obj_loc or agent_loc.node_id != obj_loc.node_id:
                return ExecutionResult(success=False, error=f"机器人与 {obj} 不在同一位置")
        return ExecutionResult(success=True, data={"object_name": obj}, message=f"已拿取 {obj}")
```

Apply the same pattern to `ApplianceCapability`: if `scene_graph_mgr` exists, fail when the robot is not co-located with the appliance; otherwise keep the current stub success path.

Update `mosaic/gateway/server.py` mock-mode configuration to inject `scene_graph_mgr` and `demo_director` into those three plugins when `ros2.enabled` is false. Add a `demo:` section to `config/mosaic.yaml`:

```yaml
demo:
  enabled: true
  scenario_file: "config/demo/embodied_brain.yaml"
```

- [ ] **Step 5: Run focused capability tests**

Run:

```bash
pytest test/mosaic_v2/test_scene_aware_mock_capabilities.py test/mosaic_v2/test_spatial_provider.py -q
```

Expected: PASS, including the new scene-aware mock tests and the existing spatial provider coverage.

- [ ] **Step 6: Commit the slice**

Run:

```bash
git add \
  mosaic/runtime/demo_director.py \
  plugins/capabilities/navigation/__init__.py \
  plugins/capabilities/manipulation/__init__.py \
  plugins/capabilities/appliance/__init__.py \
  mosaic/gateway/server.py \
  config/mosaic.yaml \
  test/mosaic_v2/test_scene_aware_mock_capabilities.py
git commit -m "feat: upgrade mock capabilities into a shared demo world layer"
```

---

### Task 3: Add A World Query Capability Backed By ARIA

**Files:**
- Create: `plugins/capabilities/world_query/__init__.py`
- Modify: `mosaic/gateway/server.py`
- Test: `test/mosaic_v2/test_world_query_capability.py`

- [ ] **Step 1: Write failing tests for ARIA-backed world queries**

Add this exact test file at `test/mosaic_v2/test_world_query_capability.py`:

```python
import pytest

from mosaic.plugin_sdk.types import ExecutionContext
from mosaic.runtime.scene_graph import SceneNode, SceneEdge, NodeType, EdgeType
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.world_state_manager import (
    WorkingMemory, SemanticMemory, EpisodicMemory, WorldStateManager,
)
from plugins.capabilities.world_query import WorldQueryCapability


def _build_world_state_manager():
    sgm = SceneGraphManager()
    g = sgm.get_full_graph()
    g.add_node(SceneNode("kitchen", NodeType.ROOM, "厨房", position=(1.0, 2.0)))
    g.add_node(SceneNode("robot", NodeType.AGENT, "机器人", position=(1.0, 2.0)))
    g.add_edge(SceneEdge("robot", "kitchen", EdgeType.AT))
    g.add_node(SceneNode("cup", NodeType.OBJECT, "水杯", affordances=["graspable"]))
    g.add_edge(SceneEdge("kitchen", "cup", EdgeType.CONTAINS))
    return WorldStateManager(
        working=WorkingMemory(),
        semantic=SemanticMemory(sgm),
        episodic=EpisodicMemory(),
    )


@pytest.mark.asyncio
async def test_locate_object_returns_room_and_label():
    cap = WorldQueryCapability(world_state_mgr=_build_world_state_manager())
    result = await cap.execute(
        "locate_object",
        {"object_name": "水杯"},
        ExecutionContext(session_id="s1"),
    )
    assert result.success is True
    assert result.data["object_label"] == "水杯"
    assert result.data["room_label"] == "厨房"


@pytest.mark.asyncio
async def test_check_goal_status_reports_agent_location():
    cap = WorldQueryCapability(world_state_mgr=_build_world_state_manager())
    result = await cap.execute(
        "check_goal_status",
        {"goal": "机器人现在在哪里"},
        ExecutionContext(session_id="s1"),
    )
    assert result.success is True
    assert "厨房" in result.message
```

- [ ] **Step 2: Run the tests and confirm the plugin is missing**

Run:

```bash
pytest test/mosaic_v2/test_world_query_capability.py -q
```

Expected: FAIL because `world_query` capability does not yet exist.

- [ ] **Step 3: Implement the new capability plugin**

Create `plugins/capabilities/world_query/__init__.py` with this exact code:

```python
from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta, ExecutionContext, ExecutionResult, HealthStatus, HealthState,
)


class WorldQueryCapability:
    def __init__(self, world_state_mgr=None) -> None:
        self.meta = PluginMeta(
            id="world-query",
            name="World Query",
            version="0.1.0",
            description="ARIA-backed world inspection tools for demo reasoning",
            kind="capability",
            author="MOSAIC",
        )
        self._world_state_mgr = world_state_mgr

    def get_supported_intents(self) -> list[str]:
        return ["inspect_scene", "locate_object", "check_goal_status"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "inspect_scene",
                "description": "查看当前任务相关场景摘要",
                "parameters": {"type": "object", "properties": {"focus": {"type": "string"}}},
            },
            {
                "name": "locate_object",
                "description": "定位某个物品当前在哪个房间或容器内",
                "parameters": {
                    "type": "object",
                    "properties": {"object_name": {"type": "string"}},
                    "required": ["object_name"],
                },
            },
            {
                "name": "check_goal_status",
                "description": "检查当前目标是否已满足，或查询机器人当前状态",
                "parameters": {
                    "type": "object",
                    "properties": {"goal": {"type": "string"}},
                    "required": ["goal"],
                },
            },
        ]

    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult:
        graph = self._world_state_mgr.semantic._sgm.get_full_graph()
        if intent == "inspect_scene":
            focus = params.get("focus", "")
            return ExecutionResult(success=True, message=self._world_state_mgr.semantic._sgm.get_scene_prompt(focus))
        if intent == "locate_object":
            name = params.get("object_name", "")
            nodes = graph.find_by_label(name)
            if not nodes:
                return ExecutionResult(success=False, error=f"未找到物品: {name}")
            room = graph.get_location_of(nodes[0].node_id)
            return ExecutionResult(
                success=True,
                data={"object_label": nodes[0].label, "room_label": room.label if room else "未知"},
                message=f"{nodes[0].label} 当前位于 {room.label if room else '未知位置'}",
            )
        if intent == "check_goal_status":
            robot_room = graph.get_agent_location()
            return ExecutionResult(
                success=True,
                data={"robot_room": robot_room.label if robot_room else "未知"},
                message=f"机器人当前位于 {robot_room.label if robot_room else '未知位置'}",
            )
        return ExecutionResult(success=False, error=f"不支持的意图: {intent}")

    async def cancel(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, message="world query 插件正常")


def create_plugin(world_state_mgr=None) -> WorldQueryCapability:
    return WorldQueryCapability(world_state_mgr=world_state_mgr)
```

- [ ] **Step 4: Inject `world_state_mgr` into the new plugin**

Update `mosaic/gateway/server.py` after `WorldStateManager` initialization:

```python
if self._world_state_mgr:
    self._registry.configure_plugin(
        "world-query",
        world_state_mgr=self._world_state_mgr,
    )
```

- [ ] **Step 5: Run plugin and registry tests**

Run:

```bash
pytest test/mosaic_v2/test_world_query_capability.py test/mosaic_v2/test_plugin_registry_kwargs.py -q
```

Expected: PASS, confirming both the new plugin behavior and injected constructor kwargs.

- [ ] **Step 6: Commit the slice**

Run:

```bash
git add \
  plugins/capabilities/world_query/__init__.py \
  mosaic/gateway/server.py \
  test/mosaic_v2/test_world_query_capability.py
git commit -m "feat: add aria-backed world query capability"
```

---

### Task 4: Record Episodes And Feed Runtime Failures Back Into Replanning

**Files:**
- Modify: `mosaic/runtime/world_state_manager.py`
- Modify: `mosaic/runtime/turn_runner.py`
- Modify: `config/mosaic.yaml`
- Test: `test/mosaic_v2/test_turn_runner_episodic_loop.py`

- [ ] **Step 1: Write a failing test for runtime feedback and episode reuse**

Add this exact test file at `test/mosaic_v2/test_turn_runner_episodic_loop.py`:

```python
import pytest

from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.gateway.session_manager import SessionManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.plugin_sdk.types import (
    PluginMeta, ProviderResponse, AssembleResult, ExecutionResult,
)
from mosaic.runtime.scene_graph import SceneNode, SceneEdge, NodeType, EdgeType
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.turn_runner import TurnRunner
from mosaic.runtime.world_state_manager import (
    WorkingMemory, SemanticMemory, EpisodicMemory, WorldStateManager,
)


@pytest.mark.asyncio
async def test_turn_runner_records_episode_and_reuses_it():
    captured = []

    class ContextEngine:
        def __init__(self):
            self.meta = PluginMeta(id="ce", name="ce", version="0.1.0", description="", kind="context-engine")
        async def ingest(self, session_id, message):
            return None
        async def assemble(self, session_id, token_budget):
            return AssembleResult(messages=[], token_count=0)
        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    class Provider:
        def __init__(self):
            self.meta = PluginMeta(id="prov", name="prov", version="0.1.0", description="", kind="provider")
            self.call_count = 0
        async def chat(self, messages, tools, config):
            captured.append(messages)
            self.call_count += 1
            if self.call_count == 1:
                return ProviderResponse(content="", tool_calls=[{
                    "id": "c1", "name": "navigate_to", "arguments": {"target": "厨房"}
                }], usage={})
            return ProviderResponse(content="已完成", tool_calls=[], usage={})
        async def stream(self, messages, tools, config):
            yield ProviderResponse(content="已完成", tool_calls=[], usage={})
        async def validate_auth(self):
            return True

    class NavCap:
        def __init__(self):
            self.meta = PluginMeta(id="navigation", name="nav", version="0.1.0", description="", kind="capability")
        def get_supported_intents(self):
            return ["navigate_to"]
        def get_tool_definitions(self):
            return [{"name": "navigate_to", "description": "导航", "parameters": {"type": "object", "properties": {"target": {"type": "string"}}}}]
        async def execute(self, intent, params, ctx):
            return ExecutionResult(success=True, message=f"已导航到 {params['target']}")
        async def cancel(self):
            return True
        async def health_check(self):
            return None

    registry = PluginRegistry()
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")
    registry.register("prov", Provider, "provider")
    registry.set_default_provider("prov")
    registry.register("navigation", NavCap, "capability")

    sgm = SceneGraphManager()
    g = sgm.get_full_graph()
    g.add_node(SceneNode("kitchen", NodeType.ROOM, "厨房", position=(1.0, 1.0)))
    g.add_node(SceneNode("robot", NodeType.AGENT, "机器人"))
    g.add_edge(SceneEdge("robot", "kitchen", EdgeType.AT))

    wsm = WorldStateManager(
        working=WorkingMemory(),
        semantic=SemanticMemory(sgm),
        episodic=EpisodicMemory(),
    )

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
    await smgr.run_turn(session.session_id, "去厨房", runner)

    recalled = wsm.episodic.recall_similar("去厨房")
    assert recalled, "首轮任务完成后应写入情景记忆"
```

- [ ] **Step 2: Run the test and confirm there is no episode write-back**

Run:

```bash
pytest test/mosaic_v2/test_turn_runner_episodic_loop.py -q
```

Expected: FAIL because turns are not yet recorded into `EpisodicMemory`.

- [ ] **Step 3: Add bounded episode recording helpers to ARIA**

Update `mosaic/runtime/world_state_manager.py` to this exact shape:

```python
class EpisodicMemory:
    def __init__(self, time_decay_factor: float = 0.95, max_episodes: int = 1000) -> None:
        self._episodes: list[TaskEpisode] = []
        self._time_decay_factor = time_decay_factor
        self._max_episodes = max_episodes

    def record_episode(self, episode: TaskEpisode) -> None:
        if episode.timestamp == 0.0:
            episode.timestamp = time.time()
        self._episodes.append(episode)
        if len(self._episodes) > self._max_episodes:
            self._episodes = self._episodes[-self._max_episodes:]


class WorldStateManager:
    def record_turn_episode(
        self,
        task_description: str,
        tool_calls: list[dict],
        execution_results: list,
        success: bool,
        failure_reason: str = "",
    ) -> None:
        self.episodic.record_episode(TaskEpisode(
            task_description=task_description,
            plan_steps=[{"action": tc.get("name", ""), "arguments": tc.get("arguments", {})} for tc in tool_calls],
            success=success,
            failure_reason=failure_reason,
            scene_snapshot_summary={"scene_text": self.semantic._sgm.get_scene_prompt(task_description)},
        ))
```

Read `aria.episodic.max_episodes` in `mosaic/gateway/server.py` when constructing `EpisodicMemory`, and add it explicitly to `config/mosaic.yaml` if missing.

- [ ] **Step 4: Update `TurnRunner` to append structured execution feedback and record turns**

Add this exact logic to `mosaic/runtime/turn_runner.py`:

```python
def _build_feedback_message(self, tool_name: str, result: ExecutionResult) -> str:
    hint = ""
    if isinstance(result.data, dict):
        hint = result.data.get("replan_hint", "")
    base = result.message if result.success else (result.error or "执行失败")
    if hint:
        base = f"{base}\n建议: {hint}"
    return f"[执行反馈]\n工具: {tool_name}\n结果: {base}"
```

After each tool result:

```python
if isinstance(tr, ExecutionResult) and not tr.success:
    messages.append({
        "role": "system",
        "content": self._build_feedback_message(tc["name"], tr),
    })
    if self._world_state_mgr:
        messages[0]["content"] = self._build_system_content(user_input)
```

Before returning success and before re-raising failure, record the episode:

```python
if self._world_state_mgr:
    self._world_state_mgr.record_turn_episode(
        task_description=user_input,
        tool_calls=all_tool_calls,
        execution_results=all_results,
        success=True,
    )
```

and in the exception path:

```python
if self._world_state_mgr:
    self._world_state_mgr.record_turn_episode(
        task_description=user_input,
        tool_calls=all_tool_calls,
        execution_results=all_results,
        success=False,
        failure_reason=str(e),
    )
```

- [ ] **Step 5: Run turn-loop and memory tests**

Run:

```bash
pytest \
  test/mosaic_v2/test_turn_runner_episodic_loop.py \
  test/mosaic_v2/test_world_state_manager.py \
  test/mosaic_v2/test_turn_runner.py -q
```

Expected: PASS, confirming turn-level episode write-back and no regression in the existing turn loop.

- [ ] **Step 6: Commit the slice**

Run:

```bash
git add \
  mosaic/runtime/world_state_manager.py \
  mosaic/runtime/turn_runner.py \
  config/mosaic.yaml \
  test/mosaic_v2/test_turn_runner_episodic_loop.py
git commit -m "feat: record episodes and feed execution feedback into replanning"
```

---

### Task 5: Ship The Mature Mock-First Demo Surface

**Files:**
- Create: `config/environments/demo_home.yaml`
- Create: `config/demo/embodied_brain.yaml`
- Create: `scripts/run_embodied_demo.py`
- Create: `docs/dev/runbooks/embodied-demo.md`
- Create: `test/mosaic_v2/test_embodied_demo_e2e.py`
- Modify: `docs/dev/README.md`

- [ ] **Step 1: Write a failing end-to-end demo test for the coffee scenario**

Add this exact test to `test/mosaic_v2/test_embodied_demo_e2e.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_embodied_demo_coffee_delivery_script_exists_and_is_loadable():
    from pathlib import Path

    assert Path("config/environments/demo_home.yaml").exists()
    assert Path("config/demo/embodied_brain.yaml").exists()
    assert Path("scripts/run_embodied_demo.py").exists()
```

- [ ] **Step 2: Run the test and confirm the demo assets do not exist**

Run:

```bash
pytest test/mosaic_v2/test_embodied_demo_e2e.py -q
```

Expected: FAIL because the demo config and runner files are not yet present.

- [ ] **Step 3: Create the canonical demo environment and scenario pack**

Create `config/environments/demo_home.yaml` with this exact content:

```yaml
environment:
  name: demo_home
  rooms:
    - id: living_room
      label: 客厅
      position: [0.0, 0.0]
      furniture:
        - id: sofa
          label: 沙发
    - id: kitchen
      label: 厨房
      position: [4.0, 0.0]
      furniture:
        - id: coffee_machine
          type: appliance
          label: 咖啡机
          state:
            power: "off"
            status: "idle"
        - id: mug
          label: 咖啡杯
          objects:
            - id: coffee_cup
              label: 水杯
              affordances: ["graspable"]
    - id: bedroom
      label: 卧室
      position: [0.0, 4.0]
      furniture:
        - id: towel_rack
          label: 毛巾架
          objects:
            - id: yellow_towel
              label: 黄色毛巾
              affordances: ["graspable"]
  connections:
    - [living_room, kitchen]
    - [living_room, bedroom]
  agents:
    - id: robot
      label: 机器人
      at: living_room
  people:
    - id: user
      label: 用户
      at: living_room
```

Create `config/demo/embodied_brain.yaml` with this exact content:

```yaml
scenarios:
  coffee_delivery:
    user_input: "去厨房做一杯咖啡送给我"
    directed_failures: []
  towel_fetch:
    user_input: "去卧室拿黄色毛巾给我"
    directed_failures: []
  blocked_route_replan:
    user_input: "去厨房拿水杯给我"
    directed_failures:
      - tool_name: navigate_to
        match_params:
          target: 厨房
        error: "厨房正门被杂物堵住"
        replan_hint: "改走客厅侧门，再尝试进入厨房"
        remaining_hits: 1
```

- [ ] **Step 4: Add the demo runner and operator runbook**

Create `scripts/run_embodied_demo.py` with this exact scaffold:

```python
from __future__ import annotations

import argparse
import asyncio
import yaml

from mosaic.gateway.server import GatewayServer


async def _run(scenario_name: str) -> None:
    with open("config/demo/embodied_brain.yaml", "r", encoding="utf-8") as f:
        scenario_file = yaml.safe_load(f)
    scenario = scenario_file["scenarios"][scenario_name]

    server = GatewayServer(config_path="config/mosaic.yaml")
    try:
        await server.start()
        session = await server.session_manager.create_session("default", "cli")
        result = await server.session_manager.run_turn(
            session.session_id,
            scenario["user_input"],
            server.turn_runner,
        )
        print("=== DEMO RESULT ===")
        print(result.response)
        print("=== TOOL CALLS ===")
        for tc in result.tool_calls:
            print(tc)
    finally:
        await server.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True)
    args = parser.parse_args()
    asyncio.run(_run(args.scenario))


if __name__ == "__main__":
    main()
```

Create `docs/dev/runbooks/embodied-demo.md` with these sections:

````md
# Embodied Demo Runbook

## Purpose

Run the mock-first ARIA-centered orchestration demo without requiring ROS2, SLAM, or full live VLM infrastructure.

## Scenarios

- `coffee_delivery`
- `towel_fetch`
- `blocked_route_replan`

## Command

```bash
python scripts/run_embodied_demo.py --scenario coffee_delivery
```

## Expected Operator Signals

- ARIA context is visible in logs
- tool calls are printed in execution order
- failure-and-replan scenario shows at least one failed tool before recovery

## Real Infrastructure Blanks

- ROS2 SensorBridge integration remains optional
- Continuous live VLM scene updates remain optional, but at least one VLM observation step is required in the demo loop
- vector retrieval remains optional
````

Update `docs/dev/README.md` to include `runbooks/embodied-demo.md` in `Key Documents`.

- [ ] **Step 5: Run the demo asset and docs checks**

Run:

```bash
pytest test/mosaic_v2/test_embodied_demo_e2e.py -q
python scripts/run_embodied_demo.py --scenario coffee_delivery
```

Expected:

- `pytest` reports PASS.
- The demo runner prints a final response plus a non-empty tool call list.

- [ ] **Step 6: Commit the slice**

Run:

```bash
git add \
  config/environments/demo_home.yaml \
  config/demo/embodied_brain.yaml \
  scripts/run_embodied_demo.py \
  docs/dev/runbooks/embodied-demo.md \
  docs/dev/README.md \
  test/mosaic_v2/test_embodied_demo_e2e.py
git commit -m "feat: ship the mature mock-first embodied demo surface"
```

---

## Final Verification

- [ ] Run the full focused demo test suite:

```bash
pytest \
  test/mosaic_v2/test_aria_context_integration.py \
  test/mosaic_v2/test_scene_aware_mock_capabilities.py \
  test/mosaic_v2/test_world_query_capability.py \
  test/mosaic_v2/test_turn_runner_episodic_loop.py \
  test/mosaic_v2/test_embodied_demo_e2e.py -q
```

Expected: PASS with all new demo-slice tests green.

- [ ] Run one operator-facing end-to-end scenario:

```bash
python scripts/run_embodied_demo.py --scenario blocked_route_replan
```

Expected:

- one failed tool result is printed first
- a follow-up successful path or alternate action is printed afterward
- final assistant response indicates recovery or completion

- [ ] Capture the final demo proof bundle:

```bash
git status --short
```

Expected: clean working tree before handing the demo branch back for review.
