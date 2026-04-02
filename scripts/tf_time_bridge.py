#!/usr/bin/env python3
"""全量时间戳桥接 — 将 Isaac Sim 仿真时间戳替换为系统时间

关键：所有输出话题使用同一个时间戳，确保 TF 和传感器数据严格同步。
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
from tf2_msgs.msg import TFMessage
from sensor_msgs.msg import LaserScan, PointCloud2
import threading


class TfTimeBridge(Node):
    def __init__(self):
        super().__init__("tf_time_bridge")

        # 共享时间戳：每次 TF 回调更新，scan/pc 回调复用
        self._lock = threading.Lock()
        self._latest_stamp = self.get_clock().now().to_msg()

        # 发布者
        self.tf_pub = self.create_publisher(TFMessage, "/tf_sys", 100)
        self.tf_static_pub = self.create_publisher(
            TFMessage, "/tf_static_sys",
            QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                       reliability=ReliabilityPolicy.RELIABLE))
        self.scan_pub = self.create_publisher(
            LaserScan, "/scan_sys",
            QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE))
        self.pc_pub = self.create_publisher(
            PointCloud2, "/lidar_points_sys",
            QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE))

        # 订阅者
        qos_be = QoSProfile(depth=50, reliability=ReliabilityPolicy.BEST_EFFORT,
                            durability=DurabilityPolicy.VOLATILE)
        qos_static = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE,
                                durability=DurabilityPolicy.TRANSIENT_LOCAL)

        self.create_subscription(TFMessage, "/tf", self._on_tf, qos_be)
        self.create_subscription(TFMessage, "/tf_static", self._on_tf_static, qos_static)
        self.create_subscription(LaserScan, "/scan_hd", self._on_scan, qos_be)
        self.create_subscription(PointCloud2, "/front_3d_lidar/lidar_points",
                                 self._on_pc, qos_be)

        self.get_logger().info("TfTimeBridge: 全量时间戳桥接（同步模式）")

    def _on_tf(self, msg: TFMessage):
        now = self.get_clock().now().to_msg()
        with self._lock:
            self._latest_stamp = now
        for t in msg.transforms:
            t.header.stamp = now
        self.tf_pub.publish(msg)

    def _on_tf_static(self, msg: TFMessage):
        now = self.get_clock().now().to_msg()
        for t in msg.transforms:
            t.header.stamp = now
        self.tf_static_pub.publish(msg)

    def _on_scan(self, msg: LaserScan):
        # 使用最近一次 TF 的时间戳，确保 scan 和 TF 同步
        with self._lock:
            msg.header.stamp = self._latest_stamp
        self.scan_pub.publish(msg)

    def _on_pc(self, msg: PointCloud2):
        with self._lock:
            msg.header.stamp = self._latest_stamp
        self.pc_pub.publish(msg)


def main():
    rclpy.init()
    node = TfTimeBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
