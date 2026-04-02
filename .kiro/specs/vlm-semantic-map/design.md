# 设计文档：VLM 语义地图

## 概述

VLM 语义地图是 ARIA SemanticMemory 的感知输入管道。它通过 VLM 分析 RGB-D 图像，将识别结果转换为 SLAM 世界坐标后写入 SceneGraph，使 ARIA 的语义记忆从静态 YAML 配置升级为动态 VLM 感知。

在 ARIA 架构中的位置：
```
CameraFrame → [VLM 管道] → SceneGraph（SemanticMemory 载体）
                                ↑
                          现有：YAML 静态配置
                          新增：VLM 动态感知 ← 本子系统
```

与其他模块的关系：
- 写入目标：SceneGraphManager（ARIA SemanticMemory 的核心载体）
- 坐标来源：SLAM 世界坐标系（通过 CoordinateAligner 转换）
- 不直接交互：导航模块、SpatialProvider、TurnRunner（它们从 SceneGraph 读取，VLM 管道往 SceneGraph 写入）

## 架构

### 数据流

```
CameraFrame ──→ VLMAnalyzer ──→ DetectionResult
                                      │
                                      ▼
                              CoordinateAligner
                              (像素→世界坐标)
                                      │
                                      ▼
                              SceneGraphWriter
                              (写入 SceneGraph)
                                      │
                                      ▼
                              SceneGraphManager
                              (ARIA SemanticMemory)
```

### 文件结构

```
mosaic/runtime/vlm_pipeline/
├── __init__.py
├── vlm_analyzer.py        # VLM API 调用 + JSON 解析
├── coordinate_aligner.py  # 像素→世界坐标转换
├── scene_graph_writer.py  # 检测结果写入 SceneGraph
└── pipeline.py            # 异步流水线编排
```

## 组件与接口

### 1. VLMAnalyzer（需求 1）

基于现有 `SceneAnalyzer` 的 API 调用模式，增强返回 DetectionResult（含房间分类）。

```python
class VLMAnalyzer:
    """VLM 视觉分析器"""

    def __init__(
        self,
        backend: str = "gpt-4v",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        timeout_s: float = 30.0,
    ) -> None: ...

    async def analyze_frame(
        self,
        frame: CameraFrame,
        scene_context: str = "",
    ) -> DetectionResult:
        """分析单帧，返回物体列表 + 房间分类
        失败时返回空 DetectionResult，不抛异常
        """

    def _build_prompt(self, scene_context: str) -> str:
        """构建 VLM prompt，含场景图摘要"""

    def _parse_response(self, raw: str) -> DetectionResult:
        """解析 VLM JSON 响应，非法时返回空结果"""
```

VLM prompt 要求返回：
```json
{
    "objects": [{"label": "...", "category": "object|furniture|appliance",
                 "bbox": [x1, y1, x2, y2]}],
    "room_type": "厨房",
    "room_confidence": 0.9
}
```

### 2. CoordinateAligner（需求 2）

从现有 `SceneAnalyzer._pixel_to_world` 提取为独立模块，增加深度图支持和逆变换。

```python
class CoordinateAligner:
    """像素坐标到 SLAM 世界坐标转换器"""

    def __init__(self, camera_intrinsics: dict[str, float]) -> None: ...

    def pixel_to_world(
        self,
        bbox: tuple[int, int, int, int],
        depth_image: np.ndarray | None,
        robot_pose: tuple[float, float, float],
    ) -> tuple[tuple[float, float], float]:
        """像素→世界坐标
        Returns: ((world_x, world_y), confidence)
        confidence: 1.0=深度图有效, 0.5=地面投影回退
        """

    def world_to_pixel(
        self,
        world_pos: tuple[float, float],
        robot_pose: tuple[float, float, float],
    ) -> tuple[int, int]:
        """世界→像素坐标（往返一致性验证用）"""
```

转换策略：
1. 深度图优先：bbox 中心区域取中值深度，相机内参反投影为 3D 点
2. 地面投影回退：深度无效时用 `camera_height * fy / dy_pixel`
3. 深度 clamp 到 [0.1, 10.0] 米
4. 3D 点通过机器人位姿 (x, y, theta) 变换到世界坐标系

### 3. SceneGraphWriter（需求 3）

将 VLM 检测结果写入 SceneGraphManager 管理的 SceneGraph。

```python
class SceneGraphWriter:
    """VLM 检测结果写入 SceneGraph"""

    def __init__(
        self,
        scene_graph_mgr: SceneGraphManager,
        semantic_memory: SemanticMemory,
        merge_distance_m: float = 0.5,
    ) -> None: ...

    def write_detections(
        self,
        result: DetectionResult,
        robot_pose: tuple[float, float, float],
    ) -> dict:
        """将检测结果写入 SceneGraph
        Returns: {"added": int, "updated": int}
        """

    def _find_or_create_node(
        self,
        label: str,
        category: str,
        position: tuple[float, float],
        confidence: float,
    ) -> tuple[str, bool]:
        """查找已有节点或创建新节点
        Returns: (node_id, is_new)
        """

    def _assign_room(self, node_id: str, position: tuple[float, float]) -> None:
        """根据坐标确定所属房间，创建 CONTAINS 边"""

    def _update_room_label(
        self,
        room_type: str,
        confidence: float,
        robot_pose: tuple[float, float, float],
    ) -> None:
        """更新机器人当前所在房间的语义标签"""
```

