"""
TaskExecutor 属性测试

使用 hypothesis 库验证 TaskExecutor 的三个核心属性：
- Property 7: 状态机合法转换
- Property 8: 执行顺序保持
- Property 9: 重试行为
"""

import sys
import os
import asyncio

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
import pytest_asyncio
from hypothesis import given, settings
from hypothesis import strategies as st

from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus,
    ExecutionPlan,
    ExecutionResult,
    PlannedAction,
    Task,
    TaskStatus,
)
from mosaic_demo.agent_core.task_executor import TaskExecutor


# ---- Mock Capability 实现 ----


class SuccessCapability(Capability):
    """始终成功的 Mock Capability"""

    def __init__(self, name: str = "success_cap", intents: list[str] = None):
        self._name = name
        self._intents = intents or ["success_action"]

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(self, task: Task, feedback_callback=None) -> ExecutionResult:
        return ExecutionResult(
            task_id=task.task_id, success=True, message="执行成功"
        )

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return "始终成功的测试能力"


class FailCapability(Capability):
    """始终失败的 Mock Capability，用于测试重试行为"""

    def __init__(self, name: str = "fail_cap", intents: list[str] = None):
        self._name = name
        self._intents = intents or ["fail_action"]
        self.call_count = 0  # 记录调用次数

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(self, task: Task, feedback_callback=None) -> ExecutionResult:
        self.call_count += 1
        return ExecutionResult(
            task_id=task.task_id,
            success=False,
            message="模拟执行失败",
            error="模拟错误",
        )

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return "始终失败的测试能力"


class OrderRecordingCapability(Capability):
    """记录调用顺序的 Mock Capability"""

    def __init__(self, name: str, intents: list[str], call_log: list):
        self._name = name
        self._intents = intents
        self._call_log = call_log  # 共享的调用记录列表

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(self, task: Task, feedback_callback=None) -> ExecutionResult:
        # 记录被调用的动作名称
        self._call_log.append(task.intent)
        return ExecutionResult(
            task_id=task.task_id, success=True, message=f"{task.intent} 完成"
        )

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return f"记录调用顺序的测试能力: {self._name}"


# ---- 合法状态集合 ----

VALID_TERMINAL_STATES = {TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELLED}


# ---- Property 7: TaskExecutor 状态机合法转换 ----


class TestTaskExecutorStateMachine:
    """Property 7: TaskExecutor 状态机合法转换

    **Validates: Requirements 5.2, 5.3, 5.7**

    对于任意任务执行序列，任务状态仅沿合法路径流转：
    PENDING → EXECUTING → SUCCEEDED/FAILED/CANCELLED
    """

    @given(
        num_actions=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_success_execution_reaches_valid_terminal_state(self, num_actions: int):
        """成功执行后，所有任务状态应为 SUCCEEDED"""
        registry = CapabilityRegistry()
        cap = SuccessCapability(name="test_cap", intents=["test_action"])
        registry.register(cap)

        executor = TaskExecutor(registry, max_retries=1, backoff_base=0)

        # 构建包含 num_actions 个动作的执行计划
        actions = [
            PlannedAction(
                action_name="test_action",
                capability_name="test_cap",
            )
            for _ in range(num_actions)
        ]
        plan = ExecutionPlan(plan_id="test-plan", actions=actions)

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_plan(plan)
        )

        # 验证最终结果状态是合法的终态
        assert result.status in VALID_TERMINAL_STATES
        assert result.success is True
        assert result.status == TaskStatus.SUCCEEDED

    @given(
        num_actions=st.integers(min_value=1, max_value=5),
        max_retries=st.integers(min_value=0, max_value=3),
    )
    @settings(max_examples=50, deadline=None)
    def test_failed_execution_reaches_valid_terminal_state(
        self, num_actions: int, max_retries: int
    ):
        """失败执行后，任务状态应为 FAILED（合法终态）"""
        registry = CapabilityRegistry()
        cap = FailCapability(name="fail_cap", intents=["fail_action"])
        registry.register(cap)

        # backoff_base 设为极小值加速测试（0**0=1 会导致 1 秒等待）
        executor = TaskExecutor(registry, max_retries=max_retries, backoff_base=0.001)

        actions = [
            PlannedAction(
                action_name="fail_action",
                capability_name="fail_cap",
            )
            for _ in range(num_actions)
        ]
        plan = ExecutionPlan(plan_id="test-plan", actions=actions)

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_plan(plan)
        )

        # 验证最终结果状态是合法的终态
        assert result.status in VALID_TERMINAL_STATES
        assert result.success is False
        assert result.status == TaskStatus.FAILED

    @given(
        num_actions=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=30, deadline=None)
    def test_cancelled_task_reaches_valid_terminal_state(self, num_actions: int):
        """取消后，任务状态应为 CANCELLED（合法终态）"""
        registry = CapabilityRegistry()
        cap = SuccessCapability(name="test_cap", intents=["test_action"])
        registry.register(cap)

        executor = TaskExecutor(registry, max_retries=0, backoff_base=0)

        task = Task(intent="test_action", params={})
        actions = [
            PlannedAction(
                action_name="test_action",
                capability_name="test_cap",
                task=task,
            )
        ]
        plan = ExecutionPlan(plan_id="test-plan", actions=actions)

        # 先取消任务
        asyncio.get_event_loop().run_until_complete(
            executor.cancel_task(task.task_id)
        )

        # 取消前任务需要先注册到 executor 内部，通过 submit_task 注册
        # 重新构建：先 submit 再 cancel
        executor2 = TaskExecutor(registry, max_retries=0, backoff_base=0)
        task2 = Task(intent="test_action", params={})

        async def cancel_and_verify():
            await executor2.submit_task(task2)
            cancelled = await executor2.cancel_task(task2.task_id)
            return cancelled, task2.status

        cancelled, status = asyncio.get_event_loop().run_until_complete(
            cancel_and_verify()
        )

        assert cancelled is True
        assert status == TaskStatus.CANCELLED
        assert status in VALID_TERMINAL_STATES


