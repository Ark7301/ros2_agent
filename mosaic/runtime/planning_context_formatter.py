from __future__ import annotations

from mosaic.runtime.world_state_manager import PlanningContext, RobotState


class PlanningContextFormatter:
    def render(self, robot_state: RobotState, context: PlanningContext) -> str:
        similar = (
            "\n".join(f"- {ep.task_description}" for ep in context.similar_episodes)
            if context.similar_episodes else "- 无"
        )
        return (
            "[ARIA]\n"
            "机器人状态:\n"
            f"- position=({robot_state.x:.2f}, {robot_state.y:.2f})\n"
            "场景上下文:\n"
            f"{context.scene_text}\n"
            "相似经验:\n"
            f"{similar}"
        )
