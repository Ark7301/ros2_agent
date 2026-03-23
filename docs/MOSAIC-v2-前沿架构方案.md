# MOSAIC v2 — 前沿架构全面重构方案

> 基于 OpenClaw 深度调研 + 2026 Agent 领域最新范式

## 〇、设计哲学

**不是优化，是重建。** MOSAIC v1 是一个线性管道 Demo，v2 要成为一个：
- 事件驱动的分布式 Agent 运行时
- 插件优先的零耦合架构
- 支持多 Agent 协作的控制面
- 具备生产级可观测性的机器人智能体框架

---

## 一、OpenClaw 关键架构深度拆解

### 1.1 ACP（Agent Control Protocol）— 最核心的设计

OpenClaw 最前沿的设计不是插件系统，而是 ACP：

```
Gateway (控制面)
    ↕ ACP 协议 (WebSocket RPC)
Agent Runtime (执行面)
    ↕ Tool Invocation
Node Host (能力节点)
```

- **AcpSessionManager**：管理 Agent 会话生命周期（init → run → cancel → close）
- **Session 隔离**：main session vs group session，不同沙箱策略
- **Runtime Handle 缓存**：复用 Agent 进程，避免冷启动
- **并发控制**：`enforceConcurrentSessionLimit` 限制同时运行的 session 数
- **Turn 级别调度**：`runTurn` 是原子执行单元，支持中断/重试/超时

### 1.2 Node Host — 分布式能力节点

```
Gateway
    ├── NodeRegistry（节点注册表）
    ├── NodeSubscriptionManager（节点事件订阅）
    ├── Node Presence Timers（心跳检测）
    └── Exec Policy（执行策略 + 权限控制）
```

- 节点可以是浏览器、远程机器、移动设备
- 通过 WebSocket 注册到 Gateway
- 支持能力发现（`refreshRemoteBinsForConnectedNodes`）
- 执行策略：allowlist + 权限审批（`ExecApprovalManager`）

### 1.3 Plugin Slot 系统 — 排他性插槽

```python
# OpenClaw 的 slot 设计：同类插件互斥
SLOT_BY_KIND = {
    "memory": "memory",           # memory-core vs memory-lancedb
    "context-engine": "contextEngine",  # legacy vs custom
}
```

选择一个 memory 插件会自动禁用同类其他插件。这比简单的注册表高级得多。

### 1.4 Gateway 热重载 + 配置驱动

- `ConfigReloader`：监听配置文件变更，区分 hot-reload vs restart
- `SecretsRuntime`：密钥运行时快照，支持降级和恢复
- Channel Health Monitor：通道健康检查 + 自动重启
- Heartbeat Runner：心跳检测 + 自动恢复


---

## 二、MOSAIC v2 全新架构

### 2.1 总体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                    MOSAIC v2 Architecture                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────── Control Plane ────────────────────────┐  │
│  │                                                           │  │
│  │  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐ │  │
│  │  │ Gateway  │  │ Session  │  │  Agent   │  │  Config   │ │  │
│  │  │ Server   │  │ Manager  │  │  Router  │  │  Reactor  │ │  │
│  │  │ (WS/gRPC)│  │          │  │          │  │ (热重载)   │ │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘ │  │
│  │       │              │              │              │       │  │
│  │  ┌────┴──────────────┴──────────────┴──────────────┴────┐ │  │
│  │  │              Event Bus (异步事件总线)                  │ │  │
│  │  └──────────────────────┬────────────────────────────────┘ │  │
│  └─────────────────────────┼─────────────────────────────────┘  │
│                            │                                     │
│  ┌─────────────────────────┼──── Agent Runtime ──────────────┐  │
│  │                         │                                 │  │
│  │  ┌──────────┐  ┌───────┴──────┐  ┌────────────────────┐  │  │
│  │  │ Context  │  │  Turn Runner │  │   Tool Executor    │  │  │
│  │  │ Engine   │  │  (原子执行)   │  │   (并行/串行)      │  │  │
│  │  │ (可插拔)  │  │              │  │                    │  │  │
│  │  └──────────┘  └──────────────┘  └────────┬───────────┘  │  │
│  │                                           │               │  │
│  │  ┌────────────────────────────────────────┴────────────┐  │  │
│  │  │           Plugin SDK (公共接口边界)                   │  │  │
│  │  └────────────────────────┬────────────────────────────┘  │  │
│  └───────────────────────────┼───────────────────────────────┘  │
│                              │                                   │
│  ┌───────────────────────────┼──── Plugin Layer ─────────────┐  │
│  │                           │                               │  │
│  │  ┌─────────┐  ┌──────────┴──┐  ┌──────────┐  ┌────────┐ │  │
│  │  │Channel  │  │ Capability  │  │ Provider │  │ Memory │ │  │
│  │  │Plugins  │  │ Plugins     │  │ Plugins  │  │ Plugins│ │  │
│  │  │         │  │             │  │          │  │        │ │  │
│  │  │• CLI    │  │• Navigation │  │• MiniMax │  │• File  │ │  │
│  │  │• Web    │  │• Motion     │  │• OpenAI  │  │• Lance │ │  │
│  │  │• ROS2   │  │• SLAM       │  │• Claude  │  │• Redis │ │  │
│  │  │• Voice  │  │• Grasp      │  │• Ollama  │  │        │ │  │
│  │  │• MQTT   │  │• Vision     │  │• Local   │  │        │ │  │
│  │  └─────────┘  └─────────────┘  └──────────┘  └────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────── Node Layer ───────────────────────────┐  │
│  │                                                           │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │  │
│  │  │ ROS2     │  │ Hardware │  │ Sensor   │  │ Remote   │ │  │
│  │  │ Bridge   │  │ Driver   │  │ Fusion   │  │ Robot    │ │  │
│  │  │ Node     │  │ Node     │  │ Node     │  │ Node     │ │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 目录结构

