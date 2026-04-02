#!/usr/bin/env python3
"""自主探索建图 v4 — 借鉴 m-explore-ros2 (explore_lite) 核心算法

核心改进（对比 v3）：
  1. Frontier 聚类：BFS 找连通 frontier cell，合并为 cluster，选 cluster 中心
  2. 黑名单机制：导航失败/超时的 frontier 加入黑名单（5 格容差）
  3. Progress 超时：同一目标无进展时自动加入黑名单并换目标
  4. Cost 函数：distance × potential_scale - size × gain_scale（近+大优先）
  5. 基于 OccupancyGrid（/map），不依赖 costmap_2d C++ 库

参考：robo-friends/m-explore-ros2 (BSD License)

用法：
  python3 scripts/auto_explore.py
"""
import rclpy
import rclpy.parameter
import numpy as np
import math
from collections import deque
from dataclasses import dataclass, field
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from nav_msgs.msg import OccupancyGrid
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from action_msgs.msg import GoalStatus
import tf2_ros

# ── 参数 ──
POTENTIAL_SCALE = 1e-3   # 距离权重（越小越不在意距离）
GAIN_SCALE = 1.0         # 面积权重（越大越偏好大 frontier）
MIN_FRONTIER_SIZE = 0.3  # 最小 frontier 尺寸（米），仿真中适当降低
PROGRESS_TIMEOUT = 30.0  # 同一目标无进展超时（秒），仿真环境需要更长
PLANNER_HZ = 0.5         # 规划频率（Hz）
BLACKLIST_TOLERANCE = 5   # 黑名单容差（格子数）
MAX_ABORT_RETRIES = 2    # ABORTED 后最大重试次数（超过才拉黑）
MAX_BLACKLIST_RESETS = 3  # 黑名单全满时最大清空重试轮数
OCCUPIED_THRESH = 50
FREE = 0
UNKNOWN = -1


@dataclass
class Frontier:
    """一个 frontier cluster"""
    size: int = 0
    min_distance: float = float('inf')
    cost: float = 0.0
    centroid: tuple[float, float] = (0.0, 0.0)
    middle: tuple[float, float] = (0.0, 0.0)
    points: list[tuple[float, float]] = field(default_factory=list)


def nhood4(idx, w, h):
    """4-连通邻居"""
    out = []
    if idx % w > 0: out.append(idx - 1)
    if idx % w < w - 1: out.append(idx + 1)
    if idx >= w: out.append(idx - w)
    if idx < w * (h - 1): out.append(idx + w)
    return out


def nhood8(idx, w, h):
    """8-连通邻居"""
    out = nhood4(idx, w, h)
    if idx % w > 0 and idx >= w: out.append(idx - 1 - w)
    if idx % w > 0 and idx < w * (h - 1): out.append(idx - 1 + w)
    if idx % w < w - 1 and idx >= w: out.append(idx + 1 - w)
    if idx % w < w - 1 and idx < w * (h - 1): out.append(idx + 1 + w)
    return out


# ── 坐标转换工具函数 ──

def idx_to_world(idx, width, origin_x, origin_y, resolution):
    """一维索引 → 世界坐标 (wx, wy)"""
    gx = idx % width
    gy = idx // width
    wx = origin_x + (gx + 0.5) * resolution
    wy = origin_y + (gy + 0.5) * resolution
    return (wx, wy)


def world_to_grid(wx, wy, origin_x, origin_y, resolution):
    """世界坐标 → 栅格坐标 (gx, gy)"""
    gx = int((wx - origin_x) / resolution)
    gy = int((wy - origin_y) / resolution)
    return (gx, gy)


def grid_to_idx(gx, gy, width):
    """栅格坐标 → 一维索引"""
    return gy * width + gx


# ── Frontier 搜索核心模块 ──

