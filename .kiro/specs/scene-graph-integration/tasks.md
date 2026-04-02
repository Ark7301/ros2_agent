# 实现计划：场景图集成（Scene Graph Integration）

## 概述

将已实现的场景图体系完整接入 MOSAIC v2 运行时，分三个阶段递进实现：
1. **运行时接入**（任务 1-7）：GatewayServer 初始化、SpatialProvider、PluginRegistry 参数注入、SensorBridge 同步、TurnRunner 三大集成点、计划验证
2. **空间感知**（任务 8-9）：MapAnalyzer SLAM 地图分析、房间拓扑到场景图映射
3. **认知架构**（任务 10-13）：ARIA 三层记忆、VLM 语义标注流水线、SceneGraphBuilder 融合构建

所有代码使用 Python，注释使用中文，变量/函数名使用英文。测试使用 pytest + hypothesis，放在 test/mosaic_v2/ 目录下。

## Tasks

- [x] 1. 实现 SpatialProvider（语义地名到坐标解析）
  - [x] 1.1 创建 `mosaic/runtime/spatial_provider.py`，实现 `LocationNotFoundError` 异常类和 `SpatialProvider` 类
    - 实现 `resolve_location(name)` 方法：精确匹配 → 模糊匹配（大小写不敏感） → 返回 (x, y) 坐标
    - 实现 `_get_position_with_fallback(node)` 方法：无 position 时沿 CONTAINS 边向上查找父节点
    - 无匹配节点或无坐标时抛出 `LocationNotFoundError`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 1.2 编写 Property 1 属性测试：SpatialProvider 坐标解析往返一致性
    - **Property 1: SpatialProvider 坐标解析往返一致性**
    - 对所有具有 position 的节点，resolve_location(node.label) 返回的坐标与直接查询 position 一致
    - **Validates: Requirements 2.1, 2.2, 2.7**

  - [x] 1.3 编写 Property 2 属性测试：模糊匹配返回有效坐标
    - **Property 2: SpatialProvider 模糊匹配返回有效坐标**
    - 对所有具有 position 的节点 label 的任意非空子串，resolve_location 返回有效坐标
    - **Validates: Requirements 2.3**

  - [x] 1.4 编写 Property 3 属性测试：层次回退
    - **Property 3: SpatialProvider 层次回退**
    - 对无 position 但有带 position 祖先的节点，返回最近祖先的 position
    - **Validates: Requirements 2.5**

  - [x] 1.5 编写 Property 4 属性测试：不存在地名抛出异常
    - **Property 4: SpatialProvider 不存在地名抛出异常**
    - 对不在场景图中的字符串，resolve_location 抛出 LocationNotFoundError
    - **Validates: Requirements 2.4**

- [x] 2. 实现 PluginRegistry 参数注入
  - [x] 2.1 修改 `mosaic/plugin_sdk/registry.py`，新增 `_factory_kwargs` 字段和 `configure_plugin` 方法
    - `register` 方法新增可选 `factory_kwargs` 参数
    - `configure_plugin(plugin_id, **kwargs)` 方法允许实例化前注入额外参数
    - `resolve` 方法将 `factory_kwargs` 作为关键字参数传入工厂函数
    - 保持无参工厂函数的向后兼容
    - _Requirements: 3.1, 3.2, 3.3, 3.7_

  - [x] 2.2 编写 Property 5 属性测试：工厂参数注入
    - **Property 5: PluginRegistry 工厂参数注入**
    - 对所有注册了 factory_kwargs 的插件，resolve 时工厂函数接收到的参数与注册时一致
    - **Validates: Requirements 3.1, 3.2, 3.3**

- [x] 3. 实现 SensorBridge 位置回调机制
  - [x] 3.1 修改 `mosaic/nodes/sensor_bridge.py`，新增位置更新回调注册
    - 新增 `_position_callbacks` 列表和 `on_position_update(callback)` 方法
    - 在 `_pose_callback` 中触发所有已注册回调，传递 (x, y) 坐标
    - 无回调注册时保持原有行为（降级兼容）
    - _Requirements: 4.1, 4.2, 4.7_

  - [x] 3.2 编写 Property 6 属性测试：位置回调触发
    - **Property 6: SensorBridge 位置回调触发**
    - 对所有已注册回调，接收到定位数据时回调被调用且坐标一致
    - **Validates: Requirements 4.2**

