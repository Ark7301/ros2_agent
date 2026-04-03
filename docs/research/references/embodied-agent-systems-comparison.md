- title: Embodied Agent Systems Comparison
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, references, embodied-agent
- source_type: note

# 论文素材：EmbodiedAgent 技术方案深度分析与 MOSAIC 系统对比

> 本文档深度剖析 EmbodiedAgent（arXiv:2504.10030, 2025）的技术方案，并与 MOSAIC 系统及同期相关工作进行系统性对比。可融入论文的"第二章 相关技术与研究现状"和"第三章 系统设计"中的技术路线论证部分。

---

## 一、EmbodiedAgent 论文概述

### 1.1 研究问题

EmbodiedAgent 聚焦于异构多机器人系统的任务规划问题，核心挑战是 LLM 在机器人规划中的**幻觉问题（Hallucination）**——当任务在物理上不可行时（如环境中不存在所需物体、机器人缺乏所需技能），LLM 仍会生成看似合理但实际不可执行的规划序列。

论文将不可行场景归纳为四类错误信号：
- **LoA（Lack of Ability）**：多机器人系统缺乏完成任务所需的基本能力（如缺少具有移动或操作能力的机器人类型）
- **LoS（Lack of Skill）**：完成任务所需的机器人技能未在配置中注册
- **LoL（Load Over Limit）**：任务要求操作的物体超出机器人负载能力
- **LoO（Lack of Object）**：任务执行所需的物体在环境中不存在或不可用

### 1.2 核心贡献

1. 提出 EmbodiedAgent 层级框架，采用**下一动作预测（Next-Action Prediction, NAP）**范式
2. 构建 MultiPlan+ 数据集（18000+ 标注规划实例，100 个场景，含不可行案例子集）
3. 提出 RPAS（Robot Planning Assessment Schema）评估框架
4. 真实环境验证（机械臂 + 四足机器人协作办公服务任务）

---

## 二、EmbodiedAgent 技术架构深度剖析

### 2.1 系统架构：双层层级控制

EmbodiedAgent 采用经典的双层层级架构：

```
用户自然语言指令
        │
        ▼
┌─────────────────────────────────────────┐
│  高层规划器（High-Level Planner）         │
│  ├─ LLM 推理引擎（微调后的 Llama-3.1-8B）│
│  ├─ 工具库（Tool Library）               │
│  │   ├─ 机器人技能函数                    │
│  │   ├─ 终止信号函数（endPlanning）       │
│  │   └─ 错误信号函数（LoA/LoS/LoL/LoO）  │
│  └─ 结构化记忆（Planning Memory）         │
│      └─ 历史动作序列 P_t                  │
└──────────────┬──────────────────────────┘
               │ 执行缓冲区 + 任务分发器
               ▼
┌─────────────────────────────────────────┐
│  低层执行模块（Low-Level Execution）      │
│  ├─ 机械臂：ACT 策略（模仿学习）         │
│  ├─ 四足机器人：SDK 内置运动能力          │
│  └─ 其他机器人：专用策略/SDK              │
└─────────────────────────────────────────┘
```

### 2.2 核心机制：下一动作预测（NAP）

EmbodiedAgent 的规划范式不同于传统的"一次性生成完整动作序列"（Full Planning Sequence, FPS），而是采用**逐步预测**模式：

```
规划状态 s_t = {M（任务描述）, E（环境配置）, P_t（规划记忆）}
        │
        ▼
LLM 推理 π(P_t | M, E) → p_{t+1}
        │
        ├─ 若 p_{t+1} = 机器人技能 a → 执行 → 更新环境 → 继续循环
        ├─ 若 p_{t+1} = ε_end（终止信号）→ 任务完成
        └─ 若 p_{t+1} ∈ {ε_LoA, ε_LoO, ε_LoS, ε_LoL} → 报告不可行 → 终止
```

NAP 的关键设计决策：
- 每次推理只生成一个动作及其参数，而非完整序列
- 规划记忆 P_t 随执行动态更新，为后续决策提供上下文
- 终止信号和错误信号被封装为可调用的"工具函数"，与技能函数同等对待
- 通过监督微调（SFT）训练 LLM 学习何时调用错误信号

### 2.3 反幻觉机制：监督微调 + 错误信号工具化

