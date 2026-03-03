# 论文素材：SubAgent 技术深度调研与 MOSAIC 系统适用性评估

> 本文档为毕业论文写作提供素材，涵盖 SubAgent/多智能体层级架构的技术现状、机器人领域的层级化任务分解研究、以及 MOSAIC 系统中 SubAgent 机制的设计定位与评估。可融入论文的"第二章 相关技术与研究现状"和"第三章 系统设计"。

---

## 一、SubAgent 概念界定与技术背景

### 1.1 什么是 SubAgent

SubAgent（子智能体）是多智能体系统中的一种层级化设计模式。在该模式下，一个高层 Agent（Orchestrator/Coordinator）负责全局规划和任务分解，将子任务委托给专门化的低层 Agent（SubAgent/Worker）执行。SubAgent 具备独立的推理能力、独立的上下文窗口和专属的工具集，但受高层 Agent 的调度和协调。

SubAgent 与普通工具调用的本质区别在于：工具是无状态的函数调用（输入→输出），而 SubAgent 内部拥有独立的 LLM 推理循环，能够根据执行过程中的观察自主调整策略。这使得 SubAgent 适合处理需要多步推理、环境感知和动态决策的复杂子任务。

### 1.2 SubAgent 的三种主流架构模式

2024-2025 年间，业界形成了三种主流的 SubAgent 架构模式：

**（1）Orchestrator-Worker 模式（编排者-工作者）**

最经典的层级模式。一个编排者 Agent 接收用户请求，分解为子任务，分配给专门化的 Worker Agent 执行，最后汇总结果。Anthropic 在 2025 年的多智能体研究系统中采用此模式——Lead Agent 分析查询、制定策略、生成专门化的 SubAgent，每个 SubAgent 在独立上下文窗口中并行工作，最终将发现汇总回 Lead Agent 进行综合。内部测试显示，该模式在复杂研究任务上的性能提升超过 90%，但 token 消耗是单 Agent 的 15 倍。

**（2）Handoff 模式（任务移交）**

OpenAI 在 2025 年 3 月发布的 Agents SDK 中提出的模式。与 Orchestrator-Worker 不同，Handoff 模式中 Agent 之间是对等关系——当一个 Agent 识别到当前任务更适合另一个专家 Agent 处理时，直接将控制权移交给对方，无需中央编排者中转。这种模式减少了延迟和 token 消耗，但缺乏全局协调能力。

**（3）Coordinator-Worker-SubAgent 三层模式**

2025 年出现的更精细的层级模式。Coordinator 负责全局规划，Worker 管理局部上下文和中间状态，SubAgent 执行细粒度任务。这种三层结构在大规模复杂任务中表现出更好的可扩展性和容错性。

### 1.3 行业实践现状（2025）

| 平台/框架 | SubAgent 模式 | 关键特性 | 发布时间 |
|---|---|---|---|
| OpenAI Agents SDK | Handoff | Agent 间对等移交，内置 Agent Loop | 2025.03 |
| Anthropic Claude Code | Orchestrator-Worker | 独立上下文窗口，并行 SubAgent | 2025.07 |
| AgentOrchestra (TEA 协议) | 层级编排 | 中央规划者 + 专门化 SubAgent，GAIA 基准 89.04% | 2025.06 |
| Claude Haiku 4.5 | SubAgent 优化 | 专为 SubAgent 编排优化的轻量模型 | 2025.10 |
| MiTa 框架 | Manager-Member 层级 | 全局任务分配 + 情景记忆集成 | 2025.01 |

---

## 二、机器人领域的 SubAgent 与层级化任务分解研究

### 2.1 从单 Agent 到层级 Agent 的演进

机器人任务规划领域的 SubAgent 思想可追溯到层级任务网络（HTN）和层级强化学习（HRL）。LLM 的引入使得层级分解从"预定义子任务模板"演进为"LLM 动态推理分解"。