# ---- Property 8: TaskExecutor 执行顺序保持 ----


class TestTaskExecutorOrderPreservation:
    """Property 8: TaskExecutor 执行顺序保持

    **Validates: Requirements 5.1**

    对于任意包含多个动作的 ExecutionPlan，
    TaskExecutor 调用 Capability 的顺序应与动作序列的顺序严格一致。
    """

    @given(
        num_actions=st.integers(min_value=2, max_value=8),
    )
    @settings(max_examples=50, deadline=None)
    def test_execution_order_matches_action_sequence(self, num_actions: int):
        """Capability 调用顺序应与动作序列顺序严格一致"""
        registry = CapabilityRegistry()
        call_log = []  # 共享调用记录

        # 为每个动作创建唯一的意图名称
        intent_names = [f"action_{i}" for i in range(num_actions)]

        # 注册一个支持所有意图的 Capability
        cap = OrderRecordingCapability(
            name="order_cap",
            intents=intent_names,
            call_log=call_log,
        )
        registry.register(cap)

        executor = TaskExecutor(registry, max_retries=0, backoff_base=0)

        # 构建按序排列的动作列表
        actions = [
            PlannedAction(
                action_name=intent_name,
                capability_name="order_cap",
            )
            for intent_name in intent_names
        ]
        plan = ExecutionPlan(plan_id="order-test", actions=actions)

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_plan(plan)
        )

        assert result.success is True
        # 验证调用顺序与动作序列严格一致
        assert call_log == intent_names
        assert len(call_log) == num_actions


# ---- Property 9: TaskExecutor 重试行为 ----


class TestTaskExecutorRetryBehavior:
    """Property 9: TaskExecutor 重试行为

    **Validates: Requirements 5.4, 5.5**

    对于任意执行失败的 Capability，TaskExecutor 应按配置的最大重试次数进行重试，
    重试次数不超过配置值。
    """

    @given(
        max_retries=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_retry_count_does_not_exceed_max_retries(self, max_retries: int):
        """始终失败的 Capability，总调用次数应为 1（首次） + max_retries（重试）"""
        registry = CapabilityRegistry()
        fail_cap = FailCapability(name="fail_cap", intents=["fail_action"])
        registry.register(fail_cap)

        # backoff_base 设为极小值加速测试（0**0=1 会导致 1 秒等待）
        executor = TaskExecutor(
            registry, max_retries=max_retries, backoff_base=0.001
        )

        actions = [
            PlannedAction(
                action_name="fail_action",
                capability_name="fail_cap",
            )
        ]
        plan = ExecutionPlan(plan_id="retry-test", actions=actions)

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_plan(plan)
        )

        # 验证执行失败
        assert result.success is False
        assert result.status == TaskStatus.FAILED

        # 总调用次数 = 1（首次执行） + max_retries（重试次数）
        expected_calls = 1 + max_retries
        assert fail_cap.call_count == expected_calls
        # 重试次数不超过配置值
        assert fail_cap.call_count <= max_retries + 1
