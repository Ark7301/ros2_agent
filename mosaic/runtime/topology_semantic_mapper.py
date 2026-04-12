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
