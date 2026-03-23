# MOSAIC v2 — 事件驱动、插件优先的机器人智能体框架
#
# 公共 API 导出
# 完整数据流: 用户输入 → Channel → EventBus → Gateway → Router → Session → TurnRunner → Provider → Capability → 响应
# 所有组件通过 EventBus 解耦通信

# ── 协议层：事件、消息类型、错误码 ──
from mosaic.protocol.events import Event, EventPriority, EventHandler
from mosaic.protocol.messages import (
    INBOUND_MESSAGE,
    OUTBOUND_MESSAGE,
    TURN_COMPLETE,
    TOOL_EXECUTED,
    NODE_STATUS_CHANGED,
    CONFIG_CHANGED,
)
from mosaic.protocol.errors import ErrorCode

# ── 核心基础设施：EventBus、HookManager、ConfigManager ──
from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager, HOOK_POINTS
from mosaic.core.config import ConfigManager

# ── 插件 SDK：元数据、协议类型、数据类型、注册表 ──
from mosaic.plugin_sdk.types import (
    # 元数据
    PluginMeta,
    # 健康状态
    HealthState,
    HealthStatus,
    # 执行上下文与结果
    ExecutionContext,
    ExecutionResult,
    # 能力插件协议
    CapabilityPlugin,
    # Provider 插件协议及数据类型
    ProviderPlugin,
    ProviderConfig,
    ProviderResponse,
    # 通道插件协议及数据类型
    ChannelPlugin,
    OutboundMessage,
    SendResult,
    # 记忆插件协议及数据类型
    MemoryPlugin,
    MemoryEntry,
    # 上下文引擎插件协议及数据类型
    ContextEnginePlugin,
    AssembleResult,
    CompactResult,
)
from mosaic.plugin_sdk.registry import PluginRegistry

# ── 控制面：Gateway、Session、Router ──
from mosaic.gateway.session_manager import SessionManager, Session, SessionState
from mosaic.gateway.agent_router import AgentRouter, RouteBinding, ResolvedRoute
from mosaic.gateway.server import GatewayServer

# ── 运行时：TurnRunner ──
from mosaic.runtime.turn_runner import TurnRunner, TurnResult

# ── 节点层：NodeRegistry ──
from mosaic.nodes.node_registry import NodeRegistry, NodeInfo, NodeStatus

# 公共 API 列表
__all__ = [
    # 协议层
    "Event",
    "EventPriority",
    "EventHandler",
    "INBOUND_MESSAGE",
    "OUTBOUND_MESSAGE",
    "TURN_COMPLETE",
    "TOOL_EXECUTED",
    "NODE_STATUS_CHANGED",
    "CONFIG_CHANGED",
    "ErrorCode",
    # 核心基础设施
    "EventBus",
    "HookManager",
    "HOOK_POINTS",
    "ConfigManager",
    # 插件 SDK — 元数据与通用类型
    "PluginMeta",
    "HealthState",
    "HealthStatus",
    "ExecutionContext",
    "ExecutionResult",
    # 插件 SDK — 协议类型
    "CapabilityPlugin",
    "ProviderPlugin",
    "ChannelPlugin",
    "MemoryPlugin",
    "ContextEnginePlugin",
    # 插件 SDK — 数据类型
    "ProviderConfig",
    "ProviderResponse",
    "OutboundMessage",
    "SendResult",
    "MemoryEntry",
    "AssembleResult",
    "CompactResult",
    # 插件 SDK — 注册表
    "PluginRegistry",
    # 控制面
    "SessionManager",
    "Session",
    "SessionState",
    "AgentRouter",
    "RouteBinding",
    "ResolvedRoute",
    "GatewayServer",
    # 运行时
    "TurnRunner",
    "TurnResult",
    # 节点层
    "NodeRegistry",
    "NodeInfo",
    "NodeStatus",
]
