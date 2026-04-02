# 需求文档：场景图集成（Scene Graph Integration）

## 简介

MOSAIC v2 框架已完整实现场景图体系（SceneGraph、SceneGraphManager、PlanVerifier、ActionRules），但这些组件尚未接入 GatewayServer 的启动流程，导致场景图注入、计划验证、执行后更新三大集成点全部旁路。本需求旨在将场景图体系完整接入系统运行时，同时补齐 SpatialProvider（语义地名→坐标解析）、插件工厂参数注入、传感器→场景图位置同步等缺失环节，使 MOSAIC 具备基于结构化世界知识的任务规划与验证能力。

此外，本需求将场景图体系提升为 ARIA（Agent with Retrieval-augmented Intelligence Architecture）三层记忆架构的语义记忆核心载体，实现：（1）SLAM 2D 占据栅格地图作为场景图 Room 层的空间骨架，通过 MapAnalyzer 从占据栅格中提取房间拓扑并映射到世界坐标；（2）SceneGraphManager 作为 ARIA 语义记忆层与工作记忆（RobotState）、情景记忆（任务执行历史）的统一集成，由 WorldStateManager 协调三层记忆的读写；（3）VLM（视觉语言模型）语义标注流水线，通过 SceneAnalyzer 从 RGB 图像识别物体和空间关系，SceneGraphBuilder 融合 SLAM 空间骨架与 VLM 语义填充，自动构建场景图以替代手工 YAML 配置。

## 术语表

- **GatewayServer**：系统入口服务，负责初始化和编排所有核心组件（ConfigManager、EventBus、PluginRegistry、TurnRunner 等）
- **SceneGraphManager**：场景图管理器，负责场景图的生命周期管理、YAML 初始化、查询、验证和执行后更新
- **SceneGraph**：三层层次化语义场景图（Room → Furniture → Object），MOSAIC 的结构化世界表征核心
- **PlanVerifier**：计划验证器，在场景图上模拟执行计划步骤，验证前置条件是否满足
- **ActionRules**：动作规则引擎，定义每个能力意图的前置条件和执行效果
- **TurnRunner**：Turn 级原子执行器，实现 ReAct 循环（LLM 推理 → 工具调用 → 结果反馈），内含三个场景图集成点
- **SpatialProvider**：空间查询提供者，将语义地名（如"厨房"）解析为世界坐标
- **NavigationCapability**：导航能力插件，支持 Mock 和 Nav2 双模式
- **PluginRegistry**：插件注册表，负责插件的自动发现、工厂注册、懒加载和 Slot/Provider 管理
- **SensorBridge**：传感器桥接节点，订阅 ROS2 话题（/odom、/amcl_pose）更新机器人实时状态
- **AT_Edge**：场景图中表示"位于"关系的边（如 robot AT living_room）
- **home.yaml**：环境配置文件（config/environments/home.yaml），定义房间、家具、物品及其空间关系
- **ARIA**：Agent with Retrieval-augmented Intelligence Architecture，MOSAIC 的三层记忆架构（工作记忆 + 语义记忆 + 情景记忆）
- **WorkingMemory**：工作记忆，存储机器人实时状态（位姿、传感器数据、能力状态），对应 RobotState，内存实时覆写
- **SemanticMemory**：语义记忆，以 SceneGraph 节点/边 + 向量嵌入索引为载体，支持 EmbodiedRAG 风格的语义检索
- **EpisodicMemory**：情景记忆，存储任务执行历史（成功/失败经验、重规划记录、环境快照），支持相似任务经验召回
- **WorldStateManager**：世界状态管理器，ARIA 三层记忆的统一门面（Facade），协调工作记忆、语义记忆、情景记忆的读写
- **MapAnalyzer**：地图分析器，对 SLAM 2D 占据栅格执行连通域分析，提取房间边界和拓扑结构
- **SceneAnalyzer**：场景分析器，调用 VLM API 对 RGB 图像进行语义分析，识别物体、表面、容器及空间关系
- **SceneGraphBuilder**：场景图构建器，融合 MapAnalyzer 的空间骨架与 SceneAnalyzer 的语义填充，自动构建 SceneGraph
- **VLM**：Vision-Language Model（视觉语言模型），如 GPT-4V 或开源 VLM，用于从图像中提取语义信息
- **OccupancyGrid**：占据栅格地图，SLAM 输出的 2D 地图（.pgm + .yaml），每个像素表示占据/空闲/未知
- **mosaic_house_map.yaml/.pgm**：SLAM 生成的家庭环境占据栅格地图文件，包含分辨率、原点等元数据
- **VectorStore**：向量存储，用于场景图节点嵌入的索引和语义相似度检索（EmbodiedRAG 的 Document Indexing）
- **EmbodiedRAG**：具身 RAG 检索流程，从任务描述出发，通过向量检索 + 子图 Grounding 获取任务相关场景上下文