写入逻辑：
- category → NodeType 映射：object→OBJECT, furniture→FURNITURE, appliance→APPLIANCE
- 去重：同 label（大小写不敏感）+ 距离 < merge_distance_m → 更新已有节点
- 房间归属：boundary_polygon 点包含测试 → 回退到质心最近邻
- 写入后调用 `semantic_memory.update_node_index()` 同步向量索引

### 4. VLMPipeline（需求 4）

```python
class VLMPipeline:
    """VLM 识别异步流水线"""

    def __init__(
        self,
        analyzer: VLMAnalyzer,
        aligner: CoordinateAligner,
        writer: SceneGraphWriter,
        scene_graph_mgr: SceneGraphManager,
    ) -> None: ...

    async def process_frame(self, frame: CameraFrame) -> dict | None:
        """处理单帧：VLM 分析 → 坐标转换 → SceneGraph 写入
        处理中到达的新帧被丢弃（_processing 标志）
        Returns: {"added": int, "updated": int} 或 None（被丢弃/失败）
        """

    def is_processing(self) -> bool:
        """当前是否正在处理帧"""
```

流水线步骤：
1. 检查 `_processing` 标志，处理中则丢弃
2. 从 SceneGraph 获取摘要文本作为 VLM 上下文
3. 调用 VLMAnalyzer.analyze_frame()
4. 对每个检测物体调用 CoordinateAligner.pixel_to_world()
5. 调用 SceneGraphWriter.write_detections()
6. 任一步骤异常：logger.error + 跳过当前帧


## 数据模型

```python
@dataclass
class CameraFrame:
    """RGB-D 相机帧"""
    image_data: bytes                          # RGB 图像（JPEG）
    depth_image: np.ndarray | None = None      # 深度图（H×W float32，米）
    robot_pose: tuple[float, float, float] = (0.0, 0.0, 0.0)  # (x, y, theta)
    timestamp: float = 0.0

@dataclass
class DetectedObject:
    """VLM 识别的物体"""
    label: str
    category: str                              # object / furniture / appliance
    bbox_pixels: tuple[int, int, int, int]     # (x1, y1, x2, y2)
    confidence: float = 0.8

@dataclass
class RoomClassification:
    """房间类型分类"""
    room_type: str
    confidence: float

@dataclass
class DetectionResult:
    """VLM 单帧检测结果"""
    objects: list[DetectedObject] = field(default_factory=list)
    room_classification: RoomClassification | None = None
```

SceneNode / SceneEdge 复用 `mosaic/runtime/scene_graph.py` 中的现有定义。VLM 写入的节点通过 `source="vlm"` 标识来源。


## 正确性属性

### Property 1: VLM 响应解析完整性
For all 包含有效 objects 数组和 room_type 字段的 JSON 字符串，解析后 DetectionResult 中物体数量等于输入 JSON 中有效物体数量。
**Validates: Requirements 1.1, 1.2**

### Property 2: 非法 JSON 返回空结果
For all 非法 JSON 字符串，解析后返回空 DetectionResult，不抛异常。
**Validates: Requirements 1.4**

### Property 3: 场景上下文注入 prompt
For all 非空 scene_context，构建的 prompt 包含该文本。
**Validates: Requirements 1.5**

### Property 4: 坐标转换往返一致性
For all 有效像素坐标、深度值 [0.1, 10.0]、机器人位姿，pixel_to_world → world_to_pixel 误差 ≤ 5 像素。
**Validates: Requirements 2.5**

### Property 5: 投影深度范围不变量
For all 输入，CoordinateAligner 的投影深度在 [0.1, 10.0] 米。
**Validates: Requirements 2.4**

### Property 6: 节点去重
For all 两个同 label 且距离 < merge_distance 的检测结果，写入后 SceneGraph 中该 label 节点数为 1。
**Validates: Requirements 3.2**

### Property 7: VLM 节点属性不变量
For all VLM 写入的 SceneNode，source=="vlm" 且 last_observed > 0 且 0 < confidence ≤ 1.0。
**Validates: Requirements 3.5**

### Property 8: 房间归属完整性
For all VLM 写入的非房间节点，SceneGraph 中存在一条 CONTAINS 边从某个 ROOM 节点指向该节点。
**Validates: Requirements 3.1, 3.4**


## 错误处理

| 场景 | 策略 |
|------|------|
| VLM API 超时/HTTP 错误 | logger.error，返回空 DetectionResult |
| VLM 返回非法 JSON | logger.warning，返回空 DetectionResult |
| 深度图无效 | 地面投影回退，confidence=0.5 |
| 流水线步骤失败 | logger.error，跳过当前帧 |


## 测试策略

测试文件：`test/mosaic_v2/test_vlm_pipeline.py`

| 层级 | 内容 | 方法 |
|------|------|------|
| 属性测试 | Property 1-8 | hypothesis |
| 单元测试 | VLMAnalyzer 解析、CoordinateAligner 边界值 | pytest |
| 单元测试 | SceneGraphWriter 去重和房间归属 | pytest |
| 单元测试 | VLMPipeline 帧丢弃 | pytest-asyncio |
