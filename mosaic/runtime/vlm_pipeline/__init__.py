# mosaic/runtime/vlm_pipeline/__init__.py
"""VLM 语义地图管道 — 包入口

导出所有公共数据模型类和组件，供外部模块使用。
"""

from mosaic.runtime.vlm_pipeline.coordinate_aligner import CoordinateAligner
from mosaic.runtime.vlm_pipeline.models import (
    CameraFrame,
    DetectedObject,
    DetectionResult,
    RoomClassification,
)
from mosaic.runtime.vlm_pipeline.vlm_analyzer import VLMAnalyzer

__all__ = [
    "CameraFrame",
    "CoordinateAligner",
    "DetectedObject",
    "DetectionResult",
    "RoomClassification",
    "VLMAnalyzer",
]
