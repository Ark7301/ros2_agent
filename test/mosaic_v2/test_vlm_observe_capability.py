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