```
mosaic/
├── pyproject.toml                    ← 项目元数据 + 依赖
│
├── mosaic/
│   ├── __init__.py
│   │
│   ├── protocol/                     ← 协议层（类似 ACP）
│   │   ├── events.py                 ← 事件定义（所有系统事件的枚举+数据类）
│   │   ├── messages.py               ← 消息协议（Agent ↔ Gateway 通信格式）
│   │   └── errors.py                 ← 错误码体系
│   │
│   ├── gateway/                      ← 控制面（借鉴 OpenClaw Gateway）
│   │   ├── server.py                 ← WebSocket/gRPC 网关服务器
│   │   ├── session_manager.py        ← 会话管理器（生命周期+并发控制）
│   │   ├── agent_router.py           ← 多 Agent 路由（多层级匹配）
│   │   ├── config_reactor.py         ← 配置热重载反应器
│   │   └── health_monitor.py         ← 健康检查 + 自动恢复
│   │
│   ├── runtime/                      ← Agent 运行时（借鉴 ACP Runtime）
│   │   ├── turn_runner.py            ← Turn 级原子执行器
│   │   ├── tool_executor.py          ← 工具执行器（并行/串行/超时）
│   │   ├── context_engine.py         ← 上下文引擎接口
│   │   ├── planner.py                ← LLM 增强规划器（ReAct/CoT）
│   │   └── sandbox.py                ← 执行沙箱（资源隔离）
│   │
│   ├── plugin_sdk/                   ← 插件 SDK（严格公共边界）
│   │   ├── __init__.py               ← SDK 根导出
│   │   ├── types.py                  ← 所有插件类型定义
│   │   ├── capability.py             ← 能力插件接口
│   │   ├── provider.py               ← Provider 插件接口
│   │   ├── channel.py                ← 通道插件接口
│   │   ├── memory.py                 ← 记忆插件接口
│   │   ├── context.py                ← 上下文引擎插件接口
│   │   ├── slots.py                  ← 排他性插槽管理
│   │   └── registry.py               ← 插件注册表（发现+加载+生命周期）
│   │
│   ├── core/                         ← 核心基础设施
│   │   ├── event_bus.py              ← 异步事件总线
│   │   ├── hooks.py                  ← 生命周期钩子系统
│   │   ├── config.py                 ← 配置管理（校验+合并+监听）
│   │   ├── logging.py                ← 结构化日志
│   │   └── di.py                     ← 依赖注入容器
│   │
│   ├── nodes/                        ← 节点层（借鉴 Node Host）
│   │   ├── node_registry.py          ← 节点注册表
│   │   ├── node_bridge.py            ← ROS2 Bridge 节点
│   │   ├── exec_policy.py            ← 执行策略（权限+allowlist）
│   │   └── health_probe.py           ← 节点健康探测
│   │
│   └── observability/                ← 可观测性
│       ├── metrics.py                ← 指标收集（Prometheus 格式）
│       ├── tracing.py                ← 分布式追踪（OpenTelemetry）
│       └── diagnostics.py            ← 诊断快照
│
├── plugins/                          ← 插件包（每个独立 Python 包）
│   ├── channels/
│   │   ├── cli/                      ← CLI 通道
│   │   ├── websocket/                ← WebSocket 通道
│   │   ├── ros2_topic/               ← ROS2 Topic 通道
│   │   ├── voice/                    ← 语音通道（ASR/TTS）
│   │   └── mqtt/                     ← MQTT 通道（IoT）
│   │
│   ├── capabilities/
│   │   ├── navigation/               ← Nav2 导航
│   │   ├── motion/                   ← 运动控制
│   │   ├── slam/                     ← SLAM 建图
│   │   ├── manipulation/             ← 机械臂抓取
│   │   ├── vision/                   ← 视觉感知
│   │   └── scene_graph/              ← 场景图理解
│   │
│   ├── providers/
│   │   ├── minimax/                  ← MiniMax
│   │   ├── openai/                   ← OpenAI
│   │   ├── anthropic/                ← Claude
│   │   ├── ollama/                   ← 本地模型
│   │   └── ros2_llm/                 ← ROS2 LLM 服务
│   │
│   ├── memory/
│   │   ├── file_memory/              ← 文件记忆
│   │   ├── vector_memory/            ← 向量记忆（FAISS/LanceDB）
│   │   └── scene_memory/             ← 场景记忆（空间语义）
│   │
│   └── context_engines/
│       ├── sliding_window/           ← 滑动窗口
│       ├── summary_compaction/       ← 摘要压缩
│       └── rag_retrieval/            ← RAG 检索增强
│
└── config/
    └── mosaic.yaml                   ← 统一配置文件
```


---

## 三、核心模块详细设计

### 3.1 事件总线 — 系统的神经中枢

v1 的致命问题是同步线性管道。v2 用事件驱动解耦一切。

