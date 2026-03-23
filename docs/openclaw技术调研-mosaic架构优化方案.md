# OpenClaw 技术调研 → MOSAIC 架构优化方案

## 一、OpenClaw 核心架构概览

OpenClaw 是一个生产级多通道 AI Agent 网关框架，TypeScript/ESM 实现，monorepo 结构。

### 1.1 整体分层

```
CLI (src/cli/) → Commands (src/commands/)
    ↓
Gateway (src/gateway/) ← WebSocket 控制面
    ├── Channels (src/channels/ + extensions/) ← 60+ 消息通道插件
    ├── Routing (src/routing/) ← 多 Agent 路由绑定
    ├── Agents (src/agents/) ← ACP RPC Agent 运行时
    │   ├── Tools (src/agents/tools/) ← Agent 工具集
    │   ├── Context Engine (src/context-engine/) ← 可插拔上下文管理
    │   └── Sandbox (src/agents/sandbox.ts) ← Docker 沙箱隔离
    ├── Plugins (src/plugins/) ← 插件运行时 + 类型系统
    ├── Hooks (src/hooks/) ← 生命周期钩子
    └── Config (src/config/) ← JSON5 配置 + 热重载
```

### 1.2 关键设计模式

| 模式 | OpenClaw 实现 | 核心价值 |
|------|-------------|---------|
| Plugin-SDK 边界隔离 | `openclaw/plugin-sdk/*` 100+ 子路径导出 | 扩展只能通过 SDK 公共接口交互，杜绝内部耦合 |
| Channel 抽象 | `ChannelPlugin` 接口 (20+ adapter 组合) | 统一消息入站/出站模型，新通道零改核心 |
| Provider 抽象 | `ProviderPlugin` 接口 (30+ 生命周期钩子) | LLM 提供者热插拔，auth/catalog/stream 全链路可定制 |
| Context Engine | 可插拔接口 (ingest/assemble/compact) | 上下文管理策略可替换（摘要/RAG/全量） |
| 路由绑定 | 多层级匹配 (peer→guild+roles→team→account→channel) | 多 Agent 精确路由，支持复杂组织结构 |
| 依赖注入 | `createDefaultDeps()` 工厂 | 测试友好，组件可替换 |
| 生命周期钩子 | bundled hooks + plugin hooks | 启动/会话/命令等关键节点可扩展 |


## 二、MOSAIC 现有架构分析

### 2.1 当前结构

```
mosaic_demo/
├── main.py                    ← 入口，手动组装所有组件
├── interfaces_abstract/       ← 抽象层
│   ├── capability.py          ← Capability ABC
│   ├── capability_registry.py ← 意图→能力映射
│   ├── model_provider.py      ← ModelProvider ABC
│   └── data_models.py         ← 核心数据结构
├── agent_core/                ← 调度核心
│   ├── task_parser.py         ← NL → TaskResult (委托 LLM)
│   ├── task_planner.py        ← TaskResult → ExecutionPlan
│   └── task_executor.py       ← ExecutionPlan → 执行 (重试+优先级队列)
├── model_providers/           ← LLM 适配层
│   ├── minimax_provider.py    ← MiniMax Anthropic API
│   ├── llm_provider.py        ← 美的 AIMP Claude API
│   └── *_client.py            ← HTTP 客户端
├── capabilities/              ← 机器人能力
│   ├── mock_navigation.py     ← 导航 Mock
│   └── mock_motion.py         ← 运动 Mock
├── interfaces/                ← 用户接口
│   └── cli_interface.py       ← CLI 交互
└── config/                    ← 配置
    ├── agent_config.yaml
    └── config_manager.py
```

### 2.2 当前管道

```
用户输入 → CLIInterface → TaskContext
    → TaskParser (LLM Tool Use) → TaskResult
    → TaskPlanner (intent→capability 映射) → ExecutionPlan
    → TaskExecutor (顺序执行+重试) → ExecutionResult
    → CLIInterface 展示
```

### 2.3 现有优势
- 抽象层设计合理：Capability ABC + ModelProvider ABC + CapabilityRegistry
- 数据模型清晰：TaskContext → TaskResult → ExecutionPlan → ExecutionResult
- 依赖倒置：TaskParser 依赖 ModelProvider 抽象而非具体实现
- 重试策略：指数退避 + 优先级队列

