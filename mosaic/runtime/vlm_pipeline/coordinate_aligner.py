# mosaic/runtime/vlm_pipeline/coordinate_aligner.py
"""VLM 语义地图管道 — 像素坐标到 SLAM 世界坐标转换器

从 SceneAnalyzer._pixel_to_world 提取为独立模块，增加：
- 深度图优先策略（bbox 中心区域取中值深度）
- 地面投影回退（深度无效时使用相机高度估算）
- 逆变换 world_to_pixel（往返一致性验证用）
"""

from __future__ import annotations

import math

import numpy as np


# 深度有效范围（米）
_DEPTH_MIN = 0.1
_DEPTH_MAX = 10.0


class CoordinateAligner:
    """像素坐标到 SLAM 世界坐标转换器

    转换策略：
    1. 深度图优先：bbox 中心区域取中值深度，相机内参反投影为 3D 点
    2. 地面投影回退：深度无效时用 camera_height * fy / dy_pixel
    3. 深度 clamp 到 [0.1, 10.0] 米
    4. 3D 点通过机器人位姿 (x, y, theta) 变换到世界坐标系
    """

    def __init__(self, camera_intrinsics: dict[str, float]) -> None:
        """初始化坐标转换器

        Args:
            camera_intrinsics: 相机内参字典，包含 fx, fy, cx, cy, camera_height
        """
        self._fx: float = camera_intrinsics["fx"]
        self._fy: float = camera_intrinsics["fy"]
        self._cx: float = camera_intrinsics["cx"]
        self._cy: float = camera_intrinsics["cy"]
        self._camera_height: float = camera_intrinsics["camera_height"]

    def pixel_to_world(
        self,
        bbox: tuple[int, int, int, int],
        depth_image: np.ndarray | None,
        robot_pose: tuple[float, float, float],
    ) -> tuple[tuple[float, float], float]:
        """像素坐标 → 世界坐标

        Args:
            bbox: 像素边界框 (x1, y1, x2, y2)
            depth_image: 深度图（H×W float32，单位：米），可为 None
            robot_pose: 机器人位姿 (x, y, theta)

        Returns:
            ((world_x, world_y), confidence)
            confidence: 1.0=深度图有效, 0.5=地面投影回退
        """
        # 1. 计算 bbox 中心像素坐标
        cx_pixel = (bbox[0] + bbox[2]) / 2.0
        cy_pixel = (bbox[1] + bbox[3]) / 2.0

        # 2. 尝试从深度图获取深度
        depth, confidence = self._depth_from_image(bbox, depth_image, cx_pixel, cy_pixel)

        # 3. 如果深度图无效，走地面投影回退
        if depth is None:
            depth = self._depth_from_ground_projection(cy_pixel)
            confidence = 0.5

        # 4. 深度 clamp 到 [0.1, 10.0]
        depth = max(_DEPTH_MIN, min(depth, _DEPTH_MAX))

        # 5. 相机坐标系中的 x 偏移
        x_cam = (cx_pixel - self._cx) * depth / self._fx

        # 6. 机器人位姿变换到世界坐标
        rx, ry, theta = robot_pose
        wx = rx + depth * math.cos(theta) - x_cam * math.sin(theta)
        wy = ry + depth * math.sin(theta) + x_cam * math.cos(theta)

        return ((wx, wy), confidence)

    def world_to_pixel(
        self,
        world_pos: tuple[float, float],
        robot_pose: tuple[float, float, float],
    ) -> tuple[int, int]:
        """世界坐标 → 像素坐标（逆变换，往返一致性验证用）

        Args:
            world_pos: 世界坐标 (x, y)
            robot_pose: 机器人位姿 (x, y, theta)

        Returns:
            (px, py) 像素坐标
        """
        rx, ry, theta = robot_pose

        # 1. 世界坐标减去机器人位置
        dx = world_pos[0] - rx
        dy = world_pos[1] - ry

        # 2. 逆旋转回相机坐标系
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        depth = dx * cos_t + dy * sin_t
        x_cam = -dx * sin_t + dy * cos_t

        # 3. 反投影到像素坐标（地面投影模型的精确逆变换）
        # 避免除零
        if abs(depth) < 1e-9:
            depth = 1e-9

        px = x_cam * self._fx / depth + self._cx
        py = self._camera_height * self._fy / depth + self._cy

        return (int(round(px)), int(round(py)))

    # ── 内部方法 ──

    def _depth_from_image(
        self,
        bbox: tuple[int, int, int, int],
        depth_image: np.ndarray | None,
        cx_pixel: float,
        cy_pixel: float,
    ) -> tuple[float | None, float]:
        """从深度图中提取 bbox 中心区域的中值深度

        在 bbox 中心 ±10% 范围内取深度值，过滤 NaN 和超出范围的值。

        Returns:
            (depth, confidence) 或 (None, 0.0) 表示深度无效
        """
        if depth_image is None:
            return (None, 0.0)

        h, w = depth_image.shape[:2]

        # bbox 中心区域（±10% 范围）
        bbox_w = bbox[2] - bbox[0]
        bbox_h = bbox[3] - bbox[1]
        margin_x = max(1, int(bbox_w * 0.1))
        margin_y = max(1, int(bbox_h * 0.1))

        # 计算采样区域（clamp 到图像边界）
        x_min = max(0, int(cx_pixel) - margin_x)
        x_max = min(w, int(cx_pixel) + margin_x + 1)
        y_min = max(0, int(cy_pixel) - margin_y)
        y_max = min(h, int(cy_pixel) + margin_y + 1)

        # 提取深度区域
        region = depth_image[y_min:y_max, x_min:x_max].flatten()

        # 过滤 NaN 和超出范围的值
        valid = region[~np.isnan(region)]
        valid = valid[(valid >= _DEPTH_MIN) & (valid <= _DEPTH_MAX)]

        if len(valid) == 0:
            return (None, 0.0)

        return (float(np.median(valid)), 1.0)

    def _depth_from_ground_projection(self, cy_pixel: float) -> float:
        """地面投影回退：通过相机高度和内参估算深度

        depth = camera_height * fy / dy_pixel
        """
        dy_pixel = cy_pixel - self._cy
        if abs(dy_pixel) < 1.0:
            dy_pixel = 1.0  # 避免除零

        depth = self._camera_height * self._fy / dy_pixel
        return depth