**BrainBody-LLM（2024）**：最早将"大脑-身体"分层隐喻引入 LLM 机器人规划。高层 LLM（Brain）负责任务分解和策略制定，低层 LLM（Body）负责将子目标转化为具体动作序列。两层之间通过仿真器反馈实现闭环纠错。这本质上是一种双层 SubAgent 架构——Body LLM 作为 Brain LLM 的 SubAgent 执行具体操作。

**SMART-LLM（2023）**：面向多机器人的任务规划框架，LLM 将高层指令分解为子任务，再通过联盟形成（coalition formation）将子任务分配给不同机器人。每个机器人可视为一个执行特定子任务的 SubAgent。在仿真和真实环境中验证了 LLM 驱动的多机器人任务分解的可行性。

### 2.2 层级化 Agent Tree：ReAcTree（2025）

ReAcTree 是将 SubAgent 思想与 ReAct 框架结合的代表性工作。针对长时域复杂任务，ReAcTree 将单一 ReAct 轨迹扩展为动态构建的 Agent 树结构：

- 根节点 Agent 接收复杂目标，将其分解为可管理的子目标
- 每个子目标由一个独立的 Agent 节点处理，该节点具备推理、行动和进一步展开子树的能力
- 控制流节点（顺序/条件/循环）协调 Agent 节点的执行策略
- 集成双重记忆系统：每个 Agent 节点从情景记忆中检索目标相关的示例，通过工作记忆共享环境观察

实验结果：在 WAH-NL 基准上，ReAcTree 使用 Qwen 2.5 72B 达到 61% 的目标成功率，几乎是 ReAct 基线（31%）的两倍。这证明了层级化 SubAgent 分解在长时域任务中的显著优势。

ReAcTree 的记忆系统设计与 MOSAIC 系统的 ARIA 三层记忆架构高度契合——情景记忆对应 ARIA 的 EpisodicMemory，工作记忆对应 ARIA 的 WorkingMemory。

### 2.3 H-AIM：LLM + PDDL + 行为树的层级多机器人规划（2026）

H-AIM（Hierarchical Autonomous Intelligent Multi-Robot Planning）提出了三阶段级联架构：

1. LLM 解析自然语言指令 → 生成 PDDL 问题描述（形式化）
2. LLM 语义推理 + 经典规划器搜索 → 生成优化动作序列
3. 动作序列编译为行为树 → 反应式控制执行

该框架通过共享黑板机制支持动态规模的异构机器人团队。在 MACE-THOR 基准（42 个复杂任务，8 种家庭布局）上，H-AIM 将任务成功率从 12% 提升至 55%，目标条件召回率从 32% 提升至 72%。

H-AIM 的启示：LLM 擅长语义理解和初步分解，但长时域推理和多机器人协调仍需形式化方法（PDDL）和反应式控制（行为树）的辅助。纯 LLM 规划在复杂场景下的可靠性不足，层级化分解 + 形式化验证是提升鲁棒性的关键。

### 2.4 EmbodiedAgent：面向幻觉问题的层级框架（2025）

EmbodiedAgent 针对 LLM 在机器人规划中的幻觉问题（生成不可执行的动作），提出了层级化框架：

- 集成下一动作预测范式与结构化记忆系统
- 将任务分解为可执行的机器人技能，同时动态验证动作是否符合环境约束
- 提出 MultiPlan+ 数据集（18000+ 标注规划实例，含不可行案例子集）
- 在真实办公环境中验证了异构机器人长时域任务的协调能力
- RPAS 评分达到 71.85%，优于当时的 SOTA 模型

### 2.5 CoMuRoS：事件驱动重规划的层级架构（2025）

CoMuRoS（Collaborative Multi-Robot System）提出了统一集中式审议与分散式执行的层级架构，支持事件驱动的重规划。这与 MOSAIC 系统的"TaskPlanner 集中规划 + Capability 分散执行 + FeedbackEvent 驱动重规划"模式高度一致。

### 2.6 MITD：可解释的层级任务分解（2025）

