- title: MCP Server And SayCan Analysis
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, paper, saycan
- source_type: paper

# MOSAIC MCP Server 方案深度分析：回溯 SayCan 设计哲学

> 从 SayCan 的 affordance grounding 核心思想出发，分析方案 D（MCP Server 包装）的细粒度架构问题

---

## 零、为什么需要回溯到 SayCan

前几份报告分析了方案 D 的宏观合理性（~200 行包装、零重写、标准协议），但忽略了一个根本问题：

**MOSAIC 不是一个普通的 Agent 框架，它是 SayCan 论文的工程实现。**

SayCan 的核心公式是：

```
π = argmax_{π∈Π} p(cπ|s, ℓπ) × p(ℓπ|i)
```

其中：
- `p(ℓπ|i)` — LLM 提供的"Say"：技能对指令有用的概率（语义落地）
- `p(cπ|s, ℓπ)` — 价值函数提供的"Can"：技能在当前状态下可行的概率（可供性落地）

这两个概率的**乘积**决定了选择哪个技能。这意味着：

1. **工具选择不是纯 LLM 决策** — 必须结合物理世界状态
2. **可供性是动态的** — 同一个 `navigate_to` 工具，电池低时不可用，路径被阻塞时不可用
3. **LLM 和可供性必须在同一个决策循环内耦合** — 不能先问 LLM 选什么工具，再去问机器人能不能做

这对 MCP Server 方案提出了根本性的架构约束。

---

## 一、核心矛盾：MCP 协议的静态工具列表 vs SayCan 的动态可供性

### 1.1 MCP 的工具模型

MCP 协议的 `tools/list` 返回一个**静态工具列表**：

```json
{
  "tools": [
    {"name": "navigate_to", "description": "导航到指定位置", "inputSchema": {...}},
    {"name": "pick_up", "description": "拿取物品", "inputSchema": {...}}
  ]
}
```

LLM 看到这个列表后，基于语义理解选择工具。这对应 SayCan 的 `p(ℓπ|i)` 部分。

### 1.2 SayCan 需要的是什么

SayCan 需要的不只是工具列表，而是**每个工具在当前状态下的可行性评分**：

```
navigate_to(厨房)  → affordance: 0.92（路径畅通，电池充足）
navigate_to(阳台)  → affordance: 0.15（门关着，需要先开门）
pick_up(杯子)      → affordance: 0.88（杯子在视野内，机械臂可达）
pick_up(遥控器)    → affordance: 0.03（遥控器不在当前位置）
```

### 1.3 矛盾的本质

| 维度 | MCP 标准模型 | SayCan 需求 |
|------|------------|------------|
| 工具列表 | 静态，启动时确定 | 动态，随物理状态变化 |
| 工具描述 | 固定文本 | 应包含当前可行性信息 |
| 选择依据 | 纯 LLM 语义推理 | LLM 语义 × 物理可供性 |
| 调用结果 | 成功/失败 | 成功/失败 + 状态更新 → 影响下一步可供性 |

---

## 二、三种 MCP 包装粒度的对比

基于上述矛盾，方案 D 不是一个单一方案，而是一个**粒度谱**。从薄到厚：

### 2.1 薄包装：纯工具代理（Thin Proxy）

```
TS Agent ──MCP──→ Python MCP Server ──→ Capability Plugin ──→ ROS2
                  （只做工具转发）
```

**实现**：~200 行，每个 Capability 的 `execute()` 直接映射为 MCP Tool。

**丢失了什么**：
- ❌ 可供性落地 — LLM 不知道哪些工具当前可行
- ❌ ReAct 循环 — TurnRunner 的多轮推理逻辑需要在 TS 端重写
- ❌ Hook 安全链 — `tool.permission` 钩子不在 MCP 调用路径上
- ❌ 上下文引擎 — 会话记忆、滑动窗口压缩需要在 TS 端重建
- ❌ 节点健康感知 — TS 端不知道 ROS2 节点是否在线

**适用场景**：只想让外部 Agent 框架"遥控"机器人做单个动作，不需要复杂推理。

