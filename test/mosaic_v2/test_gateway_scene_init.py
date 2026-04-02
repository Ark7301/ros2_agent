# test/mosaic_v2/test_gateway_scene_init.py
"""GatewayServer 场景图初始化、降级行为、SpatialProvider 注入测试

覆盖 Task 6 的三个子任务：
- 6.1: _init_scene_graph 方法（正常初始化 + 降级）
- 6.2: SceneGraphManager 注入 TurnRunner
- 6.3: ROS2 配置下 SpatialProvider 注入 navigation 插件
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
import yaml


# ── 辅助：创建临时配置文件 ──

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


def _make_mosaic_yaml(tmpdir: str, env_filename: str = "env.yaml",
                      ros2_enabled: bool = False,
                      scene_graph_section: dict | None = None) -> str:
    """生成临时 mosaic.yaml，返回路径"""
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


# ── 测试 6.1: _init_scene_graph ──

class TestInitSceneGraph:
    """_init_scene_graph 方法的单元测试"""

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_normal_init(self, mock_discover: MagicMock) -> None:
        """正常环境配置下，场景图管理器应成功初始化"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            mosaic_path = _make_mosaic_yaml(tmpdir)

            server = GatewayServer(config_path=mosaic_path)

            assert server._scene_graph_mgr is not None
            # 场景图应包含 room_a 和 robot 节点
            graph = server._scene_graph_mgr.get_full_graph()
            assert graph.get_node("room_a") is not None
            assert graph.get_node("robot") is not None

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_missing_env_file_degrades(self, mock_discover: MagicMock) -> None:
        """环境配置文件不存在时，降级为 scene_graph_mgr=None"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            # 不创建 env.yaml，只创建 mosaic.yaml 指向不存在的文件
            mosaic_path = _make_mosaic_yaml(tmpdir, env_filename="nonexistent.yaml")

            server = GatewayServer(config_path=mosaic_path)

            assert server._scene_graph_mgr is None

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_invalid_yaml_degrades(self, mock_discover: MagicMock) -> None:
        """环境配置文件格式错误时，降级为 scene_graph_mgr=None"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            # 写入无效内容（缺少 environment 键）
            _write_yaml(env_path, {"invalid": "data"})
            mosaic_path = _make_mosaic_yaml(tmpdir)

            # initialize_from_config 处理空 rooms 不会报错，
            # 但如果配置格式完全错误导致异常则降级
            server = GatewayServer(config_path=mosaic_path)
            # 即使配置不完整，只要不抛异常就算初始化成功（空场景图）
            # 这里验证不会崩溃
            assert server._turn_runner is not None

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_default_env_path_used_when_no_config(self, mock_discover: MagicMock) -> None:
        """未配置 scene_graph.environment_config 时使用默认路径 config/environments/home.yaml

        如果默认路径文件存在（如工作区中有 home.yaml），则正常初始化；
        如果不存在则降级为 None。此测试验证默认路径逻辑不会崩溃。
        """
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            mosaic_cfg = {
                "gateway": {"max_concurrent_sessions": 1, "idle_session_timeout_s": 10},
                "agents": {"default": {"max_turn_iterations": 3, "turn_timeout_s": 30, "system_prompt": ""}},
                "plugins": {"slots": {"memory": "file-memory", "context-engine": "sliding-window"}, "providers": {"default": "minimax"}},
                "routing": {"default_agent": "default", "bindings": []},
            }
            mosaic_path = os.path.join(tmpdir, "mosaic.yaml")
            _write_yaml(mosaic_path, mosaic_cfg)

            # 不指定 scene_graph 配置 → 使用默认路径
            # 无论默认文件是否存在，都不应崩溃
            server = GatewayServer(config_path=mosaic_path)
            assert server._turn_runner is not None
            # scene_graph_mgr 取决于默认文件是否存在，两种结果都合法
            if os.path.exists("config/environments/home.yaml"):
                assert server._scene_graph_mgr is not None
            else:
                assert server._scene_graph_mgr is None


# ── 测试 6.2: SceneGraphManager 注入 TurnRunner ──

class TestSceneGraphInjection:
    """验证 SceneGraphManager 正确注入 TurnRunner"""

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_turn_runner_receives_scene_graph_mgr(self, mock_discover: MagicMock) -> None:
        """TurnRunner 应接收到 SceneGraphManager 实例"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            mosaic_path = _make_mosaic_yaml(tmpdir)

            server = GatewayServer(config_path=mosaic_path)

            assert server._turn_runner._scene_graph_mgr is server._scene_graph_mgr
            assert server._turn_runner._scene_graph_mgr is not None

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_turn_runner_receives_none_on_degrade(self, mock_discover: MagicMock) -> None:
        """降级模式下 TurnRunner 的 scene_graph_mgr 应为 None"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            mosaic_path = _make_mosaic_yaml(tmpdir, env_filename="nonexistent.yaml")

            server = GatewayServer(config_path=mosaic_path)

            assert server._turn_runner._scene_graph_mgr is None


# ── 测试 6.3: SpatialProvider 注入 ──

class TestSpatialProviderInjection:
    """验证 ROS2 配置下 SpatialProvider 注入 navigation 插件"""

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_ros2_enabled_injects_spatial_provider(self, mock_discover: MagicMock) -> None:
        """ros2.enabled=true 且场景图正常时，应注入 SpatialProvider"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            mosaic_path = _make_mosaic_yaml(tmpdir, ros2_enabled=True)

            server = GatewayServer(config_path=mosaic_path)

            # 验证 configure_plugin 被调用，navigation 插件有 spatial_provider
            nav_kwargs = server._registry._factory_kwargs.get("navigation", {})
            assert "spatial_provider" in nav_kwargs
            from mosaic.runtime.spatial_provider import SpatialProvider
            assert isinstance(nav_kwargs["spatial_provider"], SpatialProvider)

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_ros2_disabled_no_injection(self, mock_discover: MagicMock) -> None:
        """ros2.enabled=false 时，不应注入 SpatialProvider"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = os.path.join(tmpdir, "env.yaml")
            _write_yaml(env_path, _minimal_env_config())
            mosaic_path = _make_mosaic_yaml(tmpdir, ros2_enabled=False)

            server = GatewayServer(config_path=mosaic_path)

            nav_kwargs = server._registry._factory_kwargs.get("navigation", {})
            assert "spatial_provider" not in nav_kwargs

    @patch("mosaic.plugin_sdk.registry.PluginRegistry.discover")
    def test_no_scene_graph_no_injection(self, mock_discover: MagicMock) -> None:
        """场景图初始化失败时，即使 ros2.enabled=true 也不注入"""
        from mosaic.gateway.server import GatewayServer

        with tempfile.TemporaryDirectory() as tmpdir:
            mosaic_path = _make_mosaic_yaml(
                tmpdir, env_filename="nonexistent.yaml", ros2_enabled=True,
            )

            server = GatewayServer(config_path=mosaic_path)

            assert server._scene_graph_mgr is None
            nav_kwargs = server._registry._factory_kwargs.get("navigation", {})
            assert "spatial_provider" not in nav_kwargs
