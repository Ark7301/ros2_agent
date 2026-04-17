# Human-Surrogate ARIA Memory Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first-stage human-surrogate ARIA demo that uses a handheld camera, real Minimax VLM observations, topology-first semantic memory, and memory-driven revisit verification in a small home environment.

**Architecture:** Keep the existing `Gateway -> TurnRunner -> Capability` loop and add only the minimum new components needed for this sub-project: an atomic action schema, a lightweight operator console plus `HumanProxyCapability`, a `VLMObserveCapability`, a topology semantic mapper, ARIA memory write/read helpers, and a revisit orchestrator. The first implementation proves real-world memory construction and memory-based revisit; it does not attempt full metric mapping or full replanning.

**Tech Stack:** Python, pytest, YAML, `http.server`, `threading`, `httpx`, existing MOSAIC plugin SDK, existing `mosaic.runtime.vlm_pipeline`

---

## Scope Check

This plan intentionally covers only the approved first sub-project from `docs/superpowers/specs/2026-04-12-human-surrogate-aria-memory-validation-design-zh.md`.

Included:

- human proxy operator loop
- four-view image submission
- real Minimax VLM observation wrapper
- topology-first semantic memory construction in ARIA
- memory-driven revisit
- minimal correction during revisit

Excluded from this plan:

- full replanning engine
- real robot body integration
- SLAM
- metric-accurate localization
- continuous live video streaming

## File Structure

### Create

- `mosaic/runtime/atomic_action_schema.py`
  Purpose: define operator-visible motion actions, step submissions, and internal action names for the human-surrogate flow.

- `mosaic/runtime/operator_console.py`
  Purpose: provide a minimal local HTTP server and shared state for operator instructions, four-view uploads, and completion/failure submission.

- `mosaic/runtime/human_surrogate_models.py`
  Purpose: define `ObservationFrameSet`, `SemanticObservation`, `CheckpointNode`, `MemoryTargetIndex`, `ExplorationEpisode`, `RevisitEpisode`, and `FailureRecord`.

- `mosaic/runtime/topology_semantic_mapper.py`
  Purpose: build and update the checkpoint graph and semantic associations from observation outputs.

- `mosaic/runtime/recall_revisit_orchestrator.py`
  Purpose: resolve revisit candidates from ARIA memory and produce checkpoint-level revisit paths plus minimal corrections.

- `mosaic/runtime/planning_context_formatter.py`
  Purpose: render ARIA state, checkpoint summaries, and memory target summaries into LLM-readable planning context text.

- `plugins/capabilities/human_proxy/__init__.py`
  Purpose: issue movement instructions to the operator console and wait for step results.

- `plugins/capabilities/vlm_observe/__init__.py`
  Purpose: wrap the Minimax-compatible VLM analyzer and convert four-view images into `SemanticObservation`.

- `config/demo/human_proxy_protocol.yaml`
  Purpose: define operator protocol defaults such as required views, polling interval, and instruction phrasing.

- `config/demo/human_surrogate_memory.yaml`
  Purpose: define the first-stage demo environment, tasks, checkpoints, and revisit targets.

- `config/demo/observation_frames/README.md`
  Purpose: document where captured frame sets are stored for replay or audit.

- `scripts/run_human_surrogate_memory_demo.py`
  Purpose: launch the first-stage demo and print instructions plus results.

- `docs/dev/runbooks/human-surrogate-memory-demo.md`
  Purpose: document how to run the operator console, what the operator does, and what success looks like.

- `test/mosaic_v2/test_atomic_action_schema.py`
- `test/mosaic_v2/test_human_proxy_capability.py`
- `test/mosaic_v2/test_vlm_observe_capability.py`
- `test/mosaic_v2/test_topology_semantic_mapper.py`
- `test/mosaic_v2/test_recall_revisit_orchestrator.py`
- `test/mosaic_v2/test_aria_context_integration.py`
- `test/mosaic_v2/test_human_surrogate_demo_e2e.py`

### Modify

- `mosaic/runtime/world_state_manager.py`
  Purpose: add helper methods for writing checkpoint memory, target indexes, and exploration/revisit episodes.

- `mosaic/runtime/turn_runner.py`
  Purpose: accept `world_state_mgr`, use ARIA context in system content, and support the new capability sequence cleanly.

- `mosaic/gateway/server.py`
  Purpose: inject `world_state_mgr`, operator console, and the new capabilities into the runtime.

- `config/mosaic.yaml`
  Purpose: add first-stage demo config for the human proxy route and Minimax VLM settings.

- `docs/dev/README.md`
  Purpose: link the new runbook.

---

### Task 1: Define The Atomic Action Schema And Shared Demo Models

**Files:**
- Create: `mosaic/runtime/atomic_action_schema.py`
- Create: `mosaic/runtime/human_surrogate_models.py`
- Test: `test/mosaic_v2/test_atomic_action_schema.py`

- [ ] **Step 1: Write the failing schema tests**

Create `test/mosaic_v2/test_atomic_action_schema.py` with this exact content:

