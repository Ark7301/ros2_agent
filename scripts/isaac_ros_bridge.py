#!/usr/bin/env python3
"""Isaac Sim → Nav2 统一桥接节点 v9

方案：在 LiDAR frame 下累积多帧 → 360° scan
  - LiDAR 是 360° 旋转式，每帧只覆盖 ~60°
  - 在 front_3d_lidar frame 下直接累积（LiDAR 硬件内部已做旋转补偿）
  - 不在 base_link 下累积，避免机器人运动导致畸变
  - scan frame = front_3d_lidar，SLAM 通过 TF 做坐标变换
  - 自发 base_link→front_3d_lidar static TF（纯平移，无旋转）

用法：
  python3 scripts/isaac_ros_bridge.py
"""
import rclpy, math, struct, sys
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from tf2_msgs.msg import TFMessage
from rosgraph_msgs.msg import Clock
from nav_msgs.msg import Odometry
from sensor_msgs.msg import PointCloud2, LaserScan
from geometry_msgs.msg import TransformStamped
import threading

ANGLE_MIN = -math.pi
ANGLE_MAX = math.pi
ANGLE_INC = math.pi / 180.0
NUM_RAYS = int((ANGLE_MAX - ANGLE_MIN) / ANGLE_INC)
RANGE_MIN = 0.15
RANGE_MAX = 25.0
Z_MIN = -0.5
Z_MAX = 0.5
LIDAR_Z = 0.526
SCAN_FRAME = "base_link"
# 累积帧数：每帧~60°，6帧=360°
ACCUM_N = 6

# Nova Carter LiDAR 盲区（Isaac Sim RTX LiDAR 已知 bug，非车身遮挡）
# 盲区: 1°~59°（左前方）和 -180°~-120°（右后方）
# 保持 inf（unknown），不填充 range_max，避免误标 free space
# 机器人旋转后其他角度的 scan 会覆盖这些区域


def quat_to_yaw(q):
    return math.atan2(2.0*(q.w*q.z + q.x*q.y),
                      1.0 - 2.0*(q.y*q.y + q.z*q.z))