- [x] 4. 实现 SceneGraphManager 位置同步与房间切换
  - [x] 4.1 在 `mosaic/runtime/scene_graph_manager.py` 中新增 `update_agent_position` 和 `_find_room_for_position` 方法
    - `update_agent_position(x, y)`：更新 agent 节点 position，重新计算所在房间
    - `_find_room_for_position(x, y)`：优先 boundary_polygon 点包含测试，回退质心最近邻
    - `_point_in_polygon(x, y, polygon)`：射线法判断点是否在多边形内
    - 房间切换时移除旧 AT_Edge、创建新 AT_Edge，通过 HookManager 发布 `scene.agent_moved` 事件
    - _Requirements: 4.3, 4.4, 4.5, 4.6, 7.9_

  - [x] 4.2 编写 Property 7 属性测试：agent 坐标更新一致性
    - **Property 7: SceneGraphManager 位置更新后 agent 坐标一致**
    - 对所有坐标 (x, y)，update_agent_position 后 agent 节点 position 等于 (x, y)
    - **Validates: Requirements 4.3**

  - [x] 4.3 编写 Property 8 属性测试：房间切换正确性
    - **Property 8: SceneGraphManager 房间切换正确性**
    - 当最近房间与当前 AT_Edge 不同时，AT_Edge 被正确更新
    - **Validates: Requirements 4.4, 4.5**

- [x] 5. Checkpoint — 确保所有测试通过
  - 运行 `pytest test/mosaic_v2/ -v`，确保所有测试通过，如有问题请向用户确认。

- [x] 6. GatewayServer 初始化场景图管理器并注入 TurnRunner
  - [x] 6.1 修改 `mosaic/gateway/server.py`，在 `__init__` 中新增 `_init_scene_graph` 方法
    - 从 `mosaic.yaml` 读取 `scene_graph.environment_config` 路径（默认 `config/environments/home.yaml`）
    - 创建 SceneGraphManager 并调用 `initialize_from_config`
    - 失败时记录 ERROR 日志，降级为 `scene_graph_mgr=None`
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 6.2 修改 `mosaic/gateway/server.py`，将 SceneGraphManager 注入 TurnRunner 构造函数
    - 在 TurnRunner 构造时传入 `scene_graph_mgr=self._scene_graph_mgr`
    - _Requirements: 1.3_

  - [x] 6.3 修改 `mosaic/gateway/server.py`，根据 `ros2.enabled` 配置通过 `configure_plugin` 注入 `spatial_provider`
    - ROS2 启用时创建 SpatialProvider 并注入 navigation 插件
    - ROS2 未启用时保持默认无参创建（Mock 模式）
    - _Requirements: 3.4, 3.5, 3.6_

