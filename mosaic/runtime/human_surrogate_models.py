from __future__ import annotations

from dataclasses import dataclass, field

REQUIRED_FRAME_KEYS = ("front", "left", "right", "back")


@dataclass
class ObservationFrameSet:
    checkpoint_id: str
    step_id: str
    issued_motion: dict
    operator_result: str
    images: dict[str, str]
    timestamp: float

    def __post_init__(self) -> None:
        missing = [key for key in REQUIRED_FRAME_KEYS if key not in self.images]
        if missing:
            raise ValueError(f"missing required frame(s): {missing}")
        extra = [key for key in self.images if key not in REQUIRED_FRAME_KEYS]
        if extra:
            raise ValueError(f"unexpected frame(s): {extra}")


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