EmbodiedAgent 解决幻觉问题的核心策略是**数据驱动的监督微调**：

1. 在 MultiPlan+ 数据集中显式包含不可行案例（impractical cases）
2. 将四类错误信号（LoA/LoS/LoL/LoO）封装为 Function Calling 工具
3. 通过 SFT 训练 LLM 学习在遇到不可行场景时主动调用错误信号函数，而非生成幻觉规划
4. 微调基座：Llama-3.1-8B-Instruct，8×A100 GPU，3 个 epoch，约 8 小时

### 2.4 评估框架：RPAS

RPAS 综合三个维度评估规划质量：

| 维度 | 方法 | 说明 |
|---|---|---|
| ASR_top-k | 自动化指标 | 预测序列前 k 步与参考序列的匹配率 |
| Expert Grading | LLM 辅助评分 | LLM 评估规划的逻辑一致性、可行性、效率、鲁棒性（0-100 分） |
| MRED | 错误诊断 | 分类诊断规划错误（UE/PoE/PlE/SE/EE 五类） |

### 2.5 实验结果

在 32 个未见测试任务上的表现：

| 模型 | ASR_top-k | RPAS |
|---|---|---|
| GPT-4o | — | 低于 EmbodiedAgent |
| OpenAI-o1 | — | 低于 EmbodiedAgent |
| LLaMA-3.1-70B | — | 低于微调 7B 模型 |
| MAP-Neo-7B-Multiplan（微调） | 竞争力强 | 显著优于 70B 未微调模型 |
| **EmbodiedAgent（微调 8B）** | **74.01%** | **71.85%** |

关键发现：经过领域自适应微调的 7-8B 参数模型显著优于未微调的 70B+ 大模型，证明了**领域特定微调优于朴素参数扩展**。

---

## 三、EmbodiedAgent 与 MOSAIC 系统的深度技术对比

### 3.1 架构哲学对比

两个系统虽然都面向 LLM 驱动的机器人任务规划，但在架构哲学上存在根本性差异：

| 维度 | EmbodiedAgent | MOSAIC |
|---|---|---|
| 核心定位 | 异构多机器人任务分配与规划 | 单机器人 AI Agent 任务调度框架 |
| LLM 使用方式 | 微调小模型（领域特化） | 调用通用大模型 API（零样本/少样本） |
| 规划范式 | 下一动作预测（NAP，逐步生成） | LLM 一次性生成执行计划 + 闭环重规划 |
| 环境表征 | JSON 描述（位置索引 + 物体列表） | 3D 场景图 + ARIA 三层记忆 + EmbodiedRAG 检索 |
| 反幻觉策略 | 监督微调 + 错误信号工具化 | SceneGraphValidator 形式化验证 + LLM 迭代修正 |
| 执行反馈 | 环境状态更新 → 下一步预测 | FeedbackEvent → 场景图更新 → LLM 重规划 |
| 低层执行 | 专用策略（ACT 模仿学习 / SDK） | ROS 2 CapabilityModule（Nav2 / MoveIt 2） |
| 机器人平台 | 异构团队（机械臂 + 四足等） | 单机器人（人形/移动操作臂） |
| 开放性 | 技能集固定（微调时确定） | 能力动态注册/注销（运行时插拔） |

### 3.2 规划范式对比：NAP vs LLM-centric 闭环规划

**EmbodiedAgent 的 NAP 模式**：

```
s_0 → LLM → a_1 → 执行 → s_1 → LLM → a_2 → 执行 → s_2 → ... → ε_end
```

优势：
- 每步决策基于最新环境状态，天然具备闭环特性
- 错误可在单步级别被检测和中断
- 微调后的小模型推理速度快

局限：
- 每步都需要一次完整的 LLM 推理，总推理次数 = 动作步数
- 缺乏全局规划视野——LLM 在生成 a_3 时不知道后续还需要 a_4、a_5
- 无法进行计划级别的验证（只能验证单步合法性）
- 微调绑定了特定技能集，新增技能需要重新微调

**MOSAIC 的 LLM-centric 闭环规划模式**：

```
TaskResult → retrieve_context() → LLM 生成完整 ExecutionPlan
    → SceneGraphValidator 验证 → 通过则执行
    → 执行中 FeedbackEvent → 场景图更新 → LLM 评估 → 必要时重规划
```

