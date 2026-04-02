# test/mosaic_v2/test_map_analyzer.py
"""MapAnalyzer 属性基测试 — 像素↔世界坐标往返一致性 + 房间质心在边界内

测试策略：
- Property 17: 直接设置 MapAnalyzer 内部状态（无需真实地图文件），验证坐标转换往返误差 ≤ 1 像素
- Property 18: 构造合成二值栅格，提取房间拓扑，验证质心在凸包边界内
"""

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from mosaic.runtime.map_analyzer import (
    MapAnalyzer,
    RoomCandidate,
    RoomTopology,
    MapAnalyzerError,
)


# ── Property 17: 像素↔世界坐标往返一致性 ──

class TestProperty17PixelWorldRoundtrip:
    """Property 17: MapAnalyzer 像素↔世界坐标往返一致性

    **Validates: Requirements 7.5**

    For all valid pixel coordinates, pixel_to_world → world_to_pixel error ≤ 1 pixel.
    """

    @settings(max_examples=100)
    @given(
        px=st.integers(0, 999),
        py=st.integers(0, 999),
        resolution=st.floats(0.01, 1.0, allow_nan=False, allow_infinity=False),
        origin_x=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
        origin_y=st.floats(-100, 100, allow_nan=False, allow_infinity=False),
    )
    def test_pixel_world_roundtrip(self, px, py, resolution, origin_x, origin_y):
        """Feature: scene-graph-integration, Property 17: 像素↔世界坐标往返一致性

        **Validates: Requirements 7.5**
        """
        analyzer = MapAnalyzer()
        analyzer._resolution = resolution
        analyzer._origin = (origin_x, origin_y, 0.0)
        # 模拟 1000x1000 栅格
        analyzer._grid = np.zeros((1000, 1000), dtype=np.uint8)

        # 像素 → 世界 → 像素
        wx, wy = analyzer.pixel_to_world(px, py)
        px2, py2 = analyzer.world_to_pixel(wx, wy)

        assert abs(px2 - px) <= 1, f"x 误差过大: {px} → {px2}"
        assert abs(py2 - py) <= 1, f"y 误差过大: {py} → {py2}"


# ── Property 18: 房间质心在边界内 ──

def _point_in_polygon(x: float, y: float, polygon: list[list[float]]) -> bool:
    """射线法判断点是否在多边形内（复用 SceneGraphManager 的逻辑）"""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


class TestProperty18CentroidInsideBoundary:
    """Property 18: MapAnalyzer 房间质心在边界内

    **Validates: Requirements 7.3**

    For all extracted room candidates, centroid world coordinates are inside boundary polygon.
    """

    @settings(max_examples=30, deadline=10000)
    @given(
        # 生成合成栅格参数：在 200x200 栅格中放置 1~3 个矩形房间
        resolution=st.floats(0.05, 0.2, allow_nan=False, allow_infinity=False),
        origin_x=st.floats(-10, 10, allow_nan=False, allow_infinity=False),
        origin_y=st.floats(-10, 10, allow_nan=False, allow_infinity=False),
        # 房间 1 的位置和大小（像素坐标）
        r1_x=st.integers(5, 40),
        r1_y=st.integers(5, 40),
        r1_w=st.integers(20, 60),
        r1_h=st.integers(20, 60),
    )
    def test_centroid_inside_boundary(
        self, resolution, origin_x, origin_y,
        r1_x, r1_y, r1_w, r1_h,
    ):
        """Feature: scene-graph-integration, Property 18: 房间质心在边界内

        **Validates: Requirements 7.3**
        """
        # 构造合成栅格：全黑（占据），在指定区域填白（空闲）
        grid_size = 200
        grid = np.zeros((grid_size, grid_size), dtype=np.uint8)

        # 填充房间区域为空闲（像素值 254 = 空闲）
        x_end = min(r1_x + r1_w, grid_size)
        y_end = min(r1_y + r1_h, grid_size)
        grid[r1_y:y_end, r1_x:x_end] = 254

        # 设置 MapAnalyzer
        analyzer = MapAnalyzer()
        analyzer._resolution = resolution
        analyzer._origin = (origin_x, origin_y, 0.0)
        analyzer._grid = grid
        analyzer._free_thresh = 0.65  # 254/255 ≈ 0.996 > 0.65

        # 提取房间拓扑
        topology = analyzer.extract_room_topology()

        # 验证每个房间的质心在其边界多边形内
        for room in topology.rooms:
            cx, cy = room.centroid_world
            polygon = room.boundary_polygon

            # 凸包至少需要 3 个顶点才能形成多边形
            if len(polygon) >= 3:
                assert _point_in_polygon(cx, cy, polygon), (
                    f"房间 {room.room_id} 的质心 ({cx:.3f}, {cy:.3f}) "
                    f"不在边界多边形内"
                )