### 2.2 中间层：可供性感知的工具代理（Affordance-Aware Proxy）

```
TS Agent ──MCP──→ Python MCP Server ──→ Affordance Filter ──→ Capability ──→ ROS2
                  （工具列表动态 + 可供性注入）
```

**实现**：~500 行。关键创新：

```python
@app.list_tools()
async def list_tools():
    """动态工具列表 — 注入当前可供性信息"""
    tools = []
    for pid in registry.list_by_kind("capability"):
        plugin = registry.resolve(pid)
        health = await plugin.health_check()
        
        for tool_def in plugin.get_tool_definitions():
            # 关键：将可供性信息编码到工具描述中
            affordance = await _compute_affordance(plugin, tool_def)
            
            enhanced_desc = (
                f"{tool_def['description']}\n"
                f"[当前可行性: {affordance.score:.0%}] "
                f"{affordance.reason}"
            )
            
            tools.append(Tool(
                name=tool_def["name"],
                description=enhanced_desc,
                inputSchema=tool_def["parameters"],
            ))
    return tools
```

**保留了什么**：
- ✅ 可供性落地 — 通过动态描述注入，LLM 能感知物理约束
- ✅ Hook 安全链 — `tool.permission` 在 `call_tool` 内触发
- ✅ 节点健康感知 — 不健康节点的工具标记为不可用
- ❌ ReAct 循环 — 仍需 TS 端实现
- ❌ 上下文引擎 — 仍需 TS 端实现

**适用场景**：TS 端有自己的 Agent 框架（如 OpenClaw），想利用 MOSAIC 的物理能力，且需要感知机器人状态。

### 2.3 厚包装：完整 Turn 代理（Full Turn Proxy）

```
TS 调度层 ──MCP──→ Python MCP Server（含 TurnRunner）──→ Capability ──→ ROS2
                   （完整 ReAct 循环在 Python 内）
```

**实现**：~800 行。MCP Server 暴露的不是原子工具，而是**高层次任务接口**：

```python
@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="execute_task",
            description="执行一个自然语言机器人任务，内部自动分解为多步骤执行",
            inputSchema={
                "type": "object",
                "properties": {
                    "instruction": {"type": "string", "description": "自然语言指令"},
                    "session_id": {"type": "string", "description": "会话ID（可选）"},
                },
                "required": ["instruction"],
            },
        ),
        Tool(
            name="get_robot_state",
            description="获取机器人当前状态（位置、电池、持有物品、周围环境）",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_capabilities",
            description="列出机器人当前可用的能力及其可行性评分",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "execute_task":
        # 完整的 TurnRunner ReAct 循环在 Python 内执行
        session = await session_manager.get_or_create(arguments.get("session_id"))
        result = await session_manager.run_turn(
            session.session_id, arguments["instruction"], turn_runner
        )
        return [TextContent(type="text", text=result.response)]
```

**保留了什么**：
- ✅ 可供性落地 — ReAct 循环内部完整保留 SayCan 机制
- ✅ ReAct 循环 — TurnRunner 完整运行在 Python 内
- ✅ Hook 安全链 — 所有钩子正常工作
- ✅ 上下文引擎 — 会话记忆完整保留
- ✅ 节点健康感知 — 完整保留

**丢失了什么**：
- ❌ TS 端对工具调用的细粒度控制 — TS 只能发指令，不能干预中间步骤
- ❌ TS Agent 框架的 ReAct 能力被浪费 — 两层 ReAct 循环冗余

**适用场景**：TS 端只做高层调度（多机器人协作、任务分配），不参与单个机器人的推理过程。

---

## 三、回溯 MOSAIC 设计哲学的关键决策

### 3.1 TurnRunner 应该在哪一侧？

这是整个方案的核心架构决策。回溯到 SayCan：

**SayCan 的 ReAct 循环本质**：
```
循环 {
    1. LLM 评估所有技能对指令的有用性 → p(ℓπ|i)
    2. 价值函数评估所有技能的可行性 → p(cπ|s, ℓπ)  
    3. 选择 argmax 的技能执行
    4. 执行后状态更新 s → s'
    5. 回到步骤 1
}
```

