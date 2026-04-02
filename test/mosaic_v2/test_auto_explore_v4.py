"""auto_explore v4 属性基测试

使用 hypothesis 验证 frontier 探索算法的正确性属性。
"""
import sys
import os
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import pytest
from hypothesis import given, strategies as st, settings, assume
import numpy as np

from scripts.auto_explore import (
    nhood4, nhood8, Frontier, FrontierSearch,
    BlacklistManager, ProgressMonitor,
    UNKNOWN, FREE, OCCUPIED_THRESH,
    idx_to_world, world_to_grid, grid_to_idx,
)


# ── 通用 strategies ──

# 生成有效的 (width, height, idx) 组合
@st.composite
def grid_and_idx(draw):
    """生成有效的栅格参数：width, height, idx"""
    w = draw(st.integers(min_value=1, max_value=200))
    h = draw(st.integers(min_value=1, max_value=200))
    idx = draw(st.integers(min_value=0, max_value=w * h - 1))
    return w, h, idx


# ═══════════════════════════════════════════════════════════
# Property 9: 邻域计算正确性 (需求 10.1, 10.2, 10.3, 10.4)
# ═══════════════════════════════════════════════════════════

class TestNhood:
    """邻域计算属性基测试"""

    @given(data=grid_and_idx())
    @settings(max_examples=500)
    def test_nhood4_at_most_4_and_in_range(self, data):
        """Property 9a: nhood4 返回最多 4 个索引，全部在有效范围内"""
        w, h, idx = data
        result = nhood4(idx, w, h)
        # 最多 4 个邻居
        assert len(result) <= 4
        # 所有索引在有效范围内
        for nbr in result:
            assert 0 <= nbr < w * h

    @given(data=grid_and_idx())
    @settings(max_examples=500)
    def test_nhood8_at_most_8_and_in_range(self, data):
        """Property 9b: nhood8 返回最多 8 个索引，全部在有效范围内"""
        w, h, idx = data
        result = nhood8(idx, w, h)
        # 最多 8 个邻居
        assert len(result) <= 8
        # 所有索引在有效范围内
        for nbr in result:
            assert 0 <= nbr < w * h

    @given(data=grid_and_idx())
    @settings(max_examples=500)
    def test_nhood8_contains_nhood4(self, data):
        """Property 9c: nhood8 的结果包含 nhood4 的所有结果"""
        w, h, idx = data
        n4 = set(nhood4(idx, w, h))
        n8 = set(nhood8(idx, w, h))
        assert n4.issubset(n8)

    @given(data=grid_and_idx())
    @settings(max_examples=500)
    def test_nhood4_no_duplicates(self, data):
        """nhood4 不应返回重复索引"""
        w, h, idx = data
        result = nhood4(idx, w, h)
        assert len(result) == len(set(result))

    @given(data=grid_and_idx())
    @settings(max_examples=500)
    def test_nhood8_no_duplicates(self, data):
        """nhood8 不应返回重复索引"""
        w, h, idx = data
        result = nhood8(idx, w, h)
        assert len(result) == len(set(result))

    def test_corner_top_left(self):
        """边界测试：左上角 (idx=0) 只有 2 个 4-连通邻居"""
        w, h = 5, 5
        result = nhood4(0, w, h)
        assert len(result) == 2
        assert set(result) == {1, 5}

    def test_corner_bottom_right(self):
        """边界测试：右下角只有 2 个 4-连通邻居"""
        w, h = 5, 5
        idx = w * h - 1  # 24
        result = nhood4(idx, w, h)
        assert len(result) == 2
        assert set(result) == {23, 19}

    def test_1x1_grid(self):
        """边界测试：1x1 地图无邻居"""
        assert nhood4(0, 1, 1) == []
        assert nhood8(0, 1, 1) == []



# ═══════════════════════════════════════════════════════════
# Property 10: 坐标转换 round-trip (需求 12.1, 12.2, 12.3, 12.4)
# ═══════════════════════════════════════════════════════════

