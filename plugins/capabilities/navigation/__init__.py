# 导航能力插件 — Nav2 导航 / Mock 双模式
# 实现 CapabilityPlugin Protocol，提供 navigate_to 和 patrol 两种导航意图
# 通过 ros_node 参数判断：传入则使用 Nav2 Action Client，否则 mock 模式

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mosaic.plugin_sdk.types import (
    PluginMeta,
    ExecutionContext,
    ExecutionResult,
    HealthStatus,
    HealthState,
)

logger = logging.getLogger(__name__)

# Nav2 依赖（可选，mock 模式不需要）
try:
    from rclpy.node import Node
    from rclpy.action import ActionClient
    from rclpy.parameter import Parameter
    from nav2_msgs.action import NavigateToPose
    from geometry_msgs.msg import PoseStamped
    from action_msgs.msg import GoalStatus

    HAS_ROS2 = True
except ImportError:
    HAS_ROS2 = False


class NavigationCapability:
    """导航能力插件 — 支持 navigate_to 和 patrol 意图

    双模式运行：
    - Nav2 模式：传入 ros_node + spatial_provider，通过 Nav2 Action 执行真实导航
    - Mock 模式：不传参数，返回模拟成功结果
    """

    def __init__(
        self,
        ros_node: Any | None = None,
        spatial_provider: Any | None = None,
    ) -> None:
        self.meta = PluginMeta(
            id="navigation",
            name="Navigation",
            version="0.2.0",
            description="Nav2 导航能力，支持目标导航和巡逻",
            kind="capability",
            author="MOSAIC",
        )
        self._cancelled = False
        self._ros_node = ros_node
        self._spatial = spatial_provider
        self._nav_client: Any | None = None
        self._current_goal_handle: Any | None = None

        # 如果有 ROS2 节点，初始化 Nav2 Action Client
        if ros_node and HAS_ROS2:
            self._nav_client = ActionClient(
                ros_node, NavigateToPose, "navigate_to_pose"
            )
            logger.info("NavigationCapability: Nav2 模式")
        else:
            logger.info("NavigationCapability: Mock 模式")

    @property
    def _is_nav2_mode(self) -> bool:
        return self._nav_client is not None

    def get_supported_intents(self) -> list[str]:
        return ["navigate_to", "patrol"]

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "navigate_to",
                "description": "导航到指定位置",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": "目标位置名称",
                        },
                        "speed": {
                            "type": "number",
                            "description": "导航速度（0.0-1.0），默认 0.5",
                            "default": 0.5,
                        },
                    },
                    "required": ["target"],
                },
            },
            {
                "name": "patrol",
                "description": "按路径点列表巡逻",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "waypoints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "巡逻路径点列表",
                        },
                        "repeat": {
                            "type": "boolean",
                            "description": "是否循环巡逻，默认 false",
                            "default": False,
                        },
                    },
                    "required": ["waypoints"],
                },
            },
        ]

    async def execute(
        self, intent: str, params: dict, ctx: ExecutionContext
    ) -> ExecutionResult:
        self._cancelled = False

        if intent == "navigate_to":
            return await self._execute_navigate_to(params)
        elif intent == "patrol":
            return await self._execute_patrol(params)
        return ExecutionResult(success=False, error=f"不支持的意图: {intent}")

    async def _execute_navigate_to(self, params: dict) -> ExecutionResult:
        """执行 navigate_to — Nav2 或 Mock"""
        target = params.get("target", "")
        speed = params.get("speed", 0.5)

        if not self._is_nav2_mode:
            # Mock 模式
            return ExecutionResult(
                success=True,
                data={"intent": "navigate_to", "target": target, "speed": speed},
                message=f"已导航到 {target}（速度: {speed}）",
            )

        # Nav2 模式：解析坐标 → 发送目标 → 等待结果
        try:
            # 解析语义地名到坐标
            if self._spatial:
                coord = self._spatial.resolve_location(target)
            else:
                return ExecutionResult(
                    success=False, error=f"无法解析目标位置: {target}（无空间查询提供者）"
                )

            # 等待 Nav2 Action Server
            if not self._nav_client.wait_for_server(timeout_sec=5.0):
                return ExecutionResult(
                    success=False, error="Nav2 导航服务不可用"
                )

            # 构造导航目标
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = "map"
            goal.pose.header.stamp = self._ros_node.get_clock().now().to_msg()
            goal.pose.pose.position.x = float(coord[0])
            goal.pose.pose.position.y = float(coord[1])
            goal.pose.pose.orientation.w = 1.0

            logger.info("发送导航目标: %s → (%.2f, %.2f)", target, coord[0], coord[1])

            # 发送目标（通过 asyncio Future 桥接）
            loop = asyncio.get_event_loop()
            result_future = loop.create_future()

            send_goal_future = self._nav_client.send_goal_async(goal)

            def _on_goal_response(future):
                goal_handle = future.result()
                if not goal_handle.accepted:
                    loop.call_soon_threadsafe(
                        result_future.set_result,
                        ExecutionResult(success=False, error="Nav2 拒绝导航目标"),
                    )
                    return

                self._current_goal_handle = goal_handle
                result_f = goal_handle.get_result_async()

                def _on_result(f):
                    result = f.result()
                    status = result.status
                    if status == GoalStatus.STATUS_SUCCEEDED:
                        r = ExecutionResult(
                            success=True,
                            data={"target": target, "coord": list(coord)},
                            message=f"已导航到 {target}",
                        )
                    elif status == GoalStatus.STATUS_CANCELED:
                        r = ExecutionResult(
                            success=False, error=f"导航到 {target} 已取消"
                        )
                    else:
                        r = ExecutionResult(
                            success=False, error=f"导航到 {target} 失败（状态: {status}）"
                        )
                    loop.call_soon_threadsafe(result_future.set_result, r)

                result_f.add_done_callback(_on_result)

            send_goal_future.add_done_callback(_on_goal_response)

            # 等待结果（带超时）
            return await asyncio.wait_for(result_future, timeout=120.0)

        except asyncio.TimeoutError:
            return ExecutionResult(success=False, error=f"导航到 {target} 超时")
        except Exception as e:
            return ExecutionResult(success=False, error=f"导航异常: {e}")

    async def _execute_patrol(self, params: dict) -> ExecutionResult:
        """执行 patrol — 依次导航到各路径点"""
        waypoints = params.get("waypoints", [])
        repeat = params.get("repeat", False)

        if not self._is_nav2_mode:
            return ExecutionResult(
                success=True,
                data={"intent": "patrol", "waypoints": waypoints, "repeat": repeat},
                message=f"巡逻完成，路径点: {waypoints}",
            )

        # Nav2 模式：依次导航到每个路径点
        for wp in waypoints:
            if self._cancelled:
                return ExecutionResult(success=False, error="巡逻已取消")
            result = await self._execute_navigate_to({"target": wp})
            if not result.success:
                return result

        return ExecutionResult(
            success=True,
            data={"intent": "patrol", "waypoints": waypoints},
            message=f"巡逻完成，路径点: {waypoints}",
        )

    async def cancel(self) -> bool:
        self._cancelled = True
        if self._current_goal_handle:
            try:
                await asyncio.wrap_future(
                    self._current_goal_handle.cancel_goal_async()
                )
            except Exception:
                logger.exception("取消导航目标失败")
        return True

    async def health_check(self) -> HealthStatus:
        if not self._is_nav2_mode:
            return HealthStatus(state=HealthState.HEALTHY, message="导航插件正常（Mock 模式）")

        if self._nav_client.wait_for_server(timeout_sec=1.0):
            return HealthStatus(state=HealthState.HEALTHY, message="Nav2 连接正常")
        return HealthStatus(state=HealthState.UNHEALTHY, message="Nav2 服务不可用")


def create_plugin(
    ros_node: Any | None = None,
    spatial_provider: Any | None = None,
) -> NavigationCapability:
    """工厂函数 — 返回 NavigationCapability 实例"""
    return NavigationCapability(ros_node=ros_node, spatial_provider=spatial_provider)