步骤 1 需要 LLM（可以在任何地方），步骤 2 需要物理状态（必须在 Python/ROS2 侧），步骤 3-4 需要两者的结合。

**如果 TurnRunner 在 TS 侧**：
- 步骤 2 需要跨 MCP 调用获取可供性 → 每轮循环多一次 RPC
- 步骤 3 的 argmax 计算在 TS 侧，但可供性数据来自 Python 侧
- 状态更新 s→s' 在 Python 侧，需要同步回 TS

**如果 TurnRunner 在 Python 侧**：
- 步骤 1-4 全部在同一进程内，零通信开销
- LLM 调用通过 httpx 直接发出（Provider 插件在 Python 内）
- 可供性评估是进程内直接调用
- TS 侧只需要发送高层指令和接收最终结果

**结论**：对于 SayCan 架构，TurnRunner 应该留在 Python 侧。

理由不是"TS 不能做"，而是 SayCan 的核心创新——**可供性落地**——要求 LLM 决策和物理状态评估在同一个紧密循环内。把它们拆到两个进程会引入不必要的延迟和复杂度，而且违背了 SayCan "Say 和 Can 必须在同一步骤内融合"的设计哲学。

### 3.2 可供性信息如何跨越 MCP 边界？

即使 TurnRunner 留在 Python 侧，TS 端仍然需要知道机器人"能做什么"。这有三种策略：

**策略 A：描述注入（推荐）**

将可供性信息编码到 MCP 工具的 description 字段：

```
navigate_to: 导航到指定位置 [可行性: 92%，路径畅通]
pick_up: 拿取物品 [可行性: 5%，目标物品不在视野内]
```

优点：零协议扩展，任何 MCP 客户端都能理解
缺点：信息是文本形式，不够结构化

**策略 B：元数据扩展**

利用 MCP Tool 的扩展字段传递结构化可供性数据：

```python
Tool(
    name="navigate_to",
    description="导航到指定位置",
    inputSchema={...},
    # MCP 允许额外字段
    annotations={
        "affordance_score": 0.92,
        "constraints": ["battery > 20%", "path_clear"],
        "node_status": "connected",
    },
)
```

优点：结构化，TS 端可以程序化处理
缺点：非标准 MCP 字段，部分客户端可能忽略

**策略 C：专用查询工具**

提供 `get_affordances` 工具让 TS 端主动查询：

```python
Tool(
    name="get_affordances",
    description="获取所有能力的当前可行性评分",
    inputSchema={"type": "object", "properties": {}},
)
```

优点：按需查询，不污染工具列表
缺点：需要额外一次 MCP 调用

**推荐组合**：策略 A（描述注入）作为默认 + 策略 C（专用查询）作为补充。这样普通 MCP 客户端通过描述就能感知可供性，高级客户端可以通过专用工具获取结构化数据。

### 3.3 Hook 系统如何跨越 MCP 边界？

MOSAIC 的 Hook 系统中，`tool.permission` 是安全关键的：

```python
# 当前：进程内钩子链
allowed = await hooks.emit("tool.permission", {
    "tool_name": "navigate_to",
    "params": {"target": "阳台"},
    "session_id": session.session_id,
})
if not allowed:
    return ExecutionResult(success=False, error="权限被拒绝")
```

**如果 TurnRunner 在 Python 侧**（推荐方案）：Hook 系统完全不需要跨边界，所有钩子在 Python 进程内正常工作。

**如果 TurnRunner 在 TS 侧**：需要将 Hook 系统暴露为 MCP 资源或通知，复杂度极高。这是另一个支持 TurnRunner 留在 Python 侧的理由。

### 3.4 会话状态如何跨越 MCP 边界？

MOSAIC 的 SessionManager 管理会话生命周期，包括：
- 会话创建/关闭
- 并发控制（max_concurrent）
- 空闲回收（idle_timeout）
- Turn 计数和状态流转

**厚包装方案下**：SessionManager 完全在 Python 侧，TS 端通过 `session_id` 参数关联会话。MCP Server 暴露会话管理工具：

