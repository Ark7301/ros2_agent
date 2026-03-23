"""属性测试 — EventBus 中间件拦截

属性 2：对于任意 Event，若中间件链中任一中间件返回 None，
则该 Event 不会进入队列，不会被分发。
当所有中间件返回非 None 时，事件正常入队。
中间件按注册顺序依次执行。

**Validates: Requirements 1.7, 1.8**
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from hypothesis import given, settings, strategies as st, assume

from mosaic.protocol.events import Event, EventPriority
from mosaic.core.event_bus import EventBus


# ── Hypothesis 策略 ──

# 事件优先级策略
priority_st = st.sampled_from(list(EventPriority))

# 事件类型策略：生成合理的事件类型字符串
event_type_st = st.from_regex(r"[a-z][a-z0-9_]{0,15}(\.[a-z][a-z0-9_]{0,15}){0,2}", fullmatch=True)

# 事件源策略
source_st = st.from_regex(r"[a-z][a-z0-9_]{1,10}", fullmatch=True)

# payload 策略：简单字典
payload_st = st.fixed_dictionaries({}, optional={"key": st.text(min_size=0, max_size=20)})

# 中间件数量策略（1~5 个中间件）
middleware_count_st = st.integers(min_value=1, max_value=5)

# 拦截位置策略（哪个中间件返回 None）
block_index_st = st.integers(min_value=0, max_value=4)


def make_event(
    event_type: str = "test.event",
    source: str = "test",
    priority: EventPriority = EventPriority.NORMAL,
    payload: dict | None = None,
) -> Event:
    """辅助函数：创建测试用 Event"""
    return Event(
        type=event_type,
        payload=payload or {},
        source=source,
        priority=priority,
    )


class TestEventBusMiddlewareInterception:
    """属性 2: EventBus 中间件拦截

    **Validates: Requirements 1.7, 1.8**
    """

    @given(
        event_type=event_type_st,
        source=source_st,
        priority=priority_st,
        mw_count=middleware_count_st,
        block_idx=block_index_st,
    )
    @settings(max_examples=200)
    def test_middleware_returning_none_blocks_event(
        self,
        event_type: str,
        source: str,
        priority: EventPriority,
        mw_count: int,
        block_idx: int,
    ):
        """任一中间件返回 None 时，事件不进入队列（Requirement 1.7）。

        生成 mw_count 个中间件，其中第 block_idx 个返回 None，
        验证 emit 后队列为空。
        """
        # 确保拦截位置在中间件数量范围内
        assume(block_idx < mw_count)

        event = make_event(event_type=event_type, source=source, priority=priority)
        bus = EventBus()

        # 记录中间件执行顺序
        execution_log: list[int] = []

        for i in range(mw_count):
            if i == block_idx:
                # 这个中间件返回 None，拦截事件
                def blocking_mw(e: Event, idx=i) -> Event | None:
                    execution_log.append(idx)
                    return None
                bus.use(blocking_mw)
            else:
                # 正常中间件，透传事件
                def passthrough_mw(e: Event, idx=i) -> Event | None:
                    execution_log.append(idx)
                    return e
                bus.use(passthrough_mw)

        async def _verify():
            await bus.emit(event)
            # 队列应为空 — 事件被拦截
            assert bus._queue.empty(), (
                f"中间件 {block_idx} 返回 None 后事件不应进入队列"
            )
            # 拦截位置之后的中间件不应执行
            assert len(execution_log) == block_idx + 1, (
                f"拦截后不应继续执行后续中间件，"
                f"期望执行 {block_idx + 1} 个，实际执行 {len(execution_log)} 个"
            )

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        event_type=event_type_st,
        source=source_st,
        priority=priority_st,
        mw_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_all_middlewares_pass_event_enters_queue(
        self,
        event_type: str,
        source: str,
        priority: EventPriority,
        mw_count: int,
    ):
        """所有中间件返回非 None 时，事件正常入队（Requirement 1.8）。"""
        event = make_event(event_type=event_type, source=source, priority=priority)
        bus = EventBus()

        # 注册 mw_count 个透传中间件
        for i in range(mw_count):
            def passthrough_mw(e: Event, idx=i) -> Event | None:
                return e
            bus.use(passthrough_mw)

        async def _verify():
            await bus.emit(event)
            # 队列应有一个事件
            assert not bus._queue.empty(), "所有中间件通过后事件应进入队列"
            queued_event = await bus._queue.get()
            assert queued_event.type == event_type
            assert queued_event.source == source

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        event_type=event_type_st,
        source=source_st,
        mw_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=200)
    def test_middlewares_execute_in_registration_order(
        self,
        event_type: str,
        source: str,
        mw_count: int,
    ):
        """中间件按注册顺序依次执行（Requirement 1.9）。"""
        event = make_event(event_type=event_type, source=source)
        bus = EventBus()

        execution_order: list[int] = []

        # 注册 mw_count 个中间件，每个记录自己的索引
        for i in range(mw_count):
            def order_tracking_mw(e: Event, idx=i) -> Event | None:
                execution_order.append(idx)
                return e
            bus.use(order_tracking_mw)

        async def _verify():
            await bus.emit(event)
            # 验证执行顺序与注册顺序一致
            assert execution_order == list(range(mw_count)), (
                f"中间件执行顺序应为 {list(range(mw_count))}，"
                f"实际为 {execution_order}"
            )

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        event_type=event_type_st,
        source=source_st,
        priority=priority_st,
    )
    @settings(max_examples=200)
    def test_no_middleware_event_always_enters_queue(
        self,
        event_type: str,
        source: str,
        priority: EventPriority,
    ):
        """无中间件时，事件直接入队（基线验证）。"""
        event = make_event(event_type=event_type, source=source, priority=priority)
        bus = EventBus()

        async def _verify():
            await bus.emit(event)
            assert not bus._queue.empty(), "无中间件时事件应直接入队"
            queued = await bus._queue.get()
            assert queued.type == event_type

        asyncio.get_event_loop().run_until_complete(_verify())


# ── 属性 17: EventBus 通配符匹配 ──


class TestEventBusWildcardMatching:
    """属性 17: EventBus 通配符匹配

    对于任意事件类型 "a.b.c"，订阅 "a.*" 的 handler 会被触发，
    订阅 "a.b.*" 的 handler 也会被触发，订阅 "x.*" 的 handler 不会被触发。
    通配符 "*" 匹配所有事件类型，精确匹配仅匹配完全相同的事件类型。

    **Validates: Requirements 1.5, 1.6**
    """

    # ── 辅助策略 ──

    # 生成合法的单段标识符（用于拼接事件类型）
    _segment_st = st.from_regex(r"[a-z][a-z0-9]{0,7}", fullmatch=True)

    @given(
        seg_a=_segment_st,
        seg_b=_segment_st,
        seg_c=_segment_st,
    )
    @settings(max_examples=200)
    def test_global_wildcard_matches_all(
        self,
        seg_a: str,
        seg_b: str,
        seg_c: str,
    ):
        """通配符 "*" 匹配所有事件类型（Requirement 1.6）。"""
        event_type = f"{seg_a}.{seg_b}.{seg_c}"
        # "*" 应匹配任意事件类型
        assert EventBus._matches("*", event_type), (
            f"通配符 '*' 应匹配事件类型 '{event_type}'"
        )

    @given(
        seg_a=_segment_st,
        seg_b=_segment_st,
        seg_c=_segment_st,
    )
    @settings(max_examples=200)
    def test_prefix_wildcard_matches_same_prefix(
        self,
        seg_a: str,
        seg_b: str,
        seg_c: str,
    ):
        """前缀通配符 "a.*" 匹配以 "a." 开头的事件类型（Requirement 1.5）。

        对于事件类型 "a.b.c"：
        - "a.*" 应匹配（前缀 "a." 匹配）
        - "a.b.*" 应匹配（前缀 "a.b." 匹配）
        """
        event_type = f"{seg_a}.{seg_b}.{seg_c}"

        # "seg_a.*" 应匹配 "seg_a.seg_b.seg_c"
        pattern_a = f"{seg_a}.*"
        assert EventBus._matches(pattern_a, event_type), (
            f"模式 '{pattern_a}' 应匹配事件类型 '{event_type}'"
        )

        # "seg_a.seg_b.*" 应匹配 "seg_a.seg_b.seg_c"
        pattern_ab = f"{seg_a}.{seg_b}.*"
        assert EventBus._matches(pattern_ab, event_type), (
            f"模式 '{pattern_ab}' 应匹配事件类型 '{event_type}'"
        )

    @given(
        seg_a=_segment_st,
        seg_b=_segment_st,
        seg_c=_segment_st,
        seg_x=_segment_st,
    )
    @settings(max_examples=200)
    def test_prefix_wildcard_no_match_different_prefix(
        self,
        seg_a: str,
        seg_b: str,
        seg_c: str,
        seg_x: str,
    ):
        """不同前缀的通配符不匹配（Requirement 1.5 反向验证）。

        对于事件类型 "a.b.c"，订阅 "x.*" 的 handler 不会被触发。
        """
        # 确保 seg_x 与 seg_a 不同，否则前缀会匹配
        assume(seg_x != seg_a)

        event_type = f"{seg_a}.{seg_b}.{seg_c}"
        pattern_x = f"{seg_x}.*"

        assert not EventBus._matches(pattern_x, event_type), (
            f"模式 '{pattern_x}' 不应匹配事件类型 '{event_type}'"
        )

    @given(
        seg_a=_segment_st,
        seg_b=_segment_st,
        seg_c=_segment_st,
    )
    @settings(max_examples=200)
    def test_exact_match_works(
        self,
        seg_a: str,
        seg_b: str,
        seg_c: str,
    ):
        """精确匹配：模式与事件类型完全相同时匹配。"""
        event_type = f"{seg_a}.{seg_b}.{seg_c}"

        # 精确匹配应成功
        assert EventBus._matches(event_type, event_type), (
            f"精确模式 '{event_type}' 应匹配自身"
        )

    @given(
        seg_a=_segment_st,
        seg_b=_segment_st,
        seg_c=_segment_st,
        seg_d=_segment_st,
    )
    @settings(max_examples=200)
    def test_exact_match_no_match_different_type(
        self,
        seg_a: str,
        seg_b: str,
        seg_c: str,
        seg_d: str,
    ):
        """精确匹配：模式与事件类型不同时不匹配。"""
        event_type = f"{seg_a}.{seg_b}.{seg_c}"
        different_type = f"{seg_d}.{seg_b}.{seg_c}"

        # 确保两个事件类型确实不同
        assume(event_type != different_type)

        assert not EventBus._matches(different_type, event_type), (
            f"精确模式 '{different_type}' 不应匹配事件类型 '{event_type}'"
        )

    @given(
        seg_a=_segment_st,
        seg_b=_segment_st,
        seg_c=_segment_st,
        seg_x=_segment_st,
    )
    @settings(max_examples=200)
    def test_dispatch_triggers_matching_handlers_only(
        self,
        seg_a: str,
        seg_b: str,
        seg_c: str,
        seg_x: str,
    ):
        """集成验证：dispatch 只触发匹配的 handler，不触发不匹配的。

        对于事件 "a.b.c"：
        - 订阅 "a.*" 的 handler 被触发
        - 订阅 "a.b.*" 的 handler 被触发
        - 订阅 "x.*" 的 handler 不被触发（x != a）
        - 订阅 "*" 的 handler 被触发
        """
        assume(seg_x != seg_a)

        event_type = f"{seg_a}.{seg_b}.{seg_c}"
        event = make_event(event_type=event_type, source="test")
        bus = EventBus()

        # 记录各 handler 是否被调用
        triggered: dict[str, bool] = {
            "prefix_a": False,
            "prefix_ab": False,
            "prefix_x": False,
            "global": False,
        }

        async def handler_prefix_a(e: Event):
            triggered["prefix_a"] = True

        async def handler_prefix_ab(e: Event):
            triggered["prefix_ab"] = True

        async def handler_prefix_x(e: Event):
            triggered["prefix_x"] = True

        async def handler_global(e: Event):
            triggered["global"] = True

        bus.on(f"{seg_a}.*", handler_prefix_a)
        bus.on(f"{seg_a}.{seg_b}.*", handler_prefix_ab)
        bus.on(f"{seg_x}.*", handler_prefix_x)
        bus.on("*", handler_global)

        async def _verify():
            await bus._dispatch(event)

            # "a.*" 应匹配
            assert triggered["prefix_a"], (
                f"订阅 '{seg_a}.*' 的 handler 应被触发"
            )
            # "a.b.*" 应匹配
            assert triggered["prefix_ab"], (
                f"订阅 '{seg_a}.{seg_b}.*' 的 handler 应被触发"
            )
            # "x.*" 不应匹配
            assert not triggered["prefix_x"], (
                f"订阅 '{seg_x}.*' 的 handler 不应被触发"
            )
            # "*" 应匹配所有
            assert triggered["global"], (
                "订阅 '*' 的 handler 应被触发"
            )

        asyncio.get_event_loop().run_until_complete(_verify())
