# test/mosaic_v2/test_slam_map_detector.py
"""SlamMapDetector 单元测试 — 验证核心检测和验证逻辑

Requirements: 1.1, 1.2, 1.3, 1.4
"""

from __future__ import annotations

import os
import time

import pytest

from mosaic.runtime.slam_map_detector import SlamMapDetector

# ── 辅助常量 ──
_VALID_YAML_CONTENT = "image: map.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.0]\n"


def _create_map_pair(directory: str, name: str = "map") -> str:
    """在指定目录创建有效的 .yaml + .pgm 文件对，返回 yaml 路径"""
    yaml_path = os.path.join(directory, f"{name}.yaml")
    pgm_path = os.path.join(directory, f"{name}.pgm")
    with open(yaml_path, "w") as f:
        # image 字段指向同目录下的 .pgm 文件
        f.write(f"image: {name}.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.0]\n")
    with open(pgm_path, "w") as f:
        f.write("")
    return yaml_path


class TestConfiguredPathValid:
    """测试配置路径有效时直接返回 — Requirements 1.1"""

    def test_returns_configured_path_when_valid(self, tmp_path: str) -> None:
        """配置路径指向有效文件对时，detect() 直接返回该路径"""
        yaml_path = _create_map_pair(str(tmp_path), "house_map")
        detector = SlamMapDetector(default_map_dir=str(tmp_path / "empty"))
        result = detector.detect(configured_path=yaml_path)
        assert result == yaml_path


class TestFallbackToDirectoryScan:
    """测试配置路径无效时回退到目录扫描 — Requirements 1.2"""

    def test_returns_newest_map_from_directory(self, tmp_path: str) -> None:
        """配置路径无效时，返回默认目录中修改时间最新的有效地图"""
        map_dir = tmp_path / "maps"
        map_dir.mkdir()

        # 创建两个地图，old_map 先创建
        _create_map_pair(str(map_dir), "old_map")
        # 确保时间戳不同
        time.sleep(0.05)
        newest_yaml = _create_map_pair(str(map_dir), "new_map")

        detector = SlamMapDetector(default_map_dir=str(map_dir))
        result = detector.detect(configured_path="/nonexistent/path.yaml")

        assert result == newest_yaml, f"应返回最新地图，期望 {newest_yaml}，实际 {result}"


class TestPgmMissing:
    """测试 .pgm 缺失时 validate_map_files 返回 False — Requirements 1.3"""

    def test_validate_returns_false_when_pgm_missing(self, tmp_path: str) -> None:
        """.yaml 存在但 .pgm 不存在时，验证应返回 False"""
        yaml_path = str(tmp_path / "map.yaml")
        with open(yaml_path, "w") as f:
            f.write(_VALID_YAML_CONTENT)
        # 不创建 map.pgm

        detector = SlamMapDetector()
        assert detector.validate_map_files(yaml_path) is False


class TestDirectoryNotExistOrEmpty:
    """测试目录不存在或为空时返回 None — Requirements 1.4"""

    def test_returns_none_when_directory_not_exist(self, tmp_path: str) -> None:
        """默认目录不存在时，detect() 返回 None 且不抛出异常"""
        detector = SlamMapDetector(default_map_dir=str(tmp_path / "nonexistent"))
        result = detector.detect(configured_path="")
        assert result is None

    def test_returns_none_when_directory_empty(self, tmp_path: str) -> None:
        """默认目录为空时，detect() 返回 None"""
        empty_dir = tmp_path / "empty_maps"
        empty_dir.mkdir()

        detector = SlamMapDetector(default_map_dir=str(empty_dir))
        result = detector.detect(configured_path="")
        assert result is None