- [x] 7. TurnRunner 三大集成点实现
  - [x] 7.1 修改 `mosaic/runtime/turn_runner.py`，新增 `scene_graph_mgr` 参数并实现集成点 1（场景图注入 LLM 上下文）
    - `__init__` 新增 `scene_graph_mgr` 可选参数
    - 在 `run` 方法组装 LLM 上下文时调用 `get_scene_prompt(user_input)` 注入 system prompt
    - `scene_graph_mgr=None` 时跳过注入（降级兼容）
    - _Requirements: 1.5, 5.1, 5.2, 5.3_

  - [x] 7.2 修改 `mosaic/runtime/turn_runner.py`，实现集成点 2（计划验证）
    - 收到 LLM 工具调用后，转换为 plan_steps 格式调用 `verify_plan`
    - 验证失败时将 `to_llm_feedback()` 注入消息历史，跳过执行让 LLM 重新规划
    - 验证通过时正常执行
    - _Requirements: 1.6, 6.1, 6.4_

  - [x] 7.3 修改 `mosaic/runtime/turn_runner.py`，实现集成点 3（执行后更新）
    - 工具执行完成后调用 `update_from_execution(action, params, success)`
    - 更新后刷新 system prompt 中的场景图文本
    - _Requirements: 1.7, 5.4, 5.5_

  - [x] 7.4 编写 Property 9 属性测试：子图提取包含关键词匹配节点
    - **Property 9: 场景图子图提取包含关键词匹配节点**
    - 对包含某节点 label 的任务描述，get_task_subgraph 返回的子图包含该节点
    - **Validates: Requirements 5.2**

  - [x] 7.5 编写 Property 10 属性测试：to_prompt_text 输出结构完整性
    - **Property 10: to_prompt_text 输出结构完整性**
    - 对包含 ROOM、FURNITURE/OBJECT、AGENT 节点和 REACHABLE 边的场景图，输出包含四个部分
    - **Validates: Requirements 5.3**

  - [x] 7.6 编写 Property 11 属性测试：navigate_to 执行后 AT_Edge 正确更新
    - **Property 11: navigate_to 执行后 AT_Edge 正确更新**
    - 成功执行 navigate_to 后，agent 的 AT_Edge 指向目标房间
    - **Validates: Requirements 5.6**

  - [x] 7.7 编写 Property 12 属性测试：pick_up 执行后 HOLDING 边正确更新
    - **Property 12: pick_up 执行后 HOLDING 边和原始位置边正确更新**
    - 成功执行 pick_up 后，agent 有 HOLDING 边，物品原始 ON_TOP/INSIDE 边被移除
    - **Validates: Requirements 5.7**

  - [x] 7.8 编写 Property 13 属性测试：PlanVerifier 不修改原始场景图
    - **Property 13: PlanVerifier 不修改原始场景图**
    - verify_plan 后原始场景图的节点数、边数和状态不变
    - **Validates: Requirements 6.2**

  - [x] 7.9 编写 Property 14 属性测试：PlanVerifier 可行性判定正确性
    - **Property 14: PlanVerifier 可行性判定正确性**
    - feasible=True 当且仅当所有前置条件在模拟场景图上满足
    - **Validates: Requirements 6.3, 6.5**

  - [x] 7.10 编写 Property 15 属性测试：未注册动作跳过验证
    - **Property 15: PlanVerifier 未注册动作跳过验证**
    - 未注册的动作名被标记为 passed=True
    - **Validates: Requirements 6.6**

  - [x] 7.11 编写 Property 16 属性测试：PlanVerifier 模拟一致性
    - **Property 16: PlanVerifier 模拟一致性**
    - 可行计划的 final_graph 与手动逐步 apply_effect 后的结果一致
    - **Validates: Requirements 6.7**

- [x] 8. Checkpoint — 确保运行时接入层所有测试通过
  - 运行 `pytest test/mosaic_v2/ -v`，确保所有测试通过，如有问题请向用户确认。

- [x] 9. 实现 MapAnalyzer（SLAM 占据栅格地图分析）
  - [x] 9.1 创建 `mosaic/runtime/map_analyzer.py`，实现 `RoomCandidate`、`RoomTopology` 数据类和 `MapAnalyzer` 类
    - `load_map(yaml_path)`：加载 .yaml 元数据和 .pgm 图像，解析 resolution、origin、阈值
    - `pixel_to_world(px, py)` 和 `world_to_pixel(wx, wy)`：像素↔世界坐标双向转换
    - `extract_room_topology()`：连通域分析 → 边界多边形（凸包） → 质心 → 相邻关系
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.6_

  - [x] 9.2 编写 Property 17 属性测试：像素↔世界坐标往返一致性
    - **Property 17: MapAnalyzer 像素↔世界坐标往返一致性**
    - 对所有有效像素坐标，pixel_to_world → world_to_pixel 误差不超过 1 像素
    - **Validates: Requirements 7.5**

  - [x] 9.3 编写 Property 18 属性测试：房间质心在边界内
    - **Property 18: MapAnalyzer 房间质心在边界内**
    - 对所有提取的房间候选区，质心世界坐标位于边界多边形内部
    - **Validates: Requirements 7.3**

