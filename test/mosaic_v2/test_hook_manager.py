"""属性测试 - HookManager 拦截语义
属性 13：对于任意钩子链，若某个 handler 返回 False，
则后续 handler 不再执行，emit() 返回 False。
**Validates: Requirement 8.4**
"""
from __future__ import annotations
import asyncio
import pytest
from hypothesis import given, settings, strategies as st, assume
from mosaic.core.hooks import HookManager

hook_point_st = st.from_regex(
    r"[a-z][a-z0-9_]{0,10}(\.[a-z][a-z0-9_]{0,10}){0,2}",
    fullmatch=True,
)
handler_count_st = st.integers(min_value=2, max_value=6)
block_index_st = st.integers(min_value=0, max_value=5)
priority_list_st = st.lists(
    st.integers(min_value=0, max_value=200),
    min_size=2, max_size=6,
).map(sorted)


def run_async(coro):
    """辅助函数：在新的事件循环中运行协程，避免循环复用问题"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestHookInterceptionSemantics:
    """属性 13: Hook 拦截语义 **Validates: Requirement 8.4**"""

    @given(
        hook_point=hook_point_st,
        handler_count=handler_count_st,
        block_idx=block_index_st,
        priorities=priority_list_st,
    )
    @settings(max_examples=200)
    def test_handler_returning_false_stops_chain(
        self, hook_point, handler_count, block_idx, priorities
    ):
        """handler 返回 False 时后续不执行，emit 返回 False"""
        assume(block_idx < handler_count)
        assume(len(priorities) >= handler_count)
        priorities = priorities[:handler_count]
        hm = HookManager()
        execution_log = []
        for i in range(handler_count):
            if i == block_idx:
                async def blocking_handler(ctx, idx=i):
                    execution_log.append(idx)
                    return False
                hm.on(hook_point, blocking_handler, priority=priorities[i])
            else:
                async def normal_handler(ctx, idx=i):
                    execution_log.append(idx)
                    return True
                hm.on(hook_point, normal_handler, priority=priorities[i])

        async def _verify():
            result = await hm.emit(hook_point, {"test": True})
            assert result is False, (
                f"handler {block_idx} 返回 False 后 emit 应返回 False"
            )
            assert len(execution_log) == block_idx + 1, (
                f"拦截后应执行 {block_idx + 1} 个 handler，"
                f"实际执行 {len(execution_log)} 个"
            )
            for idx in execution_log:
                assert idx <= block_idx
        run_async(_verify())

    @given(
        hook_point=hook_point_st,
        handler_count=handler_count_st,
        priorities=priority_list_st,
    )
    @settings(max_examples=200)
    def test_all_handlers_pass_emit_returns_true(
        self, hook_point, handler_count, priorities
    ):
        """所有 handler 返回 True/None 时，全部执行且 emit 返回 True"""
        assume(len(priorities) >= handler_count)
        priorities = priorities[:handler_count]
        hm = HookManager()
        execution_log = []
        for i in range(handler_count):
            if i % 2 == 0:
                async def true_handler(ctx, idx=i):
                    execution_log.append(idx)
                    return True
                hm.on(hook_point, true_handler, priority=priorities[i])
            else:
                async def none_handler(ctx, idx=i):
                    execution_log.append(idx)
                    return None
                hm.on(hook_point, none_handler, priority=priorities[i])

        async def _verify():
            result = await hm.emit(hook_point, {"test": True})
            assert result is True, (
                f"所有 handler 返回 True/None 时 emit 应返回 True"
            )
            assert len(execution_log) == handler_count, (
                f"应执行 {handler_count} 个 handler，"
                f"实际执行 {len(execution_log)} 个"
            )
        run_async(_verify())

    @given(
        hook_point=hook_point_st,
        priorities=st.lists(
            st.integers(min_value=0, max_value=200),
            min_size=3, max_size=6, unique=True,
        ),
    )
    @settings(max_examples=200)
    def test_handlers_execute_in_priority_order(self, hook_point, priorities):
        """handler 按 priority 升序执行（数值越小越先执行）"""
        hm = HookManager()
        execution_order = []
        for prio in priorities:
            async def ordered_handler(ctx, p=prio):
                execution_order.append(p)
                return True
            hm.on(hook_point, ordered_handler, priority=prio)

        async def _verify():
            await hm.emit(hook_point, {})
            expected = sorted(priorities)
            assert execution_order == expected, (
                f"handler 应按优先级升序执行，期望 {expected}，实际 {execution_order}"
            )
        run_async(_verify())

    @given(hook_point=hook_point_st, handler_count=handler_count_st)
    @settings(max_examples=100)
    def test_exception_handler_skipped_chain_continues(
        self, hook_point, handler_count
    ):
        """handler 抛异常时被跳过，后续 handler 继续执行（Req 8.6）"""
        assume(handler_count >= 3)
        hm = HookManager()
        execution_log = []
        for i in range(handler_count):
            if i == 1:
                async def error_handler(ctx, idx=i):
                    execution_log.append(idx)
                    raise RuntimeError("模拟异常")
                hm.on(hook_point, error_handler, priority=i * 10)
            else:
                async def normal_handler(ctx, idx=i):
                    execution_log.append(idx)
                    return True
                hm.on(hook_point, normal_handler, priority=i * 10)

        async def _verify():
            result = await hm.emit(hook_point, {})
            assert result is True, "异常 handler 不应导致 emit 返回 False"
            assert len(execution_log) >= handler_count - 1
        run_async(_verify())

    def test_timeout_handler_skipped_chain_continues(self):
        """handler 超时时被跳过，后续 handler 继续执行（Req 8.5）。
        注意：每个用例需等待 5 秒超时，使用固定用例而非 hypothesis。
        """
        hm = HookManager()
        execution_log = []

        async def before_handler(ctx):
            execution_log.append("before")
            return True
        hm.on("test.timeout", before_handler, priority=10)

        async def slow_handler(ctx):
            execution_log.append("slow_start")
            await asyncio.sleep(10)
            execution_log.append("slow_end")
            return True
        hm.on("test.timeout", slow_handler, priority=20)

        async def after_handler(ctx):
            execution_log.append("after")
            return True
        hm.on("test.timeout", after_handler, priority=30)

        async def _verify():
            result = await hm.emit("test.timeout", {})
            assert result is True, "超时 handler 不应导致 emit 返回 False"
            assert "before" in execution_log
            assert "after" in execution_log
            assert "slow_end" not in execution_log
        run_async(_verify())

    @given(hook_point=hook_point_st)
    @settings(max_examples=100)
    def test_empty_hook_point_returns_true(self, hook_point):
        """无 handler 注册时，emit 返回 True"""
        hm = HookManager()

        async def _verify():
            result = await hm.emit(hook_point, {})
            assert result is True, "无 handler 时 emit 应返回 True"
        run_async(_verify())
