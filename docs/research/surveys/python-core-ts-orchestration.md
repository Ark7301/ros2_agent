- title: Python Core And TypeScript Orchestration
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, survey, architecture
- source_type: survey

# MOSAIC 混合架构方案分析：Python 核心 + TypeScript Agent 调度层

> 分析将 MOSAIC 拆分为 Python 机器人执行层 + TypeScript Agent 调度层的合理性

---

## 一、方案定义：到底拆什么

先明确"Agent 调度层"和"机器人调用层"的边界。按当前 MOSAIC v2 的代码结构：

### 拟迁移到 TypeScript 的模块（Agent 调度层）

| 模块 | 当前文件 | 职责 |
|------|---------|------|
| Gateway Server | `mosaic/gateway/server.py` | 系统入口，组件编排，消息路由 |
| Session Manager | `mosaic/gateway/session_manager.py` | 会话生命周期，并发控制 |
| Agent Router | `mosaic/gateway/agent_router.py` | 多 Agent 路由匹配 |
| Turn Runner | `mosaic/runtime/turn_runner.py` | ReAct 循环，LLM 调用，工具调度 |
| Event Bus | `mosaic/core/event_bus.py` | 异步事件分发 |
| Hook Manager | `mosaic/core/hooks.py` | 生命周期钩子 |
| Config Manager | `mosaic/core/config.py` | 配置加载/热重载 |
| Plugin Registry | `mosaic/plugin_sdk/registry.py` | 插件发现/注册/解析 |
| Plugin SDK Types | `mosaic/plugin_sdk/types.py` | 插件接口定义 |
| Protocol Layer | `mosaic/protocol/` | 事件/消息/错误定义 |

### 保留在 Python 的模块（机器人执行层）

| 模块 | 当前文件 | 职责 |
|------|---------|------|
| Navigation Plugin | `plugins/capabilities/navigation/` | Nav2 导航 |
| Motion Plugin | `plugins/capabilities/motion/` | 运动控制 |
| Manipulation Plugin | `plugins/capabilities/manipulation/` | 机械臂抓取 |
| Appliance Plugin | `plugins/capabilities/appliance/` | 家电操作 |
| Node Registry | `mosaic/nodes/node_registry.py` | ROS2 节点管理 |
| 未来的 SLAM/Vision | — | 建图/视觉感知 |

### 两层之间的通信协议

```
┌─────────────────────────────────────────────┐
│         TypeScript Agent 调度层              │
│                                             │
│  Gateway → Router → Session → TurnRunner    │
│  EventBus, Hooks, Config, PluginRegistry    │
│  Provider Plugins (LLM API 调用)            │
│  Channel Plugins (CLI/Web/MQTT)             │
│  Context Engine, Memory                     │
│                                             │
│         ↕ gRPC / WebSocket / JSON-RPC       │
│                                             │
│         Python 机器人执行层                  │
│                                             │
│  Capability Plugins (导航/运动/抓取/家电)    │
│  Node Registry (ROS2 节点管理)              │
│  ROS2 Bridge (rclpy)                        │
│  传感器融合 / SLAM / 视觉                   │
└─────────────────────────────────────────────┘
```

---

## 二、合理性分析

### 2.1 这个方案合理的地方

**1. 关注点分离确实存在**

MOSAIC 确实有两个不同性质的关注点：
- Agent 调度：LLM 推理、会话管理、上下文压缩、多 Agent 路由——这些是纯软件逻辑，和机器人硬件无关
- 机器人执行：导航、运动控制、传感器融合——这些强依赖 ROS2 生态和硬件驱动

这两层的变更频率、依赖图、部署方式确实不同，拆分有架构上的合理性。

**2. TS 在 Agent 开发生态的真实优势**

| 维度 | TypeScript 生态 | Python 生态 |
|------|----------------|-------------|
| Vercel AI SDK | ✅ 原生支持，流式 UI 集成 | ❌ 无 |
| LangChain.js | ✅ 活跃维护 | ✅ LangChain Python 同等 |
| OpenAI SDK | ✅ 官方 TS SDK，类型完整 | ✅ 官方 Python SDK，同等 |
| Anthropic SDK | ✅ 官方 TS SDK | ✅ 官方 Python SDK |
| MCP (Model Context Protocol) | ✅ 官方 TS SDK 先发 | ⚠️ Python SDK 后发，社区维护 |
| ACP (Agent Client Protocol) | ✅ `@agentclientprotocol/sdk` | ❌ 无官方 Python SDK |
| Agent 框架 | ✅ OpenClaw, Mastra, CrewAI.js | ✅ CrewAI, AutoGen, LangGraph |
| Web UI 集成 | ✅ 前后端统一，SSE/WebSocket 原生 | ⚠️ 需要 FastAPI + 前端分离 |
| 类型系统 | ✅ 编译时完整检查 | ⚠️ mypy 可选，运行时才报错 |

