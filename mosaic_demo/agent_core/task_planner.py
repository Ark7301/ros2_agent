"""
TaskPlanner — Demo 版任务规划器

将 TaskResult 映射为 ExecutionPlan。
简化逻辑：TaskResult.intent → CapabilityRegistry.resolve() → ExecutionPlan
不含 LLM 规划、SceneGraph 验证、重规划等高级特性。
"""

import uuid

from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import (
    ExecutionPlan,
    PlannedAction,
    Task,
    TaskResult,
)


class TaskPlanner:
    """Demo 版任务规划器 — 直接意图映射

    通过 CapabilityRegistry 将意图解析为对应的 Capability，
    生成包含有序动作的 ExecutionPlan。
    """

    def __init__(self, registry: CapabilityRegistry):
        """初始化任务规划器

        Args:
            registry: 能力注册中心实例
        """
        self._registry = registry

    async def plan(self, task_result: TaskResult) -> ExecutionPlan:
        """将 TaskResult 映射为 ExecutionPlan

        - 有子任务时：遍历每个子任务，逐个映射为有序动作序列
        - 无子任务时：直接将主意图映射为单个动作
        - 意图无法解析时：返回包含错误信息的 ExecutionPlan

        Args:
            task_result: 任务解析结果

        Returns:
            包含有序动作的执行计划
        """
        actions: list[PlannedAction] = []

        if task_result.sub_tasks:
            # 多子任务：逐个映射为有序动作序列
            for sub_task in task_result.sub_tasks:
                action = self._resolve_to_action(sub_task)
                actions.append(action)
        else:
            # 单意图：直接映射为单个动作
            action = self._resolve_to_action(task_result)
            actions.append(action)

        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            actions=actions,
            original_task=task_result,
        )

    def _resolve_to_action(self, task_result: TaskResult) -> PlannedAction:
        """将单个 TaskResult 解析为 PlannedAction

        通过 CapabilityRegistry 解析意图，找到对应的 Capability，
        生成 PlannedAction。意图无法解析时返回包含错误信息的动作。

        Args:
            task_result: 单个任务解析结果

        Returns:
            对应的计划动作
        """
        try:
            capability = self._registry.resolve(task_result.intent)
            # 创建可执行任务
            task = Task(
                intent=task_result.intent,
                params=task_result.params,
            )
            return PlannedAction(
                action_name=task_result.intent,
                parameters=task_result.params,
                capability_name=capability.get_name(),
                task=task,
                description=f"执行 {task_result.intent} 动作",
            )
        except KeyError as e:
            # 意图无法解析，返回包含错误信息的动作
            return PlannedAction(
                action_name="error",
                parameters={"message": str(e)},
                capability_name="",
                task=None,
                description=f"无法解析意图: {task_result.intent}",
            )
