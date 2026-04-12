import pytest

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


def test_observation_frame_set_rejects_missing_view() -> None:
    with pytest.raises(ValueError):
        ObservationFrameSet(
            checkpoint_id="cp-01",
            step_id="step-01",
            issued_motion={"instruction_text": "前进 1.2 米"},
            operator_result="completed",
            images={
                "front": "front.jpg",
                "left": "left.jpg",
                "back": "back.jpg",
            },
            timestamp=1.0,
        )


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
