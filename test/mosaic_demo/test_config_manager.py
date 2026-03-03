"""
ConfigManager 查询默认值属性测试

**Validates: Requirements 11.2**

使用 hypothesis 库验证：对于任意不存在于配置中的 key 和任意默认值，
ConfigManager 的 get 方法应返回该默认值。
"""

import sys
import os
import tempfile

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from mosaic_demo.config.config_manager import ConfigManager


# ---- 自定义 Hypothesis Strategy ----

# 使用带前缀的 key 确保不会与已知配置冲突
nonexistent_key = st.text(
    min_size=1, max_size=30, alphabet="abcdefghijklmnopqrstuvwxyz_"
).map(lambda k: f"__nonexistent__.{k}")

# 任意默认值：覆盖常见 Python 类型
any_default_value = st.one_of(
    st.text(max_size=50),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
    st.booleans(),
    st.none(),
    st.lists(st.integers(), max_size=5),
    st.dictionaries(
        keys=st.text(min_size=1, max_size=10), values=st.integers(), max_size=3
    ),
)


def _create_config_manager(config_data: dict) -> ConfigManager:
    """辅助函数：创建临时 YAML 文件并返回已加载的 ConfigManager"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        yaml.dump(config_data, f)
        path = f.name

    try:
        manager = ConfigManager(config_path=path)
        manager.load()
        return manager
    finally:
        os.unlink(path)


# ---- 属性测试 ----


class TestConfigManagerDefaultValue:
    """Property 16: ConfigManager 查询默认值

    **Validates: Requirements 11.2**
    """

    @given(key=nonexistent_key, default=any_default_value)
    @settings(max_examples=100)
    def test_get_nonexistent_key_returns_default(self, key: str, default):
        """
        对于任意不存在于配置中的 key 和任意默认值，
        ConfigManager 的 get 方法应返回该默认值。
        """
        # 创建包含已知内容的配置
        config_data = {"known_section": {"known_key": "known_value"}}
        manager = _create_config_manager(config_data)

        # 查询不存在的 key，应返回指定的默认值
        result = manager.get(key, default=default)
        assert result == default

    @given(default=any_default_value)
    @settings(max_examples=50)
    def test_empty_config_always_returns_default(self, default):
        """
        对于空配置文件，任意 key 的查询都应返回默认值。
        """
        manager = _create_config_manager({})

        result = manager.get("any.key.here", default=default)
        assert result == default
