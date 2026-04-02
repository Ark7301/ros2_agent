# mosaic/runtime/map_analyzer.py
"""SLAM 占据栅格地图分析器 — 从占据栅格提取房间拓扑

核心功能：
1. 加载 SLAM 地图（.yaml 元数据 + .pgm 图像）
2. 像素↔世界坐标双向转换
3. 连通域分析提取房间候选区
4. 凸包边界多边形 + 质心计算
5. 相邻关系检测（膨胀掩码重叠）

依赖：numpy、scipy（连通域分析）、PIL（图像加载）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ── 数据类 ──

@dataclass
class RoomCandidate:
    """房间候选区"""
    room_id: str
    centroid_world: tuple[float, float]     # 质心世界坐标
    boundary_polygon: list[list[float]]     # 边界多边形（世界坐标）
    area_m2: float                          # 面积（平方米）
    pixel_mask: Any = None                  # 像素掩码（内部使用）


@dataclass
class RoomTopology:
    """房间拓扑"""
    rooms: list[RoomCandidate] = field(default_factory=list)
    connections: list[tuple[str, str]] = field(default_factory=list)  # 相邻房间对


class MapAnalyzerError(Exception):
    """地图分析失败"""
    pass


class MapAnalyzer:
    """SLAM 占据栅格地图分析器

    从 SLAM 生成的 .yaml + .pgm 地图文件中提取房间拓扑结构。
    """

    def __init__(self) -> None:
        self._resolution: float = 0.0       # 米/像素
        self._origin: tuple[float, float, float] = (0.0, 0.0, 0.0)
        self._grid: np.ndarray | None = None  # 灰度栅格（2D numpy 数组）
        self._free_thresh: float = 0.65     # 空闲阈值（归一化 0~1）
        self._occupied_thresh: float = 0.196  # 占据阈值（归一化 0~1）

    def load_map(self, yaml_path: str) -> None:
        """加载 SLAM 地图（.yaml + .pgm）

        Args:
            yaml_path: .yaml 元数据文件路径

        Raises:
            FileNotFoundError: 文件不存在
            MapAnalyzerError: 解析失败
        """
        import yaml

        if not os.path.exists(yaml_path):
            raise FileNotFoundError(f"地图元数据文件不存在: {yaml_path}")

        with open(yaml_path, "r") as f:
            meta = yaml.safe_load(f)

        # 解析元数据
        self._resolution = float(meta.get("resolution", 0.05))
        origin = meta.get("origin", [0.0, 0.0, 0.0])
        self._origin = (float(origin[0]), float(origin[1]), float(origin[2]))
        self._free_thresh = float(meta.get("free_thresh", 0.65))
        self._occupied_thresh = float(meta.get("occupied_thresh", 0.196))

        # 加载 .pgm 图像
        image_path = meta.get("image", "")
        if not os.path.isabs(image_path):
            # 相对路径基于 yaml 文件所在目录
            image_path = os.path.join(os.path.dirname(yaml_path), image_path)

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"地图图像文件不存在: {image_path}")

        from PIL import Image
        img = Image.open(image_path).convert("L")  # 转灰度
        self._grid = np.array(img, dtype=np.uint8)

    def pixel_to_world(self, px: int, py: int) -> tuple[float, float]:
        """像素坐标 → 世界坐标

        转换公式：
            world_x = origin_x + pixel_x * resolution
            world_y = origin_y + (image_height - 1 - pixel_y) * resolution
        """
        if self._grid is None:
            raise MapAnalyzerError("地图未加载，请先调用 load_map")
        wx = self._origin[0] + px * self._resolution
        wy = self._origin[1] + (self._grid.shape[0] - 1 - py) * self._resolution
        return (wx, wy)

    def world_to_pixel(self, wx: float, wy: float) -> tuple[int, int]:
        """世界坐标 → 像素坐标

        转换公式：
            pixel_x = round((world_x - origin_x) / resolution)
            pixel_y = round(image_height - 1 - (world_y - origin_y) / resolution)
        """
        if self._grid is None:
            raise MapAnalyzerError("地图未加载，请先调用 load_map")
        px = round((wx - self._origin[0]) / self._resolution)
        py = round(self._grid.shape[0] - 1 - (wy - self._origin[1]) / self._resolution)
        return (px, py)

    def extract_room_topology(self) -> RoomTopology:
        """提取房间拓扑：连通域分析 → 边界多边形（凸包） → 质心 → 相邻关系

        算法流程：
        1. 将栅格二值化：空闲像素 = 1，其余 = 0
        2. 连通域标记（scipy.ndimage.label）
        3. 过滤面积过小的区域（噪声）
        4. 对每个连通域计算凸包边界多边形和质心
        5. 膨胀掩码检测相邻关系

        Returns:
            RoomTopology: 包含房间候选区列表和相邻关系
        """
        if self._grid is None:
            raise MapAnalyzerError("地图未加载，请先调用 load_map")

        from scipy.ndimage import label, binary_dilation
        from scipy.spatial import ConvexHull

        # 1. 二值化：空闲区域（像素值 > free_thresh * 255）
        free_threshold = int(self._free_thresh * 255)
        free_mask = (self._grid > free_threshold).astype(np.uint8)

        # 2. 连通域标记
        labeled_array, num_features = label(free_mask)

        # 3. 过滤小区域（面积 < 100 像素，约噪声）
        min_area_pixels = 100
        rooms: list[RoomCandidate] = []

        for region_id in range(1, num_features + 1):
            mask = (labeled_array == region_id)
            area_pixels = int(np.sum(mask))

            if area_pixels < min_area_pixels:
                continue

            # 4. 计算质心（像素坐标）
            ys, xs = np.where(mask)
            centroid_px = float(np.mean(xs))
            centroid_py = float(np.mean(ys))

            # 质心转世界坐标
            centroid_world = self.pixel_to_world(
                int(round(centroid_px)), int(round(centroid_py))
            )

            # 5. 凸包边界多边形
            boundary_polygon = self._compute_convex_hull_polygon(xs, ys)

            # 面积（平方米）
            area_m2 = area_pixels * (self._resolution ** 2)

            room_id = f"room_{region_id}"
            rooms.append(RoomCandidate(
                room_id=room_id,
                centroid_world=centroid_world,
                boundary_polygon=boundary_polygon,
                area_m2=area_m2,
                pixel_mask=mask,
            ))

        # 6. 检测相邻关系（膨胀掩码重叠）
        # 使用 5x5 膨胀核（扩展 2 像素），适配 SLAM 地图中典型的 1~2 像素墙壁
        connections: list[tuple[str, str]] = []
        struct = np.ones((5, 5), dtype=np.uint8)

        for i in range(len(rooms)):
            # 膨胀房间 i 的掩码
            dilated_i = binary_dilation(rooms[i].pixel_mask, structure=struct)
            for j in range(i + 1, len(rooms)):
                # 检查膨胀后是否与房间 j 重叠
                overlap = np.logical_and(dilated_i, rooms[j].pixel_mask)
                if np.any(overlap):
                    connections.append((rooms[i].room_id, rooms[j].room_id))

        return RoomTopology(rooms=rooms, connections=connections)

    def _compute_convex_hull_polygon(
        self, xs: np.ndarray, ys: np.ndarray,
    ) -> list[list[float]]:
        """计算像素点集的凸包，并转换为世界坐标多边形

        Args:
            xs: 像素 x 坐标数组
            ys: 像素 y 坐标数组

        Returns:
            世界坐标多边形顶点列表 [[wx, wy], ...]
        """
        from scipy.spatial import ConvexHull

        # 构建点集（去重以加速）
        points = np.column_stack((xs, ys))

        # 点数太少时直接用所有点
        if len(points) < 3:
            polygon = []
            for px, py in points:
                wx, wy = self.pixel_to_world(int(px), int(py))
                polygon.append([wx, wy])
            return polygon

        try:
            hull = ConvexHull(points)
            hull_vertices = hull.vertices
        except Exception:
            # 凸包计算失败（如共线点），使用所有唯一点
            hull_vertices = list(range(min(len(points), 20)))

        polygon = []
        for idx in hull_vertices:
            px, py = int(points[idx, 0]), int(points[idx, 1])
            wx, wy = self.pixel_to_world(px, py)
            polygon.append([wx, wy])

        return polygon
