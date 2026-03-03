"""
CLIInterface 属性测试

测试 CLIInterface 的输入封装和结果格式化功能。
使用 hypothesis 库进行属性测试。
"""

import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hypothesis import given, settings
from hypothesis import strategies as st

from mosaic_demo.interfaces.cli_interface import CLIInterface
from mosaic_demo.interfaces_abstract.data_models import (
    ExecutionResult,
    TaskContext,
    TaskStatus,
)


# ---- 自定义 Hypothesis Strategy ----

# 生成随机 ExecutionResult 的 strategy
def execution_result_strategy():
    """生成随机 ExecutionResult，覆盖成功和失败两种情况"""
    return st.builds(
        ExecutionResult,
        task_id=st.text(min_size=1, max_size=36),
        success=st.booleans(),
        message=st.text(min_size=1, max_size=100),
        status=st.sampled_from([TaskStatus.SUCCEEDED, TaskStatus.FAILED]),
        data=st.just({}),
        error=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    )


# ---- 属性测试 ----


class TestCLIInterfaceInputEncapsulation:
    """Property 14: CLIInterface 输入封装

    **Validates: Requirements 10.2**

    对于任意用户输入字符串，CLIInterface 应将其正确封装为 TaskContext，
    其中 raw_input 等于原始输入。
    """

    @given(raw_input=st.text(min_size=0, max_size=200))
    @settings(max_examples=100)
    def test_create_task_context_preserves_raw_input(self, raw_input: str):
        """
        对于任意用户输入字符串，create_task_context 返回的
        TaskContext.raw_input 应等于原始输入。
        """
        context = CLIInterface.create_task_context(raw_input)

        # 验证返回类型为 TaskContext
        assert isinstance(context, TaskContext)

        # 验证 raw_input 与原始输入完全一致
        assert context.raw_input == raw_input


class TestCLIInterfaceResultFormatting:
    """Property 15: CLIInterface 结果格式化

    **Validates: Requirements 10.3**

    对于任意 ExecutionResult（成功或失败），CLIInterface 的 format_result
    方法应返回包含执行状态和消息的中文可读文本。
    """

    def _make_cli(self) -> CLIInterface:
        """创建一个带 dummy callback 的 CLIInterface 实例"""
        async def dummy_callback(ctx: TaskContext) -> ExecutionResult:
            return ExecutionResult(task_id="dummy", success=True, message="ok")
        return CLIInterface(process_callback=dummy_callback)

    @given(result=execution_result_strategy())
    @settings(max_examples=100)
    def test_format_result_contains_message(self, result: ExecutionResult):
        """
        对于任意 ExecutionResult，format_result 返回的文本应包含 message。
        """
        cli = self._make_cli()
        formatted = cli.format_result(result)

        # 格式化结果应包含原始消息
        assert result.message in formatted

    @given(
        message=st.text(min_size=1, max_size=100),
        task_id=st.text(min_size=1, max_size=36),
    )
    @settings(max_examples=100)
    def test_format_result_success_contains_checkmark(self, message: str, task_id: str):
        """
        对于成功的 ExecutionResult，format_result 返回的文本应包含 ✓ 标记。
        """
        result = ExecutionResult(
            task_id=task_id, success=True, message=message
        )
        cli = self._make_cli()
        formatted = cli.format_result(result)

        # 成功结果应包含 ✓
        assert "✓" in formatted
        assert message in formatted

    @given(
        message=st.text(min_size=1, max_size=100),
        task_id=st.text(min_size=1, max_size=36),
        error=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    )
    @settings(max_examples=100)
    def test_format_result_failure_contains_cross(self, message: str, task_id: str, error):
        """
        对于失败的 ExecutionResult，format_result 返回的文本应包含 ✗ 标记。
        """
        result = ExecutionResult(
            task_id=task_id, success=False, message=message, error=error
        )
        cli = self._make_cli()
        formatted = cli.format_result(result)

        # 失败结果应包含 ✗
        assert "✗" in formatted
        assert message in formatted
