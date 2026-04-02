# 传感器桥接 — 订阅 ROS2 传感器话题，更新机器人状态
# 订阅 /odom 更新位置，/camera/image_raw 用于 VLM 语义标注，/scan 用于障碍物检测（预留）

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Callable

from rclpy.node import Node
from rclpy.parameter import Parameter
from nav_msgs.msg import Odometry
from geometry_msgs.msg import PoseWithCovarianceStamped

logger = logging.getLogger(__name__)


@dataclass
class RobotState:
    """机器人实时状态"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    orientation_w: float = 1.0
    orientation_z: float = 0.0
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0


@dataclass
class CameraFrame:
    """相机帧数据 — 封装图像数据 + 机器人位姿 + 时间戳"""
    image_data: bytes
    robot_pose: tuple[float, float, float]  # (x, y, theta)
    timestamp: float


class SensorBridge(Node):
    """传感器桥接节点 — 订阅 /odom 和 /amcl_pose 更新机器人状态"""

    def __init__(
        self,
        odom_topic: str = "/odom",
        pose_topic: str = "/amcl_pose",
        use_sim_time: bool = True,
        camera_sample_interval: float = 2.0,
    ) -> None:
        super().__init__("mosaic_sensor_bridge")

        if use_sim_time:
            self.set_parameters([
                Parameter("use_sim_time", Parameter.Type.BOOL, True)
            ])

        self.state = RobotState()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._position_callbacks: list[Callable[[float, float], None]] = []

        # 相机帧回调基础设施
        self._camera_callbacks: list[Callable[[CameraFrame], None]] = []
        self._camera_sample_interval: float = camera_sample_interval
        self._last_camera_sample: float = 0.0

        # 订阅里程计
        self.create_subscription(
            Odometry, odom_topic, self._odom_callback, 10
        )

        # 订阅 AMCL 定位（Nav2 输出，精度更高）
        self.create_subscription(
            PoseWithCovarianceStamped, pose_topic, self._pose_callback, 10
        )

        logger.info("SensorBridge 已创建（odom=%s, pose=%s）", odom_topic, pose_topic)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """设置 asyncio 事件循环，用于跨线程投递"""
        self._loop = loop

    def _odom_callback(self, msg: Odometry) -> None:
        """里程计回调 — 更新速度"""
        self.state.linear_velocity = msg.twist.twist.linear.x
        self.state.angular_velocity = msg.twist.twist.angular.z

    def _pose_callback(self, msg: PoseWithCovarianceStamped) -> None:
        """AMCL 定位回调 — 更新位置"""
        pos = msg.pose.pose.position
        ori = msg.pose.pose.orientation
        self.state.x = pos.x
        self.state.y = pos.y
        self.state.z = pos.z
        self.state.orientation_w = ori.w
        self.state.orientation_z = ori.z

        # 通知所有已注册的位置更新回调
        for cb in self._position_callbacks:
            cb(pos.x, pos.y)

    def on_position_update(self, callback: Callable[[float, float], None]) -> None:
        """注册位置更新回调"""
        self._position_callbacks.append(callback)

    def on_camera_frame(self, callback: Callable[[CameraFrame], None]) -> None:
        """注册相机帧回调"""
        self._camera_callbacks.append(callback)

    def _camera_callback(self, image_data: bytes) -> None:
        """相机图像回调 — 按采样频率节流，封装 CameraFrame 并通知订阅者"""
        now = time.time()
        if now - self._last_camera_sample < self._camera_sample_interval:
            return
        self._last_camera_sample = now

        # 计算航向角 theta（从四元数 w, z 分量）
        theta = 2.0 * math.atan2(self.state.orientation_z, self.state.orientation_w)

        frame = CameraFrame(
            image_data=image_data,
            robot_pose=(self.state.x, self.state.y, theta),
            timestamp=now,
        )

        for cb in self._camera_callbacks:
            try:
                cb(frame)
            except Exception as e:
                logger.warning("相机帧回调执行失败: %s", e)

    def get_position(self) -> tuple[float, float]:
        """获取当前 2D 位置"""
        return (self.state.x, self.state.y)