```python
# mosaic/core/event_bus.py
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable
from datetime import datetime

class EventPriority(Enum):
    CRITICAL = 0   # 安全/紧急停止
    HIGH = 1       # 执行结果
    NORMAL = 2     # 常规消息
    LOW = 3        # 日志/遥测

@dataclass(frozen=True)
class Event:
    type: str
    payload: dict[str, Any]
    source: str                          # 发送者标识
    timestamp: datetime = field(default_factory=datetime.now)
    priority: EventPriority = EventPriority.NORMAL
    correlation_id: str | None = None    # 追踪链路
    session_id: str | None = None        # 会话隔离

EventHandler = Callable[[Event], Awaitable[None]]

class EventBus:
    """异步事件总线 — 支持优先级、通配符订阅、背压控制"""

    def __init__(self, max_queue_size: int = 10000):
        self._handlers: dict[str, list[EventHandler]] = {}
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self._running = False
        self._middlewares: list[Callable[[Event], Event | None]] = []

    def on(self, event_type: str, handler: EventHandler) -> Callable:
        """订阅事件，支持通配符 'capability.*' """
        self._handlers.setdefault(event_type, []).append(handler)
        return lambda: self._handlers[event_type].remove(handler)

    async def emit(self, event: Event) -> None:
        """发射事件到队列"""
        for mw in self._middlewares:
            event = mw(event)
            if event is None:
                return  # 中间件拦截
        await self._queue.put((event.priority.value, event.timestamp, event))

    def use(self, middleware: Callable[[Event], Event | None]):
        """注册中间件（日志/过滤/变换）"""
        self._middlewares.append(middleware)

    async def start(self):
        """启动事件分发循环"""
        self._running = True
        while self._running:
            _, _, event = await self._queue.get()
            await self._dispatch(event)

    async def _dispatch(self, event: Event):
        """分发事件到匹配的 handler"""
        tasks = []
        for pattern, handlers in self._handlers.items():
            if self._matches(pattern, event.type):
                for handler in handlers:
                    tasks.append(handler(event))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    def _matches(pattern: str, event_type: str) -> bool:
        if pattern == '*':
            return True
        if pattern.endswith('.*'):
            return event_type.startswith(pattern[:-1])
        return pattern == event_type
```

### 3.2 Plugin SDK — 严格边界隔离

借鉴 OpenClaw 的 `openclaw/plugin-sdk/*` 子路径导出模式，但用 Python 的 Protocol 实现零继承耦合。

```python
# mosaic/plugin_sdk/types.py
from __future__ import annotations
from typing import Protocol, Any, runtime_checkable
from dataclasses import dataclass

# ── 插件元数据 ──

@dataclass(frozen=True)
class PluginMeta:
    id: str
    name: str
    version: str
    description: str
    kind: str  # "capability" | "provider" | "channel" | "memory" | "context-engine"
    author: str = ""
    config_schema: dict | None = None

# ── 能力插件协议 ──

@runtime_checkable
class CapabilityPlugin(Protocol):
    meta: PluginMeta

    def get_supported_intents(self) -> list[str]: ...
    def get_tool_definitions(self) -> list[dict[str, Any]]: ...
    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult: ...
    async def cancel(self) -> bool: ...
    async def health_check(self) -> HealthStatus: ...

# ── Provider 插件协议 ──

@runtime_checkable
class ProviderPlugin(Protocol):
    meta: PluginMeta

    async def chat(self, messages: list[dict], tools: list[dict] | None,
                   config: ProviderConfig) -> ProviderResponse: ...
    async def stream(self, messages: list[dict], tools: list[dict] | None,
                     config: ProviderConfig): ...  # AsyncIterator[StreamDelta]
    async def validate_auth(self) -> bool: ...
    def get_capabilities(self) -> ProviderCapabilities: ...

# ── 通道插件协议 ──

@runtime_checkable
class ChannelPlugin(Protocol):
    meta: PluginMeta

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> SendResult: ...
    async def send_progress(self, session_id: str, text: str) -> None: ...
    def on_message(self, handler) -> None: ...  # 注册入站消息回调

# ── 记忆插件协议 ──

@runtime_checkable
class MemoryPlugin(Protocol):
    meta: PluginMeta

    async def store(self, key: str, content: str, metadata: dict) -> None: ...
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...
    async def get(self, key: str) -> MemoryEntry | None: ...
    async def delete(self, key: str) -> bool: ...

# ── 上下文引擎插件协议 ──

@runtime_checkable
class ContextEnginePlugin(Protocol):
    meta: PluginMeta

    async def ingest(self, session_id: str, message: dict) -> None: ...
    async def assemble(self, session_id: str, token_budget: int) -> AssembleResult: ...
    async def compact(self, session_id: str, force: bool = False) -> CompactResult: ...
    async def bootstrap(self, session_id: str) -> None: ...
```

```python
# mosaic/plugin_sdk/slots.py — 排他性插槽（借鉴 OpenClaw）
from dataclasses import dataclass

@dataclass
class SlotConfig:
    key: str
    default_plugin_id: str
    description: str

# 同类插件互斥：选择一个自动禁用其他
PLUGIN_SLOTS = {
    "memory": SlotConfig("memory", "file-memory", "记忆存储后端"),
    "context-engine": SlotConfig("context-engine", "sliding-window", "上下文管理策略"),
    "planner": SlotConfig("planner", "react-planner", "任务规划策略"),
}

class SlotManager:
    """排他性插槽管理器"""

    def __init__(self):
        self._active_slots: dict[str, str] = {}  # slot_key → plugin_id

    def activate(self, slot_key: str, plugin_id: str) -> list[str]:
        """激活插槽，返回被禁用的插件 ID 列表"""
        previous = self._active_slots.get(slot_key)
        self._active_slots[slot_key] = plugin_id
        disabled = [previous] if previous and previous != plugin_id else []
        return disabled

    def resolve(self, slot_key: str) -> str:
        """解析当前活跃的插件 ID"""
        if slot_key in self._active_slots:
            return self._active_slots[slot_key]
        slot = PLUGIN_SLOTS.get(slot_key)
        return slot.default_plugin_id if slot else ""
```

