# mosaic/runtime/plan_verifier.py
"""计划验证器 — 在场景图上模拟执行，验证计划可行性

核心算法（VeriGraph 思路，arXiv:2411.10446）：
1. 复制当前场景图作为模拟环境
2. 对计划中的每一步：
   a. 检查前置条件是否在当前模拟场景图上满足
   b. 如果不满足，记录失败原因，返回验证失败
   c. 如果满足，应用动作效果，更新模拟场景图
3. 所有步骤通过 → 计划可行

验证器独立于 LLM，是纯规则引擎。
价值：LLM 可能生成看似合理但物理上不可行的计划，
验证器能在执行前发现问题，避免浪费物理执行时间。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mosaic.runtime.scene_graph import SceneGraph
from mosaic.runtime.action_rules import (
    ActionRule, check_precondition, apply_effect,
)


@dataclass
class StepVerification:
    """单步验证结果"""
    step_index: int
    action: str
    passed: bool
    reason: str


@dataclass
class PlanVerificationResult:
    """计划验证结果"""
    feasible: bool
    step_results: list[StepVerification] = field(default_factory=list)
    failure_step: int = -1
    failure_reason: str = ""
    final_graph: SceneGraph | None = None  # 模拟执行后的最终场景图

    def to_llm_feedback(self) -> str:
        """转化为 LLM 可理解的反馈文本

        当计划不可行时，告诉 LLM 哪一步失败了、为什么失败，
        让 LLM 修正计划。
        """
        if self.feasible:
            return "✓ 计划验证通过，所有步骤的前置条件均满足。"

        lines = [
            f"✗ 计划在第 {self.failure_step + 1} 步失败",
            f"失败动作: {self.step_results[self.failure_step].action}",
            f"原因: {self.failure_reason}",
            "",
            "验证详情:",
        ]
        for sr in self.step_results:
            if sr.passed:
                lines.append(f"  ✓ 第 {sr.step_index + 1} 步: {sr.action}")
            else:
                lines.append(
                    f"  ✗ 第 {sr.step_index + 1} 步: {sr.action} — {sr.reason}"
                )
                break

        lines.append("")
        lines.append("请修正计划，确保失败步骤的前置条件被满足。")
        return "\n".join(lines)


class PlanVerifier:
    """计划验证器 — 在场景图上逐步模拟执行计划，验证可行性"""

    def __init__(self, action_rules: dict[str, ActionRule]) -> None:
        self._rules = action_rules

    def verify_plan(
        self,
        scene_graph: SceneGraph,
        plan_steps: list[dict],
    ) -> PlanVerificationResult:
        """验证完整计划

        Args:
            scene_graph: 当前场景图
            plan_steps: 计划步骤列表，每步格式：
                {"action": "navigate_to", "params": {"target": "厨房"}}

        Returns:
            PlanVerificationResult: 验证结果
        """
        sim_graph = scene_graph.deep_copy()  # 不修改原图
        step_results: list[StepVerification] = []

        for i, step in enumerate(plan_steps):
            action = step.get("action", "")
            params = step.get("params", {})
            rule = self._rules.get(action)

            if not rule:
                # 未知动作 — 跳过验证（可能是自定义插件）
                step_results.append(StepVerification(
                    step_index=i, action=action, passed=True,
                    reason=f"未注册规则，跳过验证",
                ))
                continue

            # 检查所有前置条件
            failed = False
            for pre in rule.preconditions:
                satisfied, reason = check_precondition(
                    sim_graph, pre, params,
                )
                if not satisfied:
                    step_results.append(StepVerification(
                        step_index=i, action=action, passed=False,
                        reason=reason,
                    ))
                    return PlanVerificationResult(
                        feasible=False,
                        step_results=step_results,
                        failure_step=i,
                        failure_reason=reason,
                    )

            # 所有前置条件满足 → 应用效果
            for effect in rule.effects:
                apply_effect(sim_graph, effect, params)

            step_results.append(StepVerification(
                step_index=i, action=action, passed=True,
                reason="前置条件满足",
            ))

        return PlanVerificationResult(
            feasible=True,
            step_results=step_results,
            final_graph=sim_graph,
        )
