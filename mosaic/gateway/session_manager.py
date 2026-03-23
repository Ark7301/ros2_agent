"""会话管理器 — 生命周期 + 并发控制 + 空闲回收

管理 Session 的完整生命周期，支持并发限制、状态流转和空闲回收。
借鉴 OpenClaw AcpSessionManager 设计模式。

状态流转图:
    INITIALIZING → READY → RUNNING ⇄ WAITING → CLOSED
                                        ↓
                                    SUSPENDED → CLOSED
"""

import asyncio
import uuid
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class SessionState(Enum):
    """会话状态枚举

    定义 Session 生命周期中的所有合法状态。
    状态流转必须遵循设计文档中的状态机规则。
    """
    INITIALIZING = "initializing"  # 初始化中（创建后的瞬态）
    READY = "ready"                # 就绪，等待 Turn 执行
    RUNNING = "running"            # Turn 正在执行中
    WAITING = "waiting"            # Turn 执行完毕，等待下一次输入
    SUSPENDED = "suspended"        # 空闲超时，已挂起
    CLOSED = "closed"              # 已关闭，不可再使用


@dataclass
class Session:
    """会话对象

    包含会话的完整状态信息，每个 Session 绑定一个 agent_id 和 channel_id。
    session_id 自动生成 UUID，created_at 和 last_active_at 自动记录时间戳。
    """
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = "default"
    channel_id: str = ""
    state: SessionState = SessionState.INITIALIZING
    turn_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """会话管理器 — 生命周期 + 并发控制 + 空闲回收

    核心职责:
    - 创建/关闭会话，管理完整生命周期
    - 通过 max_concurrent 限制并发活跃会话数量
    - 通过 session 级锁保证同一 Session 的 Turn 串行执行
    - 定期回收空闲超时的会话（WAITING → SUSPENDED）

    状态流转:
        INITIALIZING → READY → RUNNING ⇄ WAITING → CLOSED
                                            ↓
                                        SUSPENDED → CLOSED
    """

    def __init__(self, max_concurrent: int = 10, idle_timeout_s: float = 300):
        """初始化会话管理器

        Args:
            max_concurrent: 最大并发活跃会话数（RUNNING 或 READY 状态）
            idle_timeout_s: 空闲超时时间（秒），超时后 WAITING → SUSPENDED
        """
        self._sessions: dict[str, Session] = {}
        self._max_concurrent = max_concurrent
        self._idle_timeout_s = idle_timeout_s
        # 每个 Session 独立的异步锁，保证同一 Session 的 Turn 串行执行
        self._locks: dict[str, asyncio.Lock] = {}

    async def create_session(self, agent_id: str, channel_id: str) -> Session:
        """创建新会话（含并发限制检查）

        创建流程: 检查并发限制 → 实例化 Session → 分配锁 → 状态置为 READY

        Args:
            agent_id: 绑定的 Agent ID
            channel_id: 绑定的 Channel ID

        Returns:
            状态为 READY 的新 Session 实例

        Raises:
            RuntimeError: 活跃会话数已达 max_concurrent 上限
        """
        self._enforce_concurrent_limit()
        session = Session(agent_id=agent_id, channel_id=channel_id)
        self._sessions[session.session_id] = session
        self._locks[session.session_id] = asyncio.Lock()
        # INITIALIZING → READY
        session.state = SessionState.READY
        return session

    async def run_turn(self, session_id: str, user_input: str, turn_runner) -> Any:
        """执行一个 Turn（原子操作，session 级锁保护）

        通过 asyncio.Lock 保证同一 Session 的 Turn 串行执行。
        执行期间状态为 RUNNING，完成后（无论成功或失败）恢复为 WAITING。

        Args:
            session_id: 目标会话 ID
            user_input: 用户输入文本
            turn_runner: Turn 执行器，需实现 run(session, user_input) 方法

        Returns:
            turn_runner.run() 的返回值

        Raises:
            KeyError: session_id 对应的会话不存在
            RuntimeError: 会话已关闭（状态为 CLOSED）
        """
        session = self._require_session(session_id)
        async with self._locks[session_id]:
            # READY/WAITING → RUNNING
            session.state = SessionState.RUNNING
            session.turn_count += 1
            session.last_active_at = time.time()
            try:
                result = await turn_runner.run(session, user_input)
                # RUNNING → WAITING（成功）
                session.state = SessionState.WAITING
                return result
            except Exception:
                # RUNNING → WAITING（失败，状态仍恢复为 WAITING）
                session.state = SessionState.WAITING
                raise

    async def close_session(self, session_id: str) -> None:
        """关闭会话

        从管理器中移除会话并释放对应的锁资源。
        会话状态置为 CLOSED，后续不可再使用。

        Args:
            session_id: 要关闭的会话 ID
        """
        session = self._sessions.pop(session_id, None)
        if session:
            session.state = SessionState.CLOSED
            self._locks.pop(session_id, None)

    async def evict_idle_sessions(self) -> list[str]:
        """回收空闲会话

        扫描所有会话，将状态为 WAITING 且空闲时间超过 idle_timeout_s 的
        会话标记为 SUSPENDED。

        Returns:
            被挂起的会话 ID 列表
        """
        now = time.time()
        evicted = []
        for sid, session in list(self._sessions.items()):
            if (session.state == SessionState.WAITING and
                    now - session.last_active_at > self._idle_timeout_s):
                # WAITING → SUSPENDED
                session.state = SessionState.SUSPENDED
                evicted.append(sid)
        return evicted

    def get_session(self, session_id: str) -> Session | None:
        """获取会话实例（不做状态检查）

        Args:
            session_id: 会话 ID

        Returns:
            Session 实例，不存在则返回 None
        """
        return self._sessions.get(session_id)

    def find_active_session(self, agent_id: str, channel_id: str) -> Session | None:
        """查找指定 agent_id 和 channel_id 的活跃 Session

        遍历所有会话，返回第一个匹配且状态不为 CLOSED/SUSPENDED 的 Session。

        Args:
            agent_id: Agent ID
            channel_id: Channel ID

        Returns:
            匹配的活跃 Session，不存在则返回 None
        """
        for session in self._sessions.values():
            if (session.agent_id == agent_id
                    and session.channel_id == channel_id
                    and session.state not in (SessionState.CLOSED, SessionState.SUSPENDED)):
                return session
        return None

    def _enforce_concurrent_limit(self):
        """检查并发限制

        统计当前 RUNNING 或 READY 状态的活跃会话数，
        若已达 max_concurrent 上限则拒绝创建新会话。

        Raises:
            RuntimeError: 并发会话数已达上限
        """
        active = sum(1 for s in self._sessions.values()
                     if s.state in (SessionState.RUNNING, SessionState.READY))
        if active >= self._max_concurrent:
            raise RuntimeError(f"并发会话数已达上限: {self._max_concurrent}")

    def _require_session(self, session_id: str) -> Session:
        """获取会话并校验状态

        确保会话存在且处于可用状态（READY/WAITING/RUNNING），
        SUSPENDED 和 CLOSED 状态的会话不可接受新的 Turn。

        Args:
            session_id: 会话 ID

        Returns:
            有效的 Session 实例

        Raises:
            KeyError: 会话不存在
            RuntimeError: 会话已关闭或已挂起
        """
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"会话不存在: {session_id}")
        if session.state == SessionState.CLOSED:
            raise RuntimeError(f"会话已关闭: {session_id}")
        if session.state == SessionState.SUSPENDED:
            raise RuntimeError(f"会话已挂起: {session_id}")
        return session