```python
# mosaic/plugin_sdk/registry.py — 插件注册表（动态发现+加载+生命周期）
import importlib
import pkgutil
from typing import Any

class PluginRegistry:
    """插件注册表 — 自动发现、加载、生命周期管理"""

    def __init__(self, slot_manager: SlotManager):
        self._plugins: dict[str, Any] = {}  # plugin_id → plugin instance
        self._factories: dict[str, Any] = {}  # plugin_id → factory
        self._slot_manager = slot_manager

    def register(self, plugin_id: str, factory, kind: str | None = None):
        """注册插件工厂"""
        self._factories[plugin_id] = factory
        if kind and kind in PLUGIN_SLOTS:
            self._slot_manager.activate(kind, plugin_id)

    def resolve(self, plugin_id: str):
        """解析并实例化插件（懒加载）"""
        if plugin_id not in self._plugins:
            factory = self._factories.get(plugin_id)
            if not factory:
                raise KeyError(f"插件未注册: {plugin_id}")
            self._plugins[plugin_id] = factory()
        return self._plugins[plugin_id]

    def resolve_slot(self, slot_key: str):
        """通过插槽解析当前活跃插件"""
        plugin_id = self._slot_manager.resolve(slot_key)
        return self.resolve(plugin_id)

    def discover(self, package: str = "plugins"):
        """自动发现并注册所有插件包"""
        for category in ["channels", "capabilities", "providers", "memory", "context_engines"]:
            try:
                pkg = importlib.import_module(f"{package}.{category}")
                for _, name, _ in pkgutil.iter_modules(pkg.__path__):
                    try:
                        mod = importlib.import_module(f"{package}.{category}.{name}")
                        if hasattr(mod, "create_plugin"):
                            entry = mod.create_plugin()
                            self.register(entry.meta.id, lambda e=entry: e, entry.meta.kind)
                    except Exception:
                        pass  # 插件加载失败不影响系统
            except ModuleNotFoundError:
                pass

    def list_by_kind(self, kind: str) -> list[str]:
        """列出指定类型的所有已注册插件 ID"""
        return [
            pid for pid, factory in self._factories.items()
            if hasattr(factory, 'meta') and factory.meta.kind == kind
        ]
```


### 3.3 Session Manager — 会话生命周期管理（借鉴 AcpSessionManager）

这是 v1 完全缺失的核心组件。OpenClaw 的 `AcpSessionManager` 有 1400+ 行，管理 Agent 会话的完整生命周期。

```python
# mosaic/gateway/session_manager.py
import asyncio
import uuid
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class SessionState(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"       # Turn 正在执行
    WAITING = "waiting"       # 等待用户输入
    SUSPENDED = "suspended"   # 挂起（资源回收）
    CLOSED = "closed"

@dataclass
class Session:
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = "default"
    channel_id: str = ""
    state: SessionState = SessionState.INITIALIZING
    context_engine_id: str = ""
    turn_count: int = 0
    created_at: float = 0.0
    last_active_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

class SessionManager:
    """会话管理器 — 完整生命周期 + 并发控制 + 资源回收

    借鉴 OpenClaw AcpSessionManager 的设计：
    - init → ready → running → waiting → running → ... → closed
    - 并发 session 数限制
    - 空闲 session 自动挂起/回收
    - Turn 级别的原子执行
    """

    def __init__(self, max_concurrent: int = 10, idle_timeout_s: float = 300):
        self._sessions: dict[str, Session] = {}
        self._max_concurrent = max_concurrent
        self._idle_timeout_s = idle_timeout_s
        self._locks: dict[str, asyncio.Lock] = {}  # 每 session 一把锁

    async def create_session(self, agent_id: str, channel_id: str,
                              context_engine_id: str = "") -> Session:
        """创建新会话"""
        self._enforce_concurrent_limit()
        session = Session(
            agent_id=agent_id,
            channel_id=channel_id,
            context_engine_id=context_engine_id,
        )
        self._sessions[session.session_id] = session
        self._locks[session.session_id] = asyncio.Lock()
        session.state = SessionState.READY
        return session

    async def run_turn(self, session_id: str, user_input: str,
                        turn_runner) -> Any:
        """执行一个 Turn（原子操作，借鉴 AcpSessionManager.runTurn）"""
        session = self._require_session(session_id)
        async with self._locks[session_id]:
            session.state = SessionState.RUNNING
            session.turn_count += 1
            try:
                result = await turn_runner.run(session, user_input)
                session.state = SessionState.WAITING
                return result
            except Exception:
                session.state = SessionState.WAITING
                raise

    async def close_session(self, session_id: str) -> None:
        """关闭会话，释放资源"""
        session = self._sessions.pop(session_id, None)
        if session:
            session.state = SessionState.CLOSED
            self._locks.pop(session_id, None)

    async def evict_idle_sessions(self) -> list[str]:
        """回收空闲会话（借鉴 OpenClaw 的 evictIdleRuntimeHandles）"""
        import time
        now = time.time()
        evicted = []
        for sid, session in list(self._sessions.items()):
            if (session.state == SessionState.WAITING and
                now - session.last_active_at > self._idle_timeout_s):
                session.state = SessionState.SUSPENDED
                evicted.append(sid)
        return evicted

    def _enforce_concurrent_limit(self):
        active = sum(1 for s in self._sessions.values()
                     if s.state in (SessionState.RUNNING, SessionState.READY))
        if active >= self._max_concurrent:
            raise RuntimeError(f"并发会话数已达上限: {self._max_concurrent}")

    def _require_session(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if not session:
            raise KeyError(f"会话不存在: {session_id}")
        return session
```

### 3.4 Turn Runner — 原子执行单元（借鉴 ACP Turn 模型）

v1 的 `process_pipeline` 是一个简单函数。v2 的 Turn Runner 是一个完整的执行引擎。

