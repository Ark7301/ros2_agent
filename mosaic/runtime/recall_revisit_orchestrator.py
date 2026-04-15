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
