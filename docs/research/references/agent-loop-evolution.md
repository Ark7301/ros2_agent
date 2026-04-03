- title: Agent Loop Evolution
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, references, agent-loop
- source_type: note

# 论文素材：从 Function Calling 到 Agent Loop — AI Agent 任务调度技术演进研究

> 本文档为毕业论文写作提供素材，涵盖 LLM 工具调用范式的技术演进、Agent Loop 机制分析、机器人领域的闭环规划研究、以及本系统的技术路线定位。可融入论文的"第二章 相关技术与研究现状"和"第三章 系统设计"。

---

## 一、LLM 工具调用范式的演进（适用于：2.x 相关技术研究现状）

### 1.1 技术演进脉络

LLM 与外部工具的交互方式经历了四个阶段的演进：

**第一阶段：文本解析（2022 年以前）**

早期方案通过 Prompt Engineering 让 LLM 输出特定格式的文本（如 JSON），再由外部程序解析执行。这种方式依赖脆弱的正则匹配，格式错误率高，无法保证输出的结构化可靠性。

**第二阶段：Function Calling（2023）**

2023 年 6 月，OpenAI 在 GPT 系列模型中引入 Function Calling 机制。开发者预先定义函数的名称、参数 schema 和自然语言描述，LLM 在推理时可选择调用合适的函数并输出结构化的参数 JSON。这一机制首次实现了 LLM 与外部工具的可靠结构化交互。

Function Calling 的核心特征：
- 单轮决策：LLM 在一次推理中决定调用哪个函数及其参数
- 开发者执行：LLM 仅输出调用意图，实际执行由开发者代码完成
- 结果回传：开发者将函数执行结果作为新消息回传给 LLM，LLM 生成最终回复
- 无自主循环：LLM 本身不具备"观察结果 → 再次决策"的循环能力

**第三阶段：ReAct Agent Loop（2023-2024）**

Yao 等人于 2022 年提出 ReAct（Reasoning + Acting）框架，将 LLM 的推理能力与工具调用行为交织在一个循环中。其核心模式为：

```
Thought → Action → Observation → Thought → Action → ... → Final Answer
（思考）   （调用工具）（观察结果）  （再思考）  （再调用）       （最终回答）
```

ReAct 的关键突破在于引入了 Agent Loop（智能体循环）：LLM 不再是"一次性输出答案"，而是在一个循环中持续推理、调用工具、观察结果、调整策略，直到任务完成。Function Calling 在此框架中成为 Agent Loop 内部的"执行动作"环节。

LangChain、AutoGPT 等框架在 2023-2024 年间将 ReAct 模式工程化，使其成为构建 AI Agent 的主流范式。

**第四阶段：平台级 Agent 基础设施（2025）**

2025 年 3 月，OpenAI 发布 Responses API 和 Agents SDK，标志着 Agent Loop 从框架层面上升到平台基础设施层面：

- Responses API：取代旧的 Assistants API，支持在单次 API 调用中编排多个工具（Web 搜索、文件检索、代码执行等），内置工具调用的自动循环
- Agents SDK：提供 Python 原生的 Agent 构建框架，内置 Agent Loop、Handoffs（Agent 间任务委托）、Guardrails（安全护栏）
- Agent Loop 成为内置能力：开发者无需手动实现"调用工具 → 回传结果 → 再次推理"的循环，SDK 自动管理

同期，两个重要的开放协议标准出现：
- MCP（Model Context Protocol）：Anthropic 于 2024 年 11 月发布的开放标准，解决"工具如何被发现和连接"的问题，被称为"AI 的 USB-C 接口"
- A2A（Agent-to-Agent Protocol）：Google 于 2025 年 4 月发布的开放标准，解决"不同 Agent 之间如何通信协作"的问题

### 1.2 四个阶段的对比

| 维度 | 文本解析 | Function Calling | ReAct Agent Loop | 平台级 Agent |
|------|---------|-----------------|------------------|-------------|
| 时间 | ~2022 | 2023 | 2023-2024 | 2025 |
| 工具调用方式 | 正则解析 LLM 文本输出 | LLM 原生结构化输出 | LLM 在循环中结构化调用 | 平台内置循环 + 多工具编排 |
| 自主决策能力 | 无 | 单轮决策 | 多轮自主推理 | 多轮 + 多 Agent 协作 |
| 错误处理 | 开发者硬编码 | 开发者硬编码 | LLM 观察错误后自主调整 | LLM 自主 + Guardrails |
| 复合任务 | 不支持 | LLM 一次性分解 | 动态分解，可根据中间结果调整 | 动态分解 + Agent 间委托 |
| 代表系统 | 早期 ChatGPT 插件 | OpenAI Function Calling | LangChain Agent, AutoGPT | OpenAI Agents SDK, Responses API |
| 工具发现 | 硬编码 | 预定义 schema | 预定义 schema | MCP 动态发现 |

### 1.3 关键认识：层次关系而非替代关系

