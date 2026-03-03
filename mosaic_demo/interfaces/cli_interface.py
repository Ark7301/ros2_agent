"""
CLIInterface — 交互式命令行界面

接收用户自然语言输入，封装为 TaskContext 传递给处理管道，
将 ExecutionResult 格式化为中文可读文本展示给用户。
支持 "退出"/"exit" 安全关闭，异常时显示友好中文错误提示。
"""

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from mosaic_demo.interfaces_abstract.data_models import (
    ExecutionResult,
    TaskContext,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class CLIInterface:
    """交互式命令行界面

    通过回调函数与处理管道解耦，支持独立测试。
    """

    # 退出命令集合
    EXIT_COMMANDS = {"退出", "exit"}

    def __init__(
        self,
        process_callback: Callable[[TaskContext], Awaitable[ExecutionResult]],
    ):
        """初始化 CLI 界面

        Args:
            process_callback: 处理管道回调，接收 TaskContext 返回 ExecutionResult
        """
        self._process = process_callback

    async def run(self) -> None:
        """主循环：读取输入 → 处理 → 展示结果

        循环读取用户输入，输入为退出命令时安全关闭。
        异常时显示友好中文错误提示，不崩溃。
        """
        self._print_welcome()

        while True:
            try:
                # 使用 asyncio 兼容的方式读取输入
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input(">>> ")
                )

                # 去除首尾空白
                user_input = user_input.strip()

                # 空输入跳过
                if not user_input:
                    continue

                # 检查退出命令
                if user_input in self.EXIT_COMMANDS:
                    print("再见！系统已安全关闭。")
                    break

                # 封装为 TaskContext
                context = self.create_task_context(user_input)

                # 提示处理中
                print("正在处理...")

                # 调用处理管道
                result = await self._process(context)

                # 格式化并展示结果
                formatted = self.format_result(result)
                print(formatted)

            except KeyboardInterrupt:
                print("\n再见！系统已安全关闭。")
                break
            except EOFError:
                print("\n再见！系统已安全关闭。")
                break
            except Exception as e:
                logger.error("处理过程中发生异常: %s", e)
                print(f"⚠ 处理过程中发生错误: {e}")
                print("请重新输入指令，或输入 '退出' 关闭系统。")

    def format_result(self, result: ExecutionResult) -> str:
        """将 ExecutionResult 格式化为用户可读的中文文本

        成功时：✓ {message}
        失败时：✗ {message}（错误: {error}）

        Args:
            result: 执行结果

        Returns:
            格式化后的中文文本
        """
        if result.success:
            return f"✓ {result.message}"
        else:
            text = f"✗ {result.message}"
            if result.error:
                text += f"（错误: {result.error}）"
            return text

    @staticmethod
    def create_task_context(raw_input: str) -> TaskContext:
        """将用户输入封装为 TaskContext

        Args:
            raw_input: 用户原始输入字符串

        Returns:
            封装后的 TaskContext 实例
        """
        return TaskContext(raw_input=raw_input)

    def _print_welcome(self) -> None:
        """打印欢迎信息"""
        print("=" * 50)
        print("  MOSAIC Demo — 智能 Agent 交互系统")
        print("  输入自然语言指令，例如：导航到厨房")
        print("  输入 '退出' 或 'exit' 关闭系统")
        print("=" * 50)