## 需求

### 需求 1：GatewayServer 初始化场景图管理器

**用户故事：** 作为 MOSAIC 系统，我希望 GatewayServer 在启动时自动加载环境配置并初始化 SceneGraphManager，以便 TurnRunner 的三个场景图集成点能够正常工作。

#### 验收标准

1. WHEN GatewayServer 初始化, THE GatewayServer SHALL 从 mosaic.yaml 中读取环境配置文件路径并加载对应的 YAML 环境配置（默认为 config/environments/home.yaml）
2. WHEN 环境配置加载完成, THE GatewayServer SHALL 创建 SceneGraphManager 实例并调用 initialize_from_config 方法构建初始场景图
3. WHEN SceneGraphManager 初始化完成, THE GatewayServer SHALL 将 SceneGraphManager 实例传入 TurnRunner 构造函数的 scene_graph_mgr 参数
4. IF 环境配置文件不存在或格式错误, THEN THE GatewayServer SHALL 记录错误日志并以 scene_graph_mgr=None 继续启动（降级为无场景图模式）
5. WHEN TurnRunner 接收到有效的 SceneGraphManager, THE TurnRunner SHALL 在集成点 1 将场景图文本注入 LLM 的 system prompt
6. WHEN TurnRunner 接收到有效的 SceneGraphManager, THE TurnRunner SHALL 在集成点 2 使用 PlanVerifier 验证 LLM 生成的工具调用计划
7. WHEN TurnRunner 接收到有效的 SceneGraphManager, THE TurnRunner SHALL 在集成点 3 根据工具执行结果更新场景图状态

### 需求 2：实现 SpatialProvider（语义地名到坐标解析）

**用户故事：** 作为导航能力插件，我希望能将用户提到的语义地名（如"厨房"、"茶几"）解析为世界坐标，以便 Nav2 模式下能发送精确的导航目标。

#### 验收标准

1. THE SpatialProvider SHALL 从 SceneGraph 中查询节点的 position 属性，返回 (x, y) 坐标元组
2. WHEN 输入语义地名与场景图节点的 label 完全匹配, THE SpatialProvider SHALL 返回该节点的 position 坐标
3. WHEN 输入语义地名与场景图节点的 label 部分匹配（模糊匹配，大小写不敏感）, THE SpatialProvider SHALL 返回最佳匹配节点的 position 坐标
4. IF 输入语义地名在场景图中无匹配节点, THEN THE SpatialProvider SHALL 抛出 LocationNotFoundError 异常并包含输入地名
5. IF 匹配到的节点没有 position 属性, THEN THE SpatialProvider SHALL 沿场景图层次向上查找父节点（通过 CONTAINS 边）的 position 作为回退坐标
6. IF 匹配节点及其所有祖先节点均无 position 属性, THEN THE SpatialProvider SHALL 抛出 LocationNotFoundError 异常并说明原因
7. FOR ALL 具有 position 属性的场景图节点, 调用 SpatialProvider 的 resolve_location 方法后再与原始 SceneGraph 查询结果比较, SHALL 返回相同的坐标值（往返一致性）

### 需求 3：插件工厂函数支持参数注入

**用户故事：** 作为 MOSAIC 框架，我希望 PluginRegistry 支持向插件工厂函数传递运行时依赖（如 ros_node、spatial_provider），以便插件能根据实际环境配置切换运行模式。

#### 验收标准

1. THE PluginRegistry SHALL 支持在 register 方法中接受可选的 factory_kwargs 字典参数，用于存储插件的延迟配置依赖
2. WHEN PluginRegistry 的 resolve 方法首次实例化插件时, THE PluginRegistry SHALL 将已注册的 factory_kwargs 作为关键字参数传入工厂函数
3. THE PluginRegistry SHALL 提供 configure_plugin 方法，允许在插件发现后、实例化前注入额外的工厂参数
4. WHEN mosaic.yaml 中 ros2.enabled 为 true, THE GatewayServer SHALL 通过 configure_plugin 向 navigation 插件注入 spatial_provider 依赖
5. WHEN mosaic.yaml 中 ros2.enabled 为 false 或未配置, THE GatewayServer SHALL 保持 navigation 插件的默认无参创建行为（Mock 模式）
6. WHEN 插件工厂函数接收到 spatial_provider 参数, THE NavigationCapability SHALL 以 Nav2 模式初始化
7. WHEN 插件工厂函数未接收到 spatial_provider 参数, THE NavigationCapability SHALL 以 Mock 模式初始化（向后兼容）

