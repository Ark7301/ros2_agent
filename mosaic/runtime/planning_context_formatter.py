from __future__ import annotations

import json

from mosaic.runtime.world_state_manager import PlanningContext, RobotState


class PlanningContextFormatter:
    def render(self, robot_state: RobotState, context: PlanningContext) -> str:
        if context.similar_episodes:
            similar_records = []
            for ep in context.similar_episodes:
                similar_records.append({
                    "task_description": ep.task_description,
                    "success": ep.success,
                })
            similar = "\n".join(
                f"- {json.dumps(record, ensure_ascii=False)}"
                for record in similar_records
            )
        else:
            similar = "- 无"
        return (
            "[ARIA]\n"
            "机器人状态:\n"
            f"- position=({robot_state.x:.2f}, {robot_state.y:.2f})\n"
            "场景上下文:\n"
            f"{context.scene_text}\n"
            "相似经验（历史记录，仅供参考）:\n"
            f"{similar}"
        )