class FrontierSearch:
    """Frontier 检测、聚类与 cost 计算

    从 OccupancyGrid 中检测所有 frontier cell，通过 BFS 聚类为 cluster，
    使用 cost 函数排序后返回。
    """

    def __init__(self, potential_scale: float, gain_scale: float,
                 min_frontier_size: float, resolution: float):
        self.potential_scale = potential_scale
        self.gain_scale = gain_scale
        self.min_frontier_size = min_frontier_size
        self.resolution = resolution

    def _is_new_frontier_cell(self, idx: int, frontier_flag: list[bool],
                              map_data: np.ndarray, width: int, height: int) -> bool:
        """判断 cell 是否为新的 frontier cell

        条件：值为 UNKNOWN(-1) 且未标记 frontier_flag 且至少有一个 4-连通 free 邻居
        """
        # 必须是 unknown 且未被标记
        if map_data[idx] != UNKNOWN or frontier_flag[idx]:
            return False
        # 至少有一个 4-连通邻居是 free
        for nbr in nhood4(idx, width, height):
            if 0 <= map_data[nbr] < OCCUPIED_THRESH:
                return True
        return False

    def _build_new_frontier(self, initial_cell: int, reference: int,
                            frontier_flag: list[bool],
                            map_data: np.ndarray, width: int, height: int,
                            origin_x: float, origin_y: float,
                            resolution: float) -> Frontier:
        """从一个 frontier cell 出发，BFS 聚类所有 8-连通的 frontier cell

        参数:
            initial_cell: 起始 frontier cell 的一维索引
            reference: 参考点（机器人附近 free cell）的一维索引，用于计算距离
            frontier_flag: frontier 标记数组，已标记的 cell 不会重复处理
            map_data: 地图数据
            width, height: 地图尺寸
            origin_x, origin_y: 地图原点世界坐标
            resolution: 地图分辨率
        """
        frontier = Frontier()

        # 参考点世界坐标
        ref_x, ref_y = idx_to_world(reference, width, origin_x, origin_y, resolution)

        # 初始 cell 自身也要计入 frontier
        init_wx, init_wy = idx_to_world(initial_cell, width, origin_x, origin_y, resolution)
        frontier.size = 1
        frontier.points.append((init_wx, init_wy))
        cx_sum = init_wx
        cy_sum = init_wy

        # 计算初始 cell 到参考点的距离
        init_dist = math.sqrt((ref_x - init_wx) ** 2 + (ref_y - init_wy) ** 2)
        frontier.min_distance = init_dist
        frontier.middle = (init_wx, init_wy)

        bfs = deque([initial_cell])

        while bfs:
            idx = bfs.popleft()

            for nbr in nhood8(idx, width, height):
                if self._is_new_frontier_cell(nbr, frontier_flag, map_data, width, height):
                    frontier_flag[nbr] = True
                    wx, wy = idx_to_world(nbr, width, origin_x, origin_y, resolution)

                    frontier.points.append((wx, wy))
                    frontier.size += 1
                    cx_sum += wx
                    cy_sum += wy

                    # 更新最近距离
                    dist = math.sqrt((ref_x - wx) ** 2 + (ref_y - wy) ** 2)
                    if dist < frontier.min_distance:
                        frontier.min_distance = dist
                        frontier.middle = (wx, wy)

                    bfs.append(nbr)

        # 质心为所有点的算术平均
        frontier.centroid = (cx_sum / frontier.size, cy_sum / frontier.size)
        return frontier

    def _frontier_cost(self, frontier: Frontier) -> float:
        """计算 frontier 的 cost 值

        公式: potential_scale × min_distance × resolution - gain_scale × size × resolution
        """
        return (self.potential_scale * frontier.min_distance * self.resolution
                - self.gain_scale * frontier.size * self.resolution)

    @staticmethod
    def _nearest_free_cell(start: int, map_data: np.ndarray,
                           width: int, height: int) -> int:
        """BFS 找到距 start 最近的 free cell

        如果 start 本身就是 free cell，直接返回 start。
        """
        if 0 <= map_data[start] < OCCUPIED_THRESH:
            return start

        visited = [False] * (width * height)
        visited[start] = True
        bfs = deque([start])

        while bfs:
            idx = bfs.popleft()
            for nbr in nhood4(idx, width, height):
                if not visited[nbr]:
                    visited[nbr] = True
                    if 0 <= map_data[nbr] < OCCUPIED_THRESH:
                        return nbr
                    bfs.append(nbr)

        # 无 free cell 时返回 start
        return start

    def search_from(self, robot_pos: tuple[float, float],
                    map_data: np.ndarray, width: int, height: int,
                    origin_x: float, origin_y: float,
                    resolution: float) -> list[Frontier]:
        """从机器人位置出发，BFS 检测所有 frontier 并聚类返回

        步骤:
        1. 将机器人世界坐标转为 grid 坐标，超出地图范围返回空列表
        2. 找到最近的 free cell 作为 BFS 起点
        3. BFS 遍历 free space，遇到 frontier cell 时聚类
        4. 过滤小于 min_frontier_size 的 cluster
        5. 计算 cost 并按升序排列返回
        """
        # 将机器人世界坐标转为 grid 坐标
        mx, my = world_to_grid(robot_pos[0], robot_pos[1],
                               origin_x, origin_y, resolution)

        # 机器人在地图外时返回空列表
        if not (0 <= mx < width and 0 <= my < height):
            return []

        total = width * height
        frontier_flag = [False] * total
        visited_flag = [False] * total

        # 找到最近的 free cell 作为 BFS 起点
        start = self._nearest_free_cell(grid_to_idx(mx, my, width),
                                        map_data, width, height)
        bfs = deque([start])
        visited_flag[start] = True

        frontier_list: list[Frontier] = []

        while bfs:
            idx = bfs.popleft()

            for nbr in nhood4(idx, width, height):
                if visited_flag[nbr]:
                    continue

                if 0 <= map_data[nbr] < OCCUPIED_THRESH:
                    # free cell，加入 BFS 队列继续搜索
                    visited_flag[nbr] = True
                    bfs.append(nbr)
                elif self._is_new_frontier_cell(nbr, frontier_flag,
                                                map_data, width, height):
                    # frontier cell，开始聚类
                    frontier_flag[nbr] = True
                    new_frontier = self._build_new_frontier(
                        nbr, start, frontier_flag,
                        map_data, width, height,
                        origin_x, origin_y, resolution)
                    if new_frontier.size * resolution >= self.min_frontier_size:
                        frontier_list.append(new_frontier)

        # 计算 cost 并排序
        for f in frontier_list:
            f.cost = self._frontier_cost(f)
        frontier_list.sort(key=lambda f: f.cost)

        return frontier_list