```python
# mosaic/runtime/turn_runner.py
import asyncio
import time
from dataclasses import dataclass
from typing import Any

@dataclass
class TurnResult:
    success: bool
    response: str
    tool_calls: list[dict]
    execution_results: list[dict]
    tokens_used: int
    duration_ms: float
    turn_id: str = ""

class TurnRunner:
    """Turn 级原子执行器

    一个 Turn = 用户输入 → [LLM 推理 → 工具调用]* → 最终响应

    支持：
    - ReAct 循环（推理-行动-观察）
    - 并行工具调用
    - 超时控制
    - 中途取消
    - 自动重试
    """

    def __init__(self, plugin_registry, event_bus, hooks,
                 max_iterations: int = 10, turn_timeout_s: float = 120):
        self._registry = plugin_registry
        self._event_bus = event_bus
        self._hooks = hooks
        self._max_iterations = max_iterations
        self._turn_timeout_s = turn_timeout_s

    async def run(self, session, user_input: str) -> TurnResult:
        """执行完整 Turn"""
        start = time.monotonic()
        turn_id = f"turn-{session.turn_count}"

        # 1. 组装上下文
        context_engine = self._registry.resolve_slot("context-engine")
        context = await context_engine.assemble(
            session.session_id, token_budget=4096
        )

        # 2. 注入用户消息
        messages = context.messages + [{"role": "user", "content": user_input}]

        # 3. 获取可用工具定义
        tools = self._collect_tool_definitions()

        # 4. ReAct 循环
        all_tool_calls = []
        all_results = []
        provider = self._registry.resolve_slot("provider")

        for iteration in range(self._max_iterations):
            # Hook: before_llm_call
            await self._hooks.emit("before_llm_call", {
                "session_id": session.session_id,
                "iteration": iteration,
                "messages": messages,
            })

            # LLM 推理
            response = await asyncio.wait_for(
                provider.chat(messages, tools, config={}),
                timeout=self._turn_timeout_s,
            )

            # 无工具调用 → 最终响应
            if not response.tool_calls:
                await context_engine.ingest(session.session_id,
                    {"role": "user", "content": user_input})
                await context_engine.ingest(session.session_id,
                    {"role": "assistant", "content": response.content})

                return TurnResult(
                    success=True,
                    response=response.content,
                    tool_calls=all_tool_calls,
                    execution_results=all_results,
                    tokens_used=response.usage.get("total_tokens", 0),
                    duration_ms=(time.monotonic() - start) * 1000,
                    turn_id=turn_id,
                )

            # 有工具调用 → 执行工具
            tool_results = await self._execute_tools(
                response.tool_calls, session
            )
            all_tool_calls.extend(response.tool_calls)
            all_results.extend(tool_results)

            # 将工具结果追加到消息历史
            messages.append({"role": "assistant", "content": response.raw_content})
            for tc, tr in zip(response.tool_calls, tool_results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": str(tr),
                })

        raise RuntimeError(f"Turn 超过最大迭代次数: {self._max_iterations}")

    async def _execute_tools(self, tool_calls: list[dict], session) -> list[dict]:
        """并行执行工具调用"""
        tasks = []
        for tc in tool_calls:
            capability = self._resolve_capability_for_tool(tc["name"])
            tasks.append(capability.execute(
                intent=tc["name"],
                params=tc.get("arguments", {}),
                ctx={"session_id": session.session_id},
            ))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if not isinstance(r, Exception) else {"error": str(r)}
            for r in results
        ]

    def _collect_tool_definitions(self) -> list[dict]:
        """从所有已注册 Capability 插件收集工具定义"""
        tools = []
        for plugin_id in self._registry.list_by_kind("capability"):
            plugin = self._registry.resolve(plugin_id)
            tools.extend(plugin.get_tool_definitions())
        return tools

    def _resolve_capability_for_tool(self, tool_name: str):
        """根据工具名解析到对应的 Capability 插件"""
        for plugin_id in self._registry.list_by_kind("capability"):
            plugin = self._registry.resolve(plugin_id)
            if tool_name in [t["name"] for t in plugin.get_tool_definitions()]:
                return plugin
        raise KeyError(f"未找到工具: {tool_name}")
```

### 3.5 多 Agent 路由（借鉴 OpenClaw 7 层路由）

```python
# mosaic/gateway/agent_router.py
from dataclasses import dataclass

@dataclass
class RouteBinding:
    """路由绑定规则"""
    agent_id: str
    match: dict  # channel, scene, intent_pattern, priority 等

@dataclass
class ResolvedRoute:
    agent_id: str
    session_key: str
    matched_by: str  # "binding.scene" | "binding.intent" | "binding.channel" | "default"

class AgentRouter:
    """多 Agent 路由器 — 多层级优先匹配

    匹配优先级（借鉴 OpenClaw 的 7 层路由）：
    1. 显式 session 绑定（用户指定 agent）
    2. 场景绑定（厨房场景 → 厨房 Agent）
    3. 意图模式匹配（navigate_* → 导航 Agent）
    4. 通道绑定（ROS2 → 机器人 Agent）
    5. 能力匹配（谁能处理这个意图）
    6. 默认 Agent
    """

    def __init__(self, bindings: list[RouteBinding] = None):
        self._bindings = bindings or []
        self._default_agent_id = "default"

    def resolve(self, context: dict) -> ResolvedRoute:
        """解析路由"""
        # 层级匹配逻辑
        for binding in sorted(self._bindings,
                               key=lambda b: b.match.get("priority", 99)):
            if self._matches(binding.match, context):
                return ResolvedRoute(
                    agent_id=binding.agent_id,
                    session_key=f"{binding.agent_id}:{context.get('channel', 'unknown')}",
                    matched_by=f"binding.{binding.match.get('type', 'custom')}",
                )
        return ResolvedRoute(
            agent_id=self._default_agent_id,
            session_key=f"{self._default_agent_id}:default",
            matched_by="default",
        )

    def _matches(self, match_rule: dict, context: dict) -> bool:
        """规则匹配"""
        if "channel" in match_rule and match_rule["channel"] != context.get("channel"):
            return False
        if "scene" in match_rule and match_rule["scene"] != context.get("scene"):
            return False
        if "intent_pattern" in match_rule:
            import re
            intent = context.get("intent", "")
            if not re.match(match_rule["intent_pattern"], intent):
                return False
        return True
```

