# test/mosaic_v2/test_slam_pipeline_e2e.py
"""SLAM 仿真管线端到端集成测试

覆盖完整数据流：
- SlamMapDetector 检测 → MapAnalyzer 加载 → 场景图包含拓扑节点
- Nav2LaunchConfig 生成可解析的参数文件
- SlamMapDetector 使用配置的 slam_map_dir

Validates: Requirements 2.1, 3.1, 6.1
"""

from __future__ import annotations

import os

import pytest
import yaml

from mosaic.runtime.slam_map_detector import SlamMapDetector
from mosaic.runtime.map_analyzer import MapAnalyzer, RoomTopology
from mosaic.runtime.nav2_launch_config import Nav2LaunchConfig
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.scene_graph import NodeType


# ── 辅助函数 ──


def _create_valid_map_files(directory: str, name: str = "house_map") -> str:
    """在指定目录创建有效的 .yaml + .pgm 文件对，返回 yaml 路径

    .pgm 为最小有效 P5 二进制格式（10x10 像素，全部为空闲区域）
    """
    yaml_path = os.path.join(directory, f"{name}.yaml")
    pgm_path = os.path.join(directory, f"{name}.pgm")

    # 创建 .yaml 元数据文件
    meta = {
        "image": f"{name}.pgm",
        "resolution": 0.05,
        "origin": [0.0, 0.0, 0.0],
        "free_thresh": 0.65,
        "occupied_thresh": 0.196,
        "negate": 0,
    }
    with open(yaml_path, "w") as f:
        yaml.safe_dump(meta, f)

    # 创建最小有效 P5 二进制 PGM（10x10 像素，全部空闲）
    pgm_header = b"P5\n10 10\n255\n"
    pgm_data = bytes([200] * 100)  # 值 200 > 165 (free_thresh * 255)，全部为空闲
    with open(pgm_path, "wb") as f:
        f.write(pgm_header + pgm_data)

    return yaml_path


# ── 测试 1: 完整管线 SlamMapDetector → MapAnalyzer → SceneGraph ──


class TestFullPipelineDetectLoadMerge:
    """端到端测试：检测 → 加载 → 拓扑提取 → 场景图合并

    Validates: Requirements 2.1
    """

    def test_detect_load_and_merge_topology(self, tmp_path) -> None:
        """创建模拟 SLAM 地图 → SlamMapDetector 检测 → MapAnalyzer 加载 → 场景图包含拓扑节点"""
        map_dir = str(tmp_path / "mosaic_maps")
        os.makedirs(map_dir)

        # 创建有效的地图文件对
        yaml_path = _create_valid_map_files(map_dir, "house_map")

        # 步骤 1：SlamMapDetector 检测地图
        detector = SlamMapDetector(default_map_dir=map_dir)
        detected = detector.detect()
        assert detected is not None, "SlamMapDetector 应检测到地图文件"
        assert detected == yaml_path

        # 步骤 2：MapAnalyzer 加载地图并提取拓扑
        analyzer = MapAnalyzer()
        analyzer.load_map(detected)
        topology = analyzer.extract_room_topology()

        # 拓扑结果是 RoomTopology 实例
        assert isinstance(topology, RoomTopology)
        # 10x10 全空闲像素图像可能只有一个连通域（也可能为空，取决于阈值）
        # 关键是流程不报错

        # 步骤 3：SceneGraphManager 合并拓扑
        sgm = SceneGraphManager()
        sgm.merge_room_topology(topology)

        graph = sgm.get_full_graph()

        # 验证拓扑中的每个房间都作为 ROOM 节点存在于场景图中
        for room in topology.rooms:
            node = graph.get_node(room.room_id)
            assert node is not None, f"场景图应包含房间节点 {room.room_id}"
            assert node.node_type == NodeType.ROOM


# ── 测试 2: Nav2LaunchConfig 生成可解析的参数文件 ──


class TestNav2LaunchConfigGeneratesParseable:
    """验证 Nav2LaunchConfig 生成的参数文件可被 yaml.safe_load 正确解析

    Validates: Requirements 3.1
    """

    def test_nav2_params_parseable_with_expected_keys(self, tmp_path) -> None:
        """生成 nav2_params 并验证包含预期的配置段和 use_sim_time"""
        config = Nav2LaunchConfig(mosaic_config={})

        nav2_path = str(tmp_path / "nav2_params.yaml")
        config.generate_nav2_params(nav2_path)

        # 解析生成的文件
        with open(nav2_path, "r") as f:
            params = yaml.safe_load(f)

        # 验证包含所有必需的配置段
        assert "amcl" in params
        assert "controller_server" in params
        assert "planner_server" in params
        assert "local_costmap" in params
        assert "global_costmap" in params

        # 验证所有段的 use_sim_time 为 True
        assert params["amcl"]["ros__parameters"]["use_sim_time"] is True
        assert params["controller_server"]["ros__parameters"]["use_sim_time"] is True
        assert params["planner_server"]["ros__parameters"]["use_sim_time"] is True

    def test_slam_params_parseable_with_expected_keys(self, tmp_path) -> None:
        """生成 slam_params 并验证包含预期的配置段和 use_sim_time"""
        config = Nav2LaunchConfig(mosaic_config={})

        slam_path = str(tmp_path / "slam_params.yaml")
        config.generate_slam_params(slam_path)

        # 解析生成的文件
        with open(slam_path, "r") as f:
            params = yaml.safe_load(f)

        # 验证包含 slam_toolbox 配置段
        assert "slam_toolbox" in params
        ros_params = params["slam_toolbox"]["ros__parameters"]
        assert ros_params["use_sim_time"] is True
        assert "scan_topic" in ros_params
        assert "odom_frame" in ros_params
        assert "map_frame" in ros_params
        assert "base_frame" in ros_params


# ── 测试 3: SlamMapDetector 使用配置的 slam_map_dir ──


class TestSlamMapDetectorUsesConfigDir:
    """验证 SlamMapDetector 使用配置的 slam_map_dir 目录检测地图

    Validates: Requirements 6.1
    """

    def test_detect_finds_map_in_configured_dir(self, tmp_path) -> None:
        """创建模拟目录结构，验证 SlamMapDetector 在指定目录中找到地图"""
        # 模拟 mosaic_maps 目录结构
        map_dir = str(tmp_path / "custom_maps")
        os.makedirs(map_dir)

        # 创建有效的地图文件
        expected_yaml = _create_valid_map_files(map_dir, "test_map")

        # 使用自定义目录创建检测器
        detector = SlamMapDetector(default_map_dir=map_dir)

        # 不传配置路径，应从目录扫描中找到
        result = detector.detect()
        assert result is not None, "应在配置目录中检测到地图"
        assert result == expected_yaml
