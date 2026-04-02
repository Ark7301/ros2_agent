# test/mosaic_v2/test_gateway_slam_integration.py
"""GatewayServer SLAM 地图加载集成测试

覆盖 Task 2.3 的三个场景：
- 有地图时：场景图包含 SLAM 拓扑节点（merge_room_topology 被调用）
- 无地图时：系统正常启动，降级为 YAML 静态场景图
- 地图加载异常时：降级处理，不影响系统启动

Validates: Requirements 2.1, 2.2, 2.3
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml

from mosaic.runtime.map_analyzer import RoomCandidate, RoomTopology


# ── 辅助：创建临时配置文件（复制自 test_gateway_scene_init.py）──

def _write_yaml(path: str, data: dict) -> None:
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


def _minimal_env_config() -> dict:
    """最小可用的环境配置"""
    return {
        "environment": {
            "name": "test",
            "rooms": [
                {
                    "id": "room_a",
                    "label": "房间A",
                    "position": [1.0, 2.0],
                    "furniture": [],
                }
            ],
            "connections": [],
            "agents": [
                {"id": "robot", "label": "机器人", "at": "room_a"}
            ],
            "people": [],
        }
    }


def _make_mosaic_yaml(
    tmpdir: str,
    env_filename: str = "env.yaml",
    ros2_enabled: bool = False,
    scene_graph_section: dict | None = None,
) -> str:
    """生成临时 mosaic.yaml，返回路径

    支持 scene_graph 段中的 slam_map / slam_map_dir 配置。
    """
    mosaic_cfg: dict = {
        "gateway": {"max_concurrent_sessions": 1, "idle_session_timeout_s": 10},
        "agents": {
            "default": {
                "max_turn_iterations": 3,
                "turn_timeout_s": 30,
                "system_prompt": "test",
            }
        },
        "plugins": {
            "slots": {"memory": "file-memory", "context-engine": "sliding-window"},
            "providers": {"default": "minimax"},
        },
        "routing": {"default_agent": "default", "bindings": []},
        "ros2": {"enabled": ros2_enabled},
    }
    if scene_graph_section:
        mosaic_cfg["scene_graph"] = scene_graph_section
    else:
        mosaic_cfg["scene_graph"] = {
            "environment_config": os.path.join(tmpdir, env_filename),
        }
    path = os.path.join(tmpdir, "mosaic.yaml")
    _write_yaml(path, mosaic_cfg)
    return path


def _mock_room_topology() -> RoomTopology:
    """构造一个模拟的 RoomTopology 用于测试"""
    room1 = RoomCandidate(
        room_id="slam_room_1",
        centroid_world=(3.0, 4.0),
        boundary_polygon=[[2.0, 3.0], [4.0, 3.0], [4.0, 5.0], [2.0, 5.0]],
        area_m2=4.0,
    )
    room2 = RoomCandidate(
        room_id="slam_room_2",
        centroid_world=(7.0, 4.0),
        boundary_polygon=[[6.0, 3.0], [8.0, 3.0], [8.0, 5.0], [6.0, 5.0]],
        area_m2=4.0,
    )
    return RoomTopology(
        rooms=[room1, room2],
        connections=[("slam_room_1", "slam_room_2")],
    )


# ── 测试 2.3: GatewayServer SLAM 地图加载集成 ──

class TestGatewaySlamIntegration:
    """GatewayServer SLAM 地图加载集成测试"""

    @patch("mosaic.runtime.scene_graph_manager.SceneGraphManager.merge_room_topology")
    @patch("mosaic.runtime.map_analyzer.MapAnalyzer.extract_room_topology")
    @patch("mosaic.runtime.map_analyzer.MapAnalyzer.load_map")
    @patch("mosaic.runtime.slam_map_detector.SlamMapDetector.detect")
    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_with_map_calls_merge_room_topology(
        self,
        mock_discover: MagicMock,
        mock_detect: MagicMock,
        mock_load_map: MagicMock,
        mock_extract: MagicMock,
        mock_merge: MagicMock,
    ) -> None:
        """有 SLAM 地图时，应调用 merge_room_topology 合并拓扑到场景图

        Validates: Requirements 2.1
        """
        from mosaic.gateway.server import GatewayServer

        # 模拟检测到地图路径
        mock_detect.return_value = "/fake/path/house_map.yaml"
        # 模拟拓扑提取结果
        topology = _mock_room_topology()
        mock_extract.return_value = topology

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            # 配置 slam_map 和 slam_map_dir
            scene_cfg = {
                "environment_config": env_path,
                "slam_map": "/fake/path/house_map.yaml",
                "slam_map_dir": "/fake/maps",
            }
            mosaic_path = _make_mosaic_yaml(
                tmpdir, scene_graph_section=scene_cfg,
            )

            server = GatewayServer(config_path=mosaic_path)

            # 验证 detect 被调用
            mock_detect.assert_called_once()
            # 验证 load_map 被调用
            mock_load_map.assert_called_once_with("/fake/path/house_map.yaml")
            # 验证 extract_room_topology 被调用
            mock_extract.assert_called_once()
            # 验证 merge_room_topology 被调用，传入了拓扑
            mock_merge.assert_called_once_with(topology)
            # 场景图管理器应正常初始化
            assert server._scene_graph_mgr is not None

    @patch("mosaic.runtime.slam_map_detector.SlamMapDetector.detect")
    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_without_map_degrades_normally(
        self,
        mock_discover: MagicMock,
        mock_detect: MagicMock,
    ) -> None:
        """无 SLAM 地图时，系统正常启动，降级为 YAML 静态场景图

        Validates: Requirements 2.2
        """
        from mosaic.gateway.server import GatewayServer

        # 模拟未检测到地图
        mock_detect.return_value = None

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            # 不配置 slam_map，也不配置 slam_map_dir
            scene_cfg = {
                "environment_config": env_path,
            }
            mosaic_path = _make_mosaic_yaml(
                tmpdir, scene_graph_section=scene_cfg,
            )

            server = GatewayServer(config_path=mosaic_path)

            # 场景图管理器应正常初始化（来自 YAML 配置）
            assert server._scene_graph_mgr is not None
            # YAML 配置中的 room_a 节点应存在
            graph = server._scene_graph_mgr.get_full_graph()
            assert graph.get_node("room_a") is not None

    @patch("mosaic.runtime.map_analyzer.MapAnalyzer.load_map",
           side_effect=RuntimeError("模拟地图加载失败"))
    @patch("mosaic.runtime.slam_map_detector.SlamMapDetector.detect")
    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_map_loading_exception_degrades_gracefully(
        self,
        mock_discover: MagicMock,
        mock_detect: MagicMock,
        mock_load_map: MagicMock,
    ) -> None:
        """地图加载异常时，降级处理，不影响系统启动

        Validates: Requirements 2.3
        """
        from mosaic.gateway.server import GatewayServer

        # 模拟检测到地图路径，但加载时抛出异常
        mock_detect.return_value = "/fake/path/house_map.yaml"

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            scene_cfg = {
                "environment_config": env_path,
                "slam_map": "/fake/path/house_map.yaml",
            }
            mosaic_path = _make_mosaic_yaml(
                tmpdir, scene_graph_section=scene_cfg,
            )

            # 不应抛出异常
            server = GatewayServer(config_path=mosaic_path)

            # 场景图管理器应正常初始化（降级为 YAML 配置）
            assert server._scene_graph_mgr is not None
            # YAML 配置中的节点应存在
            graph = server._scene_graph_mgr.get_full_graph()
            assert graph.get_node("room_a") is not None
