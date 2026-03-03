"""
TaskPlanner 单元测试

验证 TaskPlanner 的核心功能：
- 单意图 TaskResult → 单动作 ExecutionPlan
- 多子任务 TaskResult → 有序动作序列
- 无法解析意图时返回错误动作

Requirements: 4.1, 4.2, 4.3
"""

import pytest
from typing import Callable, Optional

from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus,
    ExecutionResult,
    Task,
    TaskResult,
)
from mosaic_demo.agent_core.task_planner import TaskPlanner


class StubCapability(Capability):
    """测试用 Stub Capability"""

    def __init__(self, name: str, intents: list[str]):
        self._name = name
        self._intents = intents

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(self, task: Task, feedback_callback: Callable = None) -> ExecutionResult:
        return ExecutionResult(task_id=task.task_id, success=True, message="ok")

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return f"Stub: {self._name}"


@pytest.fixture
def registry_with_caps():
    """创建包含两个 Stub Capability 的 Registry"""
    registry = CapabilityRegistry()
    nav_cap = StubCapability("navigation", ["navigate_to", "patrol"])
    motion_cap = StubCapability("motion", ["rotate", "stop"])
    registry.register(nav_cap)
    registry.register(motion_cap)
    return registry, nav_cap, motion_cap


@pytest.mark.asyncio
class TestTaskPlanner:
    """TaskPlanner 核心功能测试"""

    async def test_single_intent_produces_single_action(self, registry_with_caps):
        """单意图 TaskResult 应生成包含单个动作的 ExecutionPlan (Req 4.1)"""
        registry, nav_cap, _ = registry_with_caps
        planner = TaskPlanner(registry)

        task_result = TaskResult(intent="navigate_to", params={"target": "厨房"})
        plan = await planner.plan(task_result)

        assert len(plan.actions) == 1
        assert plan.actions[0].action_name == "navigate_to"
        assert plan.actions[0].capability_name == "navigation"
        assert plan.actions[0].parameters == {"target": "厨房"}
        assert plan.original_task is task_result

    async def test_multi_subtasks_produce_ordered_actions(self, registry_with_caps):
        """多子任务 TaskResult 应生成有序动作序列 (Req 4.2)"""
        registry, _, _ = registry_with_caps
        planner = TaskPlanner(registry)

        task_result = TaskResult(
            intent="compound",
            sub_tasks=[
                TaskResult(intent="navigate_to", params={"target": "客厅"}),
                TaskResult(intent="rotate", params={"angle": 90}),
                TaskResult(intent="stop", params={}),
            ],
        )
        plan = await planner.plan(task_result)

        # 动作数量应与子任务数量一致
        assert len(plan.actions) == 3
        # 动作顺序应与子任务顺序一致
        assert plan.actions[0].action_name == "navigate_to"
        assert plan.actions[0].capability_name == "navigation"
        assert plan.actions[1].action_name == "rotate"
        assert plan.actions[1].capability_name == "motion"
        assert plan.actions[2].action_name == "stop"
        assert plan.actions[2].capability_name == "motion"

    async def test_unresolvable_intent_returns_error_action(self, registry_with_caps):
        """无法解析的意图应返回包含错误信息的动作 (Req 4.3)"""
        registry, _, _ = registry_with_caps
        planner = TaskPlanner(registry)

        task_result = TaskResult(intent="fly_to_moon", params={})
        plan = await planner.plan(task_result)

        assert len(plan.actions) == 1
        assert plan.actions[0].action_name == "error"
        assert "message" in plan.actions[0].parameters
        assert plan.actions[0].capability_name == ""

    async def test_subtask_with_unresolvable_intent(self, registry_with_caps):
        """子任务中包含无法解析的意图时，该动作应为错误动作 (Req 4.3)"""
        registry, _, _ = registry_with_caps
        planner = TaskPlanner(registry)

        task_result = TaskResult(
            intent="compound",
            sub_tasks=[
                TaskResult(intent="navigate_to", params={"target": "厨房"}),
                TaskResult(intent="unknown_intent", params={}),
            ],
        )
        plan = await planner.plan(task_result)

        assert len(plan.actions) == 2
        # 第一个动作正常
        assert plan.actions[0].action_name == "navigate_to"
        assert plan.actions[0].capability_name == "navigation"
        # 第二个动作为错误
        assert plan.actions[1].action_name == "error"
        assert plan.actions[1].capability_name == ""

    async def test_plan_has_valid_plan_id(self, registry_with_caps):
        """生成的 ExecutionPlan 应包含有效的 plan_id"""
        registry, _, _ = registry_with_caps
        planner = TaskPlanner(registry)

        task_result = TaskResult(intent="stop", params={})
        plan = await planner.plan(task_result)

        assert plan.plan_id is not None
        assert len(plan.plan_id) > 0

    async def test_action_task_has_correct_intent_and_params(self, registry_with_caps):
        """PlannedAction 中的 Task 应包含正确的 intent 和 params"""
        registry, _, _ = registry_with_caps
        planner = TaskPlanner(registry)

        task_result = TaskResult(intent="patrol", params={"route": "A"})
        plan = await planner.plan(task_result)

        action = plan.actions[0]
        assert action.task is not None
        assert action.task.intent == "patrol"
        assert action.task.params == {"route": "A"}


