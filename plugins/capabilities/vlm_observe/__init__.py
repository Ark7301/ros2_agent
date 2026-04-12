from __future__ import annotations

import time
from typing import Any

from mosaic.plugin_sdk.types import (
    ExecutionContext,
    ExecutionResult,
    HealthState,
    HealthStatus,
    PluginMeta,
)
from mosaic.runtime.vlm_pipeline.models import CameraFrame
from mosaic.runtime.vlm_pipeline.vlm_analyzer import VLMAnalyzer


class VLMObserveCapability:
    """VLM 观察能力插件 — 聚合多视角图像为语义观察结果."""

    def __init__(self, analyzer: Any | None = None) -> None:
        self.meta = PluginMeta(
            id="vlm-observe",
            name="VLM Observe",
            version="0.1.0",
            description="VLM 四视角观察能力，返回聚合语义结果",
            kind="capability",
            author="MOSAIC",
        )
        self._analyzer = analyzer or VLMAnalyzer()
        self._cancelled = False

    def get_supported_intents(self) -> list[str]:
        return ["observe_scene"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "observe_scene",
                "description": "聚合四视角图像，输出房间和物体语义观察结果。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "checkpoint_id": {
                            "type": "string",
                            "description": "检查点 ID",
                        },
                        "images": {
                            "type": "object",
                            "description": "四视角图像字典（front/left/right/back）",
                        },
                    },
                    "required": ["checkpoint_id", "images"],
                },
            }
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        self._cancelled = False
        if intent != "observe_scene":
            return ExecutionResult(success=False, error=f"不支持的意图: {intent}")

        checkpoint_id = params.get("checkpoint_id", "")
        images = params.get("images", {}) or {}

        view_order = ["front", "left", "right", "back"]
        analyzed_views: list[str] = []
        objects: list[str] = []
        seen_objects: set[str] = set()
        best_room_type = ""
        best_room_confidence = 0.0

        for view in view_order:
            if view not in images:
                continue
            image_value = images[view]
            if isinstance(image_value, bytes):
                image_data = image_value
            elif isinstance(image_value, str):
                try:
                    with open(image_value, "rb") as file_obj:
                        image_data = file_obj.read()
                except OSError as exc:
                    return ExecutionResult(
                        success=False,
                        error=f"读取图像失败: {exc}",
                    )
            else:
                continue
            frame = CameraFrame(image_data=image_data, timestamp=time.time())
            analyzed_views.append(view)
            result = await self._analyzer.analyze_frame(frame, scene_context="")

            room = result.room_classification
            if room and room.confidence > best_room_confidence:
                best_room_type = room.room_type
                best_room_confidence = room.confidence

            for detected in result.objects:
                label = detected.label
                if label in seen_objects:
                    continue
                seen_objects.add(label)
                objects.append(label)

        evidence_summary = (
            f"checkpoint {checkpoint_id} analyzed {len(analyzed_views)} views"
        )

        return ExecutionResult(
            success=True,
            data={
                "checkpoint_id": checkpoint_id,
                "predicted_room": best_room_type,
                "room_confidence": best_room_confidence,
                "landmarks": [],
                "objects": objects,
                "relations": [],
                "evidence_summary": evidence_summary,
            },
        )

    async def cancel(self) -> bool:
        self._cancelled = True
        return True

    async def health_check(self) -> HealthStatus:
        return HealthStatus(state=HealthState.HEALTHY, message="VLM observe ready")


def create_plugin(analyzer: Any | None = None) -> VLMObserveCapability:
    return VLMObserveCapability(analyzer=analyzer)