### 需求 4：SensorBridge 到 SceneGraph 的位置同步

**用户故事：** 作为 MOSAIC 系统，我希望传感器桥接节点的位置更新能实时同步到场景图，以便 LLM 推理和计划验证基于机器人的真实位置。

#### 验收标准

1. THE SensorBridge SHALL 支持注册位置更新回调函数，在 _pose_callback 触发时通知外部订阅者
2. WHEN SensorBridge 接收到新的 AMCL 定位数据, THE SensorBridge SHALL 调用已注册的位置更新回调函数，传递 (x, y) 坐标
3. WHEN SceneGraphManager 接收到位置更新回调, THE SceneGraphManager SHALL 更新 agent 节点的 position 属性为新坐标
4. WHEN SceneGraphManager 接收到位置更新回调, THE SceneGraphManager SHALL 通过最近邻匹配算法确定机器人当前所在房间（比较机器人坐标与各房间节点的 position 属性的欧氏距离）
5. WHEN 最近邻匹配确定的房间与 agent 当前 AT_Edge 指向的房间不同, THE SceneGraphManager SHALL 移除旧的 AT_Edge 并创建指向新房间的 AT_Edge
6. WHEN agent 的 AT_Edge 发生变化, THE SceneGraphManager SHALL 通过 HookManager 发布 scene.agent_moved 事件，包含旧房间和新房间信息
7. IF SceneGraphManager 未注入到 SensorBridge（无场景图模式）, THEN THE SensorBridge SHALL 仅更新本地 RobotState 而不尝试场景图同步（降级兼容）

### 需求 5：场景图注入 LLM 上下文的正确性

**用户故事：** 作为 LLM 推理引擎，我希望在每次推理时获得与当前任务相关的场景图信息，以便生成物理上可行的工具调用计划。

#### 验收标准

1. WHEN TurnRunner 组装 LLM 上下文时, THE TurnRunner SHALL 调用 SceneGraphManager 的 get_scene_prompt 方法，传入用户输入作为任务描述
2. THE SceneGraphManager SHALL 基于任务描述中的关键词提取相关子图（通过 extract_task_subgraph 方法，最大扩展 2 跳）
3. THE SceneGraph 的 to_prompt_text 方法 SHALL 输出包含位置层、物体层、智能体层和可达性四个部分的结构化文本
4. WHEN 工具执行完成后, THE TurnRunner SHALL 调用 SceneGraphManager 的 update_from_execution 方法更新场景图状态
5. WHEN 场景图状态更新后, THE TurnRunner SHALL 刷新 system prompt 中的场景图文本，确保后续 LLM 推理基于最新场景状态
6. FOR ALL 成功执行的 navigate_to 动作, 场景图中 agent 的 AT_Edge SHALL 指向目标位置对应的房间节点
7. FOR ALL 成功执行的 pick_up 动作, 场景图中 agent 节点 SHALL 存在指向目标物品的 HOLDING 边，且目标物品的原始 ON_TOP 或 INSIDE 边 SHALL 被移除

### 需求 6：计划验证的正确性

**用户故事：** 作为 MOSAIC 系统，我希望在执行 LLM 生成的工具调用计划前进行可行性验证，以便在执行前发现物理上不可行的计划并让 LLM 修正。

#### 验收标准

1. WHEN TurnRunner 收到 LLM 的工具调用列表, THE TurnRunner SHALL 将工具调用转换为 plan_steps 格式并调用 SceneGraphManager 的 verify_plan 方法
2. THE PlanVerifier SHALL 在场景图的深拷贝上逐步模拟执行计划，检查每一步的前置条件
3. WHEN 计划中某一步的前置条件不满足, THE PlanVerifier SHALL 返回 PlanVerificationResult（feasible=False），包含失败步骤索引和失败原因
4. WHEN 计划验证失败, THE TurnRunner SHALL 将验证反馈（通过 to_llm_feedback 方法生成）注入消息历史，跳过本次执行，让 LLM 重新规划
5. WHEN 计划中所有步骤的前置条件均满足, THE PlanVerifier SHALL 返回 PlanVerificationResult（feasible=True），并在模拟场景图上应用所有效果
6. WHEN 计划中包含未注册规则的动作, THE PlanVerifier SHALL 跳过该步骤的验证并标记为通过（兼容自定义插件）
7. FOR ALL 可行的计划, PlanVerifier 在深拷贝场景图上模拟执行后的最终状态 SHALL 与实际逐步执行 apply_effect 后的状态一致（模拟一致性）