```python
Tool(name="create_session", description="创建新的机器人交互会话"),
Tool(name="close_session", description="关闭指定会话"),
Tool(name="get_session_state", description="获取会话状态"),
```

**中间层方案下**：TS 端管理自己的会话，Python 端的 SessionManager 退化为简单的执行上下文容器。

---

## 四、推荐方案：分层 MCP Server

综合以上分析，推荐一个**分层 MCP Server**，同时暴露两个粒度的接口：

### 4.1 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    外部 TS Agent / IDE / 用户                │
└──────────────────────────┬──────────────────────────────────┘
                           │ MCP 协议 (stdio / SSE)
┌──────────────────────────┴──────────────────────────────────┐
│                  Python MOSAIC MCP Server                    │
│                                                             │
│  ┌─── 高层接口（厚包装）────────────────────────────────┐   │
│  │  execute_task(instruction, session_id?)               │   │
│  │  → 内部调用完整 TurnRunner ReAct 循环                 │   │
│  │  → 保留 SayCan 的 Say×Can 融合决策                    │   │
│  │  → 所有 Hook 正常工作                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─── 低层接口（薄包装 + 可供性）──────────────────────┐   │
│  │  navigate_to(target, speed)     [affordance: 92%]    │   │
│  │  pick_up(object)                [affordance: 88%]    │   │
│  │  operate_appliance(device, op)  [affordance: 75%]    │   │
│  │  → 直接调用 Capability Plugin                         │   │
│  │  → 跳过 TurnRunner，由外部 Agent 控制循环             │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─── 状态查询接口 ────────────────────────────────────┐   │
│  │  get_robot_state()        → 位置/电池/持有物品        │   │
│  │  get_affordances()        → 所有能力的可行性评分      │   │
│  │  get_session_state(id)    → 会话状态                  │   │
│  │  list_capabilities()      → 当前可用能力列表          │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              MOSAIC 核心（完全不动）                    │   │
│  │  Gateway → SessionManager → TurnRunner → Provider     │   │
│  │  EventBus, HookManager, PluginRegistry                │   │
│  │  Capability Plugins → NodeRegistry → ROS2 Bridge      │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 为什么是分层

两层接口服务不同的使用场景：

| 场景 | 使用接口 | 说明 |
|------|---------|------|
| IDE 集成（Kiro/Cursor） | 高层 `execute_task` | 用户输入自然语言，MOSAIC 内部完成所有推理和执行 |
| TS Agent 框架调度 | 低层原子工具 | 外部 Agent 自己做 ReAct，MOSAIC 只做执行 |
| 多机器人协作 | 高层 + 状态查询 | 协调层查询各机器人状态，分配任务 |
| 调试/监控 | 状态查询 | 实时查看机器人状态和能力可行性 |
| 论文 Demo | 高层 `execute_task` | 最简单的集成方式 |

### 4.3 SayCan 哲学的保留

这个分层设计如何保留 SayCan 的核心：

1. **高层接口保留完整的 Say×Can 融合**：`execute_task` 内部走完整的 TurnRunner ReAct 循环，LLM 推理和可供性评估在同一进程内紧密耦合，完全符合 SayCan 的 `argmax p(cπ|s,ℓπ) × p(ℓπ|i)` 公式。

2. **低层接口通过描述注入保留部分可供性**：即使外部 Agent 自己做决策，工具描述中的可行性评分也提供了 `p(cπ|s,ℓπ)` 的近似值，让外部 LLM 能感知物理约束。

3. **状态查询接口支持外部实现完整 SayCan**：如果外部 Agent 框架想自己实现 SayCan 的融合决策，可以通过 `get_affordances()` 获取结构化的可供性数据，在自己的推理循环中使用。

---

## 五、实现路径

### 5.1 阶段一：最小可用（~300 行，1-2 天）

只实现高层接口 + 基础状态查询：

