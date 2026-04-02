# ROS2 桥接管理器 — 在独立线程中运行 rclpy
# 桥接 asyncio 事件循环与 rclpy 回调机制

from __future__ import annotations

import asyncio
import threading
import logging

import rclpy
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

logger = logging.getLogger(__name__)


class ROS2BridgeManager:
    """ROS2 桥接管理器

    在独立 daemon 线程中运行 rclpy MultiThreadedExecutor，
    通过 loop.call_soon_threadsafe() 将 rclpy 回调结果投递到 asyncio 事件循环。
    """

    def __init__(self, executor_threads: int = 4) -> None:
        self._executor_threads = executor_threads
        self._executor: MultiThreadedExecutor | None = None
        self._spin_thread: threading.Thread | None = None
        self._nodes: list[Node] = []
        self._running = False

    def start(self, args: list[str] | None = None) -> None:
        """初始化 rclpy 并启动 spin 线程"""
        if self._running:
            return

        rclpy.init(args=args)
        self._executor = MultiThreadedExecutor(
            num_threads=self._executor_threads
        )
        self._running = True

        # 注册已有节点
        for node in self._nodes:
            self._executor.add_node(node)

        self._spin_thread = threading.Thread(
            target=self._spin_loop, daemon=True, name="rclpy-spin"
        )
        self._spin_thread.start()
        logger.info(
            "ROS2 Bridge 已启动（%d 线程）", self._executor_threads
        )

    def _spin_loop(self) -> None:
        """rclpy spin 循环（在独立线程中运行）"""
        try:
            while self._running and rclpy.ok():
                self._executor.spin_once(timeout_sec=0.1)
        except Exception:
            logger.exception("rclpy spin 异常")

    def register_node(self, node: Node) -> None:
        """注册 ROS2 节点到执行器"""
        self._nodes.append(node)
        if self._executor and self._running:
            self._executor.add_node(node)

    def create_node(self, name: str, **kwargs) -> Node:
        """创建并注册一个 ROS2 节点"""
        node = Node(name, **kwargs)
        self.register_node(node)
        return node

    def shutdown(self) -> None:
        """关闭 rclpy"""
        self._running = False
        if self._spin_thread:
            self._spin_thread.join(timeout=3.0)

        for node in self._nodes:
            node.destroy_node()
        self._nodes.clear()

        if rclpy.ok():
            rclpy.shutdown()
        logger.info("ROS2 Bridge 已关闭")