### 需求 7：SLAM 2D 占据栅格地图集成到 SceneGraph

**用户故事：** 作为 MOSAIC 系统，我希望 SLAM 生成的 2D 占据栅格地图（mosaic_house_map.yaml/.pgm）能作为场景图 Room 层的空间地面真值，以便场景图的房间拓扑基于真实物理空间而非手工配置。

#### 验收标准

1. THE MapAnalyzer SHALL 读取 SLAM 占据栅格地图文件（.pgm 图像 + .yaml 元数据），解析分辨率（resolution）、原点坐标（origin）和占据阈值（occupied_thresh / free_thresh）
2. WHEN MapAnalyzer 加载占据栅格后, THE MapAnalyzer SHALL 对空闲区域执行连通域分析（connected component analysis），将连通的空闲像素区域识别为独立房间候选区
3. WHEN 连通域分析完成, THE MapAnalyzer SHALL 对每个房间候选区计算边界多边形（凸包或最小外接矩形）和质心坐标，作为房间的空间范围和中心位置
4. THE MapAnalyzer SHALL 提供像素坐标到世界坐标的双向转换方法：pixel_to_world(px, py) 返回 (wx, wy)，world_to_pixel(wx, wy) 返回 (px, py)，转换公式基于 SLAM 地图的 resolution 和 origin 参数
5. FOR ALL 像素坐标 (px, py), 先调用 pixel_to_world 再调用 world_to_pixel SHALL 返回与原始像素坐标误差不超过 1 像素的结果（往返一致性）
6. WHEN MapAnalyzer 提取出房间拓扑后, THE MapAnalyzer SHALL 基于房间候选区之间的相邻关系（共享边界像素）生成房间连通性列表，每对相邻房间对应一条 REACHABLE 边
7. WHEN SceneGraphManager 接收到 MapAnalyzer 的房间拓扑数据, THE SceneGraphManager SHALL 为每个房间候选区创建 ROOM 类型节点，position 属性设置为质心的世界坐标，并创建对应的 REACHABLE 边
8. THE MapAnalyzer 输出的房间拓扑 SHALL 包含每个房间的边界多边形（世界坐标），SceneGraphManager SHALL 将边界多边形存储在 ROOM 节点的 properties["boundary_polygon"] 中
9. WHEN 判断机器人所在房间时, THE SceneGraphManager SHALL 优先使用 ROOM 节点的 boundary_polygon 进行点包含测试（point-in-polygon），而非仅依赖质心最近邻匹配

### 需求 8：ARIA 三层记忆架构集成

**用户故事：** 作为 MOSAIC 系统，我希望 SceneGraph 作为 ARIA 语义记忆的核心载体，与工作记忆（RobotState）和情景记忆（任务执行历史）统一集成，以便系统具备完整的多层记忆能力，支持 EmbodiedRAG 风格的任务驱动上下文检索。

#### 验收标准