# ── 黑名单管理模块 ──

class BlacklistManager:
    """管理导航失败/超时的 frontier 黑名单

    使用 tolerance × resolution 容差判定坐标是否在黑名单内。
    """

    def __init__(self, tolerance: int, resolution: float):
        self._tolerance = tolerance
        self._resolution = resolution
        self._points: list[tuple[float, float]] = []

    def add(self, point: tuple[float, float]) -> None:
        """添加世界坐标点到黑名单"""
        self._points.append(point)

    def is_blacklisted(self, point: tuple[float, float]) -> bool:
        """检查点是否在黑名单容差范围内

        当 x 和 y 方向差值均小于 tolerance × resolution 时返回 True。
        """
        thresh = self._tolerance * self._resolution
        for bl in self._points:
            if (abs(point[0] - bl[0]) < thresh and
                    abs(point[1] - bl[1]) < thresh):
                return True
        return False

    def clear(self) -> None:
        """清空所有黑名单点"""
        self._points.clear()

    @property
    def size(self) -> int:
        """当前黑名单大小"""
        return len(self._points)


# ── 进展超时检测模块 ──

class ProgressMonitor:
    """检测同一目标是否有进展

    目标变化或距离减小时重置计时器，超时返回 True。
    """

    def __init__(self, timeout: float):
        self._timeout = timeout
        self._goal: tuple[float, float] | None = None
        self._distance: float = float('inf')
        self._start_time: float = 0.0

    def update(self, goal: tuple[float, float], distance: float,
               current_time: float) -> bool:
        """更新目标和距离，返回是否超时

        - 目标变化时重置计时器
        - 距离减小时重置计时器（表示有进展）
        - 超时返回 True
        """
        if self._goal is None or goal != self._goal:
            # 新目标，重置
            self._goal = goal
            self._distance = distance
            self._start_time = current_time
            return False

        if distance < self._distance:
            # 有进展，重置计时器
            self._distance = distance
            self._start_time = current_time
            return False

        # 检查超时
        return (current_time - self._start_time) > self._timeout

    def reset(self) -> None:
        """重置所有状态"""
        self._goal = None
        self._distance = float('inf')
        self._start_time = 0.0


