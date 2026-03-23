# mosaic/plugin_sdk/types.py
# 插件 SDK 类型定义 — 基于 Python Protocol 的零继承耦合接口
# 所有插件类型通过 Protocol 约束而非继承，支持运行时 isinstance 检查

from __future__ import annotations

from typing import Protocol, Any, runtime_checkable, AsyncIterator, Callable
from dataclasses import dataclass, field
from enum import Enum


# ── 插件元数据 ──

@dataclass(frozen=True)
class PluginMeta:
    """插件元数据

    描述插件的基本信息，frozen=True 保证不可变性。
    kind 取值: "capability" | "provider" | "channel" | "memory" | "context-engine"
    """
    id: str
    name: str
    version: str
    description: str
    kind: str
    author: str = ""
    config_schema: dict | None = None


# ── 通用类型 ──

class HealthState(Enum):
    """插件健康状态枚举"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class HealthStatus:
    """健康检查结果"""
    state: HealthState
    message: str = ""


@dataclass
class ExecutionContext:
    """执行上下文 — 携带 session 和 turn 信息"""
    session_id: str
    turn_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """执行结果 — 工具/能力执行后的统一返回格式"""
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    error: str | None = None


# ── 能力插件协议 ──

@runtime_checkable
class CapabilityPlugin(Protocol):
    """能力插件接口 — 导航/运动/视觉等

    定义能力插件必须实现的方法：
    - meta: 插件元数据
    - get_supported_intents: 返回支持的意图列表
    - get_tool_definitions: 返回工具定义（供 LLM 调用）
    - execute: 执行指定意图
    - cancel: 取消当前执行
    - health_check: 健康检查
    """
    meta: PluginMeta

    def get_supported_intents(self) -> list[str]: ...
    def get_tool_definitions(self) -> list[dict[str, Any]]: ...
    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult: ...
    async def cancel(self) -> bool: ...
    async def health_check(self) -> HealthStatus: ...


# ── Provider 插件协议（非排他性，多 Provider 共存）──

@dataclass
class ProviderConfig:
    """Provider 配置 — LLM 调用参数"""
    model: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderResponse:
    """Provider 响应 — LLM 返回结果"""
    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    raw_content: Any = None


@runtime_checkable
class ProviderPlugin(Protocol):
    """Provider 插件接口 — LLM 提供者（多 Provider 共存，配置选择默认）

    定义 Provider 插件必须实现的方法：
    - meta: 插件元数据
    - chat: 同步聊天调用
    - stream: 流式聊天调用
    - validate_auth: 验证认证信息
    """
    meta: PluginMeta

    async def chat(self, messages: list[dict], tools: list[dict] | None,
                   config: ProviderConfig) -> ProviderResponse: ...
    async def stream(self, messages: list[dict], tools: list[dict] | None,
                     config: ProviderConfig) -> AsyncIterator: ...
    async def validate_auth(self) -> bool: ...


# ── 通道插件协议 ──

@dataclass
class OutboundMessage:
    """出站消息 — 发送给用户的消息"""
    session_id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SendResult:
    """发送结果"""
    success: bool
    error: str | None = None


@runtime_checkable
class ChannelPlugin(Protocol):
    """通道插件接口 — CLI/WebSocket/ROS2 Topic

    定义通道插件必须实现的方法：
    - meta: 插件元数据
    - start: 启动通道
    - stop: 停止通道
    - send: 发送出站消息
    - on_message: 注册入站消息处理器
    """
    meta: PluginMeta

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def send(self, message: OutboundMessage) -> SendResult: ...
    def on_message(self, handler: Callable) -> None: ...


# ── 记忆插件协议 ──

@dataclass
class MemoryEntry:
    """记忆条目 — 存储和检索的基本单元"""
    key: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0


@runtime_checkable
class MemoryPlugin(Protocol):
    """记忆插件接口 — 文件/向量/场景记忆

    定义记忆插件必须实现的方法：
    - meta: 插件元数据
    - store: 存储记忆
    - search: 语义搜索
    - get: 精确获取
    - delete: 删除记忆
    """
    meta: PluginMeta

    async def store(self, key: str, content: str, metadata: dict) -> None: ...
    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...
    async def get(self, key: str) -> MemoryEntry | None: ...
    async def delete(self, key: str) -> bool: ...


# ── 上下文引擎插件协议 ──

@dataclass
class AssembleResult:
    """上下文组装结果"""
    messages: list[dict[str, Any]]
    token_count: int


@dataclass
class CompactResult:
    """上下文压缩结果"""
    removed_count: int
    remaining_count: int


@runtime_checkable
class ContextEnginePlugin(Protocol):
    """上下文引擎接口 — 滑动窗口/摘要压缩/RAG

    定义上下文引擎插件必须实现的方法：
    - meta: 插件元数据
    - ingest: 摄入消息到上下文
    - assemble: 按 token 预算组装上下文
    - compact: 压缩/清理上下文
    """
    meta: PluginMeta

    async def ingest(self, session_id: str, message: dict) -> None: ...
    async def assemble(self, session_id: str, token_budget: int) -> AssembleResult: ...
    async def compact(self, session_id: str, force: bool = False) -> CompactResult: ...