需要强调的是，上述四个阶段并非简单的替代关系，而是层次递进的包含关系：

```
┌─────────────────────────────────────────────────┐
│  平台级 Agent 基础设施 (Agents SDK / MCP / A2A)  │
│  ┌───────────────────────────────────────────┐  │
│  │  Agent Loop (ReAct 模式)                   │  │
│  │  ┌─────────────────────────────────────┐  │  │
│  │  │  Function Calling (结构化工具调用)    │  │  │
│  │  │  ┌───────────────────────────────┐  │  │  │
│  │  │  │  LLM 推理 (自然语言理解)       │  │  │  │
│  │  │  └───────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
```

Function Calling 是 Agent Loop 的执行基元；Agent Loop 是平台级 Agent 的核心循环。每一层都建立在下一层之上，而非取代它。

---

## 二、Agent Loop 在机器人领域的研究（适用于：2.x 研究现状）

### 2.1 开环规划 vs 闭环规划

将 Agent Loop 的概念映射到机器人任务规划领域，对应的是"开环规划"与"闭环规划"的区别：

**开环规划（Open-loop Planning）**：LLM 一次性将自然语言指令分解为完整的动作序列，然后按序执行，执行过程中不根据环境反馈调整计划。SayCan（Google, 2022）即采用此模式——LLM 逐步选择最可能成功的技能，但每一步的选择仅基于语言模型的先验知识和技能的可行性评分，不考虑执行过程中的实际环境变化。

**闭环规划（Closed-loop Planning）**：LLM 在执行过程中持续接收环境反馈（如任务成功/失败检测、场景描述、传感器数据），并据此动态调整后续计划。这本质上就是 Agent Loop 在机器人领域的体现。

### 2.2 关键研究工作

**SayCan（Google, CoRL 2022）— 开环 + 能力锚定**

SayCan 的核心贡献是提出了"将语言理解锚定在机器人可用能力上"（grounding language in robotic affordances）的思想。LLM 提供任务理解（"我应该做什么"），每个机器人技能的价值函数提供可行性评估（"我能做什么"），两者相乘选出最优动作。

局限性：SayCan 是开环的——一旦选定动作序列就按序执行，如果某个技能执行失败（如物体不在预期位置），系统无法自主调整计划。此外，每个技能需要单独训练价值函数，扩展成本高。

**Inner Monologue（Google, CoRL 2022）— 闭环 + 多源反馈**

Inner Monologue 在 SayCan 的基础上引入了闭环反馈机制。系统在执行过程中持续将多种环境反馈注入 LLM 的规划 prompt 中，形成"内心独白"：

- 成功检测反馈："抓取动作失败，物体未被拾起"
- 场景描述反馈："当前场景中可见：桌子上有红色杯子和蓝色盘子"
- 人类交互反馈："用户说：不是那个，是旁边的杯子"

LLM 根据这些反馈动态调整后续计划，实现了机器人领域的 Agent Loop。实验表明，闭环反馈显著提高了长时任务的完成率。

**BrainBody-LLM（2024）— 分层闭环**

BrainBody-LLM 借鉴人类神经系统的分层结构，将规划分为"大脑"（高层 LLM 负责任务分解）和"身体"（低层 LLM 负责动作生成）两层，并通过仿真器反馈实现闭环纠错。当低层执行失败时，错误信息反馈给高层 LLM 进行重新规划。

**PaLM-E（Google, ICML 2023）— 端到端多模态**

PaLM-E 将视觉、语言和机器人状态统一编码到一个 562B 参数的多模态大模型中，实现了从感知到规划的端到端推理。虽然 PaLM-E 展示了强大的能力，但其巨大的模型规模使其难以在实际机器人系统中部署。

### 2.3 研究趋势总结

| 工作 | 年份 | 规划模式 | 反馈机制 | 工具调用方式 | 扩展成本 |
|------|------|---------|---------|------------|---------|
| SayCan | 2022 | 开环 | 无 | 技能价值函数评分 | 高（每技能需训练价值函数） |
| Inner Monologue | 2022 | 闭环 | 成功检测 + 场景描述 + 人类交互 | 技能价值函数评分 | 高 |
| ReAct | 2022 | 闭环 | 工具返回结果 | 文本格式解析 | 低（文本描述即可） |
| PaLM-E | 2023 | 闭环 | 视觉观察 | 端到端生成 | 极高（562B 模型微调） |
| BrainBody-LLM | 2024 | 分层闭环 | 仿真器错误反馈 | 分层 LLM 生成 | 中 |
| **Function Calling Agent** | **2023+** | **可开环/闭环** | **工具返回结果** | **原生结构化调用** | **极低（JSON schema）** |

可以看到，Function Calling 作为工具调用的底层机制，结合 Agent Loop 的闭环推理模式，在扩展成本上具有显著优势——新增能力只需定义 JSON schema 描述，无需训练价值函数或微调大模型。

---

## 三、本系统的技术路线定位（适用于：3.x 系统设计）

### 3.1 V1 架构：Function Calling + 开环规划