优势：
- LLM 具备全局规划视野，可以考虑动作间的依赖和顺序
- SceneGraphValidator 在执行前验证整个计划的可行性
- EmbodiedRAG 检索提供精简但充分的环境上下文
- 新增能力只需注册 Capability，无需重新训练模型
- 情景记忆提供历史经验辅助规划

局限：
- 依赖外部 LLM API，延迟和成本较高
- 全量计划生成的 token 消耗大于单步预测
- 重规划时需要重新生成完整计划

### 3.3 反幻觉策略对比：微调 vs 场景图验证

这是两个系统最核心的技术路线分歧。

**EmbodiedAgent 的策略：数据驱动微调**

- 在训练数据中显式包含不可行案例
- LLM 通过监督学习"记住"何时应该报告错误
- 错误检测能力来自训练数据的覆盖度
- 对训练分布外的新型不可行场景泛化能力有限

**MOSAIC 的策略：场景图 Grounding + 形式化验证**

- SceneGraphValidator 在执行前检查计划中引用的对象/位置是否存在于场景图中
- 空间拓扑约束验证（不能跳过房间直接到达）
- 物体状态约束验证（冰箱关着时不能放东西进去）
- 验证不通过时，将错误信息反馈给 LLM 重新生成

**对比分析**：

| 维度 | EmbodiedAgent（微调） | MOSAIC（场景图验证） |
|---|---|---|
| 错误检测方式 | 隐式（模型内部学习） | 显式（规则化验证） |
| 可解释性 | 低（黑盒决策） | 高（明确的验证错误信息） |
| 泛化能力 | 受限于训练分布 | 不受限（基于实际环境状态） |
| 新环境适应 | 需要新数据微调 | 自动适应（场景图动态更新） |
| 错误类型覆盖 | 四类预定义（LoA/LoS/LoL/LoO） | 开放式（任何场景图约束违反） |
| 实现成本 | 高（需要标注数据 + GPU 微调） | 中（需要场景图构建 + 验证器） |
| 运行时开销 | 低（微调模型直接输出） | 中（验证器额外计算） |

MOSAIC 的场景图验证方案在泛化性和可解释性上具有显著优势。EmbodiedAgent 的四类错误信号是预定义的，无法覆盖所有可能的不可行场景（如"目标物体被另一个物体遮挡"、"路径被临时障碍物阻塞"等动态约束）。而 MOSAIC 的 SceneGraphValidator 基于实际环境状态进行验证，天然覆盖所有可观测的约束违反。

### 3.4 环境表征对比：JSON 描述 vs 3D 场景图 + EmbodiedRAG

**EmbodiedAgent 的环境表征**：

```json
{
  "workspace": {"positions": [{"id": "p1", "name": "桌子旁", "x": 1.0, "y": 2.0}]},
  "robots": [{"name": "arm_1", "type": "robotic_arm", "skills": ["pick", "place"]}],
  "objects": [{"name": "cup", "position": "p1", "weight": 0.3}],
  "users": [{"name": "user_1", "position": "p2"}]
}
```

- 扁平化结构，无层级关系
- 位置用索引点表示，无空间拓扑
- 物体间无关系描述（on/in/near）
- 全量输入 LLM，无检索压缩

**MOSAIC 的环境表征**：

```
3D 场景图（层级化）：
  Building → Floor → Room → Object
  边关系：contains / on / in / near / connected_to
  节点属性：位置、语义标签、状态、affordance

+ ARIA 三层记忆：
  工作记忆（实时状态）+ 语义记忆（场景图+向量索引）+ 情景记忆（执行历史）

+ EmbodiedRAG 检索：
  任务驱动的子图检索 → 精简上下文（token 降低 90%）
```

**对比分析**：

| 维度 | EmbodiedAgent（JSON） | MOSAIC（3D 场景图 + EmbodiedRAG） |
|---|---|---|
| 空间关系 | 无（仅位置索引） | 丰富（contains/on/in/near/connected_to） |
| 层级结构 | 无 | Building → Floor → Room → Object |
| 可扩展性 | 差（全量输入，环境增大则 token 爆炸） | 好（EmbodiedRAG 检索，O(log n) 复杂度） |
| 动态更新 | 执行后更新 JSON | 实时增量更新场景图 + 向量索引 |
| 历史经验 | 仅当前任务的规划记忆 | 情景记忆跨任务积累经验 |
| 常识推理支持 | 弱（缺乏空间关系） | 强（场景图提供丰富的 grounding 信息） |

