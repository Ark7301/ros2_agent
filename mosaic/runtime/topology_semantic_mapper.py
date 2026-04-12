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
        if checkpoint_id != observation.checkpoint_id:
            raise ValueError(
                "checkpoint_id must match observation checkpoint id",
            )

        depth = 0
        if parent_checkpoint_id is not None:
            parent_node = self._checkpoints.get(parent_checkpoint_id)
            if parent_node is None:
                raise ValueError(f"parent checkpoint '{parent_checkpoint_id}' not found")
            depth = parent_node.depth_from_start + 1

        self._observations[checkpoint_id] = observation
        node = CheckpointNode(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=parent_checkpoint_id,
            motion_from_parent=motion_from_parent,
            depth_from_start=depth,
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
        candidate_checkpoint_ids: list[str] = []
        candidate_room_labels: set[str] = set()
        supporting_landmarks: set[str] = set()
        for checkpoint_id, observation in self._observations.items():
            if target_label in observation.objects:
                candidate_checkpoint_ids.append(checkpoint_id)
                if observation.predicted_room:
                    candidate_room_labels.add(observation.predicted_room)
                supporting_landmarks.update(observation.landmarks)
        return MemoryTargetIndex(
            target_label=target_label,
            candidate_room_labels=sorted(candidate_room_labels),
            candidate_checkpoint_ids=candidate_checkpoint_ids,
            supporting_landmarks=sorted(supporting_landmarks),
            confidence=1.0 if candidate_checkpoint_ids else 0.0,
        )