### 2.4 待优化点
- **单通道**：仅 CLI，无法扩展到 Web/ROS2/语音等
- **单 Provider 绑定**：main.py 硬编码 if/else 选择 provider
- **无插件机制**：Capability 注册是手动代码，无动态发现/加载
- **无上下文管理**：每次对话独立，无会话记忆/上下文压缩
- **无生命周期钩子**：无法在关键节点注入自定义逻辑
- **配置与代码耦合**：config_manager 仅读 YAML，无热重载/校验
- **Planner 过于简单**：直接 intent→capability 映射，无 LLM 规划/场景图验证


## 三、从 OpenClaw 借鉴的关键架构优化

### 3.1 插件化能力系统（借鉴 Plugin-SDK + Extension 模式）

**OpenClaw 做法**：每个 Channel/Provider 是独立 extension 包，通过 `definePluginEntry()` / `defineChannelPluginEntry()` 注册，运行时通过 SDK 子路径导出交互。

**MOSAIC 优化方案**：

```python
# mosaic/plugin_sdk/capability_plugin.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class CapabilityPluginEntry:
    """能力插件注册入口"""
    id: str
    name: str
    description: str
    capability_factory: 'Callable[[], Capability]'
    config_schema: dict | None = None

def define_capability_plugin(
    id: str, name: str, description: str,
    capability_factory, config_schema=None
) -> CapabilityPluginEntry:
    """类似 OpenClaw 的 definePluginEntry"""
    return CapabilityPluginEntry(
        id=id, name=name, description=description,
        capability_factory=capability_factory,
        config_schema=config_schema,
    )
```

```python
# mosaic/plugins/navigation/entry.py — 独立插件包
from mosaic.plugin_sdk import define_capability_plugin
from .ros2_navigation import ROS2NavigationCapability

plugin = define_capability_plugin(
    id="ros2-navigation",
    name="ROS2 Navigation",
    description="基于 Nav2 的自主导航能力",
    capability_factory=lambda: ROS2NavigationCapability(),
)
```

```python
# mosaic/core/plugin_loader.py — 动态发现+加载
import importlib, pkgutil

class PluginLoader:
    """从 mosaic.plugins.* 自动发现并加载插件"""
    def discover_plugins(self, package='mosaic.plugins'):
        entries = []
        pkg = importlib.import_module(package)
        for _, name, _ in pkgutil.iter_modules(pkg.__path__):
            mod = importlib.import_module(f"{package}.{name}.entry")
            if hasattr(mod, 'plugin'):
                entries.append(mod.plugin)
        return entries
```

**核心收益**：新增机器人能力（SLAM、抓取、语音）只需添加插件包，零改核心代码。

### 3.2 多通道接口抽象（借鉴 ChannelPlugin 模式）

**OpenClaw 做法**：`ChannelPlugin` 接口包含 20+ adapter（messaging/outbound/streaming/threading 等），每个通道实现自己的 adapter 组合。

**MOSAIC 优化方案**（简化版，适配机器人场景）：

```python
# mosaic/interfaces_abstract/channel.py
from abc import ABC, abstractmethod

class ChannelAdapter(ABC):
    """通道适配器 — 统一消息入站/出站模型"""

    @abstractmethod
    def get_id(self) -> str: ...

    @abstractmethod
    async def receive(self) -> 'TaskContext':
        """接收用户输入，封装为 TaskContext"""
        ...

    @abstractmethod
    async def send(self, result: 'ExecutionResult') -> None:
        """发送执行结果给用户"""
        ...

    @abstractmethod
    async def send_progress(self, message: str) -> None:
        """发送中间进度反馈"""
        ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
```

可实现的通道：`CLIChannel`、`WebSocketChannel`、`ROS2TopicChannel`、`VoiceChannel`。

### 3.3 Provider 注册表（借鉴 ProviderPlugin 模式）

**OpenClaw 做法**：`ProviderPlugin` 包含 auth/catalog/discovery/stream/usage 等 30+ 钩子，支持运行时动态模型解析。

**MOSAIC 优化方案**：