# ── ROS2 主节点 ──

class AutoExploreNode(Node):
    """自主探索建图 ROS2 节点

    协调 FrontierSearch、BlacklistManager、ProgressMonitor，
    通过 Nav2 NavigateToPose 实现自主探索。
    """

    def __init__(self):
        super().__init__('auto_explore')

        # TF2
        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        # Nav2 Action Client
        self._nav_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self.get_logger().info('等待 Nav2 action server...')
        self._nav_client.wait_for_server()
        self.get_logger().info('Nav2 action server 已连接')

        # 地图订阅
        qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            depth=1,
        )
        self.create_subscription(OccupancyGrid, '/map', self._map_callback, qos)

        # 地图缓存
        self._map_data: np.ndarray | None = None
        self._width = 0
        self._height = 0
        self._origin_x = 0.0
        self._origin_y = 0.0
        self._resolution = 0.05

        # 核心模块
        self._search = FrontierSearch(
            POTENTIAL_SCALE, GAIN_SCALE, MIN_FRONTIER_SIZE, self._resolution)
        self._blacklist = BlacklistManager(BLACKLIST_TOLERANCE, self._resolution)
        self._progress = ProgressMonitor(PROGRESS_TIMEOUT)

        # 状态
        self._prev_goal: tuple[float, float] | None = None
        self._prev_distance = float('inf')
        self._last_progress_time = self.get_clock().now()
        self._current_goal: tuple[float, float] | None = None
        self._abort_counts: dict[tuple[float, float], int] = {}  # 目标 → ABORT 次数
        self._blacklist_reset_count = 0  # 黑名单清空次数

        # 定时器
        self.create_timer(1.0 / PLANNER_HZ, self._make_plan)
        self.get_logger().info('AutoExploreNode 已启动')

    def _map_callback(self, msg: OccupancyGrid) -> None:
        """缓存最新地图数据"""
        self._width = msg.info.width
        self._height = msg.info.height
        self._resolution = msg.info.resolution
        self._origin_x = msg.info.origin.position.x
        self._origin_y = msg.info.origin.position.y
        self._map_data = np.array(msg.data, dtype=np.int8)
        # 更新模块的 resolution
        self._search.resolution = self._resolution
        self._blacklist._resolution = self._resolution

    def _get_robot_pose(self) -> tuple[float, float] | None:
        """通过 TF2 获取机器人位姿，失败返回 None"""
        try:
            t = self._tf_buffer.lookup_transform(
                'map', 'base_link', rclpy.time.Time())
            return (t.transform.translation.x, t.transform.translation.y)
        except (tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException) as e:
            self.get_logger().warn(f'TF 查询失败: {e}')
            return None

    def _make_plan(self) -> None:
        """主规划循环"""
        # 检查地图
        if self._map_data is None:
            self.get_logger().info('等待地图数据...')
            return

        # 获取位姿
        pose = self._get_robot_pose()
        if pose is None:
            return

        # 搜索 frontier
        frontiers = self._search.search_from(
            pose, self._map_data, self._width, self._height,
            self._origin_x, self._origin_y, self._resolution)

        if not frontiers:
            self.get_logger().info('无 frontier，探索完成')
            return

        # 找第一个不在黑名单的 frontier
        target_frontier = None
        for f in frontiers:
            if not self._blacklist.is_blacklisted(f.centroid):
                target_frontier = f
                break

        if target_frontier is None:
            if self._blacklist_reset_count < MAX_BLACKLIST_RESETS:
                self._blacklist_reset_count += 1
                self.get_logger().warn(
                    f'所有 frontier 均在黑名单，清空黑名单重试 '
                    f'({self._blacklist_reset_count}/{MAX_BLACKLIST_RESETS})')
                self._blacklist.clear()
                self._abort_counts.clear()
                self._progress.reset()
                return  # 下次定时器触发时重新规划
            self.get_logger().info('所有 frontier 均在黑名单且已达最大重试次数，探索完成')
            return

        target = target_frontier.centroid
        same_goal = (self._prev_goal is not None and
                     abs(self._prev_goal[0] - target[0]) < 1e-3 and
                     abs(self._prev_goal[1] - target[1]) < 1e-3)

        # Progress 超时检查
        now_sec = self.get_clock().now().nanoseconds / 1e9
        timed_out = self._progress.update(target, target_frontier.min_distance, now_sec)

        if timed_out:
            self.get_logger().warn(f'目标 {target} 超时，加入黑名单')
            self._blacklist.add(target)
            self._progress.reset()
            self._make_plan()  # 递归重新规划
            return

        self._prev_goal = target
        self._prev_distance = target_frontier.min_distance

        # 目标未变则不重复发送
        if same_goal:
            return

        self._send_goal(target)

    def _send_goal(self, target: tuple[float, float]) -> None:
        """发送 NavigateToPose 目标"""
        goal_msg = NavigateToPose.Goal()
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = 'map'
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = target[0]
        goal_msg.pose.pose.position.y = target[1]
        goal_msg.pose.pose.orientation.w = 1.0

        self._current_goal = target
        self.get_logger().info(f'发送导航目标: ({target[0]:.2f}, {target[1]:.2f})')

        future = self._nav_client.send_goal_async(goal_msg)
        future.add_done_callback(self._goal_response_callback)

    def _goal_response_callback(self, future) -> None:
        """目标接受回调"""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('导航目标被拒绝')
            return
        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(self._goal_result_callback)

    def _goal_result_callback(self, future) -> None:
        """导航结果回调"""
        result = future.result()
        status = result.status

        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info('导航成功')
            # 成功到达，重置黑名单清空计数
            self._blacklist_reset_count = 0
        elif status == GoalStatus.STATUS_ABORTED:
            if self._current_goal:
                # 量化目标坐标用于计数（避免浮点精度问题）
                key = (round(self._current_goal[0], 2),
                       round(self._current_goal[1], 2))
                self._abort_counts[key] = self._abort_counts.get(key, 0) + 1
                count = self._abort_counts[key]
                if count >= MAX_ABORT_RETRIES:
                    self.get_logger().warn(
                        f'导航被中止 {count} 次，拉黑目标 {self._current_goal}')
                    self._blacklist.add(self._current_goal)
                else:
                    self.get_logger().warn(
                        f'导航被中止（{count}/{MAX_ABORT_RETRIES}），稍后重试')
            self._make_plan()
            return
        elif status == GoalStatus.STATUS_CANCELED:
            self.get_logger().info('导航被取消')
            return

        self._make_plan()


# ── 入口 ──

def main():
    rclpy.init()
    node = AutoExploreNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
