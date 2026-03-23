"""属性测试 - ConfigManager 点分路径等价 & 默认值回退

属性 14：对于任意嵌套字典 config 和点分路径 "a.b.c"，
ConfigManager.get("a.b.c") 等价于 config["a"]["b"]["c"]。
**Validates: Requirement 9.2**

属性 15：对于任意不存在于配置中的 dotpath 和任意默认值 d，
ConfigManager.get(dotpath, d) 返回 d。
**Validates: Requirement 9.3**
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings, strategies as st, assume

from mosaic.core.config import ConfigManager


# ── 策略定义 ──

# 合法的字典键：非空字母数字字符串，不含点号
key_st = st.from_regex(r"[a-z][a-z0-9_]{0,8}", fullmatch=True)

# 叶子节点值：排除 None（因为实现中 None 会回退到 default）
leaf_value_st = st.one_of(
    st.integers(min_value=-1000, max_value=1000),
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L", "N"))),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6),
)

# 生成 1~3 层嵌套键路径
key_path_st = st.lists(key_st, min_size=1, max_size=3)


def build_nested_dict(keys: list[str], value) -> dict:
    """根据键路径构建嵌套字典"""
    result = {}
    current = result
    for k in keys[:-1]:
        current[k] = {}
        current = current[k]
    current[keys[-1]] = value
    return result


def _make_config_manager(config: dict) -> ConfigManager:
    """创建 ConfigManager 并直接设置 _config，无需文件 I/O"""
    cm = ConfigManager()
    cm._config = config
    return cm


class TestConfigDotpathEquivalence:
    """属性 14: Config 点分路径等价 **Validates: Requirement 9.2**"""

    @given(keys=key_path_st, value=leaf_value_st)
    @settings(max_examples=200)
    def test_get_equals_direct_dict_indexing(self, keys, value):
        """get("a.b.c") 应等价于 config["a"]["b"]["c"]

        对于任意嵌套字典和点分路径，通过 get() 取值
        应与直接字典索引取值结果一致。
        """
        # 构建嵌套字典并设置到 ConfigManager
        config = build_nested_dict(keys, value)
        cm = _make_config_manager(config)
        dotpath = ".".join(keys)

        # 直接字典索引取值
        direct_val = config
        for k in keys:
            direct_val = direct_val[k]

        # ConfigManager.get() 取值
        got = cm.get(dotpath)

        assert got == direct_val, (
            f"点分路径 '{dotpath}' 取值不一致：\n"
            f"  get() 返回: {got!r}\n"
            f"  直接索引: {direct_val!r}\n"
            f"  config: {config}"
        )

    @given(
        keys=key_path_st,
        value=leaf_value_st,
        extra_keys=st.lists(
            st.tuples(key_st, leaf_value_st),
            min_size=0, max_size=3,
        ),
    )
    @settings(max_examples=200)
    def test_get_with_sibling_keys(self, keys, value, extra_keys):
        """在同层有兄弟键的情况下，get() 仍能正确取值"""
        config = build_nested_dict(keys, value)
        # 在顶层添加兄弟键
        for ek, ev in extra_keys:
            if ek != keys[0]:  # 避免覆盖目标路径
                config[ek] = ev

        cm = _make_config_manager(config)
        dotpath = ".".join(keys)

        # 直接索引
        direct_val = config
        for k in keys:
            direct_val = direct_val[k]

        got = cm.get(dotpath)
        assert got == direct_val, (
            f"有兄弟键时点分路径 '{dotpath}' 取值不一致：\n"
            f"  get() 返回: {got!r}\n"
            f"  直接索引: {direct_val!r}"
        )

    @given(keys=key_path_st)
    @settings(max_examples=100)
    def test_single_level_path(self, keys):
        """单层路径 get("key") 等价于 config["key"]"""
        key = keys[0]
        value = 42
        config = {key: value}
        cm = _make_config_manager(config)

        got = cm.get(key)
        assert got == config[key], (
            f"单层路径 '{key}' 取值不一致：get()={got!r}, 直接={config[key]!r}"
        )


class TestConfigDefaultFallback:
    """属性 15: Config 默认值回退 **Validates: Requirement 9.3**"""

    @given(
        missing_keys=key_path_st,
        default_value=leaf_value_st,
    )
    @settings(max_examples=200)
    def test_missing_path_returns_default(self, missing_keys, default_value):
        """不存在的点分路径应返回指定的默认值

        对于任意不存在于配置中的 dotpath 和任意默认值 d，
        ConfigManager.get(dotpath, d) 应返回 d。
        """
        # 空配置，任何路径都不存在
        cm = _make_config_manager({})
        dotpath = ".".join(missing_keys)

        got = cm.get(dotpath, default_value)
        assert got == default_value, (
            f"空配置中路径 '{dotpath}' 应返回默认值 {default_value!r}，"
            f"实际返回 {got!r}"
        )

    @given(
        existing_keys=key_path_st,
        existing_value=leaf_value_st,
        missing_suffix=key_st,
        default_value=leaf_value_st,
    )
    @settings(max_examples=200)
    def test_extended_path_returns_default(
        self, existing_keys, existing_value, missing_suffix, default_value
    ):
        """已有路径追加不存在的后缀键时，应返回默认值

        例如 config 有 "a.b"=42，查询 "a.b.c" 应返回 default。
        """
        config = build_nested_dict(existing_keys, existing_value)
        cm = _make_config_manager(config)

        # 在已有路径后追加一个不存在的键
        extended_path = ".".join(existing_keys) + "." + missing_suffix
        got = cm.get(extended_path, default_value)

        assert got == default_value, (
            f"扩展路径 '{extended_path}' 应返回默认值 {default_value!r}，"
            f"实际返回 {got!r}"
        )

    @given(
        existing_keys=key_path_st,
        existing_value=leaf_value_st,
        unrelated_keys=key_path_st,
        default_value=leaf_value_st,
    )
    @settings(max_examples=200)
    def test_unrelated_path_returns_default(
        self, existing_keys, existing_value, unrelated_keys, default_value
    ):
        """查询与已有配置完全不相关的路径时，应返回默认值"""
        config = build_nested_dict(existing_keys, existing_value)
        cm = _make_config_manager(config)

        # 确保查询路径与已有路径不同
        assume(unrelated_keys[0] != existing_keys[0])
        unrelated_path = ".".join(unrelated_keys)

        got = cm.get(unrelated_path, default_value)
        assert got == default_value, (
            f"不相关路径 '{unrelated_path}' 应返回默认值 {default_value!r}，"
            f"实际返回 {got!r}"
        )

    @given(default_value=leaf_value_st)
    @settings(max_examples=100)
    def test_none_default_is_respected(self, default_value):
        """默认值为 None 时也应正确返回（使用显式 None）"""
        cm = _make_config_manager({})
        got = cm.get("nonexistent.path", None)
        assert got is None, (
            f"默认值为 None 时应返回 None，实际返回 {got!r}"
        )

    @given(
        existing_keys=key_path_st,
        existing_value=leaf_value_st,
        default_value=leaf_value_st,
    )
    @settings(max_examples=100)
    def test_existing_path_ignores_default(
        self, existing_keys, existing_value, default_value
    ):
        """已存在的路径应返回实际值，忽略默认值"""
        config = build_nested_dict(existing_keys, existing_value)
        cm = _make_config_manager(config)
        dotpath = ".".join(existing_keys)

        got = cm.get(dotpath, default_value)
        assert got == existing_value, (
            f"已存在路径 '{dotpath}' 应返回实际值 {existing_value!r}，"
            f"而非默认值 {default_value!r}，实际返回 {got!r}"
        )
