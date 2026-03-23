"""属性测试 — SessionManager 会话管理

包含三个属性测试：
- 属性 6: Session 状态机合法转换 (Validates: Requirement 4.10)
- 属性 7: Session 并发限制 (Validates: Requirements 4.2, 10.4, 11.3)
- 属性 8: Turn 原子性 (Validates: Requirements 4.5, 4.6)
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest
from hypothesis import given, settings, strategies as st, assume

from mosaic.gateway.session_manager import SessionManager, SessionState, Session


# ── 辅助工具 ──

# agent_id 策略
agent_id_st = st.from_regex(r"[a-z][a-z0-9_]{1,10}", fullmatch=True)

# channel_id 策略
channel_id_st = st.from_regex(r"[a-z][a-z0-9_]{1,10}", fullmatch=True)

# 用户输入策略
user_input_st = st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N", "P")))


class MockTurnRunner:
    """模拟 TurnRunner，可配置成功或失败"""

    def __init__(self, should_fail: bool = False):
        self._should_fail = should_fail

    async def run(self, session: Session, user_input: str) -> dict[str, Any]:
        if self._should_fail:
            raise RuntimeError("模拟 Turn 执行失败")
        return {"response": f"echo: {user_input}", "success": True}


class SlowTurnRunner:
    """模拟慢速 TurnRunner，用于并发测试"""

    def __init__(self, delay: float = 0.01):
        self._delay = delay

    async def run(self, session: Session, user_input: str) -> dict[str, Any]:
        await asyncio.sleep(self._delay)
        return {"response": f"echo: {user_input}", "success": True}


# ── 属性 6: Session 状态机合法转换 ──


class TestSessionStateMachine:
    """属性 6: Session 状态机合法转换

    Session 状态仅沿合法路径流转：
    INITIALIZING → READY → RUNNING ⇄ WAITING → CLOSED
    或 WAITING → SUSPENDED → CLOSED

    **Validates: Requirement 4.10**
    """

    # 合法状态转换表
    VALID_TRANSITIONS: dict[SessionState, set[SessionState]] = {
        SessionState.INITIALIZING: {SessionState.READY},
        SessionState.READY: {SessionState.RUNNING},
        SessionState.RUNNING: {SessionState.WAITING},
        SessionState.WAITING: {SessionState.RUNNING, SessionState.SUSPENDED, SessionState.CLOSED},
        SessionState.SUSPENDED: {SessionState.CLOSED},
        SessionState.CLOSED: set(),  # 终态，无后续转换
    }

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
    )
    @settings(max_examples=100)
    def test_create_session_transitions_to_ready(
        self,
        agent_id: str,
        channel_id: str,
    ):
        """create_session 后状态为 READY（INITIALIZING → READY）。

        验证创建会话后状态直接到达 READY，跳过 INITIALIZING 瞬态。
        """
        sm = SessionManager(max_concurrent=10)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            # 创建后状态应为 READY
            assert session.state == SessionState.READY, (
                f"创建后状态应为 READY，实际为 {session.state}"
            )
            # READY 是 INITIALIZING 的合法后继
            assert SessionState.READY in self.VALID_TRANSITIONS[SessionState.INITIALIZING]

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=100)
    def test_run_turn_transitions_running_then_waiting(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """run_turn 期间状态为 RUNNING，完成后为 WAITING。

        验证 READY → RUNNING → WAITING 的合法转换路径。
        """
        sm = SessionManager(max_concurrent=10)
        # 记录 Turn 执行期间的状态
        observed_states: list[SessionState] = []

        class StateObservingRunner:
            async def run(self, session: Session, inp: str) -> dict:
                observed_states.append(session.state)
                return {"response": "ok"}

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            pre_state = session.state
            await sm.run_turn(session.session_id, user_input, StateObservingRunner())
            post_state = session.state

            # Turn 前状态为 READY
            assert pre_state == SessionState.READY
            # Turn 执行期间状态为 RUNNING
            assert observed_states[0] == SessionState.RUNNING, (
                f"Turn 执行期间状态应为 RUNNING，实际为 {observed_states[0]}"
            )
            # RUNNING 是 READY 的合法后继
            assert SessionState.RUNNING in self.VALID_TRANSITIONS[SessionState.READY]
            # Turn 完成后状态为 WAITING
            assert post_state == SessionState.WAITING, (
                f"Turn 完成后状态应为 WAITING，实际为 {post_state}"
            )
            # WAITING 是 RUNNING 的合法后继
            assert SessionState.WAITING in self.VALID_TRANSITIONS[SessionState.RUNNING]

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=100)
    def test_failed_turn_still_transitions_to_waiting(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """Turn 失败后状态仍恢复为 WAITING（RUNNING → WAITING 合法转换）。"""
        sm = SessionManager(max_concurrent=10)
        runner = MockTurnRunner(should_fail=True)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            with pytest.raises(RuntimeError):
                await sm.run_turn(session.session_id, user_input, runner)
            # 即使失败，状态也应恢复为 WAITING
            assert session.state == SessionState.WAITING, (
                f"Turn 失败后状态应为 WAITING，实际为 {session.state}"
            )
            assert SessionState.WAITING in self.VALID_TRANSITIONS[SessionState.RUNNING]

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
    )
    @settings(max_examples=100)
    def test_close_session_transitions_to_closed(
        self,
        agent_id: str,
        channel_id: str,
    ):
        """close_session 后状态为 CLOSED（合法终态转换）。"""
        sm = SessionManager(max_concurrent=10)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            await sm.close_session(session.session_id)
            assert session.state == SessionState.CLOSED, (
                f"关闭后状态应为 CLOSED，实际为 {session.state}"
            )

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=100)
    def test_evict_idle_transitions_waiting_to_suspended(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """evict_idle_sessions 将 WAITING 状态转为 SUSPENDED（合法转换）。"""
        # 设置极短的空闲超时以便立即触发
        sm = SessionManager(max_concurrent=10, idle_timeout_s=0)
        runner = MockTurnRunner(should_fail=False)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            # 先执行一次 Turn 使状态变为 WAITING
            await sm.run_turn(session.session_id, user_input, runner)
            assert session.state == SessionState.WAITING

            # 触发空闲回收
            evicted = await sm.evict_idle_sessions()
            assert session.session_id in evicted
            assert session.state == SessionState.SUSPENDED, (
                f"空闲回收后状态应为 SUSPENDED，实际为 {session.state}"
            )
            # SUSPENDED 是 WAITING 的合法后继
            assert SessionState.SUSPENDED in self.VALID_TRANSITIONS[SessionState.WAITING]

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=50)
    def test_closed_session_rejects_run_turn(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """CLOSED 状态的 Session 不允许执行 Turn（终态无后续转换）。"""
        sm = SessionManager(max_concurrent=10)
        runner = MockTurnRunner()

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            # 手动设置为 CLOSED 状态
            session.state = SessionState.CLOSED
            with pytest.raises(RuntimeError, match="会话已关闭"):
                await sm.run_turn(session.session_id, user_input, runner)

        asyncio.get_event_loop().run_until_complete(_verify())


# ── 属性 7: Session 并发限制 ──


class TestSessionConcurrentLimit:
    """属性 7: Session 并发限制

    任意时刻 RUNNING 或 READY 的 Session 数不超过 max_concurrent。

    **Validates: Requirements 4.2, 10.4, 11.3**
    """

    @given(
        max_concurrent=st.integers(min_value=1, max_value=5),
        extra_count=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_create_session_respects_concurrent_limit(
        self,
        max_concurrent: int,
        extra_count: int,
    ):
        """创建 Session 数超过 max_concurrent 时抛出 RuntimeError。

        创建 max_concurrent 个 Session 后，再创建应被拒绝。
        """
        sm = SessionManager(max_concurrent=max_concurrent)

        async def _verify():
            # 创建 max_concurrent 个 Session（均为 READY 状态）
            sessions = []
            for i in range(max_concurrent):
                s = await sm.create_session(f"agent_{i}", f"ch_{i}")
                sessions.append(s)

            # 验证所有 Session 都是 READY 状态
            active = sum(
                1 for s in sessions
                if s.state in (SessionState.RUNNING, SessionState.READY)
            )
            assert active == max_concurrent

            # 再创建应被拒绝
            for _ in range(extra_count):
                with pytest.raises(RuntimeError, match="并发会话数已达上限"):
                    await sm.create_session("overflow_agent", "overflow_ch")

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        max_concurrent=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_closed_session_frees_slot(
        self,
        max_concurrent: int,
    ):
        """关闭 Session 后释放并发槽位，可以创建新 Session。"""
        sm = SessionManager(max_concurrent=max_concurrent)

        async def _verify():
            # 填满并发槽位
            sessions = []
            for i in range(max_concurrent):
                s = await sm.create_session(f"agent_{i}", f"ch_{i}")
                sessions.append(s)

            # 此时应拒绝新 Session
            with pytest.raises(RuntimeError):
                await sm.create_session("new_agent", "new_ch")

            # 关闭一个 Session
            await sm.close_session(sessions[0].session_id)

            # 现在应该可以创建新 Session
            new_session = await sm.create_session("new_agent", "new_ch")
            assert new_session.state == SessionState.READY

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        max_concurrent=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_waiting_session_does_not_count_as_active(
        self,
        max_concurrent: int,
    ):
        """WAITING 状态的 Session 不计入活跃数，不占用并发槽位。"""
        sm = SessionManager(max_concurrent=max_concurrent)
        runner = MockTurnRunner()

        async def _verify():
            # 创建 max_concurrent 个 Session
            sessions = []
            for i in range(max_concurrent):
                s = await sm.create_session(f"agent_{i}", f"ch_{i}")
                sessions.append(s)

            # 将所有 Session 转为 WAITING（通过执行 Turn）
            for s in sessions:
                await sm.run_turn(s.session_id, "hello", runner)
                assert s.state == SessionState.WAITING

            # WAITING 不计入活跃数，应该可以创建新 Session
            new_session = await sm.create_session("new_agent", "new_ch")
            assert new_session.state == SessionState.READY

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        max_concurrent=st.integers(min_value=2, max_value=4),
        num_concurrent_turns=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=50)
    def test_concurrent_running_sessions_within_limit(
        self,
        max_concurrent: int,
        num_concurrent_turns: int,
    ):
        """并发执行 Turn 时，RUNNING 状态的 Session 数不超过 max_concurrent。"""
        # 确保并发 Turn 数不超过 max_concurrent
        actual_concurrent = min(num_concurrent_turns, max_concurrent)
        sm = SessionManager(max_concurrent=max_concurrent)

        # 记录同时处于 RUNNING 状态的最大数量
        max_running_observed = 0
        running_count = 0
        lock = asyncio.Lock()

        class CountingRunner:
            async def run(self, session: Session, inp: str) -> dict:
                nonlocal max_running_observed, running_count
                async with lock:
                    running_count += 1
                    if running_count > max_running_observed:
                        max_running_observed = running_count
                await asyncio.sleep(0.01)  # 模拟执行时间
                async with lock:
                    running_count -= 1
                return {"response": "ok"}

        async def _verify():
            nonlocal max_running_observed
            max_running_observed = 0

            # 创建 actual_concurrent 个 Session
            sessions = []
            for i in range(actual_concurrent):
                s = await sm.create_session(f"agent_{i}", f"ch_{i}")
                sessions.append(s)

            # 并发执行 Turn
            tasks = [
                sm.run_turn(s.session_id, "hello", CountingRunner())
                for s in sessions
            ]
            await asyncio.gather(*tasks)

            # 同时 RUNNING 的数量不应超过 max_concurrent
            assert max_running_observed <= max_concurrent, (
                f"同时 RUNNING 的 Session 数 ({max_running_observed}) "
                f"超过了 max_concurrent ({max_concurrent})"
            )

        asyncio.get_event_loop().run_until_complete(_verify())


# ── 属性 8: Turn 原子性 ──


class TestTurnAtomicity:
    """属性 8: Turn 原子性

    无论成功或失败，Session.state 最终回到 WAITING，turn_count 恰好增加 1。

    **Validates: Requirements 4.5, 4.6**
    """

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=100)
    def test_successful_turn_increments_count_by_one(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """成功的 Turn 执行后，turn_count 恰好增加 1，状态回到 WAITING。"""
        sm = SessionManager(max_concurrent=10)
        runner = MockTurnRunner(should_fail=False)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            count_before = session.turn_count
            await sm.run_turn(session.session_id, user_input, runner)

            # turn_count 恰好增加 1
            assert session.turn_count == count_before + 1, (
                f"turn_count 应从 {count_before} 增加到 {count_before + 1}，"
                f"实际为 {session.turn_count}"
            )
            # 状态回到 WAITING
            assert session.state == SessionState.WAITING

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=100)
    def test_failed_turn_increments_count_by_one(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """失败的 Turn 执行后，turn_count 仍恰好增加 1，状态回到 WAITING。"""
        sm = SessionManager(max_concurrent=10)
        runner = MockTurnRunner(should_fail=True)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            count_before = session.turn_count
            with pytest.raises(RuntimeError):
                await sm.run_turn(session.session_id, user_input, runner)

            # 即使失败，turn_count 也恰好增加 1
            assert session.turn_count == count_before + 1, (
                f"失败后 turn_count 应从 {count_before} 增加到 {count_before + 1}，"
                f"实际为 {session.turn_count}"
            )
            # 状态回到 WAITING
            assert session.state == SessionState.WAITING

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        num_turns=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_multiple_turns_count_accumulates_correctly(
        self,
        agent_id: str,
        channel_id: str,
        num_turns: int,
    ):
        """连续执行多个 Turn 后，turn_count 等于执行次数。"""
        sm = SessionManager(max_concurrent=10)
        runner = MockTurnRunner(should_fail=False)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            assert session.turn_count == 0

            for i in range(num_turns):
                await sm.run_turn(session.session_id, f"input_{i}", runner)

            # turn_count 应等于执行次数
            assert session.turn_count == num_turns, (
                f"执行 {num_turns} 次 Turn 后，turn_count 应为 {num_turns}，"
                f"实际为 {session.turn_count}"
            )
            # 最终状态为 WAITING
            assert session.state == SessionState.WAITING

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        success_pattern=st.lists(
            st.booleans(), min_size=2, max_size=8,
        ),
    )
    @settings(max_examples=100)
    def test_mixed_success_failure_turns_count_correctly(
        self,
        agent_id: str,
        channel_id: str,
        success_pattern: list[bool],
    ):
        """混合成功/失败的 Turn 序列，每次 turn_count 恰好增加 1。

        无论 Turn 成功还是失败，turn_count 都应单调递增，
        最终等于总执行次数。
        """
        sm = SessionManager(max_concurrent=10)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)

            for i, should_succeed in enumerate(success_pattern):
                runner = MockTurnRunner(should_fail=not should_succeed)
                count_before = session.turn_count

                if should_succeed:
                    await sm.run_turn(session.session_id, f"input_{i}", runner)
                else:
                    with pytest.raises(RuntimeError):
                        await sm.run_turn(session.session_id, f"input_{i}", runner)

                # 每次 Turn 后 count 恰好增加 1
                assert session.turn_count == count_before + 1, (
                    f"第 {i} 次 Turn ({'成功' if should_succeed else '失败'}) 后，"
                    f"turn_count 应为 {count_before + 1}，实际为 {session.turn_count}"
                )
                # 每次 Turn 后状态都回到 WAITING
                assert session.state == SessionState.WAITING, (
                    f"第 {i} 次 Turn 后状态应为 WAITING，实际为 {session.state}"
                )

            # 最终 turn_count 等于总执行次数
            assert session.turn_count == len(success_pattern)

        asyncio.get_event_loop().run_until_complete(_verify())

    @given(
        agent_id=agent_id_st,
        channel_id=channel_id_st,
        user_input=user_input_st,
    )
    @settings(max_examples=100)
    def test_turn_updates_last_active_at(
        self,
        agent_id: str,
        channel_id: str,
        user_input: str,
    ):
        """Turn 执行后 last_active_at 被更新（Requirement 4.6 的时间戳部分）。"""
        sm = SessionManager(max_concurrent=10)
        runner = MockTurnRunner(should_fail=False)

        async def _verify():
            session = await sm.create_session(agent_id, channel_id)
            time_before = session.last_active_at
            await sm.run_turn(session.session_id, user_input, runner)
            # last_active_at 应被更新（大于等于之前的值）
            assert session.last_active_at >= time_before, (
                "Turn 执行后 last_active_at 应被更新"
            )

        asyncio.get_event_loop().run_until_complete(_verify())
