"""
MOSAIC 初期验证 Demo 入口文件

启动 Agent 系统：
1. 加载配置文件（agent_config.yaml、locations.yaml）
2. 初始化各组件并串联
3. 定义处理管道回调
4. 启动 CLI 交互主循环
"""

import asyncio
import logging
import os

from mosaic_demo.config.config_manager import ConfigManager
from mosaic_demo.capabilities.location_service import LocationService
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.capabilities.mock_navigation import MockNavigationCapability
from mosaic_demo.capabilities.mock_motion import MockMotionCapability
from mosaic_demo.model_providers.midea_client import MideaClient
from mosaic_demo.model_providers.llm_provider import LLMProvider
from mosaic_demo.model_providers.minimax_client import MiniMaxClient
from mosaic_demo.model_providers.minimax_provider import MiniMaxProvider
from mosaic_demo.agent_core.task_parser import TaskParser
from mosaic_demo.agent_core.task_planner import TaskPlanner
from mosaic_demo.agent_core.task_executor import TaskExecutor
from mosaic_demo.interfaces.cli_interface import CLIInterface
from mosaic_demo.interfaces_abstract.data_models import (
    ExecutionResult,
    TaskContext,
    TaskStatus,
)


def _get_base_dir() -> str:
    """获取 mosaic_demo 包所在目录，用于构建配置文件的相对路径"""
    return os.path.dirname(os.path.abspath(__file__))


def main():
    """主入口函数 — 初始化所有组件并启动 CLI 交互循环"""
    base_dir = _get_base_dir()

    # ── 1. 加载配置 ──
    config_path = os.path.join(base_dir, "config", "agent_config.yaml")
    config_manager = ConfigManager(config_path)
    config_manager.load()

    # 配置日志
    log_level = config_manager.get("logging.level", "INFO")
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── 2. 初始化 LocationService ──
    locations_path = os.path.join(base_dir, "config", "locations.yaml")
    location_service = LocationService(locations_path)
    location_service.load()

    # ── 3. 初始化 CapabilityRegistry 并注册 Mock 能力 ──
    registry = CapabilityRegistry()

    nav_capability = MockNavigationCapability(location_service)
    motion_capability = MockMotionCapability()

    registry.register(nav_capability)
    registry.register(motion_capability)

    # ── 4. 初始化 AI Provider 层 ──
    model_config = config_manager.get("model_provider.config", {})
    retry_config = config_manager.get("retry", {})
    provider_type = config_manager.get("model_provider.type", "minimax")

    if provider_type == "minimax":
        minimax_client = MiniMaxClient(
            config=model_config,
            max_retries=retry_config.get("max_retries", 3),
            backoff_base=retry_config.get("backoff_base", 2),
        )
        llm_provider = MiniMaxProvider(client=minimax_client, registry=registry, location_service=location_service)
    else:
        # 美的 AIMP Claude API（兼容旧配置）
        midea_client = MideaClient(
            config=model_config,
            max_retries=retry_config.get("max_retries", 3),
            backoff_base=retry_config.get("backoff_base", 2),
        )
        llm_provider = LLMProvider(client=midea_client, registry=registry, location_service=location_service)

    # ── 5. 初始化 Agent 核心调度层 ──
    task_parser = TaskParser(model_provider=llm_provider)
    task_planner = TaskPlanner(registry=registry)
    task_executor = TaskExecutor(
        registry=registry,
        max_retries=retry_config.get("max_retries", 3),
        backoff_base=retry_config.get("backoff_base", 2),
    )

    # ── 6. 定义处理管道回调 ──
    async def process_pipeline(context: TaskContext) -> ExecutionResult:
        """处理管道：解析 → 规划 → 执行

        Args:
            context: 用户输入封装的任务上下文

        Returns:
            最终执行结果
        """
        logging.info("=" * 60)
        logging.info("📥 用户输入: %s", context.raw_input)
        logging.info("=" * 60)

        # 任务解析
        logging.info("── 阶段 1/3: 任务解析 (TaskParser → MiniMax LLM) ──")
        task_result = await task_parser.parse(context)
        logging.info("📋 解析结果: intent=%s, params=%s, confidence=%.2f",
                      task_result.intent, task_result.params, task_result.confidence)

        # 如果解析结果为错误，直接返回
        if task_result.intent == "error":
            error_msg = task_result.params.get("message", "未知错误")
            logging.info("❌ 解析失败: %s", error_msg)
            return ExecutionResult(
                task_id="",
                success=False,
                message=error_msg,
                status=TaskStatus.FAILED,
                error=error_msg,
            )

        # 任务规划
        logging.info("── 阶段 2/3: 任务规划 (TaskPlanner) ──")
        plan = await task_planner.plan(task_result)
        logging.info("📝 执行计划: plan_id=%s, actions=%d",
                      plan.plan_id[:8], len(plan.actions))
        for i, action in enumerate(plan.actions):
            logging.info("  动作[%d]: %s → capability=%s, params=%s",
                          i, action.action_name, action.capability_name, action.parameters)

        # 任务执行
        logging.info("── 阶段 3/3: 任务执行 (TaskExecutor) ──")
        result = await task_executor.execute_plan(plan)
        logging.info("🏁 执行结果: success=%s, message=%s", result.success, result.message)
        if result.data:
            logging.info("📦 返回数据: %s", result.data)
        logging.info("=" * 60)
        return result

    # ── 7. 启动 CLI 交互主循环 ──
    cli = CLIInterface(process_callback=process_pipeline)
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
