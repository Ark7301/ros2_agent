# Implementation Plan: VLM 语义地图

## Overview

将 VLM 语义地图管道拆分为 4 个核心模块（数据模型 → VLMAnalyzer → CoordinateAligner → SceneGraphWriter → VLMPipeline），逐步实现并集成到 ARIA SemanticMemory。每个模块实现后紧跟属性测试，确保正确性。

## Tasks

- [x] 1. 创建包结构和数据模型
  - [x] 1.1 创建 `mosaic/runtime/vlm_pipeline/` 包目录和 `__init__.py`
    - 创建 `__init__.py`，导出所有公共类
    - _Requirements: 4.1_

  - [x] 1.2 实现数据模型 `CameraFrame`, `DetectedObject`, `RoomClassification`, `DetectionResult`
    - 在 `mosaic/runtime/vlm_pipeline/__init__.py` 或独立 `models.py` 中定义 dataclass
    - `CameraFrame`: image_data(bytes), depth_image(ndarray|None), robot_pose(tuple), timestamp(float)
    - `DetectedObject`: label, category, bbox_pixels, confidence
    - `RoomClassification`: room_type, confidence
    - `DetectionResult`: objects(list), room_classification(RoomClassification|None)
    - _Requirements: 1.1, 1.2_

- [x] 2. 实现 VLMAnalyzer
  - [x] 2.1 实现 `mosaic/runtime/vlm_pipeline/vlm_analyzer.py`
    - 基于现有 `SceneAnalyzer` 的 API 调用模式
    - `__init__`: backend, api_key, base_url, timeout_s 配置
    - `analyze_frame`: 调用 VLM API，返回 DetectionResult（含 objects + room_classification）
    - `_build_prompt`: 构建 VLM prompt，包含 scene_context 摘要
    - `_parse_response`: 解析 VLM JSON 响应，支持 markdown 代码块提取
    - VLM prompt 要求返回 objects 数组 + room_type + room_confidence
    - API 超时/HTTP 错误：logger.error，返回空 DetectionResult
    - JSON 不合法：logger.warning，返回空 DetectionResult
    - 支持 GPT-4V 和兼容 OpenAI 格式的 VLM 后端切换
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 2.2 属性测试：VLM 响应解析完整性
    - **Property 1: VLM 响应解析完整性**
    - 对所有包含有效 objects 数组和 room_type 字段的 JSON 字符串，解析后 DetectionResult 中物体数量等于输入 JSON 中有效物体数量
    - **Validates: Requirements 1.1, 1.2**

  - [x] 2.3 属性测试：非法 JSON 返回空结果
    - **Property 2: 非法 JSON 返回空结果**
    - 对所有非法 JSON 字符串，解析后返回空 DetectionResult，不抛异常
    - **Validates: Requirements 1.4**

  - [x] 2.4 属性测试：场景上下文注入 prompt
    - **Property 3: 场景上下文注入 prompt**
    - 对所有非空 scene_context，构建的 prompt 包含该文本
    - **Validates: Requirements 1.5**

- [x] 3. Checkpoint - 确保 VLMAnalyzer 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 实现 CoordinateAligner
  - [ ] 4.1 实现 `mosaic/runtime/vlm_pipeline/coordinate_aligner.py`
    - 从现有 `SceneAnalyzer._pixel_to_world` 提取为独立模块
    - `__init__`: 接收 camera_intrinsics 字典（fx, fy, cx, cy, camera_height）
    - `pixel_to_world`: bbox + depth_image + robot_pose → ((world_x, world_y), confidence)
      - 深度图优先：bbox 中心区域取中值深度，相机内参反投影
      - 地面投影回退：深度无效时用 camera_height * fy / dy_pixel，confidence=0.5
      - 深度 clamp 到 [0.1, 10.0] 米
      - 3D 点通过 robot_pose (x, y, theta) 变换到世界坐标系
    - `world_to_pixel`: 逆变换，用于往返一致性验证
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 4.2 属性测试：坐标转换往返一致性
    - **Property 4: 坐标转换往返一致性**
    - 对所有有效像素坐标、深度值 [0.1, 10.0]、机器人位姿，pixel_to_world → world_to_pixel 误差 ≤ 5 像素
    - **Validates: Requirements 2.5**

  - [ ] 4.3 属性测试：投影深度范围不变量
    - **Property 5: 投影深度范围不变量**
    - 对所有输入，CoordinateAligner 的投影深度在 [0.1, 10.0] 米
    - **Validates: Requirements 2.4**