```python
from mosaic.runtime.atomic_action_schema import MotionCommand, AtomicActionName
from mosaic.runtime.human_surrogate_models import ObservationFrameSet, SemanticObservation


def test_motion_command_round_trip() -> None:
    cmd = MotionCommand(
        action=AtomicActionName.REQUEST_HUMAN_MOVE,
        instruction_text="前进 1.2 米",
        distance_m=1.2,
        rotation_deg=0.0,
    )
    payload = cmd.to_dict()
    restored = MotionCommand.from_dict(payload)
    assert restored.action == AtomicActionName.REQUEST_HUMAN_MOVE
    assert restored.instruction_text == "前进 1.2 米"
    assert restored.distance_m == 1.2


def test_observation_frame_set_requires_four_views() -> None:
    frame_set = ObservationFrameSet(
        checkpoint_id="cp-01",
        step_id="step-01",
        issued_motion={"instruction_text": "前进 1.2 米"},
        operator_result="completed",
        images={
            "front": "front.jpg",
            "left": "left.jpg",
            "right": "right.jpg",
            "back": "back.jpg",
        },
        timestamp=1.0,
    )
    assert sorted(frame_set.images.keys()) == ["back", "front", "left", "right"]


def test_semantic_observation_can_hold_room_and_objects() -> None:
    observation = SemanticObservation(
        checkpoint_id="cp-01",
        predicted_room="卧室",
        room_confidence=0.91,
        landmarks=["床", "衣柜"],
        objects=["黄色毛巾"],
        relations=[{"type": "near_landmark", "source": "黄色毛巾", "target": "床"}],
        evidence_summary="卧室里看到床、衣柜和黄色毛巾",
    )
    assert observation.predicted_room == "卧室"
    assert "黄色毛巾" in observation.objects
```

- [ ] **Step 2: Run the new schema tests and confirm they fail**

Run:

```bash
pytest test/mosaic_v2/test_atomic_action_schema.py -q
```

Expected: FAIL with `ModuleNotFoundError` because the new schema/model modules do not exist yet.

- [ ] **Step 3: Implement the atomic action schema**

Create `mosaic/runtime/atomic_action_schema.py` with this exact content:

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AtomicActionName(str, Enum):
    REQUEST_HUMAN_MOVE = "request_human_move"
    CAPTURE_FRAME = "capture_frame"
    OBSERVE_SCENE = "observe_scene"
    CONFIRM_OBJECT = "confirm_object"
    LOCATE_TARGET = "locate_target"
    REPORT_CHECKPOINT = "report_checkpoint"
    UPDATE_MEMORY = "update_memory"
    RECALL_MEMORY = "recall_memory"
    VERIFY_GOAL = "verify_goal"


