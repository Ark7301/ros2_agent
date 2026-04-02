#!/usr/bin/env python3
"""WASD 键盘遥控节点 — 按住移动，松开自动停止

操作：
  W — 前进    S — 后退
  A — 左转    D — 右转
  Q — 左前    E — 右前
  Z/X — 减速/加速
  Ctrl+C — 退出
"""
import select
import sys
import termios
import tty
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist

KEY_MAP = {
    "w": (1.0, 0.0),
    "s": (-1.0, 0.0),
    "a": (0.0, 1.0),
    "d": (0.0, -1.0),
    "q": (1.0, 1.0),
    "e": (1.0, -1.0),
}

HELP = """
WASD 遥控器（按住移动，松开停止）
----------------------------------
  Q   W   E
  A       D
      S

Z — 减速  X — 加速
Ctrl+C — 退出
"""


def _key_available(timeout=0.1):
    """检查是否有按键输入（非阻塞）"""
    return select.select([sys.stdin], [], [], timeout)[0]


class WasdTeleop(Node):
    def __init__(self):
        super().__init__("wasd_teleop")
        self.pub = self.create_publisher(Twist, "/cmd_vel", 10)
        self.speed = 0.5
        self.turn = 1.0

    def run(self):
        print(HELP)
        print(f"速度: {self.speed:.2f}  转向: {self.turn:.2f}")

        old_settings = termios.tcgetattr(sys.stdin)
        try:
            tty.setcbreak(sys.stdin.fileno())
            while True:
                twist = Twist()

                if _key_available(0.05):
                    key = sys.stdin.read(1).lower()
                    if key == "\x03":  # Ctrl+C
                        break
                    elif key in KEY_MAP:
                        lin, ang = KEY_MAP[key]
                        twist.linear.x = lin * self.speed
                        twist.angular.z = ang * self.turn
                    elif key == "z":
                        self.speed = max(0.1, self.speed - 0.1)
                        self.turn = max(0.2, self.turn - 0.2)
                        sys.stdout.write(f"\r速度: {self.speed:.2f}  转向: {self.turn:.2f}    ")
                        sys.stdout.flush()
                        continue
                    elif key == "x":
                        self.speed = min(2.0, self.speed + 0.1)
                        self.turn = min(3.0, self.turn + 0.2)
                        sys.stdout.write(f"\r速度: {self.speed:.2f}  转向: {self.turn:.2f}    ")
                        sys.stdout.flush()
                        continue
                # 没有按键时发送零速度（自动停止）

                self.pub.publish(twist)
        finally:
            self.pub.publish(Twist())
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            print("\n已退出")


def main():
    rclpy.init()
    node = WasdTeleop()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