### 3.6 Node Registry — 分布式能力节点（借鉴 OpenClaw NodeRegistry）

这是 MOSAIC 独有的需求：机器人的硬件能力分布在不同节点上。

```python
# mosaic/nodes/node_registry.py
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum

class NodeStatus(Enum):
    CONNECTED = "connected"
    HEARTBEAT_MISS = "heartbeat_miss"
    DISCONNECTED = "disconnected"

@dataclass
class NodeInfo:
    node_id: str
    node_type: str           # "ros2_bridge" | "hardware_driver" | "sensor" | "remote"
    capabilities: list[str]  # 该节点提供的能力列表
    status: NodeStatus = NodeStatus.CONNECTED
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)

class NodeRegistry:
    """节点注册表 — 管理分布式能力节点

    机器人场景下，能力分布在不同硬件节点：
    - ROS2 Bridge Node：连接 ROS2 生态
    - Hardware Driver Node：直接驱动硬件
    - Sensor Fusion Node：传感器融合
    - Remote Robot Node：远程机器人
    """

    def __init__(self, heartbeat_timeout_s: float = 30):
        self._nodes: dict[str, NodeInfo] = {}
        self._heartbeat_timeout = heartbeat_timeout_s
        self._capability_index: dict[str, set[str]] = {}  # capability → node_ids

    def register(self, node: NodeInfo) -> None:
        """注册节点"""
        self._nodes[node.node_id] = node
        for cap in node.capabilities:
            self._capability_index.setdefault(cap, set()).add(node.node_id)

    def unregister(self, node_id: str) -> None:
        """注销节点"""
        node = self._nodes.pop(node_id, None)
        if node:
            for cap in node.capabilities:
                self._capability_index.get(cap, set()).discard(node_id)

    def heartbeat(self, node_id: str) -> None:
        """更新心跳"""
        node = self._nodes.get(node_id)
        if node:
            node.last_heartbeat = time.time()
            node.status = NodeStatus.CONNECTED

    def resolve_nodes_for_capability(self, capability: str) -> list[NodeInfo]:
        """根据能力查找可用节点"""
        node_ids = self._capability_index.get(capability, set())
        return [
            self._nodes[nid] for nid in node_ids
            if self._nodes[nid].status == NodeStatus.CONNECTED
        ]

    async def check_health(self) -> dict[str, NodeStatus]:
        """健康检查 — 标记超时节点"""
        now = time.time()
        results = {}
        for node_id, node in self._nodes.items():
            if now - node.last_heartbeat > self._heartbeat_timeout:
                node.status = NodeStatus.HEARTBEAT_MISS
            results[node_id] = node.status
        return results
```


### 3.7 生命周期钩子系统（借鉴 OpenClaw Hooks + Internal Hooks）

```python
# mosaic/core/hooks.py
from enum import Enum
from typing import Callable, Awaitable, Any
import asyncio

class HookPoint(str, Enum):
    # Gateway 生命周期
    GATEWAY_START = "gateway.start"
    GATEWAY_STOP = "gateway.stop"
    CONFIG_RELOAD = "config.reload"

    # Session 生命周期
    SESSION_CREATE = "session.create"
    SESSION_CLOSE = "session.close"
    SESSION_IDLE = "session.idle"

    # Turn 生命周期
    TURN_START = "turn.start"
    TURN_END = "turn.end"
    TURN_ERROR = "turn.error"

    # LLM 调用
    BEFORE_LLM_CALL = "llm.before_call"
    AFTER_LLM_CALL = "llm.after_call"

    # 工具执行
    BEFORE_TOOL_EXEC = "tool.before_exec"
    AFTER_TOOL_EXEC = "tool.after_exec"
    TOOL_PERMISSION = "tool.permission"     # 权限审批（借鉴 OpenClaw ExecApproval）

    # 能力节点
    NODE_CONNECT = "node.connect"
    NODE_DISCONNECT = "node.disconnect"
    NODE_HEALTH_CHANGE = "node.health_change"

    # 上下文
    CONTEXT_COMPACT = "context.compact"
    CONTEXT_OVERFLOW = "context.overflow"

HookHandler = Callable[[dict[str, Any]], Awaitable[Any]]

class HookManager:
    """生命周期钩子管理器

    支持：
    - 同步/异步 handler
    - 优先级排序
    - 拦截（handler 返回 False 可中断链）
    - 超时保护
    """

    def __init__(self):
        self._hooks: dict[str, list[tuple[int, HookHandler]]] = {}

    def on(self, point: HookPoint | str, handler: HookHandler, priority: int = 100):
        """注册钩子"""
        key = point.value if isinstance(point, HookPoint) else point
        self._hooks.setdefault(key, []).append((priority, handler))
        self._hooks[key].sort(key=lambda x: x[0])

    async def emit(self, point: HookPoint | str, context: dict[str, Any]) -> bool:
        """触发钩子链，返回 False 表示被拦截"""
        key = point.value if isinstance(point, HookPoint) else point
        for _, handler in self._hooks.get(key, []):
            try:
                result = await asyncio.wait_for(handler(context), timeout=5.0)
                if result is False:
                    return False  # 拦截
            except asyncio.TimeoutError:
                pass  # 超时跳过
            except Exception:
                pass  # 单个 hook 失败不影响链
        return True
```