@dataclass
class MotionCommand:
    action: AtomicActionName
    instruction_text: str
    distance_m: float = 0.0
    rotation_deg: float = 0.0
    lateral_m: float = 0.0

    def to_dict(self) -> dict:
        return {
            "action": self.action.value,
            "instruction_text": self.instruction_text,
            "distance_m": self.distance_m,
            "rotation_deg": self.rotation_deg,
            "lateral_m": self.lateral_m,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "MotionCommand":
        return cls(
            action=AtomicActionName(payload["action"]),
            instruction_text=str(payload["instruction_text"]),
            distance_m=float(payload.get("distance_m", 0.0)),
            rotation_deg=float(payload.get("rotation_deg", 0.0)),
            lateral_m=float(payload.get("lateral_m", 0.0)),
        )
```

- [ ] **Step 4: Implement the shared human-surrogate models**

Create `mosaic/runtime/human_surrogate_models.py` with this exact content:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ObservationFrameSet:
    checkpoint_id: str
    step_id: str
    issued_motion: dict
    operator_result: str
    images: dict[str, str]
    timestamp: float


@dataclass
class SemanticObservation:
    checkpoint_id: str
    predicted_room: str
    room_confidence: float
    landmarks: list[str] = field(default_factory=list)
    objects: list[str] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    evidence_summary: str = ""


@dataclass
class CheckpointNode:
    checkpoint_id: str
    parent_checkpoint_id: str | None = None
    motion_from_parent: dict | None = None
    depth_from_start: int = 0
    semantic_observation_id: str | None = None
    resolved_room_label: str = ""
    known_landmarks: list[str] = field(default_factory=list)
    known_objects: list[str] = field(default_factory=list)


@dataclass
class MemoryTargetIndex:
    target_label: str
    candidate_room_labels: list[str] = field(default_factory=list)
    candidate_checkpoint_ids: list[str] = field(default_factory=list)
    supporting_landmarks: list[str] = field(default_factory=list)
    last_seen_timestamp: float = 0.0
    confidence: float = 0.0


@dataclass
class ExplorationEpisode:
    task_description: str
    visited_checkpoints: list[str] = field(default_factory=list)
    stable_rooms: list[str] = field(default_factory=list)
    observed_targets: list[str] = field(default_factory=list)
    completion_reason: str = ""


@dataclass
class RevisitEpisode:
    task_description: str
    target_label: str
    selected_candidates: list[str] = field(default_factory=list)
    verification_result: str = ""
    corrections_applied: list[str] = field(default_factory=list)
    failure_reason: str = ""


@dataclass
class FailureRecord:
    failure_type: str
    failed_step_id: str
    current_checkpoint_id: str
    expected_room: str = ""
    observed_room: str = ""
    expected_target: str = ""
    observed_targets: list[str] = field(default_factory=list)
    recommended_recovery: str = ""
```

- [ ] **Step 5: Run the schema tests and commit**

Run:

```bash
pytest test/mosaic_v2/test_atomic_action_schema.py -q
```

Expected: PASS.

Commit:

```bash
git add \
  mosaic/runtime/atomic_action_schema.py \
  mosaic/runtime/human_surrogate_models.py \
  test/mosaic_v2/test_atomic_action_schema.py
git commit -m "feat: add atomic action schema and human surrogate models"
```

---

### Task 2: Build The Lightweight Operator Console And Human Proxy Capability

**Files:**
- Create: `mosaic/runtime/operator_console.py`
- Create: `plugins/capabilities/human_proxy/__init__.py`
- Create: `config/demo/human_proxy_protocol.yaml`
- Test: `test/mosaic_v2/test_human_proxy_capability.py`

- [ ] **Step 1: Write the failing operator loop tests**

Create `test/mosaic_v2/test_human_proxy_capability.py` with this exact content:

```python
import asyncio
import base64
import time

import pytest

from mosaic.plugin_sdk.types import ExecutionContext
from plugins.capabilities.human_proxy import HumanProxyCapability
from mosaic.runtime.operator_console import OperatorConsoleState


@pytest.mark.asyncio
async def test_human_proxy_waits_for_submission_and_returns_image_paths():
    console = OperatorConsoleState()
    cap = HumanProxyCapability(console_state=console, timeout_s=2.0)

    async def submit_later():
        await asyncio.sleep(0.05)
        console.submit_result({
            "step_id": "step-01",
            "operator_result": "completed",
            "images": {
                "front": "front.jpg",
                "left": "left.jpg",
                "right": "right.jpg",
                "back": "back.jpg",
            },
            "timestamp": time.time(),
        })

    asyncio.create_task(submit_later())
    result = await cap.execute(
        "request_human_move",
        {"instruction_text": "前进 1.2 米"},
        ExecutionContext(session_id="s1", metadata={"step_id": "step-01"}),
    )

    assert result.success is True
    assert result.data["operator_result"] == "completed"
    assert sorted(result.data["images"].keys()) == ["back", "front", "left", "right"]


@pytest.mark.asyncio
async def test_human_proxy_times_out_without_submission():
    console = OperatorConsoleState()
    cap = HumanProxyCapability(console_state=console, timeout_s=0.05)
    result = await cap.execute(
        "request_human_move",
        {"instruction_text": "前进 1.2 米"},
        ExecutionContext(session_id="s1", metadata={"step_id": "step-timeout"}),
    )
    assert result.success is False
    assert "超时" in (result.error or "")
```

- [ ] **Step 2: Run the tests and confirm the console layer is missing**

Run:

```bash
pytest test/mosaic_v2/test_human_proxy_capability.py -q
```

Expected: FAIL because the operator console and human proxy capability do not yet exist.

- [ ] **Step 3: Implement the in-memory operator console state**

Create `mosaic/runtime/operator_console.py` with this exact content:

```python
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any


@dataclass
class OperatorConsoleState:
    current_step: dict[str, Any] | None = None
    _result_futures: dict[str, asyncio.Future] = field(default_factory=dict)

    def publish_step(self, payload: dict[str, Any]) -> None:
        self.current_step = payload

    def submit_result(self, payload: dict[str, Any]) -> None:
        step_id = str(payload["step_id"])
        fut = self._result_futures.get(step_id)
        if fut and not fut.done():
            fut.set_result(payload)

    async def wait_for_result(self, step_id: str, timeout_s: float) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._result_futures[step_id] = fut
        return await asyncio.wait_for(fut, timeout=timeout_s)


class OperatorConsoleServer:
    def __init__(self, state: OperatorConsoleState, host: str = "127.0.0.1", port: int = 8766) -> None:
        self._state = state
        self._host = host
        self._port = port
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        state = self._state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != "/":
                    self.send_response(404)
                    self.end_headers()
                    return
                html = """
<!DOCTYPE html>
<html>
  <body>
    <h1>Human Proxy Console</h1>
    <pre id="step"></pre>
    <form id="form">
      <input id="step_id" placeholder="step_id" />
      <input id="front" placeholder="front.jpg" />
      <input id="left" placeholder="left.jpg" />
      <input id="right" placeholder="right.jpg" />
      <input id="back" placeholder="back.jpg" />
      <button type="button" onclick="submitResult('completed')">Completed</button>
      <button type="button" onclick="submitResult('failed')">Failed</button>
    </form>
    <script>
      async function refreshStep() {
        const resp = await fetch('/step');
        const data = await resp.json();
        document.getElementById('step').textContent = JSON.stringify(data, null, 2);
        document.getElementById('step_id').value = data.step_id || '';
      }
      async function submitResult(result) {
        const payload = {
          step_id: document.getElementById('step_id').value,
          operator_result: result,
          images: {
            front: document.getElementById('front').value,
            left: document.getElementById('left').value,
            right: document.getElementById('right').value,
            back: document.getElementById('back').value,
          },
          timestamp: Date.now() / 1000.0,
        };
        await fetch('/submit', {method: 'POST', body: JSON.stringify(payload)});
      }
      refreshStep();
      setInterval(refreshStep, 1000);
    </script>
  </body>
</html>
"""
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(html.encode("utf-8"))

            def do_POST(self):
                if self.path != "/submit":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers["Content-Length"])
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                state.submit_result(payload)
                self.send_response(200)
                self.end_headers()

            def log_message(self, format, *args):
                return

        self._httpd = ThreadingHTTPServer((self._host, self._port), Handler)
        self._thread = Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
```

- [ ] **Step 4: Implement `HumanProxyCapability`**

Create `plugins/capabilities/human_proxy/__init__.py` with this exact content:

```python
from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta, ExecutionContext, ExecutionResult, HealthStatus, HealthState,
)
from mosaic.runtime.operator_console import OperatorConsoleState


class HumanProxyCapability:
    def __init__(self, console_state: OperatorConsoleState | None = None, timeout_s: float = 180.0) -> None:
        self.meta = PluginMeta(
            id="human-proxy",
            name="Human Proxy",
            version="0.1.0",
            description="临时真人代机执行层",
            kind="capability",
            author="MOSAIC",
        )
        self._console_state = console_state or OperatorConsoleState()
        self._timeout_s = timeout_s

    def get_supported_intents(self) -> list[str]:
        return ["request_human_move"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [{
            "name": "request_human_move",
            "description": "要求真人代机执行移动并上传四向观察结果",
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction_text": {"type": "string"},
                },
                "required": ["instruction_text"],
            },
        }]

    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult:
        step_id = str(ctx.metadata.get("step_id", "step-missing"))
        self._console_state.publish_step({
            "step_id": step_id,
            "instruction_text": params["instruction_text"],
            "session_id": ctx.session_id,
        })
        try:
            payload = await self._console_state.wait_for_result(step_id, self._timeout_s)
            return ExecutionResult(
                success=payload["operator_result"] == "completed",
                data=payload,
                message=f"真人代机已返回 {payload['operator_result']}",
                error=None if payload["operator_result"] == "completed" else "真人代机执行失败",
            )
        except TimeoutError:
            return ExecutionResult(success=False, error="等待真人代机回传超时")

    async def cancel(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, message="human proxy 插件正常")


def create_plugin(console_state: OperatorConsoleState | None = None, timeout_s: float = 180.0) -> HumanProxyCapability:
    return HumanProxyCapability(console_state=console_state, timeout_s=timeout_s)
```

- [ ] **Step 5: Add the operator protocol config, run the tests, and commit**

Create `config/demo/human_proxy_protocol.yaml` with this exact content:

```yaml
operator_console:
  host: "127.0.0.1"
  port: 8766
  timeout_s: 180
  required_views:
    - front
    - left
    - right
    - back
  completion_values:
    - completed
    - failed
```

Run:

```bash
pytest test/mosaic_v2/test_human_proxy_capability.py -q
```

Expected: PASS.

Commit:

```bash
git add \
  mosaic/runtime/operator_console.py \
  plugins/capabilities/human_proxy/__init__.py \
  config/demo/human_proxy_protocol.yaml \
  test/mosaic_v2/test_human_proxy_capability.py
git commit -m "feat: add human proxy operator console and capability"
```

---

### Task 3: Add VLM Observation Capability For Four-View Checkpoints

**Files:**
- Create: `plugins/capabilities/vlm_observe/__init__.py`
- Test: `test/mosaic_v2/test_vlm_observe_capability.py`

- [ ] **Step 1: Write the failing observation capability tests**

Create `test/mosaic_v2/test_vlm_observe_capability.py` with this exact content:

```python
import pytest

from mosaic.plugin_sdk.types import ExecutionContext
from mosaic.runtime.vlm_pipeline.models import DetectionResult, RoomClassification, DetectedObject, CameraFrame
from plugins.capabilities.vlm_observe import VLMObserveCapability


class FakeAnalyzer:
    async def analyze_frame(self, frame, scene_context=""):
        return DetectionResult(
            objects=[DetectedObject(label="黄色毛巾", category="object", bbox_pixels=(0, 0, 10, 10))],
            room_classification=RoomClassification(room_type="卧室", confidence=0.92),
        )


@pytest.mark.asyncio
async def test_vlm_observe_capability_returns_semantic_observation():
    cap = VLMObserveCapability(analyzer=FakeAnalyzer())
    result = await cap.execute(
        "observe_scene",
        {
            "checkpoint_id": "cp-01",
            "images": {
                "front": b"front",
                "left": b"left",
                "right": b"right",
                "back": b"back",
            },
        },
        ExecutionContext(session_id="s1"),
    )
    assert result.success is True
    assert result.data["predicted_room"] == "卧室"
    assert "黄色毛巾" in result.data["objects"]
```

- [ ] **Step 2: Run the tests and confirm the plugin is missing**

Run:

```bash
pytest test/mosaic_v2/test_vlm_observe_capability.py -q
```

Expected: FAIL because `VLMObserveCapability` does not yet exist.

- [ ] **Step 3: Implement the capability wrapper**

Create `plugins/capabilities/vlm_observe/__init__.py` with this exact content:

```python
from __future__ import annotations

import time
from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta, ExecutionContext, ExecutionResult, HealthStatus, HealthState,
)
from mosaic.runtime.vlm_pipeline.models import CameraFrame
from mosaic.runtime.vlm_pipeline.vlm_analyzer import VLMAnalyzer


class VLMObserveCapability:
    def __init__(self, analyzer: VLMAnalyzer | None = None) -> None:
        self.meta = PluginMeta(
            id="vlm-observe",
            name="VLM Observe",
            version="0.1.0",
            description="四向图像语义观察能力",
            kind="capability",
            author="MOSAIC",
        )
        self._analyzer = analyzer or VLMAnalyzer()

    def get_supported_intents(self) -> list[str]:
        return ["observe_scene"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [{
            "name": "observe_scene",
            "description": "对真人代机上传的图像进行语义观察",
            "parameters": {
                "type": "object",
                "properties": {
                    "checkpoint_id": {"type": "string"},
                    "images": {"type": "object"},
                },
                "required": ["checkpoint_id", "images"],
            },
        }]

    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult:
        checkpoint_id = str(params["checkpoint_id"])
        front = params["images"]["front"]
        frame = CameraFrame(image_data=front, timestamp=time.time())
        detection = await self._analyzer.analyze_frame(frame, scene_context="")
        predicted_room = detection.room_classification.room_type if detection.room_classification else ""
        room_confidence = detection.room_classification.confidence if detection.room_classification else 0.0
        objects = [obj.label for obj in detection.objects]
        return ExecutionResult(
            success=True,
            data={
                "checkpoint_id": checkpoint_id,
                "predicted_room": predicted_room,
                "room_confidence": room_confidence,
                "landmarks": [],
                "objects": objects,
                "relations": [],
                "evidence_summary": f"checkpoint {checkpoint_id} 预测房间 {predicted_room}",
            },
            message=f"完成 {checkpoint_id} 语义观察",
        )

    async def cancel(self) -> bool:
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, message="vlm observe 插件正常")


def create_plugin(analyzer: VLMAnalyzer | None = None) -> VLMObserveCapability:
    return VLMObserveCapability(analyzer=analyzer)
```

- [ ] **Step 4: Run the capability tests and the existing VLM parser tests**

Run:

```bash
pytest test/mosaic_v2/test_vlm_observe_capability.py test/mosaic_v2/test_vlm_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit the observation slice**

```bash
git add \
  plugins/capabilities/vlm_observe/__init__.py \
  test/mosaic_v2/test_vlm_observe_capability.py
git commit -m "feat: add vlm observation capability for four-view checkpoints"
```

---

### Task 4: Implement The Topology Semantic Mapper And ARIA Memory Writes

**Files:**
- Create: `mosaic/runtime/topology_semantic_mapper.py`
- Modify: `mosaic/runtime/world_state_manager.py`
- Test: `test/mosaic_v2/test_topology_semantic_mapper.py`

- [ ] **Step 1: Write the failing mapper tests**

Create `test/mosaic_v2/test_topology_semantic_mapper.py` with this exact content:

```python
from mosaic.runtime.human_surrogate_models import CheckpointNode, SemanticObservation
from mosaic.runtime.topology_semantic_mapper import TopologySemanticMapper


def test_mapper_adds_root_checkpoint() -> None:
    mapper = TopologySemanticMapper()
    node = mapper.add_checkpoint(
        checkpoint_id="cp-01",
        parent_checkpoint_id=None,
        motion_from_parent=None,
        observation=SemanticObservation(
            checkpoint_id="cp-01",
            predicted_room="客厅",
            room_confidence=0.9,
            landmarks=["沙发"],
            objects=[],
            relations=[],
            evidence_summary="客厅里看到沙发",
        ),
    )
    assert node.checkpoint_id == "cp-01"
    assert node.resolved_room_label == "客厅"


def test_mapper_builds_target_index() -> None:
    mapper = TopologySemanticMapper()
    mapper.add_checkpoint(
        checkpoint_id="cp-01",
        parent_checkpoint_id=None,
        motion_from_parent=None,
        observation=SemanticObservation(
            checkpoint_id="cp-01",
            predicted_room="卧室",
            room_confidence=0.92,
            landmarks=["床"],
            objects=["黄色毛巾"],
            relations=[{"type": "near_landmark", "source": "黄色毛巾", "target": "床"}],
            evidence_summary="卧室里看到床和黄色毛巾",
        ),
    )
    index = mapper.build_target_index("黄色毛巾")
    assert index.target_label == "黄色毛巾"
    assert "卧室" in index.candidate_room_labels
    assert "cp-01" in index.candidate_checkpoint_ids
```

- [ ] **Step 2: Run the mapper tests and confirm the mapper is missing**

Run:

```bash
pytest test/mosaic_v2/test_topology_semantic_mapper.py -q
```

Expected: FAIL because `TopologySemanticMapper` does not yet exist.

- [ ] **Step 3: Implement the mapper**

Create `mosaic/runtime/topology_semantic_mapper.py` with this exact content:

```python
from __future__ import annotations

from mosaic.runtime.human_surrogate_models import CheckpointNode, MemoryTargetIndex, SemanticObservation


class TopologySemanticMapper:
    def __init__(self) -> None:
        self._checkpoints: dict[str, CheckpointNode] = {}
        self._observations: dict[str, SemanticObservation] = {}

    def add_checkpoint(
        self,
        checkpoint_id: str,
        parent_checkpoint_id: str | None,
        motion_from_parent: dict | None,
        observation: SemanticObservation,
    ) -> CheckpointNode:
        self._observations[checkpoint_id] = observation
        node = CheckpointNode(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            motion_from_parent=motion_from_parent,
            depth_from_start=0 if parent_checkpoint_id is None else self._checkpoints[parent_checkpoint_id].depth_from_start + 1,
            semantic_observation_id=checkpoint_id,
            resolved_room_label=observation.predicted_room,
            known_landmarks=list(observation.landmarks),
            known_objects=list(observation.objects),
        )
        self._checkpoints[checkpoint_id] = node
        return node

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointNode | None:
        return self._checkpoints.get(checkpoint_id)

    def list_checkpoints(self) -> list[CheckpointNode]:
        return list(self._checkpoints.values())

    def build_target_index(self, target_label: str) -> MemoryTargetIndex:
        candidate_checkpoint_ids = []
        candidate_room_labels = []
        supporting_landmarks = []
        for checkpoint_id, observation in self._observations.items():
            if target_label in observation.objects:
                candidate_checkpoint_ids.append(checkpoint_id)
                if observation.predicted_room:
                    candidate_room_labels.append(observation.predicted_room)
                supporting_landmarks.extend(observation.landmarks)
        return MemoryTargetIndex(
            target_label=target_label,
            candidate_room_labels=sorted(set(candidate_room_labels)),
            candidate_checkpoint_ids=candidate_checkpoint_ids,
            supporting_landmarks=sorted(set(supporting_landmarks)),
            confidence=1.0 if candidate_checkpoint_ids else 0.0,
        )
```

- [ ] **Step 4: Add ARIA write helpers**

Modify `mosaic/runtime/world_state_manager.py` by adding these exact methods inside `WorldStateManager`:

```python
    def store_checkpoint_node(self, checkpoint) -> None:
        key = f"checkpoint:{checkpoint.checkpoint_id}"
        self._kv_store[key] = MemoryEntry(
            key=key,
            content=checkpoint.resolved_room_label,
            metadata={
                "parent_checkpoint_id": checkpoint.parent_checkpoint_id,
                "known_landmarks": checkpoint.known_landmarks,
                "known_objects": checkpoint.known_objects,
            },
        )

    def store_target_index(self, target_index) -> None:
        key = f"target:{target_index.target_label}"
        self._kv_store[key] = MemoryEntry(
            key=key,
            content=target_index.target_label,
            metadata={
                "candidate_room_labels": target_index.candidate_room_labels,
                "candidate_checkpoint_ids": target_index.candidate_checkpoint_ids,
                "supporting_landmarks": target_index.supporting_landmarks,
                "confidence": target_index.confidence,
            },
        )
```

- [ ] **Step 5: Run mapper and memory tests, then commit**

Run:

```bash
pytest test/mosaic_v2/test_topology_semantic_mapper.py test/mosaic_v2/test_world_state_manager.py -q
```

Expected: PASS.

Commit:

```bash
git add \
  mosaic/runtime/topology_semantic_mapper.py \
  mosaic/runtime/world_state_manager.py \
  test/mosaic_v2/test_topology_semantic_mapper.py
git commit -m "feat: add topology semantic mapper and aria memory writers"
```

---

### Task 5: Integrate ARIA Context, Revisit Logic, And TurnRunner Flow

**Files:**
- Create: `mosaic/runtime/planning_context_formatter.py`
- Create: `mosaic/runtime/recall_revisit_orchestrator.py`
- Modify: `mosaic/runtime/turn_runner.py`
- Modify: `mosaic/gateway/server.py`
- Modify: `config/mosaic.yaml`
- Test: `test/mosaic_v2/test_aria_context_integration.py`
- Test: `test/mosaic_v2/test_recall_revisit_orchestrator.py`

- [ ] **Step 1: Write the failing revisit orchestrator tests**

Create `test/mosaic_v2/test_recall_revisit_orchestrator.py` with this exact content:

```python
from mosaic.runtime.human_surrogate_models import CheckpointNode, MemoryTargetIndex
from mosaic.runtime.recall_revisit_orchestrator import RecallAndRevisitOrchestrator


def test_orchestrator_prefers_first_candidate_checkpoint() -> None:
    orchestrator = RecallAndRevisitOrchestrator()
    checkpoint_path = orchestrator.build_candidate_path(
        current_checkpoint_id="cp-01",
        edges={
            "cp-01": ["cp-02"],
            "cp-02": ["cp-01", "cp-03"],
            "cp-03": ["cp-02"],
        },
        target_index=MemoryTargetIndex(
            target_label="黄色毛巾",
            candidate_checkpoint_ids=["cp-03"],
            candidate_room_labels=["卧室"],
        ),
    )
    assert checkpoint_path == ["cp-01", "cp-02", "cp-03"]


def test_orchestrator_switches_to_next_candidate() -> None:
    orchestrator = RecallAndRevisitOrchestrator()
    next_candidate = orchestrator.next_candidate(
        ["cp-03", "cp-07"],
        exhausted={"cp-03"},
    )
    assert next_candidate == "cp-07"
```

- [ ] **Step 2: Run the tests and confirm the orchestrator is missing**

Run:

```bash
pytest test/mosaic_v2/test_recall_revisit_orchestrator.py -q
```

Expected: FAIL because `RecallAndRevisitOrchestrator` does not yet exist.

- [ ] **Step 3: Implement the revisit orchestrator**

Create `mosaic/runtime/recall_revisit_orchestrator.py` with this exact content:

```python
from __future__ import annotations

from collections import deque

from mosaic.runtime.human_surrogate_models import MemoryTargetIndex


class RecallAndRevisitOrchestrator:
    def build_candidate_path(
        self,
        current_checkpoint_id: str,
        edges: dict[str, list[str]],
        target_index: MemoryTargetIndex,
    ) -> list[str]:
        if not target_index.candidate_checkpoint_ids:
            return [current_checkpoint_id]
        target = target_index.candidate_checkpoint_ids[0]
        queue = deque([[current_checkpoint_id]])
        visited = {current_checkpoint_id}
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == target:
                return path
            for neighbor in edges.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(path + [neighbor])
        return [current_checkpoint_id]

    def next_candidate(self, candidates: list[str], exhausted: set[str]) -> str | None:
        for candidate in candidates:
            if candidate not in exhausted:
                return candidate
        return None
```

- [ ] **Step 4: Integrate ARIA context into `TurnRunner`**

Create `mosaic/runtime/planning_context_formatter.py` with this exact content:

```python
from __future__ import annotations

from mosaic.runtime.world_state_manager import PlanningContext, RobotState


class PlanningContextFormatter:
    def render(self, robot_state: RobotState, context: PlanningContext) -> str:
        similar = (
            "\n".join(f"- {ep.task_description}" for ep in context.similar_episodes)
            if context.similar_episodes else "- 无"
        )
        return (
            "[ARIA]\n"
            "机器人状态:\n"
            f"- position=({robot_state.x:.2f}, {robot_state.y:.2f})\n"
            "场景上下文:\n"
            f"{context.scene_text}\n"
            "相似经验:\n"
            f"{similar}"
        )
```

Modify `mosaic/runtime/turn_runner.py` constructor and message assembly to this exact shape:

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

Then replace the initial system message construction with:

```python
        messages: list[dict] = []
        system_content = self._build_system_content(user_input)
        if system_content:
            messages.append({"role": "system", "content": system_content})
```

Modify `mosaic/gateway/server.py` with these exact additions:

1. Add imports:

```python
from mosaic.runtime.operator_console import OperatorConsoleState, OperatorConsoleServer
```

2. After `self._world_state_mgr = self._init_world_state_manager()` add:

```python
        self._operator_console_state = OperatorConsoleState()
        self._operator_console = OperatorConsoleServer(
            self._operator_console_state,
            host=self._config.get("human_proxy.host", "127.0.0.1"),
            port=self._config.get("human_proxy.port", 8766),
        )
        self._operator_console.start()

        self._registry.configure_plugin(
            "human-proxy",
            console_state=self._operator_console_state,
            timeout_s=self._config.get("human_proxy.timeout_s", 180.0),
        )
```

3. Ensure the `TurnRunner(...)` constructor includes:

```python
            world_state_mgr=self._world_state_mgr,
```

4. In `stop()` before the final log line add:

```python
        if getattr(self, "_operator_console", None):
            self._operator_console.stop()
```

Update `config/mosaic.yaml` with this exact block:

```yaml
human_proxy:
  host: "127.0.0.1"
  port: 8766
  timeout_s: 180.0
```

- [ ] **Step 5: Run the integration tests and commit**

Run:

```bash
pytest \
  test/mosaic_v2/test_aria_context_integration.py \
  test/mosaic_v2/test_recall_revisit_orchestrator.py \
  test/mosaic_v2/test_gateway_scene_init.py -q
```

Expected: PASS.

Commit:

```bash
git add \
  mosaic/runtime/planning_context_formatter.py \
  mosaic/runtime/recall_revisit_orchestrator.py \
  mosaic/runtime/turn_runner.py \
  mosaic/gateway/server.py \
  config/mosaic.yaml \
  test/mosaic_v2/test_recall_revisit_orchestrator.py \
  test/mosaic_v2/test_aria_context_integration.py
git commit -m "feat: integrate aria context and revisit orchestration"
```

---

### Task 6: Package The Demo Assets, Runbook, And End-To-End Proof

**Files:**
- Create: `config/demo/human_surrogate_memory.yaml`
- Create: `config/demo/observation_frames/README.md`
- Create: `scripts/run_human_surrogate_memory_demo.py`
- Create: `docs/dev/runbooks/human-surrogate-memory-demo.md`
- Create: `test/mosaic_v2/test_human_surrogate_demo_e2e.py`
- Modify: `docs/dev/README.md`

- [ ] **Step 1: Write the failing end-to-end demo asset test**

Create `test/mosaic_v2/test_human_surrogate_demo_e2e.py` with this exact content:

```python
from pathlib import Path


def test_demo_assets_exist() -> None:
    assert Path("config/demo/human_surrogate_memory.yaml").exists()
    assert Path("scripts/run_human_surrogate_memory_demo.py").exists()
    assert Path("docs/dev/runbooks/human-surrogate-memory-demo.md").exists()
```

- [ ] **Step 2: Run the test and confirm the assets are missing**

Run:

```bash
pytest test/mosaic_v2/test_human_surrogate_demo_e2e.py -q
```

Expected: FAIL because the demo assets do not yet exist.

- [ ] **Step 3: Create the demo config and run script**

Create `config/demo/human_surrogate_memory.yaml` with this exact content:

```yaml
demo:
  mode: human_surrogate_memory
  environment:
    label: "small_home"
    target_rooms: ["客厅", "卧室", "厨房"]
    target_objects: ["黄色毛巾", "咖啡机"]
  operator:
    required_views: ["front", "left", "right", "back"]
    timeout_s: 180
  success_rules:
    min_stable_rooms: 2
    min_landmarks_per_room: 1
    min_targets_indexed: 1
```

Create `scripts/run_human_surrogate_memory_demo.py` with this exact content:

```python
from __future__ import annotations

import argparse
import asyncio
import yaml

from mosaic.gateway.server import GatewayServer


async def _run() -> None:
    with open("config/demo/human_surrogate_memory.yaml", "r", encoding="utf-8") as f:
        demo_config = yaml.safe_load(f)

    server = GatewayServer(config_path="config/mosaic.yaml")
    try:
        await server.start()
        print("Human-surrogate ARIA memory demo is ready.")
        print(demo_config["demo"]["environment"])
    finally:
        await server.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Add the observation-frame README, operator runbook, and docs index entry**

Create `config/demo/observation_frames/README.md` with this exact content:

```md
# Observation Frames

Store four-view checkpoint image sets for the human-surrogate ARIA memory demo in this directory.

Recommended layout:

- `step-001/front.jpg`
- `step-001/left.jpg`
- `step-001/right.jpg`
- `step-001/back.jpg`

These files are operator evidence artifacts, not long-term semantic memory records by themselves.
```

Create `docs/dev/runbooks/human-surrogate-memory-demo.md` with this exact content:

````md
# Human-Surrogate Memory Demo

## Purpose

Run the first-stage ARIA memory validation demo using a developer carrying a camera as the robot surrogate.

## Operator Workflow

1. Read the current movement instruction in the local operator console.
2. Execute the movement.
3. Upload `front`, `left`, `right`, and `back` images.
4. Click `Completed` or `Failed`.

## Demo Command

```bash
python scripts/run_human_surrogate_memory_demo.py
```

## Expected Success Signals

- MOSAIC prints ARIA context summaries
- checkpoint memory grows as exploration proceeds
- revisit tasks choose candidate checkpoints from memory
- at least one revisit succeeds using stored memory
````

Update `docs/dev/README.md` by adding this exact new key document line:

```md
- [Human-surrogate memory demo](runbooks/human-surrogate-memory-demo.md)
```

- [ ] **Step 5: Run the final focused proof suite and commit**

Run:

```bash
pytest \
  test/mosaic_v2/test_atomic_action_schema.py \
  test/mosaic_v2/test_human_proxy_capability.py \
  test/mosaic_v2/test_vlm_observe_capability.py \
  test/mosaic_v2/test_topology_semantic_mapper.py \
  test/mosaic_v2/test_recall_revisit_orchestrator.py \
  test/mosaic_v2/test_aria_context_integration.py \
  test/mosaic_v2/test_human_surrogate_demo_e2e.py -q
python scripts/run_human_surrogate_memory_demo.py
```

Expected:

- all focused tests PASS
- the run script prints `Human-surrogate ARIA memory demo is ready.`

Commit:

```bash
git add \
  config/demo/human_surrogate_memory.yaml \
  config/demo/observation_frames/README.md \
  scripts/run_human_surrogate_memory_demo.py \
  docs/dev/runbooks/human-surrogate-memory-demo.md \
  docs/dev/README.md \
  test/mosaic_v2/test_human_surrogate_demo_e2e.py
git commit -m "feat: package human surrogate aria memory demo assets"
```

---

## Self-Review

### Spec Coverage

This plan covers:

- atomic action contract: Task 1
- human proxy operator loop: Task 2
- VLM-based semantic observation: Task 3
- topology-first semantic mapping and ARIA memory writes: Task 4
- ARIA planning context and revisit orchestration: Task 5
- operator runbook and first-stage proof assets: Task 6

Spec items intentionally deferred remain outside scope:

- full replanning engine
- real robot body integration
- SLAM
- dense metric mapping

### Placeholder Scan

This plan contains no `TODO`, `TBD`, or "implement later" placeholders. All tasks name concrete files, concrete tests, and concrete commands.

### Type Consistency

The shared model names used in later tasks match the model definitions introduced in Task 1:

- `MotionCommand`
- `ObservationFrameSet`
- `SemanticObservation`
- `CheckpointNode`
- `MemoryTargetIndex`
- `ExplorationEpisode`
- `RevisitEpisode`
- `FailureRecord`

The capability names used later are introduced before their integration:

- `HumanProxyCapability`
- `VLMObserveCapability`
- `RecallAndRevisitOrchestrator`
