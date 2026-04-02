# mosaic/runtime/vlm_pipeline/models.py
"""VLM 语义地图管道 — 数据模型

定义 VLM 管道中流转的核心数据结构：
- CameraFrame: RGB-D 相机帧
- DetectedObject: VLM 识别的物体（不含世界坐标，与 scene_analyzer 中的旧版区分）
- RoomClassification: 房间类型分类
- DetectionResult: VLM 单帧检测结果
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class CameraFrame:
    """RGB-D 相机帧数据"""

    image_data: bytes  # RGB 图像（JPEG）
    depth_image: np.ndarray | None = None  # 深度图（H×W float32，单位：米）
    robot_pose: tuple[float, float, float] = (0.0, 0.0, 0.0)  # (x, y, theta)
    timestamp: float = 0.0


@dataclass
class DetectedObject:
    """VLM 识别的物体

    与 scene_analyzer.DetectedObject 不同，此版本不含 world_position 和 relations，
    坐标转换由 CoordinateAligner 独立完成。
    """

    label: str
    category: str  # object / furniture / appliance
    bbox_pixels: tuple[int, int, int, int]  # (x1, y1, x2, y2)
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