1. THE WorldStateManager SHALL 作为 ARIA 三层记忆的统一门面（Facade），持有 WorkingMemory、SemanticMemory、EpisodicMemory 三个子模块的引用
2. THE WorkingMemory SHALL 封装 RobotState（位姿、速度、能力状态），提供 get_robot_state() 和 update_robot_state() 接口，数据存储在内存中实时覆写
3. WHEN SensorBridge 接收到新的定位数据, THE WorkingMemory SHALL 同步更新 RobotState，同时 THE WorldStateManager SHALL 将最新位姿同步到 SemanticMemory 中 agent 节点的 position 属性（工作记忆→语义记忆单向同步）
4. THE SemanticMemory SHALL 以 SceneGraphManager 为核心载体，同时维护一个 VectorStore 索引，场景图节点在写入或更新时自动生成向量嵌入并索引到 VectorStore
5. THE SemanticMemory SHALL 提供 retrieve_context(task_description) 方法，实现 EmbodiedRAG 检索流程：（a）从任务描述提取关键实体，（b）在 VectorStore 中检索相似节点，（c）以检索节点为锚点提取诱导子图，（d）返回 PlanningContext 对象
6. THE EpisodicMemory SHALL 存储任务执行记录（TaskEpisode），每条记录包含：任务描述、计划步骤、执行结果（成功/失败）、失败原因、执行时的场景图快照摘要、时间戳
7. WHEN TurnRunner 完成一次任务执行, THE EpisodicMemory SHALL 自动记录本次执行的 TaskEpisode
8. THE EpisodicMemory SHALL 提供 recall_similar(task_description, top_k) 方法，基于任务描述的向量相似度检索历史经验，返回按时间衰减加权的 top_k 条相关经验
9. WHEN WorldStateManager 组装 LLM 上下文时, THE WorldStateManager SHALL 同时提供语义记忆（场景子图）和情景记忆（相似历史经验）的组合上下文
10. THE WorldStateManager SHALL 替代当前 MemoryPlugin（file_memory）的 Slot 角色，在 PluginRegistry 中注册为 memory Slot 的新 Provider，同时保持 MemoryPlugin 接口的向后兼容（store/search/get/delete 方法映射到对应的记忆层）

### 需求 9：VLM 语义标注流水线（自动场景图构建）

**用户故事：** 作为 MOSAIC 系统，我希望通过 VLM（视觉语言模型）自动从 RGB 图像中识别物体和空间关系，并与 SLAM 地图拓扑融合，自动构建场景图，以便替代手工 YAML 环境配置，实现动态场景理解。

#### 验收标准

1. THE SensorBridge SHALL 新增 /camera/image_raw 话题订阅（sensor_msgs/Image），接收 RGB 图像数据，并支持配置采样频率（默认每 2 秒采样一帧）
2. WHEN SensorBridge 采样到新的 RGB 图像帧, THE SensorBridge SHALL 将图像数据连同当前机器人位姿（来自 WorkingMemory）一起封装为 CameraFrame 数据结构，通过回调通知 SceneAnalyzer
3. THE SceneAnalyzer SHALL 调用 VLM API（支持 GPT-4V 和开源 VLM 两种后端，通过配置切换），发送 RGB 图像和结构化 prompt，要求 VLM 返回 JSON 格式的识别结果，包含：物体列表（名称、类别、图像像素边界框）、表面和容器、物体间空间关系（on_top、inside、next_to）
4. IF VLM API 调用失败或超时, THEN THE SceneAnalyzer SHALL 记录错误日志并跳过本帧处理，不影响系统其他功能的正常运行
5. IF VLM 返回的 JSON 格式不合法或缺少必要字段, THEN THE SceneAnalyzer SHALL 记录警告日志并丢弃本帧结果
6. THE SceneAnalyzer SHALL 实现像素坐标到世界坐标的转换：利用相机内参（camera intrinsics）将像素边界框中心投影到相机坐标系，再通过 SLAM TF 变换（camera_frame → map_frame）转换为世界坐标
7. THE SceneGraphBuilder SHALL 接收 MapAnalyzer 的房间拓扑（空间骨架）和 SceneAnalyzer 的语义识别结果（语义填充），融合构建完整的 SceneGraph
8. WHEN SceneGraphBuilder 融合语义结果时, THE SceneGraphBuilder SHALL 根据物体的世界坐标判断其所属房间（使用 ROOM 节点的 boundary_polygon 进行点包含测试），并创建对应的 CONTAINS 边和层次关系
9. WHEN SceneGraphBuilder 检测到已有场景图中存在相同语义标签且世界坐标距离小于 0.5 米的节点, THE SceneGraphBuilder SHALL 更新已有节点的属性（位置、状态、置信度、last_observed 时间戳）而非创建重复节点
10. WHEN SceneGraphBuilder 完成一次融合更新, THE SceneGraphBuilder SHALL 通过 HookManager 发布 scene.graph_updated 事件，包含新增节点数、更新节点数和删除节点数
11. THE SceneAnalyzer 的 VLM prompt SHALL 包含当前场景图的摘要文本（通过 to_prompt_text 获取），以便 VLM 能参考已知场景信息进行增量识别，避免重复标注
12. FOR ALL SceneAnalyzer 输出的物体识别结果, 经 SceneGraphBuilder 融合后写入 SceneGraph 再通过 to_prompt_text 序列化, SHALL 包含该物体的语义标签和所属房间信息（融合完整性）
