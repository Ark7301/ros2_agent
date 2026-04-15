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
