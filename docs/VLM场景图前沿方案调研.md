# VLM 驱动场景图构建 — 前沿方案调研

## 核心问题

MOSAIC 当前的场景图依赖 SLAM 建图 → MapAnalyzer 提取房间拓扑 → SceneGraphManager 合并。这条路径的瓶颈在于 SLAM 建图质量差、时间同步复杂、且只能获取几何信息（墙壁轮廓），无法理解语义（"这是厨房"、"桌上有咖啡杯"）。

前沿方案的核心思路：用 VLM（视觉语言模型）直接从 RGB-D 图像构建语义级别的 3D 场景图，跳过传统 SLAM。

## 方案对比

### 1. SayPlan（CoRL 2023）— LLM + 3D 场景图任务规划

- 输入：预建的 3D 场景图（Hydra 生成）
- 核心：LLM 在场景图上做层次化搜索和任务规划
- 场景图层次：Building → Floor → Room → Object
- 亮点：语义子图搜索减少 LLM token 消耗，支持大规模环境
- 局限：依赖预建场景图（Hydra），不能实时构建
- 与 MOSAIC 关系：最接近 MOSAIC 的架构思路，SceneGraphManager 可以直接对标

### 2. HOV-SG（RSS 2024）— 层次化开放词汇 3D 场景图

- 输入：RGB-D 视频 + 里程计
- 核心：用开放词汇视觉基础模型（SAM + CLIP）构建 3D 分割级别地图，再自顶向下构建场景图
- 场景图层次：Floor → Room → Object，每层带 CLIP 特征
- 构建流程：3D 点云分割 → Voronoi 图房间分割 → CLIP 特征标注 → 层次化场景图
- 亮点：支持多楼层、开放词汇查询（"找到浴室里的马桶"）、比密集地图小 75%
- 局限：需要完整的 RGB-D 扫描（离线处理），不是实时的
- 开源：https://hovsg.github.io/

### 3. ConceptGraphs（ICRA 2024）— 开放词汇 3D 场景图

- 输入：RGB-D 视频
- 核心：用 2D 基础模型（SAM + CLIP + LLaVA）检测物体，多视角关联融合到 3D
- 场景图：物体节点 + 空间关系边，每个节点带 CLIP 嵌入和 LLM 生成的描述
- 亮点：完全开放词汇，支持自然语言查询（"找到红色的杯子"）
- 局限：物体级别，没有房间层次；需要较好的深度图
- 开源：https://concept-graphs.github.io/

### 4. DovSG（2024）— 动态开放词汇场景图 + 移动操作

- 输入：RGB-D 序列
- 核心：VLM 检测物体 → 3D 场景图 → 局部动态更新（不需要全局重建）
- 亮点：支持长期任务执行中的环境变化（物体被移动/添加/删除）
- 与 MOSAIC 关系：最匹配 MOSAIC 的需求 — 动态场景图 + LLM 任务规划

### 5. VLFM（ICRA 2024）— 视觉语言前沿地图

- 输入：RGB + 深度（实时）
- 核心：不建场景图，用 VLM 对前沿区域打分，直接导航到目标物体
- 亮点：零样本、不需要预建地图、实时
- 局限：只做目标导航，不构建持久化的场景理解
- 开源：https://github.com/bdaiinstitute/vlfm

### 6. MoMa-LLM（2024）— 动态场景图 + LLM 交互式搜索

- 输入：RGB-D（实时探索）
- 核心：开放词汇场景图动态更新 + LLM 在场景图上做推理和规划
- 亮点：紧密交织场景图更新和动作规划，支持交互式物体搜索

## MOSAIC 集成方案建议

### 推荐路径：ConceptGraphs 思路 + SayPlan 架构

MOSAIC 已有的架构优势：
- SceneGraphManager 支持层次化场景图（Room → Furniture → Object）
- SceneGraphBuilder 预留了 VLM 标注接口
- SpatialProvider 提供坐标查询
- TurnRunner 的 ReAct 循环天然支持场景图上的推理

建议的集成架构：

```
Isaac Sim RGB-D Camera
        ↓
   VLM 物体检测（SAM + CLIP / GPT-4V）
        ↓
   3D 多视角融合（深度投影 + 点云聚类）
        ↓
   开放词汇场景图构建
   ├── 物体节点（CLIP 嵌入 + 位置 + 描述）
   ├── 房间节点（Voronoi 分割 / 连通域）
   └── 空间关系边（on, in, near, next_to）
        ↓
   SceneGraphManager.merge_vlm_topology()
        ↓
   LLM 任务规划（TurnRunner）
```

### 分阶段实施

阶段 1（当前可做）：
- 用 Isaac Sim Occupancy Map 生成静态地图 → Nav2 导航
- 用 YAML 配置的静态场景图 → LLM 任务规划
- 这条路已经通了，先跑通端到端

阶段 2（论文亮点）：
- 在 Isaac Sim 中用 RGB-D 相机采集图像
- 用 GPT-4V / CLIP 做物体检测和语义标注
- 构建开放词汇场景图，替代 YAML 静态配置
- 关键创新点：LLM Agent 在 VLM 构建的动态场景图上做任务规划

阶段 3（进阶）：
- 实时场景图更新（DovSG 思路）
- 机器人执行任务后场景图自动更新（物体被移动）
- 多轮对话中场景图作为持久化记忆

### 与现有代码的对接点

| 现有模块 | VLM 方案对接 |
|---------|------------|
| SceneGraphBuilder | 改为从 VLM 输出构建，而非 SLAM 地图 |
| SceneAnalyzer | 调用 GPT-4V API 分析 RGB 图像 |
| MapAnalyzer | 可保留用于几何层面的补充 |
| SceneGraphManager | merge_vlm_topology() 新方法 |
| SpatialProvider | 从 VLM 场景图获取物体坐标 |

### 硬件需求评估

| 方案 | GPU 需求 | 你的 8GB 4070 |
|------|---------|-------------|
| GPT-4V API 调用 | 无本地 GPU 需求 | 完全可行 |
| CLIP 本地推理 | ~2GB VRAM | 可行 |
| SAM 本地推理 | ~4GB VRAM | 勉强（和 Isaac Sim 抢） |
| SAM + CLIP + Isaac Sim | ~10GB+ | 不够，需要 API 方案 |

建议：用 API 方案（GPT-4V / Claude Vision），不在本地跑视觉模型，避免 VRAM 瓶颈。

## 论文定位建议

MOSAIC 的论文亮点不应该是 SLAM 或场景图构建本身（这些是工具），而是：

"LLM 驱动的具身智能体如何利用动态语义场景图进行自然语言任务规划和执行"

核心贡献：
1. 模块化插件架构（EventBus + Protocol）让 VLM 场景图和 LLM 规划解耦
2. 场景图作为 LLM 的 grounding 机制，解决幻觉问题
3. 从静态 YAML 配置到 VLM 动态构建的渐进式场景理解