class IsaacRosBridge(Node):
    def __init__(self):
        super().__init__("isaac_ros_bridge")
        self._lock = threading.Lock()
        self._sim_stamp = None
        self._pc_parsed = False
        self._x_off = self._y_off = self._z_off = 0

        # 累积 scan（在 LiDAR frame 下，不受机器人运动影响）
        self._ranges = [float('inf')] * NUM_RAYS
        self._frame_count = 0
        # 最新 odom 时间戳（scan 用这个，确保 TF 查询不会 extrapolate）
        self._last_odom_stamp = None

        # 发布者
        self.clock_pub = self.create_publisher(Clock, "/clock", 10)
        self.tf_pub = self.create_publisher(TFMessage, "/tf", 100)
        self.tf_static_pub = self.create_publisher(TFMessage, "/tf_static",
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.TRANSIENT_LOCAL))
        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.scan_pub = self.create_publisher(LaserScan, "/scan",
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE))

        # 订阅者
        qb = QoSProfile(depth=50, reliability=ReliabilityPolicy.BEST_EFFORT,
                         durability=DurabilityPolicy.VOLATILE)
        qr = QoSProfile(depth=50, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        self.create_subscription(TFMessage, "/tf", self._on_tf, qr)
        self.create_subscription(TFMessage, "/tf", self._on_tf, qb)
        self.create_subscription(PointCloud2,
            "/front_3d_lidar/lidar_points", self._on_pc, qb)
        self.create_subscription(Odometry, "/chassis/odom",
            self._on_odom, qb)
        self.create_subscription(Odometry, "/chassis/odom",
            self._on_odom, qr)

        self._clk_n = self._odom_n = self._scan_n = 0
        self._publish_static_tf()
        self.create_timer(5.0, self._publish_static_tf)
        self.get_logger().info(
            f"v9: LiDAR frame 累积 {ACCUM_N} 帧 → 360° scan")

    def _publish_static_tf(self):
        """base_link→front_3d_lidar: 纯平移，无旋转"""
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = "base_link"
        t.child_frame_id = SCAN_FRAME
        t.transform.translation.z = LIDAR_Z
        t.transform.rotation.w = 1.0
        self.tf_static_pub.publish(TFMessage(transforms=[t]))

    def _on_tf(self, msg: TFMessage):
        if not msg.transforms:
            return
        stamp = None
        for t in msg.transforms:
            if t.header.frame_id == "odom" and t.child_frame_id == "base_link":
                continue
            if "base_link" in (t.header.frame_id, t.child_frame_id):
                stamp = t.header.stamp
                break
        if stamp is None:
            return
        with self._lock:
            if (self._sim_stamp and stamp.sec == self._sim_stamp.sec
                    and stamp.nanosec == self._sim_stamp.nanosec):
                return
            self._sim_stamp = stamp
        c = Clock(); c.clock = stamp
        self.clock_pub.publish(c)
        self._clk_n += 1
        if self._clk_n % 500 == 1:
            self.get_logger().info(
                f"sim={stamp.sec}.{stamp.nanosec//1000000:03d}s "
                f"clk={self._clk_n} odom={self._odom_n} scan={self._scan_n}")

    def _on_odom(self, msg: Odometry):
        msg.header.frame_id = "odom"
        msg.child_frame_id = "base_link"
        self.odom_pub.publish(msg)
        t = TransformStamped()
        t.header.stamp = msg.header.stamp
        t.header.frame_id = "odom"
        t.child_frame_id = "base_link"
        t.transform.translation.x = msg.pose.pose.position.x
        t.transform.translation.y = msg.pose.pose.position.y
        t.transform.translation.z = msg.pose.pose.position.z
        t.transform.rotation = msg.pose.pose.orientation
        self.tf_pub.publish(TFMessage(transforms=[t]))
        self._odom_n += 1
        self._last_odom_stamp = msg.header.stamp

    def _on_pc(self, msg: PointCloud2):
        """在 LiDAR frame 下累积多帧点云，凑满 360° 后发布"""
        if not self._pc_parsed:
            for f in msg.fields:
                if f.name == 'x': self._x_off = f.offset
                elif f.name == 'y': self._y_off = f.offset
                elif f.name == 'z': self._z_off = f.offset
            self._pc_parsed = True
            self.get_logger().info(
                f"[PC] step={msg.point_step} n={msg.width*msg.height}")

        data = msg.data
        ps = msg.point_step
        n = msg.width * msg.height

        for i in range(n):
            base = i * ps
            if base + ps > len(data):
                break
            x = struct.unpack_from('f', data, base + self._x_off)[0]
            y = struct.unpack_from('f', data, base + self._y_off)[0]
            z = struct.unpack_from('f', data, base + self._z_off)[0]
            if z < Z_MIN or z > Z_MAX:
                continue
            r = math.sqrt(x*x + y*y)
            if r < RANGE_MIN or r > RANGE_MAX:
                continue
            angle = math.atan2(y, x)
            idx = int((angle - ANGLE_MIN) / ANGLE_INC)
            if 0 <= idx < NUM_RAYS and r < self._ranges[idx]:
                self._ranges[idx] = r

        self._frame_count += 1
        if self._frame_count < ACCUM_N:
            return

        # 发布累积的 360° scan
        # 用 odom 时间戳（而非点云时间戳），确保 collision_monitor 查 TF 时数据存在
        scan = LaserScan()
        scan.header.stamp = self._last_odom_stamp if self._last_odom_stamp else msg.header.stamp
        scan.header.frame_id = SCAN_FRAME
        scan.angle_min = ANGLE_MIN
        scan.angle_max = ANGLE_MAX
        scan.angle_increment = ANGLE_INC
        scan.time_increment = 0.0
        scan.scan_time = 0.05 * ACCUM_N
        scan.range_min = RANGE_MIN
        scan.range_max = RANGE_MAX
        scan.ranges = list(self._ranges)
        self.scan_pub.publish(scan)
        self._scan_n += 1

        if self._scan_n <= 3:
            nr = sum(1 for r in self._ranges if r < float('inf'))
            self.get_logger().warn(
                f"[SCAN#{self._scan_n}] rays={nr}/{NUM_RAYS} "
                f"({ACCUM_N}帧累积)")

        # 重置
        self._ranges = [float('inf')] * NUM_RAYS
        self._frame_count = 0


def main():
    rclpy.init()
    node = IsaacRosBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