关键点：ACP 协议只有 TS SDK，MCP 的 TS SDK 是官方先发。如果 MOSAIC 未来要接入 IDE 集成、MCP 工具生态、ACP 客户端，TS 调度层确实更顺畅。

**3. OpenClaw 本身就是这个模式的验证**

OpenClaw 的架构就是 TS 控制面 + 分布式节点执行：
- `src/acp/` — Agent Control Protocol，TS 实现的控制面
- `src/node-host/` — 节点执行，通过 WebSocket 调用远程节点
- 节点可以是浏览器、远程机器、移动设备——和 MOSAIC 的 ROS2 节点概念一致

---

### 2.2 这个方案的问题

**1. 跨语言通信是最大的成本**

当前 MOSAIC 的 TurnRunner 调用 Capability 插件是进程内直接调用：

```python
# 当前：进程内调用，零延迟，零序列化
cap = self._resolve_capability_for_tool(tc["name"])
result = await cap.execute(intent, params, ctx)
```

拆分后变成跨进程 RPC：

```
TS TurnRunner → gRPC/WebSocket → Python Capability Server → rclpy → ROS2
```

这意味着：
- 每次工具调用增加 1-5ms 网络延迟（本地 loopback）
- 需要定义和维护一套 IDL（protobuf/JSON Schema）
- 参数和返回值需要序列化/反序列化
- 错误处理变复杂（网络超时、连接断开、重试）
- 调试变困难（两个进程、两种语言、两套日志）

**对于 MOSAIC 的影响**：LLM API 调用延迟是秒级，1-5ms 的 RPC 延迟可以忽略。但调试复杂度的增加是实实在在的。

**2. 你需要重写的代码量**

| 需要重写的模块 | Python 行数 | 复杂度 |
|--------------|-----------|--------|
| Gateway Server | ~250 行 | 高（组件编排） |
| Session Manager | ~180 行 | 中 |
| Agent Router | ~120 行 | 低 |
| Turn Runner | ~300 行 | 高（ReAct 循环核心） |
| Event Bus | ~90 行 | 中 |
| Hook Manager | ~50 行 | 低 |
| Config Manager | ~80 行 | 低 |
| Plugin Registry | ~100 行 | 中 |
| Plugin SDK Types | ~150 行 | 中 |
| Protocol Layer | ~80 行 | 低 |
| **合计** | **~1400 行** | |

加上：
- 新增 gRPC/WebSocket 通信层：~500 行（TS 端）+ ~300 行（Python 端）
- 新增 IDL 定义：~200 行
- 重写所有测试：~2000 行
- Provider 插件迁移（minimax 等）：~300 行
- Channel 插件迁移（CLI 等）：~200 行

**总计约 5000 行代码的重写/新增工作量。**

**3. 两套构建系统、两套依赖管理、两套部署流程**

| 维度 | 当前（纯 Python） | 混合架构 |
|------|-----------------|---------|
| 启动 | `python3 -c "from mosaic..."` | 先启动 Python 执行层，再启动 TS 调度层 |
| 依赖 | `pip install -r requirements.txt` | pip + pnpm，两套 lockfile |
| 测试 | `pytest` | pytest + vitest，两套测试框架 |
| CI/CD | 一条 pipeline | 两条 pipeline |
| 部署 | 一个 Docker 镜像 | 两个进程（或一个镜像装两个运行时） |
| 调试 | 一个 debugger | 两个 debugger，跨进程断点困难 |

**4. 你的 Capability 插件不只是"执行"**

看当前的 TurnRunner 代码，Capability 插件不只是被动执行——它们参与 LLM 的工具定义：

```python
# TurnRunner._collect_tool_definitions()
for pid in self._registry.list_by_kind("capability"):
    plugin = self._registry.resolve(pid)
    tools.extend(plugin.get_tool_definitions())
```

这意味着 TS 调度层需要在启动时从 Python 执行层拉取所有工具定义，并在插件变更时同步更新。这不是简单的"调用"关系，而是"注册+发现+调用"的完整生命周期。

**5. 你的项目阶段不适合**

从文件结构看（论文素材、外文翻译、冒烟测试报告），MOSAIC 处于研究/原型阶段。这个阶段的核心需求是：
- 快速迭代验证想法
- 端到端跑通 Demo
- 写论文展示成果

