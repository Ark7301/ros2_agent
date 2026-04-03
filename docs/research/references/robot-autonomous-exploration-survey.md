- title: Robot Autonomous Exploration Survey
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, references, exploration
- source_type: note

# 机器人自主探索与环境理解前沿方案调研

## 研究背景

传统机器人任务规划依赖人工预定义的环境模型（如 PDDL Domain），限制了机器人在未知环境中的自主性。近年来，视觉语言模型（VLM）、基础分割模型（SAM）和大语言模型（LLM）的突破，使机器人具备了自主感知、理解和形式化描述环境的能力。本调研聚焦于"机器人如何自主探索并理解新环境"这一核心问题，梳理业界五大技术流派。

## 流派一：语义地图（Semantic Map）

在传统栅格地图每个像素上叠加视觉语言特征（CLIP embedding），使地图支持自然语言查询。

代表工作：
- **VLMaps**（Google, 2023）：机器人探索时每帧 RGB 通过 CLIP 编码后投影到地图，查询时用文本 embedding 做相似度匹配，支持空间关系查询（如"沙发和电视之间"），零样本泛化无需标注数据 [vlmaps.github.io](https://vlmaps.github.io/)
- **MSLMaps**（2025）：VLMaps 的多模态扩展，支持文本、图像、音频多模态目标查询 [mslmaps.github.io](https://mslmaps.github.io/)

优势：实现简单，与现有 SLAM 无缝集成，零样本泛化能力强

局限：仅 2D 平面信息，缺乏物体间关系和层级结构，难以直接映射为 PDDL 形式化表示

## 流派二：3D 场景图（3D Scene Graph）

将环境表征为层级图结构（Building → Floor → Room → Object），节点携带语义属性，边表示空间关系。

代表工作：

**Hydra**（MIT SPARK Lab, 2022-2024）：首个实时构建层级 3D 场景图的系统，结合几何、拓扑和语义信息，在视觉惯性传感器数据上增量构建多分辨率表示。层级结构包含物体层（3D 实例 + 空间关系）、场所层（可通行区域 + 连通性）、房间层（语义房间 + 门/通道）、建筑层（楼层 + 楼梯/电梯）。已在 Clearpath Jackal 和 Unitree A1 真实机器人上验证 [alphaxiv 2305.07154](https://www.alphaxiv.org/overview/2305.07154)

**ConceptGraphs**（2024, ICRA）：开放词汇 3D 场景图，利用 2D 基础模型（SAM 分割 + CLIP 特征）的输出通过多视角关联融合到 3D，无需预定义物体类别，任何自然语言描述都能查询。不需要大规模 3D 数据集或模型微调 [concept-graphs.github.io](https://concept-graphs.github.io/)

**HOV-SG**（2024）：层级开放词汇 3D 场景图，利用开放词汇视觉基础模型获取 3D 语义分割，构建 floor-room-object 三级层级，每级节点携带开放词汇特征，支持语言 grounding 的机器人导航 [arxiv 2403.17846](https://arxiv.org/abs/2403.17846)

**DovSG**（2024）：动态开放词汇场景图，支持长期语言引导的移动操作任务。关键创新是高效的局部更新机制——机器人交互过程中只需动态调整场景图的局部，无需全场景重建 [arxiv 2410.11989](https://arxiv.org/html/2410.11989)

**SayPlan**（2023, CoRL）：将 3D 场景图作为 LLM 的 grounding 输入进行大规模任务规划。在 3 层楼、36 个房间、140 个物体的环境中成功规划长时域任务，验证了场景图作为 LLM 规划 grounding 的可行性 [sayplan.github.io](https://sayplan.github.io/)

**与 PDDL 的天然映射关系**：

| 场景图元素 | PDDL 对应 | 示例 |
|---|---|---|
| 节点类型 | types | room, object, surface, container |
| 节点实例 | objects | kitchen - room, cup_1 - object |
| 边关系 | predicates | (object_at cup_1 kitchen), (on cup_1 table_1) |
| 层级结构 | 层级 types | floor > room > object |

## 流派三：语义前沿探索（Semantic Frontier Exploration）

在传统 frontier exploration（探索未知边界）基础上引入语义推理，使机器人能优先探索高价值区域。

代表工作：

**RayFronts**（CMU AirLab, 2025）：语义射线前沿系统，不仅对已探索区域编码开放集语义，还对地图边界的未知区域用射线编码"预测语义"。机器人能推理"门后面可能是厨房"，从而优先探索高价值区域。在 NVIDIA Orin AGX 上实时运行 8.84 Hz [rayfronts.github.io](https://rayfronts.github.io/)

**Co-NavGPT**（2024）：多机器人协作语义导航，将多个机器人的子地图聚合为统一全局地图，VLM 根据语义信息为不同机器人分配前沿区域，实现协调高效探索 [arxiv 2310.07937](https://arxiv.org/html/2310.07937v3)

**SCOPE**（2025）：语义认知驱动探索框架，采用滚动时域策略，VLM 对候选前沿评分时综合考虑语义丰富度、可探索性和目标相关性

优势：显著提升探索效率，减少无效探索

局限：依赖 VLM 推理质量，预测语义可能不准确

## 流派四：世界模型（World Model）

训练神经网络"模拟器"，输入当前观测和动作，预测未来状态，机器人在"想象"中评估不同策略。

代表工作：

**TesserAct**（2025）：4D 具身世界模型，在 RGB-DN 视频上训练，预测空间和时间动态，改善逆动力学学习、视图合成和策略性能 [huggingface papers 2504.20995](https://huggingface.co/papers/2504.20995)

**RWM**（Google, 2025）：机器人世界模型，学习的黑盒神经网络模拟器，从过去的观测-动作历史预测未来观测，策略可以在"想象"中训练而无需真实交互 [sites.google.com/view/roboticworldmodel](https://sites.google.com/view/roboticworldmodel)

**LaDi-WM**（2025）：基于潜在扩散的世界模型，利用预训练视觉基础模型（DINO 几何特征 + CLIP 语义特征）的潜在空间进行未来状态预测 [arxiv 2505.11528](https://arxiv.org/html/2505.11528)

优势：能预测动作后果，支持"先想后做"的规划范式

局限：目前处于研究阶段，训练成本高，泛化能力有限，离工程落地有距离

## 流派五：零样本开放知识集成

不训练任何模型，纯粹组合现有基础模型实现端到端能力。

代表工作：

**OK-Robot**（Meta, 2024）：组合 VLM（物体检测）+ 导航原语 + 抓取原语，实现零训练的 pick-and-drop 操作。流程为 iPhone 扫描环境生成 3D 点云 → CLIP 编码语义特征 → VLM 定位目标 → 导航 → 抓取 → 放置。在 10 个真实家庭环境中达到 58.5% 成功率，整洁环境 82% [ok-robot.github.io](https://ok-robot.github.io/)

优势：零训练、即插即用、工程实现简洁

局限：成功率受环境整洁度影响大，缺乏形式化推理能力

## 技术对比与选型分析

| 维度 | 语义地图 | 3D 场景图 | 语义前沿 | 世界模型 | 零样本集成 |
|---|---|---|---|---|---|
| 与 PDDL 契合度 | 低 | **极高** | 中 | 低 | 低 |
| 工程成熟度 | 高 | 中高 | 中 | 低 | 中高 |
| 开放词汇能力 | 有 | 有 | 有 | 有限 | 有 |
| 层级结构 | 无 | **有** | 无 | 无 | 无 |
| 动态更新 | 容易 | 容易 | 容易 | 困难 | 容易 |
| 实时性 | 高 | 中 | 高 | 低 | 中 |
| 可解释性 | 中 | **高** | 中 | 低 | 低 |

## 对本项目的启示

3D 场景图是最适合本项目 DomainGenerator 的环境表征方案，因为：

1. 场景图的层级结构天然对应 PDDL 的 types/objects/predicates，转换路径清晰
2. ConceptGraphs 的开放词汇能力使机器人无需预定义物体类别即可理解新环境
3. DovSG 的动态局部更新机制支持运行时增量扩展 Domain
4. SayPlan 已验证场景图作为 LLM grounding 输入的可行性

建议技术栈组合：
- 探索策略：Nav2 frontier exploration + RayFronts 语义前沿（优先探索高价值区域）
- 场景感知：SAM2（实例分割）+ CLIP（语义特征编码）→ 多视角融合到 3D
- 场景表征：ConceptGraphs 风格的开放词汇 3D 场景图
- 知识转化：LLM 将场景图结构转化为 PDDL Domain 定义