```python
# mosaic/mcp_server.py
from mcp.server import Server
from mcp.types import Tool, TextContent

app = Server("mosaic-robot")

@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="execute_task",
            description="执行自然语言机器人任务（内部自动分解多步骤）",
            inputSchema={
                "type": "object",
                "properties": {
                    "instruction": {"type": "string"},
                    "session_id": {"type": "string"},
                },
                "required": ["instruction"],
            },
        ),
        Tool(
            name="get_robot_state",
            description="获取机器人当前状态",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

@app.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "execute_task":
        result = await gateway.handle_task(arguments["instruction"],
                                           arguments.get("session_id"))
        return [TextContent(type="text", text=result.response)]
    elif name == "get_robot_state":
        state = await gateway.get_state()
        return [TextContent(type="text", text=json.dumps(state))]
```

### 5.2 阶段二：可供性感知（+200 行，1 天）

添加低层原子工具 + 可供性注入：

```python
@app.list_tools()
async def list_tools():
    tools = [...]  # 阶段一的工具
    
    # 动态添加所有 Capability 的原子工具
    for pid in registry.list_by_kind("capability"):
        plugin = registry.resolve(pid)
        health = await plugin.health_check()
        
        for tool_def in plugin.get_tool_definitions():
            affordance = _compute_affordance(plugin, tool_def, health)
            tools.append(Tool(
                name=f"raw_{tool_def['name']}",  # 前缀区分高层/低层
                description=f"{tool_def['description']} [可行性: {affordance:.0%}]",
                inputSchema=tool_def["parameters"],
            ))
    
    return tools
```

### 5.3 阶段三：完整分层（+300 行，1-2 天）

添加会话管理、结构化可供性查询、MCP 资源（机器人状态订阅）。

### 5.4 总工作量

| 阶段 | 新增代码 | 修改现有代码 | 耗时 |
|------|---------|------------|------|
| 阶段一 | ~300 行 | 0 行 | 1-2 天 |
| 阶段二 | ~200 行 | 0 行 | 1 天 |
| 阶段三 | ~300 行 | 0 行 | 1-2 天 |
| **合计** | **~800 行** | **0 行** | **3-5 天** |

关键点：**现有 MOSAIC 代码零修改**。MCP Server 是纯增量的一层包装。

---

## 六、与论文的关系

### 6.1 对论文的价值

MCP Server 包装为论文提供了一个重要的**系统贡献点**：

> "我们将 SayCan 的 affordance grounding 机制封装为标准 MCP 协议接口，使任何支持 MCP 的 Agent 框架都能调用具备物理可供性感知的机器人能力。这是首次将 SayCan 的 Say×Can 融合决策暴露为标准化的 Agent 工具协议。"

这比"我们用 Python 实现了 SayCan"更有学术价值，因为它解决了一个实际问题：**如何让通用 Agent 框架与具身机器人交互，同时保留物理可供性约束**。

### 6.2 可以写进论文的创新点

1. **可供性感知的动态工具描述**：将 `p(cπ|s,ℓπ)` 编码到 MCP 工具描述中，让外部 LLM 在工具选择时自然地考虑物理约束
2. **分层接口设计**：高层保留完整 SayCan 循环，低层暴露原子能力，适配不同集成场景
3. **零侵入包装**：证明 SayCan 架构可以在不修改核心代码的情况下标准化为 Agent 协议

---

## 七、结论

回溯到 SayCan 的设计哲学后，方案 D 的细粒度决策变得清晰：

1. **TurnRunner 必须留在 Python 侧** — SayCan 的 Say×Can 融合要求 LLM 决策和可供性评估在同一紧密循环内
2. **MCP 工具列表必须是动态的** — 静态工具列表丢失了 SayCan 最核心的可供性落地
3. **分层接口是最优解** — 高层保留完整 SayCan，低层服务外部 Agent 框架
4. **可供性通过描述注入跨越 MCP 边界** — 零协议扩展，任何 MCP 客户端都能受益
5. **现有代码零修改** — MCP Server 是纯增量包装层

这个方案既保留了 MOSAIC 作为 SayCan 工程实现的学术完整性，又获得了 MCP 生态的标准化接入能力。对于论文阶段的项目，这是投入产出比最高的架构演进路径。