混合架构会显著降低迭代速度。每次改一个工具定义，你需要改 Python 端的实现 + TS 端的 IDL + 两端的测试。

---

## 三、替代方案对比

### 方案 A：纯 Python（当前方案）

```
Python 进程
├── Gateway (asyncio)
├── TurnRunner (ReAct 循环)
├── LLM Provider (httpx 异步调用)
├── Capability Plugins (rclpy)
└── Channel Plugins (CLI/WebSocket)
```

优点：零通信开销，单进程调试，快速迭代
缺点：TS Agent 生态（ACP/MCP）接入需要额外适配

### 方案 B：Python 核心 + TS 调度层（你提出的方案）

```
TS 进程 (Agent 调度)          Python 进程 (机器人执行)
├── Gateway                   ├── Capability Server (gRPC)
├── TurnRunner                ├── Navigation Plugin
├── LLM Provider              ├── Motion Plugin
├── Session/Router            ├── Node Registry
└── Channel Plugins           └── ROS2 Bridge
        ↕ gRPC/WebSocket
```

优点：TS Agent 生态原生接入，类型系统更强
缺点：跨语言通信成本，双倍运维复杂度，5000 行重写

### 方案 C：Python 核心 + TS Web 控制面板（上份报告建议）

```
Python 进程 (完整 MOSAIC)     TS 进程 (Web UI)
├── Gateway (WebSocket API)   ├── Next.js/React Dashboard
├── TurnRunner                ├── 实时状态展示
├── All Plugins               ├── 会话管理 UI
└── ROS2 Bridge               └── 配置管理 UI
        ↕ WebSocket (只传状态/命令)
```

优点：Python 核心不动，TS 只做展示层，通信协议简单
缺点：Agent 调度逻辑仍在 Python，无法直接用 TS Agent 框架

### 方案 D：Python 核心 + MCP Server 暴露能力（推荐）

```
TS Agent 框架 (外部)          Python MCP Server (MOSAIC)
├── 任意 TS Agent 框架         ├── MCP Tool: navigate_to
├── OpenClaw / Mastra / 自研   ├── MCP Tool: pick_up
├── ACP 客户端                 ├── MCP Tool: operate_appliance
└── Web UI                    ├── Gateway (管理 ROS2 节点)
        ↕ MCP 协议 (stdio/SSE)  └── ROS2 Bridge
```

这个方案的核心思路：**不拆 MOSAIC，而是把 MOSAIC 包装成一个 MCP Server。**

- MOSAIC 保持纯 Python，内部架构不变
- 对外暴露 MCP 协议接口，每个 Capability 注册为一个 MCP Tool
- 任何 TS Agent 框架（OpenClaw、Mastra、自研）都可以通过 MCP 协议调用 MOSAIC 的机器人能力
- 如果需要自己的 Agent 调度，可以用 TS 写一个轻量调度层，通过 MCP 调用 MOSAIC

**这样你同时获得了：**
1. Python 核心不动（零重写成本）
2. TS Agent 生态可以接入（通过 MCP 标准协议）
3. 通信协议是标准化的（MCP，不是自定义 gRPC）
4. 未来可以被任何支持 MCP 的 Agent 框架调用

---

## 四、方案 D 的具体实现路径

### 4.1 将 MOSAIC 包装为 MCP Server

```python
# mosaic/mcp_server.py
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("mosaic-robot")

@app.list_tools()
async def list_tools():
    """从 PluginRegistry 动态收集所有 Capability 的工具定义"""
    tools = []
    for pid in registry.list_by_kind("capability"):
        plugin = registry.resolve(pid)
        for tool_def in plugin.get_tool_definitions():
            tools.append(Tool(
                name=tool_def["name"],
                description=tool_def["description"],
                inputSchema=tool_def["parameters"],
            ))
    return tools

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    """路由到对应的 Capability 插件执行"""
    cap = resolve_capability_for_tool(name)
    result = await cap.execute(name, arguments, ctx)
    return [TextContent(type="text", text=result.message)]
```

### 4.2 TS 调度层通过 MCP 调用

```typescript
// ts-agent/src/index.ts
import { Client } from "@modelcontextprotocol/sdk/client";

const mosaicClient = new Client({
  name: "mosaic-agent",
  version: "1.0.0",
});

// 连接到 MOSAIC MCP Server
await mosaicClient.connect(new StdioClientTransport({
  command: "python3",
  args: ["-m", "mosaic.mcp_server"],
}));

// 获取所有机器人能力
const tools = await mosaicClient.listTools();

// 在 Agent 循环中调用机器人能力
const result = await mosaicClient.callTool({
  name: "navigate_to",
  arguments: { target: "厨房", speed: 0.5 },
});
```