MOSAIC 的环境表征方案在大规模环境下具有决定性优势。EmbodiedAgent 的 JSON 描述在小规模场景（如单个办公室）下足够，但当环境扩展到多楼层建筑时，全量 JSON 输入会超出 LLM 上下文窗口。MOSAIC 的 EmbodiedRAG 检索机制（参考 arXiv:2410.23968）通过任务驱动的子图检索解决了这一可扩展性问题。

### 3.5 能力扩展性对比

| 维度 | EmbodiedAgent | MOSAIC |
|---|---|---|
| 新增机器人技能 | 需要在 MultiPlan+ 中添加新技能数据 → 重新微调模型 | 实现 Capability 接口 → 注册到 Registry → LLM 自动发现 |
| 新增机器人类型 | 需要新数据 + 重新微调 | 实现 CapabilityModule → 注册 → 零修改核心 |
| 新增场景 | 需要新场景数据 + 重新微调 | 场景图自动构建（SLAM + VLM） |
| 运行时动态调整 | 不支持（技能集在微调时固定） | 支持（Capability 运行时加载/卸载） |
| 跨平台迁移 | 需要针对新平台重新收集数据 | ROS 2 标准接口，天然跨平台 |

MOSAIC 的依赖倒置 + 动态注册设计使其在能力扩展性上具有显著优势。EmbodiedAgent 的微调方案虽然在特定领域内表现优异，但每次扩展都需要数据收集和模型重训练的成本。

---

## 四、与同期相关工作的横向对比

### 4.1 多系统对比矩阵

| 维度 | EmbodiedAgent | MOSAIC | H-AIM | EMOS | VeriGraph |
|---|---|---|---|---|---|
| 发表时间 | 2025.04 | 2025-2026 | 2026.01 | 2024.10 (ICLR 2025) | 2024.11 |
| 核心问题 | 多机器人幻觉规划 | 单机器人 Agent 调度 | 多机器人长时域规划 | 异构多机器人协作 | VLM 规划验证 |
| LLM 使用 | 微调 8B | API 调用通用大模型 | API + PDDL 规划器 | 多 Agent（每机器人一个） | VLM + LLM |
| 规划范式 | NAP（逐步预测） | 完整计划 + 闭环重规划 | LLM→PDDL→行为树 | 多 Agent 协商 | LLM 生成 + 场景图验证 |
| 环境表征 | JSON 描述 | 3D 场景图 + EmbodiedRAG | PDDL Domain | Robot Resume（URDF） | 场景图（VLM 生成） |
| 反幻觉 | 微调学习错误信号 | SceneGraphValidator | PDDL 形式化验证 | 物理能力约束 | 场景图约束检查 |
| 记忆系统 | 短期规划记忆 | ARIA 三层记忆 | 无 | 无 | 无 |
| 评估基准 | MultiPlan+（18000+） | 自定义验证 | MACE-THOR（42 任务） | Habitat-MAS | 操作场景 |
| 真实部署 | 办公服务（臂+狗） | ROS 2 仿真+真实 | AI2-THOR 仿真 | Habitat 仿真 | 桌面操作 |
| 最佳 RPAS/SR | 71.85% | — | 55% SR | — | +58% 提升 |

### 4.2 关键技术路线分析

**路线一：微调特化（EmbodiedAgent 代表）**

核心思路：用领域特定数据微调小模型，使其"记住"正确的规划模式和错误检测能力。

优势：推理速度快、可本地部署、特定领域内精度高
劣势：泛化性差、扩展成本高、需要持续的数据收集和重训练

**路线二：场景图 Grounding + 通用 LLM（MOSAIC / VeriGraph 代表）**

核心思路：用结构化的环境表征（场景图）为通用 LLM 提供 grounding，通过形式化验证确保规划可行性。

优势：泛化性强、可解释性高、新环境零样本适应
劣势：依赖外部 API、场景图构建成本、验证器设计复杂度

