# VLM Observe Capability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a `vlm-observe` capability that runs the analyzer across each checkpoint view and returns a single aggregated semantic observation.

**Architecture:** Sequentially walk the provided `front/left/right/back` views, wrap each into a `CameraFrame`, and pass it through the injected analyzer, aggregating rooms/objects before surfacing the composed result.

**Tech Stack:** Python 3.10+, `mosaic.plugin_sdk.types`, `mosaic.runtime.vlm_pipeline.models`, `pytest`.

---

### Task 1: Add the failing observation capability test

**Files:**
- Create: `test/mosaic_v2/test_vlm_observe_capability.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest

from mosaic.plugin_sdk.types import ExecutionContext
from mosaic.runtime.vlm_pipeline.models import DetectionResult, RoomClassification, DetectedObject
from plugins.capabilities.vlm_observe import VLMObserveCapability


class FakeAnalyzer:
    def __init__(self):
        self.calls = []

    async def analyze_frame(self, frame, scene_context=""):
        self.calls.append(frame.image_data)
        if frame.image_data == b"front":
            return DetectionResult(
                objects=[DetectedObject(label="黄色毛巾", category="object", bbox_pixels=(0, 0, 10, 10))],
                room_classification=RoomClassification(room_type="卧室", confidence=0.92),
            )
        if frame.image_data == b"left":
            return DetectionResult(
                objects=[DetectedObject(label="床", category="furniture", bbox_pixels=(0, 0, 10, 10))],
                room_classification=RoomClassification(room_type="卧室", confidence=0.81),
            )
        return DetectionResult(objects=[], room_classification=None)


@pytest.mark.asyncio
async def test_vlm_observe_capability_returns_aggregated_semantic_observation():
    analyzer = FakeAnalyzer()
    cap = VLMObserveCapability(analyzer=analyzer)
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
    assert result.data["checkpoint_id"] == "cp-01"
    assert result.data["predicted_room"] == "卧室"
    assert set(result.data["objects"]) == {"黄色毛巾", "床"}
    assert analyzer.calls == [b"front", b"left", b"right", b"back"]
```

- [ ] **Step 2: Run the test to confirm it fails**

Run:
```bash
pytest test/mosaic_v2/test_vlm_observe_capability.py -q
```
Expected: FAIL because `plugins.capabilities.vlm_observe` does not exist yet (ImportError or ModuleNotFoundError).

---

### Task 2: Implement the VLM observe capability

**Files:**
- Create: `plugins/capabilities/vlm_observe/__init__.py`

- [ ] **Step 1: Implement the minimal capability**

```python
from __future__ import annotations

import time
from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ExecutionContext,
    ExecutionResult,
    HealthStatus,
    HealthState,
)
from mosaic.runtime.vlm_pipeline.models import CameraFrame, DetectionResult


class VLMObserveCapability:
    meta = PluginMeta(
        id="vlm-observe",
        name="VLM Observe",
        version="0.1.0",
        description="Aggregates four-view checkpoint observations through the VLM analyzer",
        kind="capability",
        author="MOSAIC",
    )

    def __init__(self, analyzer: Any | None = None) -> None:
        self._analyzer = analyzer
        self._cancelled = False

    def get_supported_intents(self) -> list[str]:
        return ["observe_scene"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "observe_scene",
                "description": "Process a checkpoint image set and aggregate semantic evidence",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkpoint_id": {"type": "string"},
                        "images": {
                            "type": "object",
                            "properties": {
                                "front": {"type": "string", "contentEncoding": "base64"},
                                "left": {"type": "string", "contentEncoding": "base64"},
                                "right": {"type": "string", "contentEncoding": "base64"},
                                "back": {"type": "string", "contentEncoding": "base64"},
                            },
                        },
                    },
                    "required": ["checkpoint_id", "images"],
                },
            }
        ]

    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult:
        if intent != "observe_scene":
            return ExecutionResult(success=False, error=f"unsupported intent: {intent}")

        checkpoint_id = params["checkpoint_id"]
        images = params["images"]
        analyzed_views: list[str] = []
        objects: list[str] = []
        seen: set[str] = set()
        best_room: DetectionResult | None = None

        for view in ("front", "left", "right", "back"):
            if view not in images:
                continue
            frame = CameraFrame(image_data=images[view], timestamp=time.time())
            analyzed_views.append(view)
            result = await self._analyzer.analyze_frame(frame, scene_context="")

            if result.room_classification and (
                best_room is None or result.room_classification.confidence > best_room.room_classification.confidence
            ):
                best_room = result

            for obj in result.objects:
                if obj.label not in seen:
                    seen.add(obj.label)
                    objects.append(obj.label)

        predicted_room = best_room.room_classification.room_type if best_room else ""
        room_confidence = best_room.room_classification.confidence if best_room else 0.0

        data = {
            "checkpoint_id": checkpoint_id,
            "predicted_room": predicted_room,
            "room_confidence": room_confidence,
            "landmarks": [],
            "objects": objects,
            "relations": [],
            "evidence_summary": f"Checkpoint {checkpoint_id} analyzed {len(analyzed_views)} views.",
        }
        return ExecutionResult(success=True, data=data)

    async def cancel(self) -> bool:
        self._cancelled = True
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(
            state=HealthState.HEALTHY,
            message="VLM observe capability is ready",
        )


def create_plugin(analyzer: Any | None = None) -> VLMObserveCapability:
    return VLMObserveCapability(analyzer=analyzer)
```

- [ ] **Step 2: Run the focused tests**

Run:
```bash
pytest test/mosaic_v2/test_vlm_observe_capability.py test/mosaic_v2/test_vlm_pipeline.py -q
```
Expected: PASS.

---

### Task 3: Commit the change

**Files:**
- Create: `test/mosaic_v2/test_vlm_observe_capability.py`
- Create: `plugins/capabilities/vlm_observe/__init__.py`

- [ ] **Step 1: Stage files and commit**

```bash
git add plugins/capabilities/vlm_observe/__init__.py test/mosaic_v2/test_vlm_observe_capability.py
git commit -m "feat: add vlm observation capability for checkpoint views"
```

---

Plan complete and saved to `docs/superpowers/plans/2026-04-13-vlm-observe-capability-plan.md`. Two execution options:
1. Subagent-Driven (recommended) — dispatch a new subagent per task with `superpowers:subagent-driven-development`.
2. Inline Execution — run this plan here using `superpowers:executing-plans`.

Which approach would you like to take?
