"""
TaskParser — 任务解析器

将自然语言指令委托给 ModelProvider 解析为结构化 TaskResult，
并校验解析结果的合法性（如 intent 非空）。
"""

from mosaic_demo.interfaces_abstract.model_provider import ModelProvider
from mosaic_demo.interfaces_abstract.data_models import TaskContext, TaskResult


class TaskParser:
    """任务解析器 — 自然语言 → 结构化 TaskResult

    通过依赖倒置接收 ModelProvider 实例，
    委托其完成实际的自然语言解析工作。
    """

    def __init__(self, model_provider: ModelProvider):
        """初始化任务解析器

        Args:
            model_provider: AI 模型提供者实例（依赖倒置）
        """
        self._provider = model_provider

    async def parse(self, context: TaskContext) -> TaskResult:
        """解析自然语言指令

        委托 ModelProvider 解析，然后校验结果合法性。
        若 intent 为空，返回包含错误信息的 TaskResult 而非抛出异常。

        Args:
            context: 任务上下文，包含用户原始输入

        Returns:
            解析后的结构化任务结果，或包含错误信息的结果
        """
        result = await self._provider.parse_task(context)
        return self._validate(result)

    def _validate(self, result: TaskResult) -> TaskResult:
        """校验解析结果合法性

        检查 intent 是否为空，为空时返回包含错误信息的 TaskResult。

        Args:
            result: ModelProvider 返回的解析结果

        Returns:
            校验通过的原始结果，或包含错误信息的新结果
        """
        if not result.intent or not result.intent.strip():
            # intent 为空时，返回错误结果而非抛出异常
            return TaskResult(
                intent="error",
                params={"message": "意图解析为空，请重新输入"},
                confidence=0.0,
                raw_response=result.raw_response,
            )
        return result