- [x] 10. 实现 RoomTopology 到 SceneGraph 的映射
  - [x] 10.1 在 `mosaic/runtime/scene_graph_manager.py` 中新增 `merge_room_topology(topology)` 方法
    - 为每个 RoomCandidate 创建 ROOM 节点，position 设为质心世界坐标
    - 将 boundary_polygon 存储在 `properties["boundary_polygon"]` 中
    - 为相邻房间对创建双向 REACHABLE 边
    - _Requirements: 7.7, 7.8_

  - [x] 10.2 编写 Property 19 属性测试：RoomTopology 到 SceneGraph 映射完整性
    - **Property 19: RoomTopology 到 SceneGraph 的映射完整性**
    - 对所有 RoomCandidate，场景图包含对应 ROOM 节点，position 和 boundary_polygon 正确
    - **Validates: Requirements 7.7, 7.8**

  - [x] 10.3 编写 Property 20 属性测试：点包含测试确定房间归属
    - **Property 20: 点包含测试确定房间归属**
    - 对位于某房间 boundary_polygon 内的坐标，_find_room_for_position 返回该房间
    - **Validates: Requirements 7.9, 9.8**

- [x] 11. Checkpoint — 确保空间感知层所有测试通过
  - 运行 `pytest test/mosaic_v2/ -v`，确保所有测试通过，如有问题请向用户确认。

- [x] 12. 实现 ARIA 三层记忆架构
  - [x] 12.1 创建 `mosaic/runtime/world_state_manager.py`，实现 `WorkingMemory` 类
    - 封装 RobotState，提供 `get_robot_state()` 和 `update_robot_state(**kwargs)` 接口
    - 数据存储在内存中实时覆写
    - _Requirements: 8.2_

  - [x] 12.2 在 `mosaic/runtime/world_state_manager.py` 中实现 `SemanticMemory` 类
    - 以 SceneGraphManager 为核心载体，维护 VectorStore 索引
    - 实现 `retrieve_context(task_description)` 方法：提取关键实体 → VectorStore 检索 → 诱导子图 → 返回 PlanningContext
    - 节点写入/更新时自动生成向量嵌入
    - _Requirements: 8.4, 8.5_

  - [x] 12.3 在 `mosaic/runtime/world_state_manager.py` 中实现 `EpisodicMemory` 类
    - 存储 TaskEpisode（任务描述、计划步骤、执行结果、场景图快照摘要、时间戳）
    - 实现 `record_episode(episode)` 和 `recall_similar(task_description, top_k)` 方法
    - 基于向量相似度 + 时间衰减加权检索
    - _Requirements: 8.6, 8.7, 8.8_

  - [x] 12.4 在 `mosaic/runtime/world_state_manager.py` 中实现 `WorldStateManager` 类
    - 作为 ARIA 三层记忆的统一 Facade，持有 WorkingMemory、SemanticMemory、EpisodicMemory 引用
    - 实现 MemoryPlugin 兼容接口：`store`、`search`、`get`、`delete` 方法映射到对应记忆层
    - 实现位姿同步：SensorBridge 更新 → WorkingMemory → SemanticMemory agent 节点 position
    - 实现 LLM 上下文组装：同时提供语义记忆（场景子图）和情景记忆（相似历史经验）
    - _Requirements: 8.1, 8.3, 8.9, 8.10_

  - [x] 12.5 编写 Property 21 属性测试：WorkingMemory 状态往返一致性
    - **Property 21: WorkingMemory 状态往返一致性**
    - update_robot_state 后 get_robot_state 返回包含最新值的 RobotState
    - **Validates: Requirements 8.2**

  - [x] 12.6 编写 Property 22 属性测试：工作记忆→语义记忆位姿同步
    - **Property 22: 工作记忆→语义记忆位姿同步**
    - 通过 WorldStateManager 更新位姿后，SemanticMemory 中 agent 节点 position 一致
    - **Validates: Requirements 8.3**

  - [x] 12.7 编写 Property 23 属性测试：EpisodicMemory 存储→召回往返
    - **Property 23: EpisodicMemory 存储→召回往返**
    - 存储 TaskEpisode 后，recall_similar 返回结果中包含该 episode
    - **Validates: Requirements 8.6**

  - [x] 12.8 编写 Property 24 属性测试：WorldStateManager MemoryPlugin 接口兼容
    - **Property 24: WorldStateManager MemoryPlugin 接口兼容**
    - store → get 返回相同 content；delete → get 返回 None
    - **Validates: Requirements 8.10**

