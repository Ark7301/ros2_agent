#!/usr/bin/env python3
"""仿真时钟桥接 — 从 Isaac Sim 的 /tf 提取仿真时间发布到 /clock

Isaac Sim ROS2 Assets 版不发布 /clock，但所有消息用仿真时间戳。
本节点从 /tf 消息中提取时间戳，以高频率发布到 /clock，
使 use_sim_time:=true 的节点能正常工作。
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from tf2_msgs.msg import TFMessage
from rosgraph_msgs.msg import Clock


class SimClockBridge(Node):
    def __init__(self):
        super().__init__("sim_clock_bridge")
        self.clock_pub = self.create_publisher(Clock, "/clock", 10)

        # 用 RELIABLE QoS 订阅 /tf（匹配 Isaac Sim 的发布 QoS）
        for qos in [
            QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE),
            QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT,
                       durability=DurabilityPolicy.VOLATILE),
        ]:
            self.create_subscription(TFMessage, "/tf", self._on_tf, qos)

        self._last_sec = 0
        self._last_nsec = 0
        self._count = 0
        self.get_logger().info("SimClockBridge: /tf 时间戳 → /clock")

    def _on_tf(self, msg: TFMessage):
        if not msg.transforms:
            return
        stamp = msg.transforms[0].header.stamp
        # 始终发布最新时间戳（支持仿真重启后时间回退）
        if stamp.sec != self._last_sec or stamp.nanosec != self._last_nsec:
            self._last_sec = stamp.sec
            self._last_nsec = stamp.nanosec
            clock_msg = Clock()
            clock_msg.clock = stamp
            self.clock_pub.publish(clock_msg)
            self._count += 1
            if self._count % 100 == 1:
                self.get_logger().info(f"/clock: sec={stamp.sec} nsec={stamp.nanosec}")


def main():
    rclpy.init()
    node = SimClockBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
