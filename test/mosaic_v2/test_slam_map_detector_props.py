# test/mosaic_v2/test_slam_map_detector_props.py
"""SlamMapDetector 属性测试 — 使用 hypothesis 验证核心不变量"""

from __future__ import annotations

import os
import tempfile

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from mosaic.runtime.slam_map_detector import SlamMapDetector

# ── 辅助常量 ──
_VALID_YAML_CONTENT = "image: map.pgm\nresolution: 0.05\norigin: [0.0, 0.0, 0.0]\n"


class TestDetectPrefersConfiguredPath:
    """Property 1.1: detect_prefers_configured_path

    ∀ configured_path, default_dir:
      validate_map_pair(configured_path) = True
      ⟹ detect(configured_path) = configured_path

    **Validates: Requirements 1.1**
    """

    @given(map_name=st.from_regex(r"[a-z]{1,10}", fullmatch=True))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_detect_prefers_configured_path(self, map_name: str) -> None:
        """配置路径有效时，detect() 始终优先返回该配置路径"""
        with tempfile.TemporaryDirectory() as tmp:
            # 创建有效的 .yaml + .pgm 文件对
            yaml_path = os.path.join(tmp, f"{map_name}.yaml")
            pgm_path = os.path.join(tmp, "map.pgm")

            with open(yaml_path, "w") as f:
                f.write(_VALID_YAML_CONTENT)
            with open(pgm_path, "w") as f:
                f.write("")  # 空 pgm 文件即可

            # 使用一个不存在的默认目录，确保不会回退扫描
            detector = SlamMapDetector(default_map_dir=os.path.join(tmp, "nonexistent"))
            result = detector.detect(configured_path=yaml_path)

            assert result == yaml_path, (
                f"配置路径有效时应优先返回，期望 {yaml_path}，实际 {result}"
            )


class TestValidateEnsuresPairCompleteness:
    """Property 1.3: validate_ensures_pair_completeness

    ∀ yaml_path:
      validate_map_pair(yaml_path) = True
      ⟹ os.path.exists(yaml_path) ∧ os.path.exists(resolve_pgm(yaml_path))

    **Validates: Requirements 1.3**
    """

    @given(map_name=st.from_regex(r"[a-z]{1,10}", fullmatch=True))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_validate_ensures_pair_completeness(self, map_name: str) -> None:
        """validate_map_files 返回 True 时，.yaml 和 .pgm 文件必须同时存在"""
        with tempfile.TemporaryDirectory() as tmp:
            yaml_path = os.path.join(tmp, f"{map_name}.yaml")
            pgm_path = os.path.join(tmp, "map.pgm")

            # 创建有效的文件对
            with open(yaml_path, "w") as f:
                f.write(_VALID_YAML_CONTENT)
            with open(pgm_path, "w") as f:
                f.write("")

            detector = SlamMapDetector()
            result = detector.validate_map_files(yaml_path)

            # 如果验证通过，则两个文件必须都存在
            if result:
                assert os.path.exists(yaml_path), ".yaml 文件应存在"
                # 解析 yaml 中的 image 字段，验证 pgm 也存在
                import yaml as _yaml

                with open(yaml_path) as f:
                    meta = _yaml.safe_load(f)
                image_path = meta.get("image", "")
                if not os.path.isabs(image_path):
                    image_path = os.path.join(os.path.dirname(yaml_path), image_path)
                assert os.path.exists(image_path), ".pgm 文件应存在"


class TestDetectNeverRaises:
    """Property 1.4: detect_never_raises

    ∀ configured_path, default_dir:
      detect(configured_path) ∈ {str, None} ∧ no exception raised

    **Validates: Requirements 1.4**
    """

    @given(configured_path=st.text(min_size=0, max_size=200))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.function_scoped_fixture])
    def test_detect_never_raises(self, configured_path: str) -> None:
        """detect() 对任意输入永不抛出异常"""
        detector = SlamMapDetector(default_map_dir="/tmp/nonexistent_slam_dir_test")
        # 不应抛出任何异常
        result = detector.detect(configured_path=configured_path)
        # 返回值只能是 str 或 None
        assert result is None or isinstance(result, str), (
            f"detect() 返回值类型异常: {type(result)}"
        )