**路线三：形式化规划 + LLM 辅助（H-AIM 代表）**

核心思路：LLM 负责语义理解和初步分解，PDDL 等形式化方法负责精确规划和验证。

优势：规划正确性有形式化保证、可处理复杂约束
劣势：PDDL Domain 定义成本高、灵活性受限于预定义的 action schema

**路线四：具身感知自适应（EMOS 代表）**

核心思路：每个机器人 Agent 通过理解自身 URDF 文件自动生成"能力简历"，基于物理能力约束进行规划。

优势：自动适应不同机器人硬件、无需人工定义能力描述
劣势：URDF 理解的准确性有限、缺乏环境级别的 grounding

### 4.3 MOSAIC 的技术路线定位

MOSAIC 采用的是**路线二（场景图 Grounding + 通用 LLM）**，并融合了路线三的形式化验证思想（SceneGraphValidator）。这一选择的理由：

1. **面向 ROS 2 生态的通用性需求**：MOSAIC 定位为 ROS 2 生态的通用任务调度中间层，不能绑定特定的微调模型或特定的机器人平台。通用 LLM API + 动态能力注册是实现通用性的必要条件。

2. **场景图提供的 grounding 质量优于 JSON 描述**：3D 场景图的层级结构和丰富的空间关系为 LLM 提供了更高质量的环境 grounding，使得通用 LLM 无需微调即可进行高质量规划。

3. **EmbodiedRAG 解决了可扩展性瓶颈**：EmbodiedAgent 的 JSON 全量输入方案在大规模环境下不可行，而 MOSAIC 的 EmbodiedRAG 检索机制将 token 消耗降低 90%，使系统可扩展到多楼层建筑级别。

4. **SceneGraphValidator 提供了比微调更可靠的反幻觉保证**：微调方案的错误检测能力受限于训练数据分布，而场景图验证基于实际环境状态，对任何可观测的约束违反都能检测。

---

## 五、EmbodiedAgent 的局限性分析（论文可引用的批判性讨论）

### 5.1 环境表征的局限

EmbodiedAgent 使用扁平化 JSON 描述环境，缺乏空间拓扑和物体间关系。这导致：
- LLM 无法推理"杯子在桌子上"、"桌子在厨房里"等层级空间关系
- 无法进行路径可达性推理（如"从 A 房间到 B 房间需要经过走廊"）
- 环境规模增大时，JSON 描述的 token 数量线性增长，无压缩机制

相比之下，SayPlan（CoRL 2023）和 EmbodiedRAG（2024）已证明 3D 场景图 + 向量检索是更优的环境表征方案。

### 5.2 微调方案的泛化性瓶颈

EmbodiedAgent 的核心竞争力来自 MultiPlan+ 数据集上的监督微调。但这也是其最大的局限：

- **技能集固化**：微调时确定的技能集在推理时无法动态扩展。若机器人新增了一个"扫地"技能，需要收集包含该技能的新数据并重新微调。
- **场景分布偏移**：MultiPlan+ 覆盖 100 个场景，但真实部署环境可能与训练分布存在显著差异。论文未报告跨分布泛化性能。
- **错误类型固化**：四类错误信号（LoA/LoS/LoL/LoO）是预定义的，无法覆盖动态环境中的新型不可行场景（如临时障碍物、设备故障、电量不足等）。

### 5.3 缺乏长时记忆与经验积累

EmbodiedAgent 的规划记忆 P_t 仅维护当前任务的历史动作序列，不具备跨任务的经验积累能力。这意味着：
- 系统无法从历史执行中学习（如"上次在厨房找杯子时，杯子在水槽旁"）
- 重复遇到相似任务时，无法利用先前经验加速规划
- 缺乏 ReMEmbR（NVIDIA, 2024）提出的长时时空语义记忆能力

MOSAIC 的 ARIA 情景记忆（EpisodicMemory）通过向量化存储历史执行经历并在规划时召回相似经验，解决了这一问题。

### 5.4 评估框架的局限

