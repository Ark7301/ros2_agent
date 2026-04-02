# 需求文档：VLM 语义地图

## 简介

为 MOSAIC 的 ARIA 记忆系统实现 VLM 驱动的语义地图感知管道。

ARIA 三层记忆架构中，SemanticMemory 以 SceneGraphManager 为核心载体。当前 SceneGraph 的数据来源是 YAML 静态配置。本子系统的职责是：通过 VLM 分析 RGB-D 图像，识别场景中的物体和房间类型，将识别结果转换为 SLAM 世界坐标，最终写入 SceneGraph，成为 SemanticMemory 的动态数据源。

定位：ARIA SemanticMemory 的感知输入管道，不是独立系统。

与 SLAM 的关系：VLM 识别结果的像素坐标通过深度图+相机内参转换为 SLAM 世界坐标，写入 SceneGraph 节点的 position 字段。这是唯一的坐标关联点，低耦合。

与导航模块的关系：无直接关系。导航模块通过 SpatialProvider 从 SceneGraph 查询坐标，VLM 管道只负责往 SceneGraph 写入数据。

## 术语表

- **VLMAnalyzer**：VLM 视觉分析器，调用 VLM API 分析 RGB-D 图像
- **CoordinateAligner**：坐标对齐器，像素坐标→SLAM 世界坐标
- **DetectionResult**：VLM 单帧检测结果（物体列表 + 房间分类）
- **CameraFrame**：RGB-D 相机帧数据
- **SemanticMemory**：ARIA 语义记忆层，以 SceneGraphManager 为载体
- **SceneGraph**：三层层次化场景图（Room → Furniture → Object），VLM 管道的写入目标

## 需求

### 需求 1：VLM 场景识别

**用户故事：** 作为 ARIA SemanticMemory 的感知管道，我需要通过 VLM 分析 RGB-D 图像来识别场景中的物体和房间类型。

#### 验收标准

1. WHEN 一帧 CameraFrame 被提交给 VLMAnalyzer，THE VLMAnalyzer SHALL 调用 VLM API 并返回包含物体标签、类别（object/furniture/appliance）、像素边界框的 DetectionResult
2. WHEN VLMAnalyzer 收到 CameraFrame，THE VLMAnalyzer SHALL 同时推断当前视角所属的房间类型，包含标签和置信度
3. WHEN VLM API 调用超时或返回 HTTP 错误，THE VLMAnalyzer SHALL 记录错误日志并返回空的 DetectionResult，不抛出异常
4. WHEN VLM API 返回的 JSON 格式不合法，THE VLMAnalyzer SHALL 记录警告日志并返回空的 DetectionResult
5. WHEN SceneGraph 摘要文本作为上下文传入，THE VLMAnalyzer SHALL 在 prompt 中包含该摘要，指导 VLM 关注新出现的物体
6. THE VLMAnalyzer SHALL 支持通过配置切换 VLM 后端（GPT-4V 和兼容 OpenAI 格式的 VLM）

### 需求 2：像素坐标到世界坐标转换

**用户故事：** 作为坐标对齐模块，我需要将 VLM 识别结果的像素坐标转换为 SLAM 世界坐标，以便写入 SceneGraph 节点的 position 字段。

#### 验收标准

1. WHEN DetectionResult 中包含物体的像素边界框和对应的深度图，THE CoordinateAligner SHALL 利用相机内参将像素坐标投影为相机坐标系下的 3D 点
2. WHEN 相机坐标系下的 3D 点和机器人位姿（x, y, theta）可用，THE CoordinateAligner SHALL 将 3D 点变换到 SLAM 世界坐标系，输出 (x, y) 世界坐标
3. IF 深度图在物体边界框区域内的深度值无效（NaN 或超出合理范围），THEN THE CoordinateAligner SHALL 使用地面平面投影模型作为回退，置信度标记为低
4. THE CoordinateAligner SHALL 将投影深度限制在 0.1 米到 10.0 米范围内
5. FOR ALL 有效的像素坐标和深度值，经 CoordinateAligner 转换后的世界坐标，再通过逆变换回像素坐标，误差 SHALL 在 5 像素以内（往返一致性）

### 需求 3：VLM 检测结果写入 SceneGraph

**用户故事：** 作为 SemanticMemory 的数据写入器，我需要将 VLM 检测结果（带世界坐标）写入 SceneGraph，使 ARIA 的语义记忆动态更新。

#### 验收标准

1. WHEN DetectionResult 中的物体具有有效世界坐标，THE 写入器 SHALL 在 SceneGraph 中创建对应类型的 SceneNode（Object/Furniture/Appliance），设置 source="vlm"，并根据坐标确定所属房间创建 CONTAINS 边
2. WHEN 新检测到的物体与 SceneGraph 中已有节点的标签相同且世界坐标距离小于合并阈值（默认 0.5 米），THE 写入器 SHALL 更新已有节点而非创建重复节点
3. WHEN 房间分类结果可用，THE 写入器 SHALL 更新对应房间节点的语义标签（如 "room_1" → "厨房"）
4. WHEN 物体坐标不在任何已知房间的 boundary_polygon 内，THE 写入器 SHALL 将该物体挂载到质心距离最近的房间节点
5. THE 写入器 SHALL 为每个 VLM 节点记录 last_observed 时间戳和 confidence 置信度
6. THE 写入器 SHALL 在写入完成后同步更新 SemanticMemory 的向量索引

### 需求 4：VLM 识别流水线

**用户故事：** 作为系统集成模块，我需要将 VLM 识别、坐标转换、SceneGraph 写入串联为异步流水线。

#### 验收标准

1. WHEN 新的 CameraFrame 到达，THE 流水线 SHALL 按顺序执行：VLM 分析 → 坐标转换 → SceneGraph 写入
2. THE 流水线 SHALL 使用 asyncio 异步执行，不阻塞其他模块
3. WHILE 流水线正在处理一帧，THE 流水线 SHALL 丢弃期间到达的新帧
4. WHEN 流水线中任一步骤失败，THE 流水线 SHALL 记录错误日志并跳过当前帧
5. THE 流水线 SHALL 通过回调函数接收 CameraFrame