### 4.3 架构图

```
┌─────────────────────────────────────────────────────────┐
│                    用户/外部系统                          │
│  CLI / Web UI / IDE / 其他 Agent                        │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              TS Agent 调度层（可选，轻量）                │
│                                                         │
│  可以是 OpenClaw / Mastra / 自研 TS Agent               │
│  负责：LLM 推理、会话管理、上下文、多 Agent 路由         │
│  通过 MCP 协议调用机器人能力                             │
│                                                         │
└────────────────────────┬────────────────────────────────┘
                         │ MCP 协议 (stdio / SSE)
┌────────────────────────┴────────────────────────────────┐
│              Python MOSAIC MCP Server                    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │  MCP Tool 注册层（自动从 PluginRegistry 收集）    │    │
│  └──────────────────────┬──────────────────────────┘    │
│                         │                               │
│  ┌──────────┐ ┌────────┴───┐ ┌──────────┐ ┌────────┐  │
│  │Navigation│ │Manipulation│ │ Motion   │ │Appliance│  │
│  │ Plugin   │ │  Plugin    │ │ Plugin   │ │ Plugin  │  │
│  └────┬─────┘ └─────┬──────┘ └────┬─────┘ └────┬───┘  │
│       │             │              │             │       │
│  ┌────┴─────────────┴──────────────┴─────────────┴───┐  │
│  │           Node Registry + ROS2 Bridge              │  │
│  └────────────────────────────────────────────────────┘  │
│                         │                               │
│                    rclpy / Nav2 / MoveIt2                │
└─────────────────────────────────────────────────────────┘
```

---

## 五、四个方案的决策矩阵

| 维度 | 方案 A (纯 Python) | 方案 B (Python+TS 拆分) | 方案 C (Python+TS UI) | 方案 D (MCP Server) |
|------|-------------------|----------------------|---------------------|-------------------|
| 重写成本 | 0 | ~5000 行 | ~1000 行 (UI) | ~200 行 (MCP 包装) |
| TS Agent 生态接入 | ❌ 需适配 | ✅ 原生 | ❌ 仅 UI | ✅ 标准协议 |
| ROS2 集成 | ✅ 直接 | ✅ Python 端直接 | ✅ 直接 | ✅ 直接 |
| 调试复杂度 | 低 | 高（双进程双语言） | 中 | 中（MCP 有调试工具） |
| 运维复杂度 | 低 | 高（双构建双部署） | 中 | 低（MCP Server 是子进程） |
| 迭代速度 | 快 | 慢 | 快 | 快 |
| 未来扩展性 | 中 | 高 | 中 | 高（任何 MCP 客户端可接入） |
| 适合项目阶段 | ✅ 研究/原型 | ❌ 需要成熟团队 | ✅ 需要 UI 时 | ✅ 研究/原型 + 生态接入 |

---

## 六、结论

### 方案 B（你提出的 Python+TS 拆分）的判断

**架构上合理，但时机不对。**

合理性在于：Agent 调度和机器人执行确实是两个不同的关注点，TS 在 Agent 开发生态（ACP/MCP/Vercel AI SDK）确实有优势。

不合理的地方在于：
1. **5000 行重写成本**对于研究阶段项目太重
2. **跨语言通信层**的开发和维护成本被低估——你需要定义 IDL、处理序列化、处理连接管理、处理错误传播、处理两端的日志关联
3. **Capability 插件不只是被动执行**，它们参与工具定义注册，拆分后需要同步机制
4. **调试体验断崖式下降**——两个进程、两种语言、两套日志、跨进程断点

### 推荐路径

**短期（现在）**：方案 A，继续纯 Python，把精力放在功能完善和论文上。

**中期（需要 TS Agent 生态时）**：方案 D，把 MOSAIC 包装成 MCP Server。这只需要 ~200 行代码，就能让任何 TS Agent 框架通过标准协议调用你的机器人能力。你可以用 OpenClaw 或任何 TS 框架做 Agent 调度，MOSAIC 专注做它擅长的事——机器人能力执行。

**长期（如果项目变成产品）**：再考虑方案 B 的完整拆分。到那时你有更多人手、更明确的需求、更稳定的接口定义。

MCP Server 方案的核心优势是：**你不需要重写任何现有代码，只需要加一层薄薄的 MCP 包装，就能同时获得 Python 生态和 TS 生态的好处。**
