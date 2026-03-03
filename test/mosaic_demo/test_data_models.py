"""
TaskResult 序列化 round-trip 属性测试

**Validates: Requirements 12.3**

使用 hypothesis 库验证：对于任意合法的 TaskResult 实例，
to_dict() 后再 from_dict() 应产生等价对象。
"""

import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from mosaic_demo.interfaces_abstract.data_models import TaskResult


# ---- 自定义 Hypothesis Strategy ----

# JSON 可序列化的基本类型值
json_primitive = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.booleans(),
    st.none(),
)

# params 字典：键为字符串，值为 JSON 基本类型
json_params = st.dictionaries(
    keys=st.text(min_size=1, max_size=20),
    values=json_primitive,
    max_size=5,
)


def task_result_strategy(max_depth=2):
    """
    递归生成 TaskResult 的 strategy。
    通过 max_depth 控制 sub_tasks 的嵌套深度，避免无限递归。
    """
    if max_depth <= 0:
        # 叶子节点：无子任务
        return st.builds(
            TaskResult,
            intent=st.text(min_size=1, max_size=30),
            params=json_params,
            sub_tasks=st.just([]),
            confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            raw_response=st.one_of(st.none(), st.text(max_size=100)),
        )
    else:
        # 递归节点：可包含子任务
        return st.builds(
            TaskResult,
            intent=st.text(min_size=1, max_size=30),
            params=json_params,
            sub_tasks=st.lists(
                task_result_strategy(max_depth=max_depth - 1),
                max_size=3,
            ),
            confidence=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
            raw_response=st.one_of(st.none(), st.text(max_size=100)),
        )


# ---- 属性测试 ----


class TestTaskResultRoundTrip:
    """Property 12: TaskResult 序列化 round-trip

    **Validates: Requirements 12.3**
    """

    @given(task_result=task_result_strategy(max_depth=2))
    @settings(max_examples=100)
    def test_to_dict_from_dict_round_trip(self, task_result: TaskResult):
        """
        对于任意合法的 TaskResult 实例，
        to_dict() 后再 from_dict() 应产生等价对象。
        """
        # 序列化
        serialized = task_result.to_dict()

        # 反序列化
        restored = TaskResult.from_dict(serialized)

        # 验证所有字段等价
        assert restored.intent == task_result.intent
        assert restored.params == task_result.params
        assert restored.confidence == task_result.confidence
        assert restored.raw_response == task_result.raw_response
        assert len(restored.sub_tasks) == len(task_result.sub_tasks)

        # 递归验证：再次序列化应产生相同字典
        assert restored.to_dict() == serialized


# ---- 单元测试 ----
# **Validates: Requirements 12.1, 12.2**

import pytest
from mosaic_demo.interfaces_abstract.data_models import (
    TaskStatus,
    CapabilityStatus,
    ExecutionPlan,
    PlannedAction,
)


