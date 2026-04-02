# mosaic/runtime/nav2_launch_config.py
"""Nav2 导航栈 launch 配置生成器 — 生成适配 Isaac Sim 仿真环境的参数文件

核心功能：
1. Nav2SimParams / SlamToolboxParams 数据模型及参数验证
2. 生成 Nav2 参数 YAML（amcl、controller_server、planner_server、costmap）
3. 生成 SLAM Toolbox 参数 YAML
4. 生成 ros2 launch 命令

所有参数默认设置 use_sim_time: true，适配 Isaac Sim 仿真环境。
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import yaml


# ── 数据模型 ──


@dataclass
class Nav2SimParams:
    """Nav2 仿真环境参数

    包含 AMCL 定位、Costmap 代价地图、控制器等核心参数。
    所有数值参数在 __post_init__ 中进行合法性校验。
    """

    use_sim_time: bool = True
    robot_model_type: str = "differential"  # Nova Carter 差速驱动
    robot_radius: float = 0.22              # Nova Carter 半径（米）
    scan_topic: str = "/scan"
    odom_topic: str = "/odom"
    cmd_vel_topic: str = "/cmd_vel"
    map_topic: str = "/map"
    # AMCL 粒子滤波参数
    amcl_max_particles: int = 2000
    amcl_min_particles: int = 500
    # Costmap 代价地图参数
    inflation_radius: float = 0.55
    cost_scaling_factor: float = 2.0
    # 控制器速度限制
    max_vel_x: float = 0.5
    max_vel_theta: float = 1.0

    def __post_init__(self) -> None:
        """参数合法性校验"""
        if self.robot_radius <= 0:
            raise ValueError(
                f"robot_radius 必须为正数，当前值: {self.robot_radius}"
            )
        if self.inflation_radius <= self.robot_radius:
            raise ValueError(
                f"inflation_radius ({self.inflation_radius}) "
                f"必须大于 robot_radius ({self.robot_radius})"
            )
        if self.amcl_max_particles <= self.amcl_min_particles:
            raise ValueError(
                f"amcl_max_particles ({self.amcl_max_particles}) "
                f"必须大于 amcl_min_particles ({self.amcl_min_particles})"
            )
        if self.max_vel_x <= 0:
            raise ValueError(
                f"max_vel_x 必须为正数，当前值: {self.max_vel_x}"
            )
        if self.max_vel_theta <= 0:
            raise ValueError(
                f"max_vel_theta 必须为正数，当前值: {self.max_vel_theta}"
            )


@dataclass
class SlamToolboxParams:
    """SLAM Toolbox 仿真参数

    适配 Isaac Sim 传感器话题和坐标系配置。
    """

    use_sim_time: bool = True
    mode: str = "mapping"                   # mapping | localization
    scan_topic: str = "/scan"
    odom_frame: str = "odom"
    map_frame: str = "map"
    base_frame: str = "base_link"
    resolution: float = 0.05               # 地图分辨率（米/像素）
    max_laser_range: float = 12.0          # 最大激光距离
    minimum_travel_distance: float = 0.5   # 最小移动距离触发建图
    minimum_travel_heading: float = 0.5    # 最小旋转角度触发建图
    map_update_interval: float = 5.0       # 地图更新间隔（秒）


# ── Nav2 配置生成器 ──


class Nav2LaunchConfig:
    """Nav2 导航栈 launch 配置生成器

    从 mosaic_config 字典读取参数，生成 Nav2 和 SLAM Toolbox 的 YAML 参数文件，
    并提供 ros2 launch 命令字符串。
    """

    def __init__(self, mosaic_config: dict) -> None:
        """初始化配置生成器

        Args:
            mosaic_config: MOSAIC 配置字典，可包含 nav2 相关参数覆盖
        """
        self._config = mosaic_config
        # 从配置构建参数对象，使用默认值
        self._nav2_params = Nav2SimParams()
        self._slam_params = SlamToolboxParams()

    def generate_nav2_params(self, output_path: str) -> str:
        """生成 Nav2 参数 YAML 文件

        生成包含 amcl、controller_server、planner_server、
        local_costmap、global_costmap 配置段的 YAML 文件。
        所有段均设置 use_sim_time: true。

        Args:
            output_path: 输出文件路径

        Returns:
            生成的文件绝对路径
        """
        p = self._nav2_params

        # 构建 ROS2 参数格式的嵌套字典
        params = {
            "amcl": {
                "ros__parameters": {
                    "use_sim_time": p.use_sim_time,
                    "max_particles": p.amcl_max_particles,
                    "min_particles": p.amcl_min_particles,
                    "robot_model_type": p.robot_model_type,
                    "scan_topic": p.scan_topic,
                    "odom_frame_id": "odom",
                    "base_frame_id": "base_link",
                }
            },
            "controller_server": {
                "ros__parameters": {
                    "use_sim_time": p.use_sim_time,
                    "odom_topic": p.odom_topic,
                    "cmd_vel_topic": p.cmd_vel_topic,
                    "max_vel_x": p.max_vel_x,
                    "max_vel_theta": p.max_vel_theta,
                }
            },
            "planner_server": {
                "ros__parameters": {
                    "use_sim_time": p.use_sim_time,
                }
            },
            "local_costmap": {
                "local_costmap": {
                    "ros__parameters": {
                        "use_sim_time": p.use_sim_time,
                        "robot_radius": p.robot_radius,
                        "inflation_layer": {
                            "inflation_radius": p.inflation_radius,
                            "cost_scaling_factor": p.cost_scaling_factor,
                        },
                    }
                }
            },
            "global_costmap": {
                "global_costmap": {
                    "ros__parameters": {
                        "use_sim_time": p.use_sim_time,
                        "robot_radius": p.robot_radius,
                        "inflation_layer": {
                            "inflation_radius": p.inflation_radius,
                            "cost_scaling_factor": p.cost_scaling_factor,
                        },
                    }
                }
            },
        }

        # 自动创建输出目录
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            yaml.safe_dump(params, f, default_flow_style=False, sort_keys=False)

        return output_path

    def generate_slam_params(self, output_path: str) -> str:
        """生成 SLAM Toolbox 参数 YAML 文件

        Args:
            output_path: 输出文件路径

        Returns:
            生成的文件绝对路径
        """
        s = self._slam_params

        params = {
            "slam_toolbox": {
                "ros__parameters": {
                    "use_sim_time": s.use_sim_time,
                    "mode": s.mode,
                    "scan_topic": s.scan_topic,
                    "odom_frame": s.odom_frame,
                    "map_frame": s.map_frame,
                    "base_frame": s.base_frame,
                    "resolution": s.resolution,
                    "max_laser_range": s.max_laser_range,
                    "minimum_travel_distance": s.minimum_travel_distance,
                    "minimum_travel_heading": s.minimum_travel_heading,
                    "map_update_interval": s.map_update_interval,
                }
            }
        }

        # 自动创建输出目录
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w") as f:
            yaml.safe_dump(params, f, default_flow_style=False, sort_keys=False)

        return output_path

    def get_launch_command(self, map_path: str) -> str:
        """生成 Nav2 bringup launch 命令

        Args:
            map_path: SLAM 地图 .yaml 文件路径

        Returns:
            完整的 ros2 launch 命令字符串
        """
        return (
            f"ros2 launch nav2_bringup bringup_launch.py "
            f"use_sim_time:=True map:={map_path}"
        )