### 3.8 配置系统（借鉴 OpenClaw ConfigReactor + 热重载）

```yaml
# config/mosaic.yaml — 统一配置
gateway:
  host: "0.0.0.0"
  port: 8765
  max_concurrent_sessions: 10
  idle_session_timeout_s: 300

agents:
  default:
    provider: "minimax"
    model: "MiniMax-M2.5"
    context_engine: "sliding-window"
    memory: "file-memory"
    max_turn_iterations: 10
    turn_timeout_s: 120

  navigation_agent:
    provider: "minimax"
    model: "MiniMax-M2.5"
    capabilities: ["navigation", "slam"]

plugins:
  slots:
    memory: "file-memory"           # 或 "vector-memory"
    context-engine: "sliding-window" # 或 "summary-compaction" 或 "rag-retrieval"
    planner: "react-planner"

  entries:
    navigation:
      enabled: true
      config:
        ros2_namespace: "/robot1"
    motion:
      enabled: true
    vision:
      enabled: false

channels:
  cli:
    enabled: true
  websocket:
    enabled: true
    port: 8766
  ros2_topic:
    enabled: true
    subscribe_topic: "/user_command"
    publish_topic: "/agent_response"

nodes:
  heartbeat_timeout_s: 30
  auto_discovery: true

routing:
  bindings:
    - agent_id: "navigation_agent"
      match:
        type: "intent"
        intent_pattern: "navigate_.*|patrol"
        priority: 1
    - agent_id: "default"
      match:
        type: "channel"
        channel: "*"
        priority: 99

hooks:
  - point: "tool.before_exec"
    action: "log"
    config:
      level: "INFO"
  - point: "turn.error"
    action: "notify"
    config:
      channel: "websocket"

observability:
  metrics:
    enabled: true
    port: 9090
  tracing:
    enabled: false
    exporter: "otlp"
```

```python
# mosaic/core/config.py
import yaml
import asyncio
from pathlib import Path
from typing import Any, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ConfigManager:
    """配置管理器 — 校验 + 合并 + 热重载

    借鉴 OpenClaw 的 ConfigReactor：
    - 文件变更自动检测
    - 区分 hot-reload（不重启）vs cold-reload（需重启）
    - 配置校验 + 降级
    """

    def __init__(self, config_path: str):
        self._path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._listeners: list[Callable[[dict, dict], None]] = []
        self._observer: Observer | None = None

    def load(self) -> dict[str, Any]:
        """加载并校验配置"""
        with open(self._path) as f:
            self._config = yaml.safe_load(f) or {}
        return self._config

    def get(self, dotpath: str, default=None) -> Any:
        """点分路径取值: 'gateway.port' → config['gateway']['port']"""
        keys = dotpath.split(".")
        val = self._config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def on_change(self, listener: Callable[[dict, dict], None]):
        """注册配置变更监听器"""
        self._listeners.append(listener)

    def start_watching(self):
        """启动文件监听（热重载）"""
        class Handler(FileSystemEventHandler):
            def __init__(self, manager):
                self.manager = manager
            def on_modified(self, event):
                if event.src_path == str(self.manager._path):
                    old = self.manager._config.copy()
                    self.manager.load()
                    for listener in self.manager._listeners:
                        listener(old, self.manager._config)

        self._observer = Observer()
        self._observer.schedule(Handler(self), str(self._path.parent))
        self._observer.start()

    def stop_watching(self):
        if self._observer:
            self._observer.stop()
```

### 3.9 可观测性（借鉴 OpenClaw diagnostics-otel 扩展）

```python
# mosaic/observability/tracing.py
import time
import uuid
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

@dataclass
class Span:
    trace_id: str
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    attributes: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)

    def set_attribute(self, key: str, value):
        self.attributes[key] = value

    def add_event(self, name: str, attributes: dict = None):
        self.events.append({
            "name": name,
            "timestamp": time.monotonic(),
            "attributes": attributes or {},
        })

    def end(self):
        self.end_time = time.monotonic()

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0

class Tracer:
    """分布式追踪器 — 追踪完整的 Turn 执行链路

    Turn → LLM Call → Tool Execution → Capability Execute → Node RPC
    每一层都有 Span，形成完整的调用树。
    """

    def __init__(self):
        self._spans: list[Span] = []
        self._exporters: list = []

    @asynccontextmanager
    async def span(self, name: str, trace_id: str = None,
                    parent_span_id: str = None):
        s = Span(
            trace_id=trace_id or str(uuid.uuid4())[:16],
            name=name,
            parent_span_id=parent_span_id,
        )
        try:
            yield s
        finally:
            s.end()
            self._spans.append(s)
            for exporter in self._exporters:
                await exporter.export(s)
```


---

## 四、v1 → v2 关键差异对比