- [ ] 5. Checkpoint - 确保 CoordinateAligner 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. 实现 SceneGraphWriter
  - [ ] 6.1 实现 `mosaic/runtime/vlm_pipeline/scene_graph_writer.py`
    - `__init__`: 接收 SceneGraphManager, SemanticMemory, merge_distance_m(默认0.5)
    - `write_detections`: DetectionResult + robot_pose → {"added": int, "updated": int}
      - category → NodeType 映射：object→OBJECT, furniture→FURNITURE, appliance→APPLIANCE
      - 设置 source="vlm", last_observed=timestamp, confidence
    - `_find_or_create_node`: 去重逻辑
      - 同 label（大小写不敏感）+ 距离 < merge_distance_m → 更新已有节点
      - 否则创建新节点
    - `_assign_room`: 根据坐标确定所属房间
      - 优先 boundary_polygon 点包含测试
      - 回退到质心最近邻
      - 创建 CONTAINS 边
    - `_update_room_label`: 更新房间语义标签
    - 写入后调用 semantic_memory.update_node_index() 同步向量索引
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ] 6.2 属性测试：节点去重
    - **Property 6: 节点去重**
    - 对所有两个同 label 且距离 < merge_distance 的检测结果，写入后 SceneGraph 中该 label 节点数为 1
    - **Validates: Requirements 3.2**

  - [ ] 6.3 属性测试：VLM 节点属性不变量
    - **Property 7: VLM 节点属性不变量**
    - 对所有 VLM 写入的 SceneNode，source=="vlm" 且 last_observed > 0 且 0 < confidence ≤ 1.0
    - **Validates: Requirements 3.5**

  - [ ] 6.4 属性测试：房间归属完整性
    - **Property 8: 房间归属完整性**
    - 对所有 VLM 写入的非房间节点，SceneGraph 中存在一条 CONTAINS 边从某个 ROOM 节点指向该节点
    - **Validates: Requirements 3.1, 3.4**

- [ ] 7. Checkpoint - 确保 SceneGraphWriter 测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. 实现 VLMPipeline 并集成
  - [ ] 8.1 实现 `mosaic/runtime/vlm_pipeline/pipeline.py`
    - `__init__`: 接收 VLMAnalyzer, CoordinateAligner, SceneGraphWriter, SceneGraphManager
    - `process_frame`: CameraFrame → dict|None
      - 检查 _processing 标志，处理中则丢弃新帧
      - 从 SceneGraph 获取摘要文本作为 VLM 上下文
      - 调用 VLMAnalyzer.analyze_frame()
      - 对每个检测物体调用 CoordinateAligner.pixel_to_world()
      - 调用 SceneGraphWriter.write_detections()
      - 任一步骤异常：logger.error + 跳过当前帧
    - `is_processing`: 返回当前处理状态
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 8.2 单元测试：VLMPipeline 帧丢弃和异常处理
    - 测试 _processing 标志：处理中到达的新帧被丢弃返回 None
    - 测试异常处理：VLM 分析失败时跳过当前帧
    - 测试正常流程：VLM 分析 → 坐标转换 → SceneGraph 写入完整链路
    - 使用 pytest-asyncio
    - _Requirements: 4.2, 4.3, 4.4_

- [ ] 9. 更新 `__init__.py` 导出并连通模块
  - 确保 `mosaic/runtime/vlm_pipeline/__init__.py` 导出所有公共类
  - 确认各模块间依赖正确连通
  - _Requirements: 4.1_

- [ ] 10. Final checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 测试文件统一放在 `test/mosaic_v2/test_vlm_pipeline.py`
- 属性测试使用 hypothesis 库
- 异步测试使用 pytest-asyncio
- Tasks marked with `*` are optional and can be skipped for faster MVP
- 中文注释，英文变量名
- VLM 写入的节点通过 `source="vlm"` 标识来源，复用现有 SceneNode/SceneEdge 定义
