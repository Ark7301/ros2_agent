"""
TaskExecutor — 任务执行器

内置优先级队列 + 执行调度。
职责：
1. 接收 ExecutionPlan，按序执行
2. 通过 CapabilityRegistry 解析 capability_name，调用 Capability.execute()
3. 跟踪状态流转：PENDING → EXECUTING → SUCCEEDED/FAILED/CANCELLED
4. 支持配置化重试策略（指数退避）
5. 支持任务取消
"""

import asyncio
import heapq
import logging
import uuid
from typing import Optional

from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import (
    ExecutionPlan,
    ExecutionResult,
    PlannedAction,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class TaskExecutor:
    """任务执行器 — 内置优先级队列 + 执行调度"""

    def __init__(
        self,
        registry: CapabilityRegistry,
        max_retries: int = 3,
        backoff_base: int = 2,
    ):
        """初始化任务执行器

        Args:
            registry: 能力注册中心，用于根据 capability_name 解析 Capability
            max_retries: 最大重试次数，默认 3
            backoff_base: 指数退避基数，默认 2
        """
        self._registry = registry
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        # 优先级队列：元素为 (priority, 序号, Task)，序号用于保持稳定排序
        self._queue: list[tuple[int, int, Task]] = []
        self._seq = 0
        # task_id → Task 映射，用于状态跟踪和取消
        self._tasks: dict[str, Task] = {}
        # 已取消的 task_id 集合
        self._cancelled: set[str] = set()

    async def execute_plan(self, plan: ExecutionPlan) -> ExecutionResult:
        """执行整个计划，按序遍历动作列表

        遍历 ExecutionPlan 中的每个 PlannedAction，
        通过 CapabilityRegistry 找到对应 Capability 并执行。
        遇到错误动作或执行失败（重试耗尽）时立即返回失败结果。

        Args:
            plan: 待执行的执行计划

        Returns:
            最终执行结果
        """
        last_result: Optional[ExecutionResult] = None

        while not plan.is_complete():
            action = plan.peek_next()
            if action is None:
                break

            # 错误动作直接返回失败
            if action.action_name == "error":
                error_msg = action.parameters.get("message", "未知错误")
                return ExecutionResult(
                    task_id=plan.plan_id,
                    success=False,
                    message=f"计划包含错误动作: {error_msg}",
                    status=TaskStatus.FAILED,
                    error=error_msg,
                )

            # 执行单个动作
            result = await self._execute_action(action, plan.plan_id)
            last_result = result

            # 执行失败则中止后续动作
            if not result.success:
                return result

            plan.advance()

        # 所有动作执行完毕
        if last_result is not None:
            return last_result

        # 空计划
        return ExecutionResult(
            task_id=plan.plan_id,
            success=True,
            message="执行计划为空，无需执行",
            status=TaskStatus.SUCCEEDED,
        )

    async def submit_task(self, task: Task) -> None:
        """将任务入队到优先级队列

        使用负优先级值实现高优先级先出队（heapq 是最小堆）。

        Args:
            task: 待入队的任务
        """
        self._tasks[task.task_id] = task
        # 负优先级：数值越大优先级越高，取负后在最小堆中越靠前
        heapq.heappush(self._queue, (-task.priority, self._seq, task))
        self._seq += 1

    async def cancel_task(self, task_id: str) -> bool:
        """取消指定任务

        设置取消标志，在执行循环中检查。
        如果任务存在且尚未完成，将其状态设为 CANCELLED。

        Args:
            task_id: 待取消的任务 ID

        Returns:
            取消是否成功
        """
        task = self._tasks.get(task_id)
        if task is None:
            return False

        # 只有 PENDING 或 EXECUTING 状态的任务可以取消
        if task.status in (TaskStatus.PENDING, TaskStatus.EXECUTING):
            self._cancelled.add(task_id)
            task.status = TaskStatus.CANCELLED
            return True

        return False

    async def _execute_action(
        self, action: PlannedAction, plan_id: str
    ) -> ExecutionResult:
        """执行单个动作，包含重试逻辑

        状态流转：PENDING → EXECUTING → SUCCEEDED/FAILED/CANCELLED
        失败时按指数退避重试，最多 max_retries 次。

        Args:
            action: 待执行的计划动作
            plan_id: 所属计划 ID

        Returns:
            执行结果
        """
        # 确保动作关联了 Task，没有则创建一个
        task = action.task
        if task is None:
            task = Task(
                intent=action.action_name,
                params=action.parameters,
            )
            action.task = task

        # 注册到任务映射
        self._tasks[task.task_id] = task

        # 状态流转：PENDING → EXECUTING
        task.status = TaskStatus.EXECUTING

        # 通过 CapabilityRegistry 解析 Capability
        try:
            capability = self._registry.resolve(action.action_name)
        except KeyError as e:
            # 无法解析能力，直接失败
            task.status = TaskStatus.FAILED
            return ExecutionResult(
                task_id=task.task_id,
                success=False,
                message=f"无法解析能力: {e}",
                status=TaskStatus.FAILED,
                error=str(e),
            )

        # 带重试的执行
        last_error: Optional[str] = None
        for attempt in range(self._max_retries + 1):
            # 检查取消标志
            if task.task_id in self._cancelled:
                task.status = TaskStatus.CANCELLED
                return ExecutionResult(
                    task_id=task.task_id,
                    success=False,
                    message="任务已取消",
                    status=TaskStatus.CANCELLED,
                )

            try:
                result = await capability.execute(task)

                if result.success:
                    # 执行成功：EXECUTING → SUCCEEDED
                    task.status = TaskStatus.SUCCEEDED
                    result.status = TaskStatus.SUCCEEDED
                    return result
                else:
                    # Capability 返回失败结果
                    last_error = result.error or result.message
                    task.retry_count = attempt + 1

            except Exception as e:
                # 执行过程中抛出异常
                last_error = str(e)
                task.retry_count = attempt + 1
                logger.warning(
                    "动作 '%s' 第 %d 次执行失败: %s",
                    action.action_name,
                    attempt + 1,
                    last_error,
                )

            # 如果还有重试机会，等待指数退避时间
            if attempt < self._max_retries:
                backoff_time = self._backoff_base ** attempt
                await asyncio.sleep(backoff_time)

        # 重试耗尽：EXECUTING → FAILED
        task.status = TaskStatus.FAILED
        return ExecutionResult(
            task_id=task.task_id,
            success=False,
            message=f"动作 '{action.action_name}' 重试 {self._max_retries} 次后仍失败",
            status=TaskStatus.FAILED,
            error=last_error,
        )
