- title: VLA State Of The Art
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, references, vla
- source_type: note

# VLA（Vision-Language-Action）技术研究现状深度调研

> 调研时间：2026年2月 | 覆盖2023-2026年VLA领域核心进展

## 1. VLA概述与定义

### 1.1 什么是VLA

VLA（Vision-Language-Action）模型是将视觉感知、自然语言理解和动作生成统一在单一学习框架中的多模态模型。它将预训练的视觉-语言模型（VLM）从被动的序列生成器转变为能在复杂动态环境中进行操作和决策的主动智能体。

VLA的核心思想：一个端到端模型同时完成"看"（视觉）、"理解"（语言）、"做"（动作）三件事。

### 1.2 VLA的定义争议

根据ICLR 2026 VLA研究综述（Moritz Reuss），VLA的定义在社区中存在争议：
- 宽泛定义：接受视觉观测和语言指令，输出机器人控制命令的系统
- 严格定义（更被认可）：使用在大规模视觉-语言数据上预训练的骨干网络，随后训练生成控制命令的模型

关键区分点在于：**互联网规模的视觉-语言预训练**是VLA区别于普通多模态策略的核心特征。

### 1.3 VLA三大核心组件

1. **视觉-语言骨干网络**：通常基于大型VLM预训练（如PaLI-X、PaliGemma、Llama 2+视觉编码器），已具备物体识别、文本理解、空间推理能力
2. **动作接口**：在VLM之上添加动作生成机制，可以是离散token预测、连续动作回归、扩散生成等
3. **多模态输入**：相机图像、自然语言指令，通常还包括机器人状态（关节位置、夹爪状态等）

## 2. VLA发展历程

### 2.1 起源：RT-2（Google DeepMind，2023.7）

RT-2是VLA概念的开创者，首次证明可以将网络规模的视觉-语言知识迁移到机器人控制：
- 基于PaLM-E（12B）或PaLI-X（55B）VLM骨干
- 将机器人动作编码为文本token（离散化为256个bin）
- 在网络数据和机器人数据上联合训练
- 展示了对未见过的物体和指令的泛化能力（如"把瓶子移到泰勒·斯威夫特旁边"）
- 局限：模型巨大（55B参数）、推理慢、动作精度有限