- [x] 13. 实现 VLM 语义标注流水线
  - [x] 13.1 修改 `mosaic/nodes/sensor_bridge.py`，新增 `/camera/image_raw` 话题订阅
    - 新增 CameraFrame 数据结构，封装图像数据 + 机器人位姿 + 时间戳
    - 支持配置采样频率（默认每 2 秒采样一帧）
    - 通过回调通知 SceneAnalyzer
    - _Requirements: 9.1, 9.2_

  - [x] 13.2 创建 `mosaic/runtime/scene_analyzer.py`，实现 `SceneAnalyzer` 类
    - 实现 `analyze_frame(frame, scene_context)` 方法：调用 VLM API 分析 RGB 图像
    - 支持 GPT-4V 和开源 VLM 两种后端，通过配置切换
    - VLM prompt 包含当前场景图摘要文本（增量识别）
    - 返回 DetectedObject 列表（label、category、bbox、world_position、relations）
    - 实现像素坐标到世界坐标转换（相机内参 + SLAM TF 变换）
    - VLM API 失败/超时时记录错误日志并跳过本帧；JSON 格式不合法时记录警告并丢弃
    - _Requirements: 9.3, 9.4, 9.5, 9.6, 9.11_

  - [x] 13.3 创建 `mosaic/runtime/scene_graph_builder.py`，实现 `SceneGraphBuilder` 类
    - `merge_room_topology(topology)`：接收 MapAnalyzer 房间拓扑作为空间骨架
    - `merge_detections(detections)`：融合 VLM 语义识别结果
      - 根据物体世界坐标判断所属房间（boundary_polygon 点包含测试）
      - 创建 CONTAINS 边和层次关系
      - 节点去重：相同 label 且距离 < 0.5m 时更新已有节点（位置、状态、置信度、last_observed）
    - 融合完成后通过 HookManager 发布 `scene.graph_updated` 事件
    - _Requirements: 9.7, 9.8, 9.9, 9.10_

  - [x] 13.4 编写 Property 25 属性测试：SceneGraphBuilder 节点去重
    - **Property 25: SceneGraphBuilder 节点去重**
    - 对已存在的同名且距离 < 0.5m 的检测结果，节点总数不增加，last_observed 被更新
    - **Validates: Requirements 9.9**

  - [x] 13.5 编写 Property 26 属性测试：SceneGraphBuilder 融合完整性
    - **Property 26: SceneGraphBuilder 融合完整性**
    - 对所有 DetectedObject，融合后 to_prompt_text() 包含其 label 和所属房间信息
    - **Validates: Requirements 9.12**

- [x] 14. 最终集成与配置
  - [x] 14.1 更新 `config/mosaic.yaml`，新增 scene_graph、vlm、aria 配置段
    - scene_graph: environment_config、slam_map、auto_build
    - vlm: backend、api_key、base_url、sample_interval_s、merge_distance_m
    - aria: episodic（max_episodes、time_decay_factor）、semantic（vector_store、embedding_model）
    - _Requirements: 1.1, 7.1, 8.4, 9.3_

  - [x] 14.2 在 `mosaic/gateway/server.py` 中集成 ARIA WorldStateManager
    - 创建 WorldStateManager 并注册为 memory Slot 的新 Provider
    - 将 SensorBridge 位置回调连接到 WorldStateManager
    - 保持 MemoryPlugin 接口向后兼容
    - _Requirements: 8.1, 8.3, 8.10_

  - [x] 14.3 在 `mosaic/gateway/server.py` 中集成 MapAnalyzer 和 VLM 流水线（条件启用）
    - 当 `scene_graph.slam_map` 配置存在时，加载 SLAM 地图并合并房间拓扑
    - 当 `scene_graph.auto_build` 为 true 时，启动 VLM 语义标注流水线
    - 任一组件失败时降级为 YAML 配置初始化
    - _Requirements: 7.1, 9.1_

- [x] 15. Final Checkpoint — 确保所有测试通过
  - 运行 `pytest test/mosaic_v2/ -v`，确保所有测试通过，如有问题请向用户确认。

## Notes

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP
- 每个任务引用了具体的需求编号，确保可追溯性
- 属性测试使用 hypothesis 库，每个属性至少运行 100 次迭代
- Checkpoint 任务确保增量验证，避免问题累积
- 所有场景图相关功能失败时系统降级为无场景图模式，不影响核心运行