MITD（Mechanistically Interpretable Task Decomposition）提出了 Planner-Coordinator-Executor 三模块层级 Transformer 架构，用于检测和缓解具身 AI 中的奖励黑客问题。其三层分解思想（规划→协调→执行）与 MOSAIC 的 TaskPlanner→TaskExecutor→Capability 三层架构形成对照。

---

## 三、SubAgent 在机器人系统中的典型应用场景

### 3.1 物体搜索（Object Search）

物体搜索是机器人领域最典型的 SubAgent 应用场景。当用户说"找到红色杯子"时，系统需要：

1. 推理目标物体最可能的位置（基于场景图语义知识）
2. 规划搜索路径（优先搜索高概率区域）
3. 导航到候选位置
4. 视觉确认目标是否存在
5. 若未找到，根据观察结果调整搜索策略
6. 重复 2-5 直到找到或穷尽候选

这个过程需要 LLM 推理（步骤 1、5）+ 导航执行（步骤 3）+ 视觉感知（步骤 4）的交织循环，是典型的 SubAgent 行为——内部拥有独立的 Agent Loop，而非简单的工具调用。

### 3.2 智能抓取（Smart Grasp）

当目标物体的抓取条件不满足时（如物体被遮挡、容器关闭），SubAgent 需要推理前置条件并自主规划解决方案：

1. 检测目标物体状态（被遮挡/容器关闭/位置不可达）
2. LLM 推理需要的前置操作（移开遮挡物/打开容器/调整机器人位置）
3. 执行前置操作
4. 重新评估抓取条件
5. 执行抓取

### 3.3 多步操作任务

"准备一杯咖啡"这类任务需要 SubAgent 在执行过程中持续感知和推理：找到咖啡机→检查水量→放入咖啡胶囊→放置杯子→启动→等待完成→取出。每一步都可能需要根据实际观察调整策略。

---

## 四、MOSAIC 系统的 SubAgent 设计评估

### 4.1 MOSAIC 现有 SubAgent 设计回顾

MOSAIC 系统在设计阶段已预留了 SubAgent 机制。Capability 接口中定义了 `is_sub_agent()` 方法，将 Capability 分为四类：纯执行、感知、协作、SubAgent。SubAgent Capability 的核心特征是 `execute()` 内部会调用 ModelProvider 进行 LLM 推理，然后基于推理结果调用底层执行。

当前设计中的 SubAgent 示例：
- **ObjectSearchCapability**（搜索模块）：内部调用 LLM 推理目标位置 → 调用 NavigationCapability 前往 → VLM 确认
- **SmartGrasp**（预留）：内部调用 LLM 推理抓取策略 → 调用视觉+操作模块执行

### 4.2 评估：MOSAIC 是否需要更深层的 SubAgent 优化

**结论：MOSAIC 当前的 SubAgent 设计已经合理且充分，不需要引入更复杂的多 Agent 编排框架，但可以在论文中明确其设计定位和理论依据。**

评估依据如下：

**（1）MOSAIC 的 SubAgent 是"能力级"而非"系统级"**

业界的 SubAgent 架构（如 Anthropic 的 Orchestrator-Worker、OpenAI 的 Handoff）面向的是通用软件任务——多个 Agent 处理不同领域的子任务（如一个 Agent 写代码、一个 Agent 搜索文档、一个 Agent 做数据分析）。这些 Agent 之间的任务边界模糊，需要复杂的协调机制。

MOSAIC 的场景不同：机器人的能力边界是清晰的（导航、操作、视觉、搜索），每个 CapabilityModule 的职责明确。SubAgent 只在特定 Capability 内部使用 LLM 推理来增强执行智能，而非在系统层面引入多个对等 Agent。这种"能力级 SubAgent"设计更轻量、更可控。

**（2）TaskPlanner 已承担了"Orchestrator"角色**

