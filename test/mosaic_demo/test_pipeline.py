"""
管道错误传播属性测试 & 端到端管道集成测试

Property 13: 管道错误传播
- 对于任意管道阶段（TaskParser / TaskPlanner / TaskExecutor）中抛出的异常，
  Agent 应将其封装为 ExecutionResult 回传，不产生未处理异常。

端到端集成测试:
- 使用全 Mock 组件测试完整管道：输入 → 解析 → 规划 → 执行 → 结果
- 验证错误处理路径

Validates: Requirements 13.1, 13.2, 13.3, 13.4
"""

import pytest
from hypothesis import given, strategies as st, settings

from mosaic_demo.interfaces_abstract.model_provider import ModelProvider
from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus,
    ExecutionResult,
    Task,
    TaskContext,
    TaskResult,
    TaskStatus,
)
from mosaic_demo.agent_core.task_parser import TaskParser
from mosaic_demo.agent_core.task_planner import TaskPlanner
from mosaic_demo.agent_core.task_executor import TaskExecutor


# ── Mock 组件 ──


class SuccessModelProvider(ModelProvider):
    """Mock ModelProvider — 返回固定成功的 TaskResult"""

    def __init__(self, intent: str = "navigate_to", params: dict = None):
        self._intent = intent
        self._params = params or {"target": "厨房"}

    async def parse_task(self, context: TaskContext) -> TaskResult:
        return TaskResult(
            intent=self._intent,
            params=self._params,
            confidence=0.95,
        )

    def get_supported_intents(self) -> list[str]:
        return [self._intent]


class ErrorModelProvider(ModelProvider):
    """Mock ModelProvider — 抛出异常"""

    def __init__(self, error_msg: str = "模型调用失败"):
        self._error_msg = error_msg

    async def parse_task(self, context: TaskContext) -> TaskResult:
        raise RuntimeError(self._error_msg)

    def get_supported_intents(self) -> list[str]:
        return []


class SuccessCapability(Capability):
    """Mock Capability — 始终返回成功"""

    def __init__(self, name: str = "test_cap", intents: list[str] = None):
        self._name = name
        self._intents = intents or ["navigate_to"]

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(self, task: Task, feedback_callback=None) -> ExecutionResult:
        return ExecutionResult(
            task_id=task.task_id,
            success=True,
            message=f"执行 {task.intent} 成功",
            status=TaskStatus.SUCCEEDED,
        )

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return "测试用成功能力"


class ErrorCapability(Capability):
    """Mock Capability — 执行时抛出异常"""

    def __init__(self, name: str = "error_cap", intents: list[str] = None,
                 error_msg: str = "能力执行异常"):
        self._name = name
        self._intents = intents or ["error_intent"]
        self._error_msg = error_msg

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(self, task: Task, feedback_callback=None) -> ExecutionResult:
        raise RuntimeError(self._error_msg)

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return "测试用异常能力"


# ── 管道处理函数（复刻 main.py 中的 process_pipeline 逻辑） ──


async def process_pipeline(
    task_parser: TaskParser,
    task_planner: TaskPlanner,
    task_executor: TaskExecutor,
    context: TaskContext,
) -> ExecutionResult:
    """处理管道：解析 → 规划 → 执行

    复刻 main.py 中的管道逻辑，外层包装 try/except 确保不产生未处理异常。

    Args:
        task_parser: 任务解析器
        task_planner: 任务规划器
        task_executor: 任务执行器
        context: 用户输入封装的任务上下文

    Returns:
        最终执行结果，异常时返回包含错误信息的 ExecutionResult
    """
    try:
        # 任务解析
        task_result = await task_parser.parse(context)

        # 如果解析结果为错误，直接返回
        if task_result.intent == "error":
            error_msg = task_result.params.get("message", "未知错误")
            return ExecutionResult(
                task_id="",
                success=False,
                message=error_msg,
                status=TaskStatus.FAILED,
                error=error_msg,
            )

        # 任务规划
        plan = await task_planner.plan(task_result)

        # 任务执行
        result = await task_executor.execute_plan(plan)
        return result

    except Exception as e:
        # 捕获所有未处理异常，封装为 ExecutionResult
        return ExecutionResult(
            task_id="",
            success=False,
            message=f"管道处理异常: {e}",
            status=TaskStatus.FAILED,
            error=str(e),
        )