```python
# mosaic/interfaces_abstract/model_provider.py（增强版）
class ModelProvider(ABC):
    @abstractmethod
    def get_id(self) -> str: ...

    @abstractmethod
    async def parse_task(self, context: TaskContext) -> TaskResult: ...

    @abstractmethod
    def get_supported_intents(self) -> list[str]: ...

    # 新增：借鉴 OpenClaw 的 provider 生命周期
    async def validate_auth(self) -> bool: ...
    def get_capabilities(self) -> dict: ...  # 支持 streaming/tool_use 等

class ProviderRegistry:
    """Provider 注册表 — 支持多 provider 共存和动态切换"""
    def register(self, provider: ModelProvider): ...
    def resolve(self, provider_id: str) -> ModelProvider: ...
    def resolve_by_capability(self, capability: str) -> ModelProvider: ...
```

### 3.4 上下文引擎（借鉴 ContextEngine 接口）

**OpenClaw 做法**：`ContextEngine` 接口定义 `bootstrap/ingest/assemble/compact` 生命周期，支持插槽替换（legacy/memory-lancedb 等）。

**MOSAIC 优化方案**：

```python
# mosaic/context/context_engine.py
from abc import ABC, abstractmethod

class ContextEngine(ABC):
    """上下文引擎 — 管理对话历史和场景状态"""

    @abstractmethod
    async def ingest(self, session_id: str, message: dict) -> None:
        """摄入一条消息到上下文存储"""

    @abstractmethod
    async def assemble(self, session_id: str, token_budget: int) -> list[dict]:
        """在 token 预算内组装模型上下文"""

    @abstractmethod
    async def compact(self, session_id: str) -> None:
        """压缩上下文（摘要/裁剪）"""

# 实现：SimpleContextEngine（内存）、PersistentContextEngine（文件）、RAGContextEngine（向量检索）
```

**核心收益**：机器人多轮对话记忆、场景状态持久化、长对话自动压缩。

### 3.5 生命周期钩子（借鉴 Hooks 系统）

**OpenClaw 做法**：bundled hooks（boot-md/session-memory/command-logger）+ plugin hooks，在启动/会话/命令等节点注入逻辑。

**MOSAIC 优化方案**：

```python
# mosaic/core/hooks.py
from enum import Enum
from typing import Callable, Any

class HookEvent(Enum):
    BEFORE_PARSE = "before_parse"      # 解析前
    AFTER_PARSE = "after_parse"        # 解析后
    BEFORE_PLAN = "before_plan"        # 规划前
    AFTER_PLAN = "after_plan"          # 规划后
    BEFORE_EXECUTE = "before_execute"  # 执行前
    AFTER_EXECUTE = "after_execute"    # 执行后
    ON_ERROR = "on_error"              # 错误时
    ON_CAPABILITY_REGISTER = "on_capability_register"  # 能力注册时

class HookManager:
    def __init__(self):
        self._hooks: dict[HookEvent, list[Callable]] = {}

    def on(self, event: HookEvent, handler: Callable):
        self._hooks.setdefault(event, []).append(handler)

    async def emit(self, event: HookEvent, context: dict[str, Any]):
        for handler in self._hooks.get(event, []):
            await handler(context)
```

**应用场景**：执行前安全检查、执行后日志记录、错误时自动降级、场景图验证等。

### 3.6 路由系统（借鉴 Routing 多层匹配）

**OpenClaw 做法**：7 层优先级匹配（peer→parent_peer→guild+roles→guild→team→account→channel），支持多 Agent 路由。

**MOSAIC 优化方案**（适配多机器人/多 Agent 场景）：

```python
# mosaic/routing/router.py
class AgentRouter:
    """多 Agent 路由 — 根据意图/场景/权限分发到不同 Agent"""

    def resolve(self, context: TaskContext) -> str:
        """返回目标 agent_id"""
        # 优先级：显式指定 > 场景绑定 > 意图匹配 > 默认 agent
```

**核心收益**：支持多机器人协作场景（导航 Agent + 抓取 Agent + 对话 Agent）。


## 四、优化后的 MOSAIC 目标架构