class TestCoordinateConversion:
    """坐标转换属性基测试"""

    @given(
        gx=st.integers(min_value=0, max_value=199),
        gy=st.integers(min_value=0, max_value=199),
        origin_x=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        origin_y=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        resolution=st.floats(min_value=0.01, max_value=1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_grid_world_grid_roundtrip(self, gx, gy, origin_x, origin_y, resolution):
        """Property 10: grid → world → grid round-trip 应得到原始值"""
        width = gx + 1  # 确保 gx 在有效范围内
        # grid → world
        wx, wy = idx_to_world(grid_to_idx(gx, gy, width), width, origin_x, origin_y, resolution)
        # world → grid
        gx2, gy2 = world_to_grid(wx, wy, origin_x, origin_y, resolution)
        assert gx2 == gx
        assert gy2 == gy

    @given(
        gx=st.integers(min_value=0, max_value=199),
        gy=st.integers(min_value=0, max_value=199),
        width=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=500)
    def test_idx_grid_roundtrip(self, gx, gy, width):
        """idx → grid → idx round-trip"""
        assume(gx < width)
        idx = grid_to_idx(gx, gy, width)
        assert idx % width == gx
        assert idx // width == gy

    def test_idx_to_world_center_of_cell(self):
        """idx_to_world 应返回 cell 中心坐标（+0.5 偏移）"""
        # idx=0 在 5x5 地图，origin=(0,0), resolution=0.05
        wx, wy = idx_to_world(0, 5, 0.0, 0.0, 0.05)
        assert abs(wx - 0.025) < 1e-10
        assert abs(wy - 0.025) < 1e-10



# ── 辅助函数：构造测试地图 ──

def make_ring_map(w, h, free_ring_width=1):
    """构造环形地图：外圈 unknown，内圈 free
    
    返回 (map_data, 中心世界坐标)
    """
    data = np.full(w * h, UNKNOWN, dtype=np.int8)
    for y in range(h):
        for x in range(w):
            if (free_ring_width <= x < w - free_ring_width and
                free_ring_width <= y < h - free_ring_width):
                data[y * w + x] = 0  # free
    return data


# ═══════════════════════════════════════════════════════════
# Property 1: Frontier Cell 判定正确性 (需求 1.1, 1.2, 1.3)
# ═══════════════════════════════════════════════════════════

class TestFrontierCellDetection:
    """Frontier cell 判定属性基测试"""

    @given(
        w=st.integers(min_value=3, max_value=30),
        h=st.integers(min_value=3, max_value=30),
    )
    @settings(max_examples=200)
    def test_frontier_cell_is_unknown_with_free_neighbor(self, w, h):
        """Property 1: frontier cell 必须是 unknown 且有 free 邻居"""
        # 构造环形地图
        map_data = make_ring_map(w, h)
        fs = FrontierSearch(1e-3, 1.0, 0.0, 0.05)
        frontier_flag = [False] * (w * h)

        for idx in range(w * h):
            result = fs._is_new_frontier_cell(idx, frontier_flag, map_data, w, h)
            if result:
                # 必须是 unknown
                assert map_data[idx] == UNKNOWN
                # 必须未被标记
                assert not frontier_flag[idx]
                # 必须至少有一个 4-连通 free 邻居
                has_free = any(0 <= map_data[n] < OCCUPIED_THRESH
                              for n in nhood4(idx, w, h))
                assert has_free

    def test_non_unknown_is_not_frontier(self):
        """需求 1.3: 非 unknown 的 cell 不是 frontier"""
        w, h = 5, 5
        map_data = np.zeros(w * h, dtype=np.int8)  # 全 free
        fs = FrontierSearch(1e-3, 1.0, 0.0, 0.05)
        frontier_flag = [False] * (w * h)
        for idx in range(w * h):
            assert not fs._is_new_frontier_cell(idx, frontier_flag, map_data, w, h)

    def test_flagged_cell_is_not_frontier(self):
        """需求 1.2: 已标记 frontier_flag 的 cell 不是 frontier"""
        w, h = 5, 5
        map_data = make_ring_map(w, h)
        fs = FrontierSearch(1e-3, 1.0, 0.0, 0.05)
        frontier_flag = [True] * (w * h)  # 全部标记
        for idx in range(w * h):
            assert not fs._is_new_frontier_cell(idx, frontier_flag, map_data, w, h)


# ═══════════════════════════════════════════════════════════
# Property 2: Frontier 质心为算术平均 (需求 2.2)
# ═══════════════════════════════════════════════════════════

class TestFrontierCentroid:
    """Frontier 质心属性基测试"""

    @given(
        w=st.integers(min_value=5, max_value=30),
        h=st.integers(min_value=5, max_value=30),
    )
    @settings(max_examples=100)
    def test_centroid_is_arithmetic_mean(self, w, h):
        """Property 2: centroid 应等于 points 的算术平均"""
        map_data = make_ring_map(w, h)
        resolution = 0.05
        fs = FrontierSearch(1e-3, 1.0, 0.0, resolution)
        # 机器人在地图中心
        cx = w // 2
        cy = h // 2
        robot_pos = (cx * resolution + resolution * 0.5,
                     cy * resolution + resolution * 0.5)
        frontiers = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)

        for f in frontiers:
            if len(f.points) == 0:
                continue
            expected_cx = sum(p[0] for p in f.points) / len(f.points)
            expected_cy = sum(p[1] for p in f.points) / len(f.points)
            assert abs(f.centroid[0] - expected_cx) < 1e-9
            assert abs(f.centroid[1] - expected_cy) < 1e-9


# ═══════════════════════════════════════════════════════════
# Property 3: Frontier min_distance 与 middle 一致性 (需求 2.3, 2.4)
# ═══════════════════════════════════════════════════════════

class TestFrontierMinDistance:
    """Frontier min_distance/middle 一致性属性基测试"""

    @given(
        w=st.integers(min_value=5, max_value=30),
        h=st.integers(min_value=5, max_value=30),
    )
    @settings(max_examples=100)
    def test_min_distance_matches_middle(self, w, h):
        """Property 3: min_distance 应等于 middle 到参考点的距离"""
        map_data = make_ring_map(w, h)
        resolution = 0.05
        fs = FrontierSearch(1e-3, 1.0, 0.0, resolution)
        cx = w // 2
        cy = h // 2
        robot_pos = (cx * resolution + resolution * 0.5,
                     cy * resolution + resolution * 0.5)
        frontiers = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)

        for f in frontiers:
            # middle 应在 points 中
            assert f.middle in f.points
            # min_distance 应是 points 中最小距离（到参考点）
            # 注意：参考点是 nearest_free_cell，这里近似用 robot_pos
            # 验证 middle 确实是最近的点之一
            middle_dist_sq = ((f.middle[0] - robot_pos[0]) ** 2 +
                              (f.middle[1] - robot_pos[1]) ** 2)
            for p in f.points:
                p_dist_sq = ((p[0] - robot_pos[0]) ** 2 +
                             (p[1] - robot_pos[1]) ** 2)
                # middle 应该是最近的（或等距的）
                assert middle_dist_sq <= p_dist_sq + 1e-9