MOSAIC 的 TaskPlanner 本质上就是一个 Orchestrator——它接收用户指令，通过 LLM 进行任务分解和规划，将子任务分配给不同的 Capability 执行，并在执行失败时触发重规划。这与 Orchestrator-Worker 模式的核心逻辑一致，只是 Worker 层是 Capability 而非独立 Agent。

引入额外的系统级 SubAgent 编排层会导致：
- 架构复杂度显著增加（双层 LLM 调用链路）
- 延迟增加（SubAgent 内部的 LLM 推理 + 外部 TaskPlanner 的 LLM 推理）
- token 消耗倍增（Anthropic 数据：15 倍）
- 对于单机器人系统，收益有限

**（3）SubAgent Capability 的设计已覆盖关键场景**

物体搜索（ObjectSearch）是单机器人场景中最需要 SubAgent 的任务类型。MOSAIC 已将其设计为 SubAgent Capability，内部拥有独立的 LLM 推理循环。其他需要 SubAgent 的场景（智能抓取、多步操作）也可以按相同模式扩展，无需改变系统架构。

**（4）未来多机器人场景的扩展路径清晰**

当 MOSAIC 扩展到多机器人场景时，可以参考 SMART-LLM 和 CoMuRoS 的思路，在 TaskPlanner 层面引入多机器人任务分配逻辑，每个机器人作为一个执行单元（类似 Worker）。这种扩展不需要重构现有的 SubAgent Capability 设计。

### 4.3 MOSAIC SubAgent 设计与前沿研究的对照

| 维度 | MOSAIC 现有设计 | ReAcTree | H-AIM | EmbodiedAgent |
|---|---|---|---|---|
| 层级结构 | TaskPlanner → TaskExecutor → Capability（含 SubAgent） | 动态 Agent 树（多层） | LLM → PDDL → 行为树（三阶段） | 层级框架 + 结构化记忆 |
| SubAgent 粒度 | 能力级（Capability 内部） | 子目标级（每个子目标一个 Agent） | 机器人级（每个机器人一个执行者） | 技能级（可执行技能） |
| LLM 推理位置 | TaskPlanner + SubAgent Capability | 每个 Agent 节点 | 第一阶段（解析）+ 第二阶段（规划） | 高层分解 + 低层验证 |
| 记忆系统 | ARIA 三层记忆 | 情景记忆 + 工作记忆 | 无显式记忆 | 结构化记忆 |
| 重规划机制 | FeedbackEvent → LLM 重规划 | Agent 节点自主调整 | 行为树反应式控制 | 动态验证 + 调整 |
| 形式化验证 | SceneGraphValidator | 无 | PDDL 规划器 | 环境约束验证 |
| 适用规模 | 单机器人（可扩展多机器人） | 单 Agent 复杂任务 | 异构多机器人 | 异构多机器人 |

### 4.4 MOSAIC SubAgent 设计的理论定位

MOSAIC 的 SubAgent 设计可以定位为 **"能力内嵌式 SubAgent"（Capability-Embedded SubAgent）** 模式：

- SubAgent 不是独立的系统级实体，而是嵌入在特定 Capability 内部的 LLM 推理循环
- 对外保持标准 Capability 接口，TaskExecutor 无需区分纯执行和 SubAgent
- 内部通过 ModelProvider + WorldStateManager（只读）实现自主推理
- 通过依赖注入保持依赖倒置，Agent 核心不感知 Capability 内部是否使用了 LLM

这种设计的优势：
1. 最小化架构复杂度——不引入额外的 Agent 编排层
2. 保持接口一致性——SubAgent 对外行为与纯执行 Capability 一致
3. 可控的 LLM 调用——SubAgent 的 LLM 推理范围被限定在特定能力域内
4. 渐进式扩展——新增 SubAgent 只需实现新的 Capability，不影响现有架构

---

## 五、SubAgent 技术的开放问题与发展趋势

### 5.1 开放问题

**（1）token 消耗与延迟**：多层 LLM 调用导致 token 消耗和延迟倍增。Anthropic 数据显示 SubAgent 模式的 token 消耗是单 Agent 的 15 倍。对于实时性要求高的机器人系统，这是关键瓶颈。