RPAS 评估框架存在以下不足：
- **测试集规模小**：仅 32 个未见任务（其中 2 个不可行案例），统计显著性存疑
- **ASR_top-k 的局限**：仅比较前 k 步是否匹配参考序列，但合理的规划可能有多种等价方案
- **LLM 评分的可靠性**：Expert Grading 使用 LLM 而非人类专家评分，LLM 评分的一致性和准确性未充分验证
- **缺乏执行级评估**：RPAS 仅评估规划质量，未评估实际执行成功率

### 5.5 真实部署的有限性

论文的真实部署实验仅涉及一个办公服务场景（机械臂擦桌子 + 四足机器人送纸巾），任务复杂度有限。未验证：
- 大规模环境下的规划性能
- 动态环境中的鲁棒性（如人员走动、物体被移动）
- 长时间连续运行的稳定性
- 多于两个机器人的协调能力

---

## 六、对 MOSAIC 系统设计的启示

### 6.1 可借鉴的设计思想

1. **错误信号工具化**：将不可行场景的检测封装为 Function Calling 工具的思想值得借鉴。MOSAIC 可以在 SceneGraphValidator 的基础上，将常见的不可行原因（目标不存在、路径不可达、能力不足等）封装为结构化的错误响应，提升用户体验。

2. **NAP 作为 SubAgent 内部范式**：虽然 MOSAIC 的 TaskPlanner 采用完整计划生成模式，但 SubAgent Capability（如 ObjectSearch）内部可以借鉴 NAP 的逐步推理模式——每次推理一个搜索动作，观察结果后决定下一步。

3. **RPAS 评估思路**：MOSAIC 可以参考 RPAS 的多维度评估框架，设计自己的规划质量评估方案，特别是 MRED 错误诊断分类法。

### 6.2 MOSAIC 的差异化优势总结

| 优势维度 | 具体体现 |
|---|---|
| 环境表征 | 3D 场景图 + EmbodiedRAG 检索 vs 扁平 JSON |
| 可扩展性 | 动态能力注册 vs 微调绑定技能集 |
| 反幻觉 | 场景图形式化验证（开放式）vs 微调学习（封闭式） |
| 记忆系统 | ARIA 三层记忆 + 经验积累 vs 仅当前任务记忆 |
| 平台通用性 | ROS 2 标准接口 + 依赖倒置 vs 专用 SDK/策略 |
| 重规划能力 | FeedbackEvent 驱动的 LLM 动态重规划 vs 无显式重规划 |

---

## 七、参考文献

1. Wan H, et al. EmbodiedAgent: A Scalable Hierarchical Approach to Overcome Practical Challenge in Multi-Robot Control. arXiv:2504.10030, 2025.
2. Wan H, et al. Toward Universal Embodied Planning in Scalable Heterogeneous Field Robots Collaboration and Control (MultiPlan). Journal of Field Robotics, 2025.
3. Rana K, et al. SayPlan: Grounding Large Language Models Using 3D Scene Graphs for Scalable Robot Task Planning. CoRL 2023.
4. Booker M, et al. EmbodiedRAG: Dynamic 3D Scene Graph Retrieval for Efficient and Scalable Robot Task Planning. arXiv:2410.23968, 2024.
5. Zeng H, et al. H-AIM: Orchestrating LLMs, PDDL, and Behavior Trees for Hierarchical Multi-Robot Planning. arXiv:2601.11063, 2026.
6. Chen Y, et al. EMOS: Embodiment-aware Heterogeneous Multi-robot Operating System with LLM Agents. ICLR 2025.
7. Ekpo D, et al. VeriGraph: Scene Graphs for Execution Verifiable Robot Planning. arXiv:2411.10446, 2024.
8. Kannan S, et al. SMART-LLM: Smart Multi-Agent Robot Task Planning using Large Language Models. IROS 2024.
9. Quach J, et al. ReMEmbR: Building and Reasoning Over Long-Horizon Spatio-Temporal Memory for Robot Navigation. arXiv:2409.13682, 2024.
10. Dalal M, et al. BrainBody-LLM: Grounding LLMs For Robot Task Planning Using Closed-loop State Feedback. arXiv:2402.08546, 2024.
11. Yao S, et al. ReAct: Synergizing Reasoning and Acting in Language Models. ICLR 2023.
12. Zhao T, et al. Learning Fine-Grained Bimanual Manipulation with Low-Cost Hardware (ACT). arXiv:2304.13705, 2023.