```
mosaic/
├── core/                          ← 核心调度（不依赖具体实现）
│   ├── pipeline.py                ← 处理管道编排
│   ├── hooks.py                   ← 生命周期钩子管理
│   ├── plugin_loader.py           ← 插件动态发现+加载
│   └── agent_router.py            ← 多 Agent 路由
├── plugin_sdk/                    ← 插件 SDK（公共接口边界）
│   ├── capability_plugin.py       ← 能力插件入口定义
│   ├── provider_plugin.py         ← Provider 插件入口定义
│   └── channel_plugin.py          ← 通道插件入口定义
├── interfaces_abstract/           ← 抽象契约层（保留现有+增强）
│   ├── capability.py              ← Capability ABC
│   ├── capability_registry.py     ← 能力注册中心
│   ├── model_provider.py          ← ModelProvider ABC（增强）
│   ├── channel.py                 ← ChannelAdapter ABC（新增）
│   ├── context_engine.py          ← ContextEngine ABC（新增）
│   └── data_models.py             ← 核心数据结构
├── agent_core/                    ← Agent 调度核心（保留现有+增强）
│   ├── task_parser.py             ← 任务解析器
│   ├── task_planner.py            ← 任务规划器（可升级为 LLM 规划）
│   └── task_executor.py           ← 任务执行器
├── context/                       ← 上下文管理（新增）
│   ├── simple_engine.py           ← 内存上下文引擎
│   └── persistent_engine.py       ← 持久化上下文引擎
├── plugins/                       ← 插件包（每个独立目录）
│   ├── navigation/                ← 导航能力插件
│   ├── motion/                    ← 运动能力插件
│   ├── manipulation/              ← 抓取能力插件（未来）
│   └── slam/                      ← SLAM 能力插件（未来）
├── providers/                     ← LLM Provider 插件
│   ├── minimax/
│   ├── openai/
│   └── midea_claude/
├── channels/                      ← 通道插件
│   ├── cli/
│   ├── websocket/
│   └── ros2_topic/
└── config/
    ├── config_manager.py          ← 配置管理（增强：校验+热重载）
    └── agent_config.yaml
```

### 管道流程（优化后）

```
Channel.receive() → TaskContext
    ↓
HookManager.emit(BEFORE_PARSE)
    ↓
ContextEngine.assemble() → 注入历史上下文
    ↓
TaskParser.parse() → TaskResult
    ↓
HookManager.emit(AFTER_PARSE)
    ↓
AgentRouter.resolve() → 选择目标 Agent
    ↓
TaskPlanner.plan() → ExecutionPlan
    ↓
HookManager.emit(BEFORE_EXECUTE)
    ↓
TaskExecutor.execute_plan() → ExecutionResult
    ↓
ContextEngine.ingest() → 存储本轮对话
    ↓
HookManager.emit(AFTER_EXECUTE)
    ↓
Channel.send() → 返回结果
```

## 五、实施优先级

| 优先级 | 优化项 | 工作量 | 影响面 |
|--------|--------|--------|--------|
| P0 | 多通道 ChannelAdapter 抽象 | 小 | 解锁 Web/ROS2/语音接入 |
| P0 | 插件化 Capability 系统 | 中 | 新能力零改核心 |
| P1 | ContextEngine 上下文管理 | 中 | 多轮对话记忆 |
| P1 | Provider 注册表 | 小 | 多 LLM 动态切换 |
| P2 | 生命周期钩子 | 小 | 可扩展性基础设施 |
| P2 | 多 Agent 路由 | 中 | 多机器人协作 |
| P3 | LLM 增强 Planner | 大 | 复杂任务分解 |
| P3 | 配置热重载+校验 | 小 | 运维体验 |

## 六、总结

OpenClaw 的核心架构思想是"一切皆插件 + 严格边界隔离"。MOSAIC 当前的抽象层设计（Capability ABC + ModelProvider ABC + Registry）方向正确，但缺少：
1. 插件动态发现/加载机制
2. 多通道统一接口
3. 上下文生命周期管理
4. 生命周期钩子扩展点

以上优化方案保持 MOSAIC 现有代码结构不变，通过增量引入 OpenClaw 的关键模式来提升架构的可扩展性和生产就绪度。