# ── 单元测试：基本功能验证 ──

class TestMapAnalyzerBasic:
    """MapAnalyzer 基本功能单元测试"""

    def test_pixel_to_world_basic(self):
        """基本像素→世界坐标转换"""
        analyzer = MapAnalyzer()
        analyzer._resolution = 0.05
        analyzer._origin = (-10.0, -10.0, 0.0)
        analyzer._grid = np.zeros((100, 100), dtype=np.uint8)

        wx, wy = analyzer.pixel_to_world(0, 0)
        # world_x = -10 + 0 * 0.05 = -10
        # world_y = -10 + (99 - 0) * 0.05 = -10 + 4.95 = -5.05
        assert wx == pytest.approx(-10.0)
        assert wy == pytest.approx(-5.05)

    def test_world_to_pixel_basic(self):
        """基本世界→像素坐标转换"""
        analyzer = MapAnalyzer()
        analyzer._resolution = 0.05
        analyzer._origin = (-10.0, -10.0, 0.0)
        analyzer._grid = np.zeros((100, 100), dtype=np.uint8)

        px, py = analyzer.world_to_pixel(-10.0, -5.05)
        assert px == 0
        assert py == 0

    def test_grid_not_loaded_raises(self):
        """未加载地图时调用转换方法应抛出异常"""
        analyzer = MapAnalyzer()
        with pytest.raises(MapAnalyzerError):
            analyzer.pixel_to_world(0, 0)
        with pytest.raises(MapAnalyzerError):
            analyzer.world_to_pixel(0.0, 0.0)

    def test_extract_room_topology_not_loaded(self):
        """未加载地图时提取拓扑应抛出异常"""
        analyzer = MapAnalyzer()
        with pytest.raises(MapAnalyzerError):
            analyzer.extract_room_topology()

    def test_extract_single_room(self):
        """单个矩形房间的拓扑提取"""
        grid = np.zeros((100, 100), dtype=np.uint8)
        grid[20:80, 20:80] = 254  # 60x60 空闲区域

        analyzer = MapAnalyzer()
        analyzer._resolution = 0.05
        analyzer._origin = (0.0, 0.0, 0.0)
        analyzer._grid = grid

        topology = analyzer.extract_room_topology()

        assert len(topology.rooms) == 1
        room = topology.rooms[0]
        assert room.area_m2 > 0
        assert len(room.boundary_polygon) >= 3
        # 质心应大致在中心
        cx, cy = room.centroid_world
        assert 0.5 < cx < 3.5  # 大致范围
        assert 0.5 < cy < 3.5

    def test_extract_two_rooms_with_connection(self):
        """两个相邻房间（1 像素墙壁）应检测到连接关系"""
        grid = np.zeros((100, 200), dtype=np.uint8)
        # 房间 1：列 10~89
        grid[20:80, 10:90] = 254
        # 房间 2：列 91~180（间隔 1 像素墙壁：列 90）
        grid[20:80, 91:180] = 254

        analyzer = MapAnalyzer()
        analyzer._resolution = 0.05
        analyzer._origin = (0.0, 0.0, 0.0)
        analyzer._grid = grid

        topology = analyzer.extract_room_topology()

        # 应该有 2 个独立房间
        assert len(topology.rooms) == 2
        # 5x5 膨胀核（扩展 2 像素）可以桥接 1 像素墙壁
        assert len(topology.connections) == 1

    def test_data_classes(self):
        """数据类基本创建"""
        room = RoomCandidate(
            room_id="test_room",
            centroid_world=(1.0, 2.0),
            boundary_polygon=[[0, 0], [2, 0], [2, 4], [0, 4]],
            area_m2=8.0,
        )
        assert room.room_id == "test_room"
        assert room.centroid_world == (1.0, 2.0)
        assert room.area_m2 == 8.0

        topology = RoomTopology(
            rooms=[room],
            connections=[("room_1", "room_2")],
        )
        assert len(topology.rooms) == 1
        assert len(topology.connections) == 1
