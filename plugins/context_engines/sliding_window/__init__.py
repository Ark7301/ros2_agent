# 滑动窗口上下文引擎插件
# 基于滑动窗口策略管理对话上下文，按 token 预算从尾部截取消息

from __future__ import annotations

from typing import Any

from mosaic.plugin_sdk.types import (
    AssembleResult,
    CompactResult,
    ContextEnginePlugin,
    PluginMeta,
)

# 默认压缩阈值：当消息数超过此值时触发自动压缩
_DEFAULT_COMPACT_THRESHOLD = 100


def _estimate_tokens(message: dict) -> int:
    """简单 token 估算：字符串长度 // 4"""
    return max(len(str(message)) // 4, 1)


class SlidingWindowContextEngine:
    """滑动窗口上下文引擎

    按 session 隔离存储消息，assemble 时从尾部向前选取
    直到 token 预算耗尽，compact 时移除最旧的消息。
    """

    def __init__(self, compact_threshold: int = _DEFAULT_COMPACT_THRESHOLD):
        self.meta = PluginMeta(
            id="sliding-window-context",
            name="Sliding Window Context Engine",
            version="0.1.0",
            description="基于滑动窗口的上下文引擎，按 token 预算裁剪历史消息",
            kind="context-engine",
            author="MOSAIC",
        )
        # 每个 session 的消息列表
        self._sessions: dict[str, list[dict[str, Any]]] = {}
        # 压缩阈值
        self._compact_threshold = compact_threshold

    async def ingest(self, session_id: str, message: dict) -> None:
        """摄入消息到指定 session 的上下文"""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
        self._sessions[session_id].append(message)

    async def assemble(self, session_id: str, token_budget: int) -> AssembleResult:
        """按 token 预算从尾部组装上下文消息

        从最新消息向前遍历，累计 token 不超过 budget，
        返回的消息保持时间顺序（旧 → 新）。
        """
        messages = self._sessions.get(session_id, [])
        selected: list[dict[str, Any]] = []
        total_tokens = 0

        # 从尾部向前选取
        for msg in reversed(messages):
            msg_tokens = _estimate_tokens(msg)
            if total_tokens + msg_tokens > token_budget:
                break
            selected.append(msg)
            total_tokens += msg_tokens

        # 反转恢复时间顺序
        selected.reverse()
        return AssembleResult(messages=selected, token_count=total_tokens)

    async def compact(self, session_id: str, force: bool = False) -> CompactResult:
        """压缩上下文：移除最旧的消息

        当 force=True 或消息数超过阈值时，移除前半部分消息。
        """
        messages = self._sessions.get(session_id, [])
        total = len(messages)

        if not force and total <= self._compact_threshold:
            return CompactResult(removed_count=0, remaining_count=total)

        # 移除前半部分消息
        half = total // 2
        self._sessions[session_id] = messages[half:]
        remaining = len(self._sessions[session_id])
        return CompactResult(removed_count=half, remaining_count=remaining)


def create_plugin() -> SlidingWindowContextEngine:
    """工厂函数 — 返回 SlidingWindowContextEngine 实例"""
    return SlidingWindowContextEngine()