[来源](https://robotics-transformer2.github.io/)

### 2.2 开源先驱：OpenVLA（Stanford/UC Berkeley，2024.6）

OpenVLA是首个高质量开源VLA模型，大幅降低了VLA研究门槛：
- 基于Llama 2（7B）语言模型 + DINOv2/SigLIP双流视觉编码器
- 在近100万条机器人轨迹（70+域）上微调
- 动作表示：将Llama 2词表最后256个未使用token重新映射为离散动作bin
- 以7B参数超越RT-2-X（55B）16.5%的绝对任务成功率
- 支持LoRA高效微调，适配新场景

[来源](https://arxiv.org/abs/2406.09246)

### 2.3 OpenVLA-OFT：精调方法论突破（2025.2）

OpenVLA-OFT提出了优化精调（Optimized Fine-Tuning）方案，系统性解决VLA微调效率问题：
- 并行解码（非自回归逐token生成）
- Action Chunking（动作块预测）
- 连续动作表示（替代离散bin）
- L1回归损失（替代交叉熵）
- 推理速度提升25-50倍，成功率提升20%+
- 在LIBERO基准上达到97.1%平均成功率，超越π0、Diffusion Policy等

[来源](https://openvla-oft.github.io/)

### 2.4 Octo（UC Berkeley，2024）

π0的前身，早期跨形态通用策略模型，为后续VLA基础模型奠定数据和架构基础。

## 3. 当前主流VLA模型深度分析

### 3.1 π0系列（Physical Intelligence）

Physical Intelligence是VLA领域融资最多的公司（$1.1B，估值$5.6B），其π系列模型代表了VLA的工业前沿。

**π0（2024.10）**
- 架构：PaliGemma（3B VLM）+ Flow Matching动作生成
- 创新：在VLM骨干上构建流匹配（Flow Matching）架构，继承互联网规模语义知识
- 训练数据：来自多个灵巧机器人平台（单臂、双臂、移动操作器）
- 能力：叠衣服、清理桌面、舀咖啡豆、组装箱子等
- 控制频率：50Hz实时控制
- 开源：通过OpenPI项目开源

**π0-FAST（2025.1）**
- 引入FAST（Frequency-space Action Sequence Tokenization）动作token化方案
- 将连续动作轨迹通过频域变换编码为离散token序列
- 自回归生成，兼顾效率和精度
- FAST+：通用机器人动作tokenizer，在100万真实轨迹上训练

**π0.5（2025.4）**
- 首个具备开放世界泛化能力的VLA
- 使用多机器人数据、高层语义预测、网络数据等多源训练
- 首次实现端到端学习系统在全新家庭环境中完成长时序灵巧操作（清理厨房/卧室）
- 泛化层次：物理层→视觉层→语义层同时泛化

**π*0.6 + RECAP（2025.11）**
- 引入RECAP方法，让VLA通过强化学习从错误中学习
- 无需策略梯度，通过经验回放实现在线改进
- 标志着VLA从纯模仿学习向RL增强的转变

**Weave & Ultra（2026.2）**
- Physical Intelligence最新产品化方向
- 将VLA模型作为即插即用的"智能层"API提供给第三方硬件
- 类比LLM API之于软件开发，VLA API之于机器人开发

[来源](https://www.physicalintelligence.company/)

### 3.2 Gemini Robotics（Google DeepMind，2025）

Google DeepMind基于Gemini 2.0构建的机器人AI系统，分为两个模型：

**Gemini Robotics 1.5（VLA）**
- 基于Gemini 2.0，将物理动作作为新的输出模态
- 直接控制机器人，性能基准比此前SOTA VLA翻倍
- 支持多语言对话指令
- 具备精细运动技能（灵巧操作）

**Gemini Robotics-ER 1.5（VLM，具身推理）**
- "ER"= Embodied Reasoning
- 作为高层"编排器"，负责规划、逻辑决策、调用数字工具（如Google搜索）
- 与Robotics 1.5配合：ER负责"想"，Robotics负责"做"

**Embodied Thinking能力**
- VLA模型在动作之间穿插内部自然语言推理
- 显著提升复杂多步骤任务的处理能力

[来源](https://deepmind.google/blog/gemini-robotics-brings-ai-into-the-physical-world/)

### 3.3 Figure Helix（Figure AI，2025.2）

专为人形机器人设计的VLA模型，采用受人类认知启发的双系统架构：

**System 2（慢思考）**
- 7B参数VLM
- 解释指令、分析环境
- 运行频率：7-9 Hz

**System 1（快思考）**
- 高频视觉运动策略
- 运行频率：200 Hz
- 负责实时精细运动控制

**关键特性：**
- 首个输出全身上半身连续控制的VLA（手腕、躯干、头部、单个手指）
- 首个同时在两台机器人上运行的VLA，实现多机协作
- 零样本泛化到未见过的家居物品

[来源](https://www.figure.ai/news/helix)

### 3.4 NVIDIA GR00T N1（2025.3）

世界首个开源人形机器人基础模型：

**双系统架构（与Helix类似）**
- System 2：基于Eagle-2 VLM的视觉-语言模块，负责环境理解和指令解析
- System 1：扩散Transformer（DiT）模块，生成流畅实时运动

**特点：**
- 开源开放
- 在仿真和真实任务中超越纯模仿学习基线
- 支持多步骤任务和人机协作

[来源](https://arxiv.org/abs/2503.14734)

### 3.5 SmolVLA（Hugging Face，2025.6）

VLA民主化的代表作，证明"小模型也能做好VLA"：
- 仅450M参数（比OpenVLA小15倍+）
- 可在消费级硬件上运行（MacBook、普通GPU甚至CPU）
- 单GPU即可训练
- 跳过图像分块（image tiling），使用pixel shuffling将视觉token压缩到仅64个/帧
- 在LIBERO、Meta-World仿真和真实世界任务中超越更大的VLA模型
- 支持异步推理，响应速度提升30%
- 完全基于社区贡献数据（LeRobot社区）训练

[来源](https://arxiv.org/abs/2506.01844)

### 3.6 VLA-0（NVIDIA，2025）

用最简单的方式构建SOTA级VLA：
- 核心发现：直接将动作表示为文本（无需修改VLM词表或添加特殊动作头）
- 零修改VLM架构，直接提示VLM预测动作文本
- 出人意料地超越了更复杂的模型
- 证明了VLM预训练知识的强大迁移能力

[来源](https://vla0.github.io/)

### 3.7 Xiaomi-Robotics-0（小米，2026.2）

小米最新发布的VLA模型，聚焦高性能与实时部署：
- 先在大规模跨形态机器人轨迹和视觉-语言数据上预训练
- 获取广泛可泛化的动作生成知识，同时保留VLM能力
- 精心设计的训练配方和部署策略
- 优化实时执行的流畅性

[来源](https://xiaomi-robotics-0.github.io/)

### 3.8 Microsoft Rho-alpha：VLA+的开端（2026.1）

微软首个机器人模型，基于Phi系列，提出VLA+概念：
- 在视觉和语言之外加入**触觉感知**，让机器人在操作中"感受"物体
- 支持**在线学习**：部署后可从人类纠正中实时改进
- 解决纯视觉VLA在精密任务中的不足（如视线被遮挡时的插拔操作）
- 正在扩展力传感等更多模态

VLA+的意义：标志着VLA从"视觉-语言-动作"向"多感官-语言-动作"的演进。

[来源](https://labs.ai.azure.com/projects/rho-alpha/)

## 4. VLA核心技术架构分类

根据兰州大学2025年综述（分析102个VLA模型），VLA方法可分为五大范式：

### 4.1 自回归范式（Autoregressive）

**代表：** RT-2、OpenVLA、VLA-0、π0-FAST

将动作token化后，用自回归方式逐token生成：
```
输入: [图像token] [语言token] → 输出: [动作token1] [动作token2] ...
```

**优势：** 直接复用LLM架构和预训练权重，实现简单
**劣势：** 离散化损失精度，逐token生成速度慢

### 4.2 扩散/流匹配范式（Diffusion/Flow Matching）

**代表：** π0、GR00T N1的System 1

将动作生成建模为连续空间的去噪/流匹配过程：
```
噪声动作 → 多步去噪 → 精确连续动作
```

**优势：** 天然支持连续动作空间，能建模多模态动作分布
**劣势：** 多步去噪增加延迟，与自回归VLM的集成需要特殊设计

### 4.3 强化学习增强范式（RL-enhanced）

**代表：** π*0.6/RECAP、GR-RL、VLA-RL

在模仿学习基础上引入RL进行在线优化：
- GR-RL：VLA通用策略 → 离线行为克隆 → 动作增强 → 在线RL → 灵巧专家
- RECAP：无需策略梯度的经验回放RL方法
- VLA-RL：可扩展的在线强化学习框架

**优势：** 突破人类示教的上限，持续改进
**劣势：** 训练不稳定，需要大量交互

### 4.4 混合专家范式（Mixture-of-Experts）

**代表：** ChatVLA、AdaMoE

使用MoE架构解决VLA训练中的知识遗忘问题：
- ChatVLA：分阶段对齐训练 + MoE架构，先掌握控制再整合多模态
- AdaMoE：将密集VLA的前馈层替换为稀疏激活的MoE层，扩展动作专家容量

**优势：** 减少任务间干扰，保留VLM预训练知识
**劣势：** 架构复杂，路由策略设计困难

### 4.5 推理增强范式（Reasoning-enhanced）

**代表：** CoT-VLA、ACoT-VLA、BagelVLA

在动作生成前引入显式或隐式推理：

**CoT-VLA（NVIDIA，CVPR 2025）**
- 视觉思维链：先自回归预测未来图像帧作为视觉子目标，再生成短动作序列
- 将"想象未来"作为推理过程

**ACoT-VLA**
- 动作思维链：推理过程本身就是结构化的粗粒度动作意图序列
- 显式动作推理器（EAR）生成粗参考轨迹 + 隐式动作推理器（IAR）提取潜在动作先验
- 在动作空间而非语言空间进行推理

**BagelVLA**
- 交错生成：语言规划 ↔ 视觉预测 ↔ 动作生成，通过残差流引导统一

**Recurrent-Depth VLA**
- 隐式测试时计算缩放：通过潜在迭代推理实现可变计算深度
- 简单调整少算，复杂操作多算

## 5. 动作表示与Token化方案

动作如何表示是VLA设计的核心问题之一：

| 方案 | 代表 | 原理 | 优劣 |
|------|------|------|------|
| 离散bin | RT-2, OpenVLA | 将连续动作均匀离散化为256个bin | 简单但损失精度 |
| FAST | π0-FAST | 频域变换后离散化，保留时序结构 | 高保真，通用性强 |
| Flow Matching | π0 | 条件流匹配生成连续动作 | 精度高，多步去噪慢 |
| 文本直出 | VLA-0 | 直接用文本表示动作数值 | 零修改，出奇有效 |
| Action Chunking | ACT/OpenVLA-OFT | 一次预测多步动作块 | 减少累积误差 |
| 连续回归 | OpenVLA-OFT | L1损失直接回归连续值 | 精度高，需并行解码 |
| Oat-VLA | 物体-智能体中心token化 | 仅保留场景物体和智能体的少量视觉token | 极致高效（几个token） |

## 6. 双系统架构：VLA的主流设计模式

2025年出现的一个显著趋势是**双系统架构**，受人类认知的"快思考/慢思考"理论启发：

| 模型 | System 2（慢/高层） | System 1（快/低层） | S2频率 | S1频率 |
|------|---------------------|---------------------|--------|--------|
| Helix | 7B VLM | 视觉运动策略 | 7-9 Hz | 200 Hz |
| GR00T N1 | Eagle-2 VLM | 扩散Transformer | 低频 | 高频 |
| Gemini Robotics | Robotics-ER (VLM) | Robotics (VLA) | 按需 | 实时 |

这种设计解决了一个根本矛盾：**大模型推理慢但理解深 vs 实时控制需要高频响应**。

## 7. 数据与训练

### 7.1 数据来源

VLA训练数据通常包含三类：
1. **互联网视觉-语言数据**：图文对、视频字幕等，提供世界知识
2. **机器人操作数据**：遥操作采集的轨迹数据（Open X-Embodiment等）
3. **仿真数据**：LIBERO、Meta-World、Isaac Sim等平台生成

### 7.2 数据规模

- Open X-Embodiment：最大的开源机器人数据集，覆盖多种机器人形态
- GraspVLA：十亿级合成动作数据预训练
- UniHand-2.0：35,000+小时跨形态数据
- LeRobot社区数据：Hugging Face社区贡献的开源机器人数据

### 7.3 训练范式

典型的VLA训练流程：
```
阶段1: VLM预训练（互联网数据）
  ↓
阶段2: 跨形态机器人数据预训练（获取通用操作知识）
  ↓
阶段3: 任务/场景特定微调（LoRA/全参数）
  ↓
（可选）阶段4: 在线RL精调（突破模仿学习上限）
```

## 8. 评估基准与性能

### 8.1 主要仿真基准

| 基准 | 特点 | 常用指标 |
|------|------|---------|
| LIBERO | 4个任务套件，多物体操作 | 平均成功率 |
| Meta-World | 50个操作任务 | 成功率 |
| SimplerEnv | 简化真实环境 | 成功率 |
| MultiNet v0.2 | 程序生成的开放环境 | 泛化性能 |

### 8.2 代表性性能数据

| 模型 | LIBERO平均成功率 | 备注 |
|------|-----------------|------|
| OpenVLA-OFT | 97.1% | 当前LIBERO SOTA |
| SmolVLA | 竞争力强 | 仅450M参数 |
| π0（微调后） | ~60%（简单抓取） | 高精度放置误差2.2cm/12.4° |
| Diffusion Policy | 基线 | 被OpenVLA-OFT超越 |

### 8.3 仿真与真实的鸿沟

ICLR 2026综述指出一个关键问题：**仿真排行榜隐藏了前沿实验室与学术实验室之间的巨大差距**。仿真中的高成功率不等于真实世界的可靠性，π0微调后在真实简单抓取任务上也仅约60%成功率。

## 9. ICLR 2026 VLA研究趋势

根据ICLR 2026提交论文分析，当前VLA研究的热点方向：

1. **离散扩散VLA**：将扩散过程应用于离散token空间
2. **推理VLA与具身思维链（ECoT）**：让VLA在行动前"思考"
3. **新型离散tokenizer**：FAST、Oat-VLA等更高效的动作编码
4. **高效VLA**：SmolVLA引领的小模型路线
5. **VLA + RL**：从纯模仿向强化学习增强演进
6. **VLA + 视频预测**：World-VLA-Loop等将世界模型与VLA结合
7. **跨动作空间学习**：统一不同机器人的动作表示
8. **评估与基准**：更严格、更贴近真实的评估方法

## 10. 核心挑战与未解问题

### 10.1 精度不足

当前VLA在高精度任务上仍然薄弱。π0微调后放置精度误差达2.2cm/12.4°，远不能满足工业装配等场景需求。

### 10.2 知识遗忘

VLM微调为VLA时，预训练获得的开放世界推理能力会退化。ChatVLA的MoE方案和分阶段训练是当前的缓解策略。

### 10.3 实时性矛盾

大模型推理延迟与实时控制需求的矛盾。双系统架构（Helix/GR00T N1）和高效模型（SmolVLA）是两条解决路径。

### 10.4 数据瓶颈

高质量机器人操作数据仍然稀缺且昂贵。仿真数据的sim-to-real gap、合成数据的质量问题尚未完全解决。

### 10.5 泛化的层次性

真正的泛化需要在多个层次同时发生：物理层（不同物体的抓取力度）、视觉层（不同光照/背景）、语义层（理解新指令）。π0.5是首个尝试全层次泛化的模型。

### 10.6 安全与可靠性

VLA模型的黑盒特性使其行为难以预测和验证，在安全关键场景中的部署面临挑战。

## 11. 技术趋势判断

1. **VLA+多感官融合**将成为下一代标准（触觉、力觉、本体感觉），Microsoft Rho-alpha开启了这一方向
2. **双系统架构**已成为人形机器人VLA的事实标准（Helix、GR00T N1、Gemini Robotics）
3. **小模型路线**（SmolVLA）与**大模型路线**（Gemini Robotics）将长期并存，分别服务于边缘部署和云端推理
4. **VLA API化**（Physical Intelligence的Weave/Ultra）将降低机器人智能的使用门槛
5. **推理增强**（CoT-VLA、ACoT-VLA）将成为提升长时序任务成功率的关键
6. **RL精调**将从可选变为必选，纯模仿学习的天花板已经可见
7. **动作token化**仍在快速演进，FAST方案目前领先但远未收敛

## 12. 主流VLA模型速查表

| 模型 | 机构 | 时间 | 参数量 | 动作表示 | 开源 | 核心特点 |
|------|------|------|--------|---------|------|---------|
| RT-2 | Google DeepMind | 2023.7 | 55B | 离散bin | 否 | VLA开创者 |
| OpenVLA | Stanford/UCB | 2024.6 | 7B | 离散bin | 是 | 首个高质量开源VLA |
| Octo | UCB | 2024 | - | 连续 | 是 | π0前身 |
| π0 | Physical Intelligence | 2024.10 | 3B+ | Flow Matching | 是 | 跨形态通用策略 |
| π0-FAST | Physical Intelligence | 2025.1 | 3B+ | FAST token | 是 | 高效自回归VLA |
| π0.5 | Physical Intelligence | 2025.4 | - | Flow Matching | 否 | 开放世界泛化 |
| Helix | Figure AI | 2025.2 | 7B(S2) | 双系统 | 否 | 人形机器人全身控制 |
| GR00T N1 | NVIDIA | 2025.3 | - | DiT | 是 | 开源人形基础模型 |
| Gemini Robotics | Google DeepMind | 2025 | 大 | 多模态 | 否 | 具身推理+动作 |
| OpenVLA-OFT | Stanford | 2025.2 | 7B | 连续回归 | 是 | LIBERO SOTA |
| SmolVLA | Hugging Face | 2025.6 | 450M | FAST | 是 | 消费级硬件可运行 |
| VLA-0 | NVIDIA | 2025 | VLM级 | 文本直出 | 是 | 零修改VLM |
| ChatVLA | - | 2025 | MoE | 离散 | 是 | MoE防遗忘 |
| ACoT-VLA | - | 2025 | - | 动作CoT | - | 动作空间推理 |
| CoT-VLA | NVIDIA | 2025 | - | 视觉CoT | - | 视觉思维链 |
| DexVLA | - | 2025 | 1B+ | 扩散专家 | - | 跨形态长时序 |
| GR-RL | - | 2025 | - | VLA+RL | - | 通用→专家精调 |
| GR-Dexter | - | 2025 | - | VLA | - | 双臂灵巧手 |
| Xiaomi-Robotics-0 | 小米 | 2026.2 | - | - | - | 实时部署优化 |
| Rho-alpha | Microsoft | 2026.1 | Phi级 | VLA+ | - | 触觉+在线学习 |
| π*0.6 | Physical Intelligence | 2025.11 | - | RECAP | 否 | RL从错误学习 |

## 13. 关键参考文献

1. RT-2: "Vision-Language-Action Models Transfer Web Knowledge to Robotic Control", Google DeepMind, 2023. [链接](https://robotics-transformer2.github.io/)
2. OpenVLA: Kim et al., "An Open-Source Vision-Language-Action Model", 2024. [链接](https://arxiv.org/abs/2406.09246)
3. π0: "A Vision-Language-Action Flow Model for General Robot Control", Physical Intelligence, 2024. [链接](https://arxiv.org/abs/2410.24164)
4. π0.5: "A VLA Model with Open-World Generalization", 2025. [链接](https://arxiv.org/abs/2504.16054)
5. Helix: Figure AI, "A VLA Model for Generalist Humanoid Control", 2025. [链接](https://www.figure.ai/news/helix)
6. GR00T N1: NVIDIA, "An Open Foundation Model for Generalist Humanoid Robots", 2025. [链接](https://arxiv.org/abs/2503.14734)
7. SmolVLA: "A VLA for Affordable and Efficient Robotics", Hugging Face, 2025. [链接](https://arxiv.org/abs/2506.01844)
8. OpenVLA-OFT: "Fine-Tuning Vision-Language-Action Models", 2025. [链接](https://arxiv.org/abs/2502.19645)
9. FAST: "Efficient Action Tokenization for VLA Models", Physical Intelligence, 2025. [链接](https://arxiv.org/abs/2501.09747)
10. VLA-0: "Building State-of-the-Art VLAs with Zero Modification", NVIDIA, 2025. [链接](https://vla0.github.io/)
11. CoT-VLA: "Visual Chain-of-Thought Reasoning for VLA Models", NVIDIA, CVPR 2025. [链接](https://research.nvidia.com/labs/eai/publication/cot-vila/)
12. ACoT-VLA: "Action Chain-of-Thought for VLA Models", 2025. [链接](https://arxiv.org/abs/2601.11404)
13. ChatVLA: "Unified Multimodal Understanding and Robot Control with VLA Model", EMNLP 2025. [链接](https://arxiv.org/abs/2502.14420)
14. Rho-alpha: Microsoft Research, VLA+ Model, 2026. [链接](https://labs.ai.azure.com/projects/rho-alpha/)
15. Gemini Robotics: Google DeepMind, 2025. [链接](https://deepmind.google/blog/gemini-robotics-brings-ai-into-the-physical-world/)
16. VLA综述（102模型）: "Vision Language Action Models in Robotic Manipulation: A Systematic Review", 2025. [链接](https://arxiv.org/abs/2507.10672)
17. Pure VLA综述: "Pure Vision Language Action Models: A Comprehensive Survey", 兰州大学, 2025. [链接](https://arxiv.org/abs/2509.19012)
18. ICLR 2026 VLA研究趋势: Moritz Reuss, "State of VLA Research at ICLR 2026". [链接](https://mbreuss.github.io/blog_post_iclr_26_vla.html)
19. Nature Machine Intelligence: "What matters in building VLA models for generalist robots", 2026. [链接](https://www.nature.com/articles/s42256-025-01168-7)
20. Xiaomi-Robotics-0, 小米, 2026. [链接](https://xiaomi-robotics-0.github.io/)
21. GR-RL: "Going Dexterous and Precise for Long-Horizon Robotic Manipulation", 2025. [链接](https://arxiv.org/abs/2512.01801)
22. DexVLA: "Vision-Language Model with Plug-In Diffusion Expert", 2025. [链接](https://arxiv.org/abs/2502.05855)
