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
from mosaic.runtime.vlm_pipeline.models import CameraFrame, RoomClassification


class VLMObserveCapability:
    meta = PluginMeta(
        id="vlm-observe",
        name="VLM Observe",
        version="0.1.0",
        description="Aggregates four checkpoint views via the VLM analyzer",
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
                "description": "Submit a checkpoint's four-view images for VLM observation",
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

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        if intent != "observe_scene":
            return ExecutionResult(success=False, error=f"unsupported intent: {intent}")

        if self._analyzer is None:
            return ExecutionResult(success=False, error="analyzer is not configured")

        checkpoint_id = params.get("checkpoint_id", "")
        images = params.get("images", {})
        analyzed_views: list[str] = []
        objects: list[str] = []
        seen: set[str] = set()
        best_room: RoomClassification | None = None

        for view in ("front", "left", "right", "back"):
            image_data = images.get(view)
            if image_data is None:
                continue
            frame = CameraFrame(image_data=image_data, timestamp=time.time())
            analyzed_views.append(view)
            result = await self._analyzer.analyze_frame(frame, scene_context="")

            room = result.room_classification
            if room and (best_room is None or room.confidence > best_room.confidence):
                best_room = room

            for obj in result.objects:
                if obj.label not in seen:
                    seen.add(obj.label)
                    objects.append(obj.label)

        predicted_room = best_room.room_type if best_room else ""
        room_confidence = best_room.confidence if best_room else 0.0

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
        if self._analyzer:
            return HealthStatus(
                state=HealthState.HEALTHY,
                message="VLM observe capability is ready",
            )
        return HealthStatus(
            state=HealthState.UNHEALTHY,
            message="Analyzer is not configured",
        )


def create_plugin(analyzer: Any | None = None) -> VLMObserveCapability:
    return VLMObserveCapability(analyzer=analyzer)