本系统 V1 阶段采用 OpenAI GPT Function Calling 作为核心调度机制，实现开环规划模式：

```
用户指令 → LLM (Function Calling) → 结构化任务序列 → 按序执行 → 返回结果
                    ↑                        ↓
              工具 schema 描述          ROS 2 Action 调用
              (actions.yaml)
```

选择 Function Calling 作为 V1 核心的理由：
1. 可靠性高：原生结构化输出，避免文本解析的脆弱性
2. 扩展成本极低：新增机器人能力只需在配置文件中添加工具描述
3. 工程复杂度可控：适合毕设周期内完成开发和验证
4. 与 ROS 2 Action 模型天然匹配：Function Calling 的"函数名 + 参数"模式与 ROS 2 Action 的"Goal 类型 + 参数"模式高度对应

### 3.2 V2 架构预留：Agent Loop + 闭环规划

V1 架构在任务执行模块中预留 Agent Loop 的扩展点，V2 阶段可升级为闭环规划模式：

```
用户指令 → Agent Loop 开始
              │
              ├→ LLM 推理 (Thought): "用户要找红色杯子，先去厨房看看"
              ├→ 工具调用 (Action): navigate_to(厨房)
              ├→ 环境反馈 (Observation): "已到达厨房，未发现红色杯子"
              │
              ├→ LLM 推理 (Thought): "厨房没有，去客厅找"
              ├→ 工具调用 (Action): navigate_to(客厅)
              ├→ 环境反馈 (Observation): "已到达客厅，发现红色杯子在茶几上"
              │
              ├→ LLM 推理 (Thought): "找到了，任务完成"
              └→ 最终回答: "红色杯子在客厅茶几上"
```

V1 → V2 的升级路径：
1. 在 TaskExecutor 中引入 Agent Loop 循环，替代当前的"一次解析、按序执行"模式
2. 将 ROS 2 Action 的执行结果（成功/失败/超时）和环境状态（机器人位置、传感器数据）格式化为 Observation 文本，回传给 LLM
3. LLM 根据 Observation 决定下一步动作：继续执行、调整计划、或报告完成
4. 设置最大循环次数和超时机制，防止无限循环

### 3.3 开环 vs 闭环的对比（本系统场景）

| 场景 | V1 开环（Function Calling） | V2 闭环（Agent Loop） |
|------|---------------------------|---------------------|
| "去厨房" | 直接导航，成功/失败 | 同左（简单任务无差异） |
| "找到红色杯子" | 查询语义地名映射，若无记录则报错 | 依次搜索各房间，根据反馈动态调整 |
| 导航失败 | 预定义重试逻辑（重试 N 次） | LLM 分析失败原因，决定重试/换路线/报告 |
| "打扫所有脏的房间" | 无法处理（需要运行时感知判断） | 逐房间检查，根据观察结果决定是否清扫 |

### 3.4 面向未来的协议兼容性

本系统的 Provider 插件机制和 ROS 2 通信适配层的设计，为未来接入新兴 Agent 协议标准预留了空间：

| 协议 | 发布方 | 时间 | 解决的问题 | 与本系统的关系 |
|------|--------|------|-----------|--------------|
| Function Calling | OpenAI | 2023.06 | LLM 如何调用工具 | V1 核心机制 |
| MCP | Anthropic | 2024.11 | 工具如何被发现和连接 | 未来可将 ROS 2 Action 注册为 MCP Server，实现跨模型的工具发现 |
| A2A | Google | 2025.04 | Agent 之间如何通信协作 | 未来多机器人场景下，各机器人的 Agent 可通过 A2A 协议协作 |
| Agents SDK | OpenAI | 2025.03 | Agent Loop 的工程化实现 | V2 阶段可参考其 Agent Loop 和 Handoffs 模式 |

---

## 四、关键参考文献

1. Yao, S., et al. "ReAct: Synergizing Reasoning and Acting in Language Models." *ICLR*, 2023.
2. Ahn, M., et al. "Do As I Can, Not As I Say: Grounding Language in Robotic Affordances." *CoRL*, 2022. (SayCan)
3. Huang, W., et al. "Inner Monologue: Embodied Reasoning through Planning with Language Models." *CoRL*, 2022.
4. Driess, D., et al. "PaLM-E: An Embodied Multimodal Language Model." *ICML*, 2023.
5. Dalal, M., et al. "Grounding LLMs For Robot Task Planning Using Closed-loop State Feedback." *arXiv:2402.08546*, 2024. (BrainBody-LLM)
6. OpenAI. "Function Calling and Other API Updates." 2023. https://openai.com/blog/function-calling-and-other-api-updates
7. OpenAI. "New Tools for Building Agents." 2025. https://openai.com/index/new-tools-for-building-agents/
8. Anthropic. "Introducing the Model Context Protocol." 2024. https://www.anthropic.com/news/model-context-protocol
9. Google. "Agent2Agent (A2A) Protocol." 2025. https://github.com/google/A2A
