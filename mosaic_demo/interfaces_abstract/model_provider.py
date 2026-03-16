from __future__ import annotations

"""
ModelProvider 抽象基类 — AI 模型提供者接口

定义 Agent 核心与 AI 模型之间的抽象契约，
具体实现（如 LLMProvider）需继承此基类。
"""

from abc import ABC, abstractmethod

from mosaic_demo.interfaces_abstract.data_models import TaskContext, TaskResult


class ModelProvider(ABC):
    """AI 模型提供者抽象接口

    所有 AI 模型实现（如 OpenAI Function Calling）
    必须继承此基类并实现所有抽象方法。
    """

    @abstractmethod
    async def parse_task(self, context: TaskContext) -> TaskResult:
        """解析自然语言指令为结构化任务

        Args:
            context: 任务上下文，包含用户原始输入及元数据

        Returns:
            解析后的结构化任务结果
        """
        pass

    @abstractmethod
    def get_supported_intents(self) -> list[str]:
        """返回支持的意图类型列表

        Returns:
            当前模型提供者支持解析的意图名称列表
        """
        pass