| 维度 | MOSAIC v1 (Demo) | MOSAIC v2 (前沿) | 借鉴来源 |
|------|-----------------|-----------------|---------|
| 架构范式 | 同步线性管道 | 事件驱动 + 控制面/执行面分离 | OpenClaw Gateway/ACP |
| 执行模型 | 单次 pipeline 调用 | Turn 级原子执行 + ReAct 循环 | OpenClaw AcpSessionManager.runTurn |
| 插件系统 | 手动 register() | 自动发现 + 排他性插槽 + Protocol 接口 | OpenClaw Plugin-SDK + Slots |
| 会话管理 | 无 | 完整生命周期 + 并发控制 + 资源回收 | OpenClaw AcpSessionManager |
| 上下文 | 无记忆 | 可插拔引擎 (滑动窗口/摘要压缩/RAG) | OpenClaw ContextEngine |
| 通道 | 仅 CLI | 多通道插件 (CLI/WS/ROS2/Voice/MQTT) | OpenClaw ChannelPlugin |
| Provider | 硬编码 if/else | 注册表 + 动态切换 + 流式输出 | OpenClaw ProviderPlugin |
| 路由 | 无 | 多层级优先匹配 + 多 Agent 协作 | OpenClaw resolveAgentRoute |
| 节点管理 | 无 | 分布式节点注册 + 心跳 + 能力发现 | OpenClaw NodeRegistry |
| 钩子 | 无 | 20+ 生命周期钩子点 + 拦截链 | OpenClaw Hooks + Internal Hooks |
| 配置 | 静态 YAML 读取 | 热重载 + 校验 + 变更监听 | OpenClaw ConfigReactor |
| 可观测性 | print/logging | 结构化日志 + 指标 + 分布式追踪 | OpenClaw diagnostics-otel |
| 规划器 | 直接 intent→capability | ReAct 循环 + 多轮工具调用 | Agent 领域前沿范式 |
| 工具执行 | 串行 + 简单重试 | 并行执行 + 超时 + 权限审批 | OpenClaw ExecApprovalManager |
| 记忆 | 无 | 可插拔 (文件/向量/场景记忆) | OpenClaw memory-core/memory-lancedb |
| 安全 | 无 | 执行策略 + allowlist + 沙箱 | OpenClaw exec-policy + sandbox |

---

## 五、v2 数据流全景

```
                    ┌─────────────────────────────────────────┐
                    │            用户/外部系统                  │
                    └──────┬──────────────┬───────────────┬───┘
                           │              │               │
                    ┌──────▼──┐    ┌──────▼──┐    ┌───────▼──┐
                    │  CLI    │    │  WebSocket│    │  ROS2    │
                    │ Channel │    │  Channel │    │  Channel │
                    └──────┬──┘    └──────┬──┘    └───────┬──┘
                           │              │               │
                    ┌──────▼──────────────▼───────────────▼───┐
                    │           Gateway Server                 │
                    │  ┌─────────────────────────────────────┐ │
                    │  │         Event Bus                    │ │
                    │  └──────────────┬──────────────────────┘ │
                    │                 │                         │
                    │  ┌──────────────▼──────────────────────┐ │
                    │  │       Agent Router                   │ │
                    │  │  (多层级匹配 → 选择 Agent)           │ │
                    │  └──────────────┬──────────────────────┘ │
                    │                 │                         │
                    │  ┌──────────────▼──────────────────────┐ │
                    │  │      Session Manager                 │ │
                    │  │  (创建/复用 Session + 并发控制)       │ │
                    │  └──────────────┬──────────────────────┘ │
                    └─────────────────┼────────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────────┐
                    │           Turn Runner                     │
                    │                                           │
                    │  ┌─────────────────────────────────────┐ │
                    │  │  1. Context Engine.assemble()        │ │
                    │  │     (组装历史上下文)                   │ │
                    │  └──────────────┬──────────────────────┘ │
                    │                 │                         │
                    │  ┌──────────────▼──────────────────────┐ │
                    │  │  2. Provider.chat()                  │ │
                    │  │     (LLM 推理 + Tool Use)            │ │
                    │  └──────────────┬──────────────────────┘ │
                    │                 │                         │
                    │           ┌─────▼─────┐                  │
                    │           │ 有工具调用? │                  │
                    │           └─────┬─────┘                  │
                    │          Yes    │    No                   │
                    │  ┌──────────────▼───┐  ┌──────────────┐ │
                    │  │  3. Tool Executor │  │ 返回最终响应  │ │
                    │  │  (并行执行工具)    │  └──────────────┘ │
                    │  └──────────────┬───┘                    │
                    │                 │                         │
                    │  ┌──────────────▼──────────────────────┐ │
                    │  │  4. Capability.execute()             │ │
                    │  │     ↓                                │ │
                    │  │  Node Registry → 选择节点             │ │
                    │  │     ↓                                │ │
                    │  │  ROS2 Bridge / Hardware Driver        │ │
                    │  └──────────────┬──────────────────────┘ │
                    │                 │                         │
                    │  ┌──────────────▼──────────────────────┐ │
                    │  │  5. 工具结果 → 追加到消息历史         │ │
                    │  │     → 回到步骤 2（ReAct 循环）       │ │
                    │  └─────────────────────────────────────┘ │
                    │                                           │
                    │  ┌─────────────────────────────────────┐ │
                    │  │  6. Context Engine.ingest()          │ │
                    │  │     (存储本轮对话)                    │ │
                    │  └─────────────────────────────────────┘ │
                    └───────────────────────────────────────────┘
```

---

## 六、与 v1 调研报告的区别

上一份报告是"渐进优化"思路——保留现有代码，增量引入模式。这份是"推倒重建"：

1. **不是加 ChannelAdapter 抽象**，而是整个 Gateway 控制面 + 事件总线
2. **不是加 ContextEngine 接口**，而是完整的 Turn Runner + ReAct 循环 + 上下文生命周期
3. **不是加 HookManager**，而是 20+ 钩子点覆盖全链路 + 拦截链 + 权限审批
4. **不是加 ProviderRegistry**，而是排他性插槽 + 自动发现 + Protocol 零继承
5. **新增 Node Layer**：分布式能力节点管理，这是机器人场景独有的需求
6. **新增可观测性层**：结构化日志 + 指标 + 分布式追踪，生产级必备
7. **新增安全层**：执行策略 + allowlist + 沙箱隔离

这不是优化方案，是一个全新的机器人智能体框架的架构蓝图。
