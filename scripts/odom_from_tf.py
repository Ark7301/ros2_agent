#!/usr/bin/env python3
"""里程计桥接 — 为 Nav2 提供 odom→base_link TF 和 /odom 话题

Isaac Sim Nova Carter ROS Assets 不发布 odom→base_link TF 和 /odom，
导致 Nav2 AMCL 无法工作。

本节点使用 use_sim_time，以仿真时钟频率发布：
  1. odom→base_link TF（identity）
  2. /odom 话题（零速度）

AMCL 通过 /scan 和地图匹配修正 map→odom 变换。

依赖：sim_clock_bridge.py 必须先启动，提供 /clock。

用法：
  python3 scripts/odom_from_tf.py --ros-args -p use_sim_time:=true
  # 或直接运行（脚本内部强制 use_sim_time）：
  python3 scripts/odom_from_tf.py
"""
import rclpy
import rclpy.parameter
from rclpy.node import Node
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped


class OdomBridge(Node):
    def __init__(self):
        super().__init__("odom_bridge", parameter_overrides=[
            rclpy.parameter.Parameter("use_sim_time", rclpy.Parameter.Type.BOOL, True)
        ])

        self.odom_pub = self.create_publisher(Odometry, "/odom", 10)
        self.tf_pub = self.create_publisher(TFMessage, "/tf", 100)

        # 20Hz 发布
        self.timer = self.create_timer(0.05, self._publish)
        self._count = 0
        self._clock_ok = False
        self.get_logger().info("OdomBridge: use_sim_time=true, 等待 /clock...")

    def _publish(self):
        now = self.get_clock().now()
        now_ns = now.nanoseconds

        # 等 /clock 生效（sim_time > 0）
        if now_ns == 0:
            if self._count % 100 == 0:
                self.get_logger().warn("等待 /clock... sim_time=0")
            self._count += 1
            return

        if not self._clock_ok:
            self._clock_ok = True
            self.get_logger().info(f"/clock 已就绪, sim_time={now_ns/1e9:.1f}s")

        stamp = now.to_msg()

        # odom→base_link TF
        t = TransformStamped()
        t.header.stamp = stamp
        t.header.frame_id = "odom"
        t.child_frame_id = "base_link"
        t.transform.rotation.w = 1.0
        self.tf_pub.publish(TFMessage(transforms=[t]))

        # /odom
        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = "odom"
        odom.child_frame_id = "base_link"
        odom.pose.pose.orientation.w = 1.0
        self.odom_pub.publish(odom)

        self._count += 1
        if self._count % 500 == 1:
            self.get_logger().info(f"odom TF: sim_time={now_ns/1e9:.1f}s")


def main():
    rclpy.init()
    node = OdomBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