# ============================================================
# 属性测试 — 使用 Hypothesis 验证 TaskPlanner 的核心属性
# ============================================================

from hypothesis import given, strategies as st, settings


def _intent_strategy():
    """生成合法的意图名称策略：非空 ASCII 字母+下划线"""
    return st.from_regex(r"[a-z][a-z0-9_]{0,19}", fullmatch=True)


@pytest.mark.asyncio
class TestTaskPlannerSingleIntentProperty:
    """属性 5：TaskPlanner 单意图映射

    对于任意包含单个意图的 TaskResult（无子任务），
    TaskPlanner 生成的 ExecutionPlan 应恰好包含一个动作，
    且该动作的 capability_name 与 Registry 中解析到的 Capability 一致。

    **Validates: Requirements 4.1**
    """

    @given(intent_name=_intent_strategy())
    @settings(max_examples=50, deadline=None)
    async def test_single_intent_maps_to_one_action_with_correct_capability(
        self, intent_name: str
    ):
        """单意图 TaskResult 应生成恰好一个动作，capability_name 与 Registry 一致"""
        # 构造：创建支持该意图的 StubCapability 并注册
        cap_name = f"cap_{intent_name}"
        cap = StubCapability(cap_name, [intent_name])
        registry = CapabilityRegistry()
        registry.register(cap)

        planner = TaskPlanner(registry)
        task_result = TaskResult(intent=intent_name, params={})

        plan = await planner.plan(task_result)

        # 断言：恰好一个动作
        assert len(plan.actions) == 1
        action = plan.actions[0]
        # 断言：动作名称与意图一致
        assert action.action_name == intent_name
        # 断言：capability_name 与 Registry 中解析到的 Capability 名称一致
        resolved_cap = registry.resolve(intent_name)
        assert action.capability_name == resolved_cap.get_name()
        # 断言：original_task 引用正确
        assert plan.original_task is task_result


@pytest.mark.asyncio
class TestTaskPlannerMultiSubtaskProperty:
    """属性 6：TaskPlanner 多子任务映射

    对于任意包含 N 个子任务的 TaskResult，
    TaskPlanner 生成的 ExecutionPlan 应包含 N 个有序动作，
    且动作顺序与子任务顺序一致。

    **Validates: Requirements 4.2**
    """

    @given(
        intent_names=st.lists(
            _intent_strategy(),
            min_size=1,
            max_size=8,
        )
    )
    @settings(max_examples=50, deadline=None)
    async def test_multi_subtasks_produce_n_ordered_actions(
        self, intent_names: list[str]
    ):
        """N 个子任务应生成 N 个有序动作，顺序与子任务一致"""
        # 构造：为每个意图创建独立的 StubCapability 并注册
        registry = CapabilityRegistry()
        # 去重意图名称用于注册（同名意图共享同一个 Capability）
        unique_intents = list(dict.fromkeys(intent_names))
        for intent in unique_intents:
            cap = StubCapability(f"cap_{intent}", [intent])
            registry.register(cap)

        planner = TaskPlanner(registry)

        # 构造包含 N 个子任务的 TaskResult
        sub_tasks = [
            TaskResult(intent=name, params={"idx": i})
            for i, name in enumerate(intent_names)
        ]
        task_result = TaskResult(
            intent="compound",
            sub_tasks=sub_tasks,
        )

        plan = await planner.plan(task_result)

        # 断言：动作数量等于子任务数量
        assert len(plan.actions) == len(intent_names)

        # 断言：动作顺序与子任务顺序一致
        for i, (action, expected_intent) in enumerate(
            zip(plan.actions, intent_names)
        ):
            assert action.action_name == expected_intent, (
                f"第 {i} 个动作的 action_name 应为 '{expected_intent}'，"
                f"实际为 '{action.action_name}'"
            )
            # 验证 capability_name 与 Registry 解析结果一致
            resolved_cap = registry.resolve(expected_intent)
            assert action.capability_name == resolved_cap.get_name()
