# CLI 通道插件
# 实现 ChannelPlugin Protocol，提供交互式命令行输入/输出通道
# 支持 "退出" 和 "exit" 命令安全关闭

from __future__ import annotations

import asyncio
import sys
from typing import Any, Callable

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ChannelPlugin,
    OutboundMessage,
    SendResult,
)

# 退出命令集合
_QUIT_COMMANDS = {"退出", "exit"}

# 默认输入提示符
_DEFAULT_PROMPT = ">>> "


class CLIChannel:
    """CLI 通道插件 — 交互式命令行输入/输出

    通过 stdin 读取用户输入，stdout 输出响应。
    使用 asyncio.run_in_executor 将阻塞的 input() 包装为异步操作。
    支持 "退出" 和 "exit" 命令安全关闭。
    """

    def __init__(self, prompt: str = _DEFAULT_PROMPT) -> None:
        self.meta = PluginMeta(
            id="cli",
            name="CLI Channel",
            version="0.1.0",
            description="交互式命令行通道，支持 stdin 输入和 stdout 输出",
            kind="channel",
            author="MOSAIC",
        )
        self._prompt = prompt
        self._handler: Callable | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """启动交互式输入循环

        创建一个 asyncio Task，在后台通过 run_in_executor
        读取 stdin 输入。每行输入触发已注册的消息处理器。
        """
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._input_loop())

    async def stop(self) -> None:
        """停止输入循环，取消后台任务"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def send(self, message: OutboundMessage) -> SendResult:
        """将消息输出到 stdout，并重新显示输入提示符

        Args:
            message: 出站消息对象

        Returns:
            SendResult: 发送结果
        """
        try:
            print(f"\n{message.content}")
            # 重新显示提示符，让用户知道可以继续输入
            print(self._prompt, end="", flush=True)
            return SendResult(success=True)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def on_message(self, handler: Callable) -> None:
        """注册入站消息处理器

        Args:
            handler: 接收用户输入的回调函数
        """
        self._handler = handler

    async def _input_loop(self) -> None:
        """交互式输入循环核心

        使用 run_in_executor 将阻塞的 input() 调用
        放到线程池执行，避免阻塞事件循环。
        遇到退出命令或 EOF 时安全停止。
        """
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                # 在线程池中执行阻塞的 input()
                line = await loop.run_in_executor(
                    None, lambda: input(self._prompt)
                )
            except (EOFError, KeyboardInterrupt):
                # EOF 或 Ctrl+C 时安全退出
                break

            # 跳过空行
            stripped = line.strip()
            if not stripped:
                continue

            # 检查退出命令
            if stripped.lower() in _QUIT_COMMANDS or stripped in _QUIT_COMMANDS:
                print("再见！")
                break

            # 触发消息处理器
            if self._handler is not None:
                try:
                    result = self._handler(stripped)
                    # 支持异步处理器
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    # 处理器异常不应中断输入循环
                    pass

        # 循环结束后标记停止
        self._running = False


def create_plugin() -> CLIChannel:
    """工厂函数 — 返回 CLIChannel 实例"""
    return CLIChannel()