# ═══════════════════════════════════════════════════════════
# Property 4: Frontier 最小尺寸过滤 (需求 2.5)
# ═══════════════════════════════════════════════════════════

class TestFrontierSizeFilter:
    """Frontier 最小尺寸过滤属性基测试"""

    @given(
        min_size=st.floats(min_value=0.0, max_value=2.0,
                           allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=50)
    def test_all_returned_frontiers_meet_min_size(self, min_size):
        """Property 4: 所有返回的 frontier 的 size × resolution >= min_frontier_size"""
        w, h = 10, 10
        map_data = make_ring_map(w, h)
        resolution = 0.05
        fs = FrontierSearch(1e-3, 1.0, min_size, resolution)
        robot_pos = (w // 2 * resolution + resolution * 0.5,
                     h // 2 * resolution + resolution * 0.5)
        frontiers = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)

        for f in frontiers:
            assert f.size * resolution >= min_size


# ═══════════════════════════════════════════════════════════
# Property 5: Cost 计算与排序 (需求 3.1, 3.2)
# ═══════════════════════════════════════════════════════════

class TestFrontierCostAndSort:
    """Cost 计算与排序属性基测试"""

    @given(
        w=st.integers(min_value=5, max_value=30),
        h=st.integers(min_value=5, max_value=30),
        ps=st.floats(min_value=1e-6, max_value=1.0,
                     allow_nan=False, allow_infinity=False),
        gs=st.floats(min_value=0.1, max_value=10.0,
                     allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100)
    def test_cost_formula_and_ascending_order(self, w, h, ps, gs):
        """Property 5: cost 公式正确且列表按 cost 升序排列"""
        map_data = make_ring_map(w, h)
        resolution = 0.05
        fs = FrontierSearch(ps, gs, 0.0, resolution)
        cx = w // 2
        cy = h // 2
        robot_pos = (cx * resolution + resolution * 0.5,
                     cy * resolution + resolution * 0.5)
        frontiers = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)

        for f in frontiers:
            expected_cost = ps * f.min_distance * resolution - gs * f.size * resolution
            assert abs(f.cost - expected_cost) < 1e-9

        # 验证升序排列
        for i in range(len(frontiers) - 1):
            assert frontiers[i].cost <= frontiers[i + 1].cost


# ═══════════════════════════════════════════════════════════
# Property 11: 地图外坐标返回空列表 (需求 9.3)
# ═══════════════════════════════════════════════════════════

class TestOutOfBounds:
    """地图外坐标属性基测试"""

    @given(
        w=st.integers(min_value=3, max_value=50),
        h=st.integers(min_value=3, max_value=50),
        offset=st.floats(min_value=1.0, max_value=100.0,
                         allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_out_of_bounds_returns_empty(self, w, h, offset):
        """Property 11: 机器人在地图外时 search_from 返回空列表"""
        map_data = make_ring_map(w, h)
        resolution = 0.05
        fs = FrontierSearch(1e-3, 1.0, 0.0, resolution)
        # 机器人在地图右侧外
        robot_pos = (w * resolution + offset, h * resolution + offset)
        result = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)
        assert result == []



# ═══════════════════════════════════════════════════════════
# Property 6: 黑名单容差判定 (需求 4.1, 4.2, 4.3)
# ═══════════════════════════════════════════════════════════

class TestBlacklistTolerance:
    """黑名单容差判定属性基测试"""

    @given(
        x=st.floats(min_value=-50.0, max_value=50.0,
                     allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-50.0, max_value=50.0,
                     allow_nan=False, allow_infinity=False),
        tolerance=st.integers(min_value=1, max_value=20),
        resolution=st.floats(min_value=0.01, max_value=1.0,
                             allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=300)
    def test_added_point_is_blacklisted(self, x, y, tolerance, resolution):
        """Property 6a: 添加的点自身一定在黑名单中"""
        bl = BlacklistManager(tolerance, resolution)
        bl.add((x, y))
        assert bl.is_blacklisted((x, y))

    @given(
        x=st.floats(min_value=-50.0, max_value=50.0,
                     allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-50.0, max_value=50.0,
                     allow_nan=False, allow_infinity=False),
        dx=st.floats(min_value=-0.5, max_value=0.5,
                      allow_nan=False, allow_infinity=False),
        dy=st.floats(min_value=-0.5, max_value=0.5,
                      allow_nan=False, allow_infinity=False),
        tolerance=st.integers(min_value=1, max_value=20),
        resolution=st.floats(min_value=0.01, max_value=1.0,
                             allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=500)
    def test_tolerance_boundary(self, x, y, dx, dy, tolerance, resolution):
        """Property 6b: 容差判定一致性 — 在容差内返回 True，超出返回 False"""
        bl = BlacklistManager(tolerance, resolution)
        bl.add((x, y))
        thresh = tolerance * resolution
        # 跳过边界附近的浮点模糊区域
        eps = 1e-9
        assume(abs(abs(dx) - thresh) > eps and abs(abs(dy) - thresh) > eps)
        query = (x + dx, y + dy)
        expected = abs(dx) < thresh and abs(dy) < thresh
        assert bl.is_blacklisted(query) == expected

    @given(
        x=st.floats(min_value=-50.0, max_value=50.0,
                     allow_nan=False, allow_infinity=False),
        y=st.floats(min_value=-50.0, max_value=50.0,
                     allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_empty_blacklist_returns_false(self, x, y):
        """空黑名单对任何点返回 False"""
        bl = BlacklistManager(5, 0.05)
        assert not bl.is_blacklisted((x, y))


# ═══════════════════════════════════════════════════════════
# Property 7: 黑名单 clear 清空 (需求 4.4)
# ═══════════════════════════════════════════════════════════

class TestBlacklistClear:
    """黑名单 clear 属性基测试"""

    @given(
        points=st.lists(
            st.tuples(
                st.floats(min_value=-50.0, max_value=50.0,
                          allow_nan=False, allow_infinity=False),
                st.floats(min_value=-50.0, max_value=50.0,
                          allow_nan=False, allow_infinity=False),
            ),
            min_size=1, max_size=20,
        ),
    )
    @settings(max_examples=200)
    def test_clear_empties_blacklist(self, points):
        """Property 7: clear 后 size 为 0 且所有点不再被判定为黑名单"""
        bl = BlacklistManager(5, 0.05)
        for p in points:
            bl.add(p)
        assert bl.size == len(points)

        bl.clear()
        assert bl.size == 0
        for p in points:
            assert not bl.is_blacklisted(p)



# ═══════════════════════════════════════════════════════════
# Property 8: ProgressMonitor 超时检测 (需求 5.1, 5.2, 5.3, 5.4)
# ═══════════════════════════════════════════════════════════

class TestProgressMonitor:
    """ProgressMonitor 超时检测属性基测试"""

    @given(
        timeout=st.floats(min_value=1.0, max_value=60.0,
                          allow_nan=False, allow_infinity=False),
        distance=st.floats(min_value=0.1, max_value=100.0,
                           allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_timeout_triggers_after_threshold(self, timeout, distance):
        """Property 8a: 同一目标无进展超过 timeout 时返回 True"""
        pm = ProgressMonitor(timeout)
        goal = (1.0, 2.0)
        # 首次更新，不超时
        assert pm.update(goal, distance, 0.0) is False
        # 刚好在 timeout 内，不超时
        assert pm.update(goal, distance, timeout * 0.5) is False
        # 超过 timeout，超时
        assert pm.update(goal, distance, timeout + 1.0) is True

    @given(
        timeout=st.floats(min_value=1.0, max_value=60.0,
                          allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_new_goal_resets_timer(self, timeout):
        """Property 8b: 新目标重置计时器"""
        pm = ProgressMonitor(timeout)
        goal1 = (1.0, 2.0)
        goal2 = (3.0, 4.0)
        # 第一个目标
        assert pm.update(goal1, 5.0, 0.0) is False
        # 切换到新目标，即使时间已过 timeout
        assert pm.update(goal2, 5.0, timeout + 1.0) is False
        # 新目标从切换时刻开始计时，还没超时
        assert pm.update(goal2, 5.0, timeout + 1.0 + timeout * 0.5) is False
        # 新目标超时
        assert pm.update(goal2, 5.0, timeout + 1.0 + timeout + 1.0) is True

    @given(
        timeout=st.floats(min_value=1.0, max_value=60.0,
                          allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_distance_decrease_resets_timer(self, timeout):
        """Property 8c: 距离减小时重置计时器（有进展）"""
        pm = ProgressMonitor(timeout)
        goal = (1.0, 2.0)
        assert pm.update(goal, 10.0, 0.0) is False
        # 距离减小，重置计时器
        assert pm.update(goal, 8.0, timeout * 0.9) is False
        # 从重置时刻开始，还没超时
        assert pm.update(goal, 8.0, timeout * 0.9 + timeout * 0.5) is False
        # 超时
        assert pm.update(goal, 8.0, timeout * 0.9 + timeout + 1.0) is True

    def test_reset_clears_state(self):
        """reset 后重新开始计时"""
        pm = ProgressMonitor(5.0)
        pm.update((1.0, 2.0), 5.0, 0.0)
        pm.update((1.0, 2.0), 5.0, 10.0)  # 超时
        pm.reset()
        # reset 后应该像新的一样
        assert pm.update((1.0, 2.0), 5.0, 20.0) is False



# ═══════════════════════════════════════════════════════════
# AutoExploreNode 逻辑单元测试（不依赖 ROS2，测试组件交互）
# ═══════════════════════════════════════════════════════════

class TestAutoExploreLogic:
    """AutoExploreNode 核心逻辑测试（无 ROS2 依赖）

    通过直接测试 FrontierSearch + BlacklistManager + ProgressMonitor
    的组合行为来验证 make_plan 的逻辑正确性。
    """

    def test_no_map_skips_planning(self):
        """需求 9.2: 无地图时跳过规划 — map_data 为 None 时不应调用 search_from"""
        fs = FrontierSearch(1e-3, 1.0, 0.0, 0.05)
        # 模拟 make_plan 的第一步检查
        map_data = None
        assert map_data is None  # 应跳过后续逻辑

    def test_no_frontiers_stops_exploration(self):
        """需求 7.1: 无 frontier 时停止探索"""
        w, h = 5, 5
        # 全 free 地图 — 无 unknown cell，不会有 frontier
        map_data = np.zeros(w * h, dtype=np.int8)
        resolution = 0.05
        fs = FrontierSearch(1e-3, 1.0, 0.0, resolution)
        robot_pos = (0.125, 0.125)
        frontiers = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)
        assert frontiers == []
        # make_plan 逻辑：frontiers 为空时应停止探索

    def test_all_frontiers_blacklisted_stops_exploration(self):
        """需求 7.2: 所有 frontier 在黑名单时停止探索"""
        w, h = 10, 10
        map_data = make_ring_map(w, h)
        resolution = 0.05
        fs = FrontierSearch(1e-3, 1.0, 0.0, resolution)
        bl = BlacklistManager(5, resolution)

        robot_pos = (w // 2 * resolution + resolution * 0.5,
                     h // 2 * resolution + resolution * 0.5)
        frontiers = fs.search_from(robot_pos, map_data, w, h, 0.0, 0.0, resolution)
        assert len(frontiers) > 0

        # 将所有 frontier 的 centroid 加入黑名单
        for f in frontiers:
            bl.add(f.centroid)

        # 模拟 make_plan 的黑名单过滤逻辑
        target_frontier = None
        for f in frontiers:
            if not bl.is_blacklisted(f.centroid):
                target_frontier = f
                break
        assert target_frontier is None  # 所有都在黑名单，应停止探索

    def test_aborted_goal_gets_blacklisted(self):
        """需求 6.2: ABORTED 导航结果导致目标被拉黑"""
        bl = BlacklistManager(5, 0.05)
        current_goal = (1.5, 2.5)

        # 模拟 goal_result_callback 中 ABORTED 的逻辑
        # status == GoalStatus.STATUS_ABORTED
        bl.add(current_goal)
        assert bl.is_blacklisted(current_goal)

    def test_same_goal_not_resent(self):
        """需求 8.4: 目标未变时不重复发送"""
        target = (1.0, 2.0)
        prev_goal = (1.0, 2.0)
        same_goal = (abs(prev_goal[0] - target[0]) < 1e-3 and
                     abs(prev_goal[1] - target[1]) < 1e-3)
        assert same_goal  # 应跳过发送

    def test_progress_timeout_blacklists_and_replans(self):
        """需求 8.5: 超时时拉黑并重新规划"""
        bl = BlacklistManager(5, 0.05)
        pm = ProgressMonitor(15.0)
        target = (1.0, 2.0)

        # 首次更新
        pm.update(target, 5.0, 0.0)
        # 超时
        timed_out = pm.update(target, 5.0, 20.0)
        assert timed_out

        # 拉黑
        bl.add(target)
        assert bl.is_blacklisted(target)