**（2）SubAgent 间的状态一致性**：多个 SubAgent 并行执行时，如何保证它们对环境状态的认知一致？MOSAIC 通过 ARIA 的集中式状态管理（WorldStateManager）解决此问题，但分布式多机器人场景下仍是挑战。

**（3）错误传播与恢复**：SubAgent 内部的 LLM 推理错误如何向上传播？SubAgent 失败时，高层 Agent 如何决定重试、替代方案还是放弃？MOSAIC 通过 FeedbackEvent 机制和 TaskPlanner 的 LLM 重规划来处理。

**（4）可解释性**：SubAgent 的多层推理链路使得决策过程更难追踪和解释。MITD 的可解释性分解思想值得借鉴。

### 5.2 发展趋势

**（1）轻量化 SubAgent 模型**：Anthropic 的 Claude Haiku 4.5 专为 SubAgent 编排优化，体现了"大模型做编排、小模型做执行"的趋势。MOSAIC 未来可以为 SubAgent Capability 配置更轻量的 LLM（如本地部署的小模型），降低延迟和成本。

**（2）协议标准化**：MCP（工具发现）、A2A（Agent 间通信）、TEA（工具-环境-Agent 统一抽象）等协议的出现，正在推动 SubAgent 交互的标准化。MOSAIC 的 Capability 接口设计与这些协议的理念一致。

**（3）记忆增强的 SubAgent**：ReAcTree 的双重记忆系统、MiTa 的情景记忆集成，表明记忆机制是提升 SubAgent 效果的关键。MOSAIC 的 ARIA 三层记忆架构为 SubAgent 提供了天然的记忆基础设施。

**（4）形式化验证 + LLM 推理的融合**：H-AIM 证明了 LLM + PDDL + 行为树的组合优于纯 LLM 规划。MOSAIC 的 SceneGraphValidator 承担了类似的形式化验证角色，确保 LLM 生成的计划在场景图约束下可执行。

---

## 六、关键参考文献

1. ReAcTree: Hierarchical LLM Agent Trees with Control Flow for Long-Horizon Task Planning. arXiv:2511.02424, 2025.
2. AgentOrchestra: Orchestrating Multi-Agent Intelligence with the TEA Protocol. arXiv:2506.12508, 2025.
3. H-AIM: Orchestrating LLMs, PDDL, and Behavior Trees for Hierarchical Multi-Robot Planning. arXiv:2601.11063, 2026.
4. EmbodiedAgent: A Scalable Hierarchical Approach to Overcome Practical Challenge in Multi-Robot Control. arXiv:2504.10030, 2025.
5. SMART-LLM: Smart Multi-Agent Robot Task Planning using Large Language Models. arXiv:2309.10062, 2023.
6. CoMuRoS: LLM-Based Generalizable Hierarchical Task Planning and Execution for Heterogeneous Robot Teams with Event-Driven Replanning. arXiv:2511.22354, 2025.
7. MITD: Mechanistically Interpretable Task Decomposition for Detecting and Mitigating Reward Hacking in Embodied AI Systems. arXiv:2511.17869, 2025.
8. MiTa: A Hierarchical Multi-Agent Collaboration Framework with Memory-integrated and Task allocation. arXiv:2601.22974, 2025.
9. BrainBody-LLM: Grounding LLMs For Robot Task Planning Using Closed-loop State Feedback. arXiv:2402.08546, 2024.
10. OpenAI. "New Tools for Building Agents." 2025. https://openai.com/index/new-tools-for-building-agents/
11. Anthropic. "Building Production Multi-Agent Research Systems with Claude." 2025.
12. HTAM: Designing Domain-Specific Agents via Hierarchical Task Abstraction Mechanism. arXiv:2511.17198, 2025.
13. HCRL: Hierarchical in-Context Reinforcement Learning with Hindsight Modular Reflections for Planning. arXiv:2408.06520, 2024.
