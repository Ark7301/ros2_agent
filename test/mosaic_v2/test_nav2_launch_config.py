# test/mosaic_v2/test_nav2_launch_config.py
"""Nav2LaunchConfig 单元测试 — 验证参数生成、验证和命令格式"""

from __future__ import annotations

import os

import pytest
import yaml

from mosaic.runtime.nav2_launch_config import (
    Nav2LaunchConfig,
    Nav2SimParams,
    SlamToolboxParams,
)


# ── Nav2SimParams 参数验证测试 ──


class TestNav2SimParamsValidation:
    """测试 Nav2SimParams 数据类的参数验证逻辑"""

    def test_inflation_radius_le_robot_radius_raises(self) -> None:
        """inflation_radius <= robot_radius 时应抛出 ValueError"""
        with pytest.raises(ValueError, match="inflation_radius"):
            Nav2SimParams(robot_radius=0.22, inflation_radius=0.22)

    def test_inflation_radius_lt_robot_radius_raises(self) -> None:
        """inflation_radius < robot_radius 时应抛出 ValueError"""
        with pytest.raises(ValueError, match="inflation_radius"):
            Nav2SimParams(robot_radius=0.22, inflation_radius=0.10)

    def test_max_particles_le_min_particles_raises(self) -> None:
        """max_particles <= min_particles 时应抛出 ValueError"""
        with pytest.raises(ValueError, match="amcl_max_particles"):
            Nav2SimParams(amcl_max_particles=500, amcl_min_particles=500)

    def test_negative_robot_radius_raises(self) -> None:
        """robot_radius <= 0 时应抛出 ValueError"""
        with pytest.raises(ValueError, match="robot_radius"):
            Nav2SimParams(robot_radius=-0.1)

    def test_valid_params_no_error(self) -> None:
        """合法参数不应抛出异常"""
        params = Nav2SimParams(
            robot_radius=0.22,
            inflation_radius=0.55,
            amcl_min_particles=500,
            amcl_max_particles=2000,
        )
        assert params.robot_radius == 0.22


# ── generate_nav2_params 测试 ──


class TestGenerateNav2Params:
    """测试 generate_nav2_params 生成的 YAML 文件结构"""

    def test_contains_all_required_sections(self, tmp_path) -> None:
        """生成的 YAML 应包含 amcl、controller_server、planner_server、local_costmap、global_costmap"""
        config = Nav2LaunchConfig(mosaic_config={})
        output = os.path.join(str(tmp_path), "nav2_params.yaml")
        config.generate_nav2_params(output)

        with open(output) as f:
            data = yaml.safe_load(f)

        required_sections = [
            "amcl",
            "controller_server",
            "planner_server",
            "local_costmap",
            "global_costmap",
        ]
        for section in required_sections:
            assert section in data, f"缺少必需配置段: {section}"

    def test_use_sim_time_true_in_all_sections(self, tmp_path) -> None:
        """所有配置段的 use_sim_time 应为 True"""
        config = Nav2LaunchConfig(mosaic_config={})
        output = os.path.join(str(tmp_path), "nav2_params.yaml")
        config.generate_nav2_params(output)

        with open(output) as f:
            data = yaml.safe_load(f)

        # 顶层节点直接包含 ros__parameters
        assert data["amcl"]["ros__parameters"]["use_sim_time"] is True
        assert data["controller_server"]["ros__parameters"]["use_sim_time"] is True
        assert data["planner_server"]["ros__parameters"]["use_sim_time"] is True

        # costmap 有嵌套结构
        assert data["local_costmap"]["local_costmap"]["ros__parameters"]["use_sim_time"] is True
        assert data["global_costmap"]["global_costmap"]["ros__parameters"]["use_sim_time"] is True

    def test_creates_output_directory(self, tmp_path) -> None:
        """输出目录不存在时应自动创建"""
        config = Nav2LaunchConfig(mosaic_config={})
        output = os.path.join(str(tmp_path), "subdir", "nav2_params.yaml")
        config.generate_nav2_params(output)

        assert os.path.exists(output)


# ── generate_slam_params 测试 ──


class TestGenerateSlamParams:
    """测试 generate_slam_params 生成的 SLAM Toolbox 参数"""

    def test_slam_params_structure(self, tmp_path) -> None:
        """生成的 SLAM 参数应包含正确的 scan_topic、odom_frame、map_frame、base_frame"""
        config = Nav2LaunchConfig(mosaic_config={})
        output = os.path.join(str(tmp_path), "slam_params.yaml")
        config.generate_slam_params(output)

        with open(output) as f:
            data = yaml.safe_load(f)

        slam_params = data["slam_toolbox"]["ros__parameters"]
        assert slam_params["use_sim_time"] is True
        assert slam_params["scan_topic"] == "/scan"
        assert slam_params["odom_frame"] == "odom"
        assert slam_params["map_frame"] == "map"
        assert slam_params["base_frame"] == "base_link"


# ── get_launch_command 测试 ──


class TestGetLaunchCommand:
    """测试 get_launch_command 返回的 ros2 launch 命令格式"""

    def test_command_format(self) -> None:
        """命令应包含 ros2 launch、use_sim_time:=True 和 map 参数"""
        config = Nav2LaunchConfig(mosaic_config={})
        cmd = config.get_launch_command("/home/user/maps/house_map.yaml")

        assert "ros2 launch nav2_bringup bringup_launch.py" in cmd
        assert "use_sim_time:=True" in cmd
        assert "map:=/home/user/maps/house_map.yaml" in cmd