class TestTaskStatusEnum:
    """测试 TaskStatus 枚举的所有值"""

    def test_all_values_exist(self):
        """验证 TaskStatus 包含全部 5 个状态"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.EXECUTING.value == "executing"
        assert TaskStatus.SUCCEEDED.value == "succeeded"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_member_count(self):
        """验证 TaskStatus 恰好有 5 个成员"""
        assert len(TaskStatus) == 5

    def test_from_value(self):
        """验证可以通过字符串值获取枚举成员"""
        assert TaskStatus("pending") is TaskStatus.PENDING
        assert TaskStatus("failed") is TaskStatus.FAILED

    def test_invalid_value_raises(self):
        """验证无效值抛出 ValueError"""
        with pytest.raises(ValueError):
            TaskStatus("unknown")


class TestCapabilityStatusEnum:
    """测试 CapabilityStatus 枚举的所有值"""

    def test_all_values_exist(self):
        """验证 CapabilityStatus 包含全部 3 个状态"""
        assert CapabilityStatus.IDLE.value == "idle"
        assert CapabilityStatus.BUSY.value == "busy"
        assert CapabilityStatus.ERROR.value == "error"

    def test_member_count(self):
        """验证 CapabilityStatus 恰好有 3 个成员"""
        assert len(CapabilityStatus) == 3

    def test_invalid_value_raises(self):
        """验证无效值抛出 ValueError"""
        with pytest.raises(ValueError):
            CapabilityStatus("offline")


class TestExecutionPlan:
    """测试 ExecutionPlan 的 peek_next、advance、is_complete 逻辑"""

    def _make_plan(self, n_actions: int) -> ExecutionPlan:
        """辅助方法：创建包含 n 个动作的 ExecutionPlan"""
        actions = [
            PlannedAction(action_name=f"action_{i}", capability_name=f"cap_{i}")
            for i in range(n_actions)
        ]
        return ExecutionPlan(plan_id="test-plan", actions=actions)

    def test_empty_plan_is_complete(self):
        """空动作列表的计划应立即完成"""
        plan = self._make_plan(0)
        assert plan.is_complete() is True
        assert plan.peek_next() is None

    def test_peek_next_returns_current_action(self):
        """peek_next 应返回当前索引对应的动作"""
        plan = self._make_plan(3)
        action = plan.peek_next()
        assert action is not None
        assert action.action_name == "action_0"

    def test_advance_moves_index(self):
        """advance 后 peek_next 应返回下一个动作"""
        plan = self._make_plan(3)
        plan.advance()
        action = plan.peek_next()
        assert action is not None
        assert action.action_name == "action_1"

    def test_full_traversal(self):
        """遍历所有动作后 is_complete 应为 True"""
        plan = self._make_plan(2)
        assert plan.is_complete() is False

        plan.advance()  # index -> 1
        assert plan.is_complete() is False

        plan.advance()  # index -> 2
        assert plan.is_complete() is True
        assert plan.peek_next() is None

    def test_advance_beyond_end(self):
        """超出末尾继续 advance 不应报错，is_complete 仍为 True"""
        plan = self._make_plan(1)
        plan.advance()
        plan.advance()  # 超出末尾
        assert plan.is_complete() is True


class TestTaskResultSerialization:
    """测试 TaskResult.to_dict 和 from_dict 的基本用例"""

    def test_simple_to_dict(self):
        """简单 TaskResult 序列化为字典"""
        tr = TaskResult(intent="navigate_to", params={"target": "厨房"}, confidence=0.95)
        d = tr.to_dict()
        assert d["intent"] == "navigate_to"
        assert d["params"] == {"target": "厨房"}
        assert d["confidence"] == 0.95
        assert d["sub_tasks"] == []
        assert d["raw_response"] is None

    def test_simple_from_dict(self):
        """从字典反序列化为 TaskResult"""
        data = {
            "intent": "rotate",
            "params": {"angle": 90},
            "sub_tasks": [],
            "confidence": 0.8,
            "raw_response": "ok",
        }
        tr = TaskResult.from_dict(data)
        assert tr.intent == "rotate"
        assert tr.params == {"angle": 90}
        assert tr.confidence == 0.8
        assert tr.raw_response == "ok"
        assert tr.sub_tasks == []

    def test_nested_sub_tasks_round_trip(self):
        """包含嵌套子任务的 TaskResult 序列化/反序列化"""
        child = TaskResult(intent="stop", params={})
        parent = TaskResult(
            intent="patrol",
            params={"area": "一楼"},
            sub_tasks=[child],
            confidence=0.9,
        )
        d = parent.to_dict()
        restored = TaskResult.from_dict(d)

        assert restored.intent == "patrol"
        assert len(restored.sub_tasks) == 1
        assert restored.sub_tasks[0].intent == "stop"

    def test_from_dict_defaults(self):
        """from_dict 对缺失字段使用默认值"""
        data = {"intent": "test"}
        tr = TaskResult.from_dict(data)
        assert tr.params == {}
        assert tr.sub_tasks == []
        assert tr.confidence == 1.0
        assert tr.raw_response is None