# ── 辅助函数 ──


def _build_pipeline(
    model_provider: ModelProvider,
    capabilities: list[Capability] = None,
    max_retries: int = 0,
) -> tuple[TaskParser, TaskPlanner, TaskExecutor, CapabilityRegistry]:
    """构建完整管道组件

    Args:
        model_provider: AI 模型提供者
        capabilities: 要注册的能力列表
        max_retries: TaskExecutor 最大重试次数

    Returns:
        (task_parser, task_planner, task_executor, registry) 元组
    """
    registry = CapabilityRegistry()
    if capabilities:
        for cap in capabilities:
            registry.register(cap)

    parser = TaskParser(model_provider=model_provider)
    planner = TaskPlanner(registry=registry)
    executor = TaskExecutor(registry=registry, max_retries=max_retries, backoff_base=0)

    return parser, planner, executor, registry


# ══════════════════════════════════════════════════════════════
# 10.2 属性测试 — Property 13: 管道错误传播
# ══════════════════════════════════════════════════════════════


# 生成随机错误消息的策略
error_message_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P", "Z")),
    min_size=1,
    max_size=100,
)

# 管道阶段名称策略
pipeline_stage_strategy = st.sampled_from(["parser", "planner", "executor"])


@pytest.mark.asyncio
class TestPipelineErrorPropagation:
    """Property 13: 管道错误传播

    **Validates: Requirements 13.1, 13.2**
    """

    @given(error_msg=error_message_strategy)
    @settings(max_examples=50)
    async def test_property13_parser_error_propagation(self, error_msg: str):
        """TaskParser 阶段抛出异常时，管道应返回 ExecutionResult 而非未处理异常

        **Validates: Requirements 13.1, 13.2**
        """
        # 构造会抛出异常的 ModelProvider
        provider = ErrorModelProvider(error_msg=error_msg)
        cap = SuccessCapability()
        parser, planner, executor, _ = _build_pipeline(provider, [cap])

        context = TaskContext(raw_input="测试输入")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证：返回 ExecutionResult，不产生未处理异常
        assert isinstance(result, ExecutionResult), "管道应返回 ExecutionResult"
        assert result.success is False, "异常情况应返回失败结果"
        assert result.error is not None, "错误结果应包含 error 字段"

    @given(error_msg=error_message_strategy)
    @settings(max_examples=50)
    async def test_property13_executor_error_propagation(self, error_msg: str):
        """TaskExecutor 阶段 Capability 抛出异常时，管道应返回 ExecutionResult

        **Validates: Requirements 13.1, 13.2**
        """
        # 构造正常 Provider + 会抛出异常的 Capability
        intent = "error_intent"
        provider = SuccessModelProvider(intent=intent, params={})
        error_cap = ErrorCapability(
            name="error_cap", intents=[intent], error_msg=error_msg
        )
        parser, planner, executor, _ = _build_pipeline(provider, [error_cap])

        context = TaskContext(raw_input="测试输入")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证：返回 ExecutionResult，不产生未处理异常
        assert isinstance(result, ExecutionResult), "管道应返回 ExecutionResult"
        assert result.success is False, "异常情况应返回失败结果"

    @given(raw_input=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    async def test_property13_unregistered_intent_propagation(self, raw_input: str):
        """未注册意图时，管道应返回 ExecutionResult 而非未处理异常

        **Validates: Requirements 13.1, 13.2**
        """
        # 构造返回未注册意图的 Provider，不注册任何 Capability
        provider = SuccessModelProvider(intent="unknown_intent", params={})
        parser, planner, executor, _ = _build_pipeline(provider, [])

        context = TaskContext(raw_input=raw_input)
        result = await process_pipeline(parser, planner, executor, context)

        # 验证：返回 ExecutionResult，不产生未处理异常
        assert isinstance(result, ExecutionResult), "管道应返回 ExecutionResult"
        assert result.success is False, "未注册意图应返回失败结果"


# ══════════════════════════════════════════════════════════════
# 10.3 端到端管道集成测试
# ══════════════════════════════════════════════════════════════


@pytest.mark.asyncio
class TestPipelineIntegration:
    """端到端管道集成测试 — 全 Mock 组件

    **Validates: Requirements 13.1, 13.2, 13.3, 13.4**
    """

    async def test_success_path_navigate_to(self):
        """成功路径：输入 → 解析为 navigate_to → 规划 → 执行 → 成功结果

        **Validates: Requirements 13.1**
        """
        # 构造全 Mock 管道
        provider = SuccessModelProvider(intent="navigate_to", params={"target": "厨房"})
        cap = SuccessCapability(name="nav", intents=["navigate_to"])
        parser, planner, executor, _ = _build_pipeline(provider, [cap])

        context = TaskContext(raw_input="导航到厨房")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证成功路径
        assert isinstance(result, ExecutionResult)
        assert result.success is True, "成功路径应返回 success=True"
        assert result.status == TaskStatus.SUCCEEDED

    async def test_error_path_parse_failure(self):
        """错误路径：解析失败 → 返回错误 ExecutionResult

        **Validates: Requirements 13.2, 13.3**
        """
        # 构造抛出异常的 ModelProvider
        provider = ErrorModelProvider(error_msg="LLM 调用失败")
        parser, planner, executor, _ = _build_pipeline(provider, [])

        context = TaskContext(raw_input="导航到厨房")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证错误路径
        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.status == TaskStatus.FAILED
        assert result.error is not None

    async def test_error_path_unregistered_intent(self):
        """错误路径：未注册意图 → 返回错误 ExecutionResult

        **Validates: Requirements 13.2, 13.4**
        """
        # Provider 返回 navigate_to 意图，但 Registry 中未注册该意图
        provider = SuccessModelProvider(intent="navigate_to", params={"target": "厨房"})
        parser, planner, executor, _ = _build_pipeline(provider, [])

        context = TaskContext(raw_input="导航到厨房")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证：未注册意图应返回失败
        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.status == TaskStatus.FAILED

    async def test_error_path_capability_execution_failure(self):
        """错误路径：Capability 执行失败 → 返回错误 ExecutionResult

        **Validates: Requirements 13.1, 13.2**
        """
        intent = "fail_action"
        provider = SuccessModelProvider(intent=intent, params={})
        error_cap = ErrorCapability(
            name="fail_cap", intents=[intent], error_msg="执行过程中发生错误"
        )
        parser, planner, executor, _ = _build_pipeline(provider, [error_cap])

        context = TaskContext(raw_input="执行失败动作")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证：Capability 异常应被封装为 ExecutionResult
        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.status == TaskStatus.FAILED

    async def test_empty_intent_returns_error(self):
        """错误路径：ModelProvider 返回空意图 → TaskParser 拒绝 → 返回错误

        **Validates: Requirements 13.4**
        """
        # 构造返回空意图的 Provider
        class EmptyIntentProvider(ModelProvider):
            async def parse_task(self, context: TaskContext) -> TaskResult:
                return TaskResult(intent="", params={})

            def get_supported_intents(self) -> list[str]:
                return []

        provider = EmptyIntentProvider()
        parser, planner, executor, _ = _build_pipeline(provider, [])

        context = TaskContext(raw_input="空意图测试")
        result = await process_pipeline(parser, planner, executor, context)

        # 验证：空意图被 TaskParser 拒绝，管道返回错误
        assert isinstance(result, ExecutionResult)
        assert result.success is False
        assert result.status == TaskStatus.FAILED
