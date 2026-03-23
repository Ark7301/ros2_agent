"""属性测试 — Event 优先级排序

属性 1：对于任意两个 Event e1(priority=CRITICAL) 和 e2(priority=LOW)，
无论 timestamp 顺序如何，EventBus 总是先分发 e1 再分发 e2。

同优先级事件按 timestamp 先后排序。

**Validates: Requirements 1.3, 1.4**
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from hypothesis import given, settings, strategies as st

from mosaic.protocol.events import Event, EventPriority


# ── Hypothesis 策略 ──

# 生成任意 datetime（在合理范围内）
datetime_st = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
)


def make_event(priority: EventPriority, timestamp: datetime) -> Event:
    """辅助函数：创建指定优先级和时间戳的 Event"""
    return Event(
        type="test.event",
        payload={},
        source="test",
        priority=priority,
        timestamp=timestamp,
    )


class TestEventPriorityOrdering:
    """属性 1: Event 优先级排序

    **Validates: Requirements 1.3, 1.4**
    """

    @given(ts_critical=datetime_st, ts_low=datetime_st)
    @settings(max_examples=200)
    def test_critical_always_before_low_in_priority_queue(
        self, ts_critical: datetime, ts_low: datetime
    ):
        """CRITICAL 事件总是排在 LOW 事件之前，无论 timestamp 顺序如何。

        使用 asyncio.PriorityQueue 验证出队顺序。
        """
        e_critical = make_event(EventPriority.CRITICAL, ts_critical)
        e_low = make_event(EventPriority.LOW, ts_low)

        async def _verify():
            q: asyncio.PriorityQueue = asyncio.PriorityQueue()
            # 无论入队顺序如何，先放 LOW 再放 CRITICAL
            await q.put(e_low)
            await q.put(e_critical)

            first = await q.get()
            second = await q.get()

            # CRITICAL(0) 应始终先于 LOW(3) 出队
            assert first.priority == EventPriority.CRITICAL
            assert second.priority == EventPriority.LOW

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(ts_critical=datetime_st, ts_low=datetime_st)
    @settings(max_examples=200)
    def test_critical_before_low_reverse_insert_order(
        self, ts_critical: datetime, ts_low: datetime
    ):
        """反向入队顺序：先放 CRITICAL 再放 LOW，结果不变。"""
        e_critical = make_event(EventPriority.CRITICAL, ts_critical)
        e_low = make_event(EventPriority.LOW, ts_low)

        async def _verify():
            q: asyncio.PriorityQueue = asyncio.PriorityQueue()
            # 先放 CRITICAL 再放 LOW
            await q.put(e_critical)
            await q.put(e_low)

            first = await q.get()
            second = await q.get()

            assert first.priority == EventPriority.CRITICAL
            assert second.priority == EventPriority.LOW

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        ts1=datetime_st,
        ts2=datetime_st,
    )
    @settings(max_examples=200)
    def test_same_priority_ordered_by_timestamp(
        self, ts1: datetime, ts2: datetime
    ):
        """同优先级事件按 timestamp 先后排序（Requirements 1.4）。"""
        e1 = make_event(EventPriority.NORMAL, ts1)
        e2 = make_event(EventPriority.NORMAL, ts2)

        async def _verify():
            q: asyncio.PriorityQueue = asyncio.PriorityQueue()
            await q.put(e1)
            await q.put(e2)

            first = await q.get()
            second = await q.get()

            # 时间戳较早的应先出队
            assert first.timestamp <= second.timestamp

        asyncio.get_event_loop().run_until_complete(_verify())
