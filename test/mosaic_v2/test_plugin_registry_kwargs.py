# test/mosaic_v2/test_plugin_registry_kwargs.py
"""PluginRegistry 工厂参数注入属性基测试

# Feature: scene-graph-integration, Property 5: PluginRegistry 工厂参数注入

对所有注册了 factory_kwargs 的插件，resolve 时工厂函数接收到的参数与注册时一致。

**Validates: Requirements 3.1, 3.2, 3.3**
"""

from hypothesis import given, settings, strategies as st

from mosaic.plugin_sdk.registry import PluginRegistry


# ── Hypothesis 策略 ──

# 插件 ID 策略
plugin_id_st = st.from_regex(r"[a-z][a-z0-9_]{1,15}", fullmatch=True)

# 插件类型策略
kind_st = st.sampled_from(["capability", "provider", "channel", "memory", "context-engine"])

# kwargs 值策略：字符串、整数、浮点数（排除 NaN/Inf）
_kwargs_value_st = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-10000, max_value=10000),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
)

# kwargs 字典策略：字符串键 + 混合值
# 键使用合法 Python 标识符，确保可作为关键字参数传入
_kwargs_st = st.dictionaries(
    keys=st.from_regex(r"[a-z][a-z0-9_]{0,15}", fullmatch=True),
    values=_kwargs_value_st,
    min_size=1,
    max_size=10,
)

# 额外注入的 kwargs 策略（用于 configure_plugin 测试）
_extra_kwargs_st = st.dictionaries(
    keys=st.from_regex(r"extra_[a-z0-9]{1,10}", fullmatch=True),
    values=_kwargs_value_st,
    min_size=1,
    max_size=5,
)


# ── Property 5: PluginRegistry 工厂参数注入 ──

# Feature: scene-graph-integration, Property 5: PluginRegistry 工厂参数注入
# **Validates: Requirements 3.1, 3.2, 3.3**
@settings(max_examples=100)
@given(
    plugin_id=plugin_id_st,
    kind=kind_st,
    kwargs=_kwargs_st,
)
def test_register_factory_kwargs_passed_to_factory(plugin_id, kind, kwargs):
    """Property 5a: 通过 register 注册 factory_kwargs 后，
    resolve 时工厂函数接收到的参数与注册时完全一致。

    验证流程：
    1. 生成随机 kwargs 字典（字符串键，字符串/整数/浮点值）
    2. 创建 mock 工厂函数，捕获接收到的 kwargs
    3. 通过 register(factory_kwargs=kwargs) 注册插件
    4. 调用 resolve()，断言工厂函数接收到的参数与注册时一致
    """
    registry = PluginRegistry()

    # 捕获工厂函数接收到的参数
    captured_kwargs = {}

    def mock_factory(**kw):
        captured_kwargs.update(kw)
        return object()

    # 注册插件，附带 factory_kwargs
    registry.register(plugin_id, mock_factory, kind, factory_kwargs=dict(kwargs))

    # resolve 触发工厂调用
    registry.resolve(plugin_id)

    # 断言工厂接收到的参数与注册时一致
    assert captured_kwargs == kwargs, (
        f"工厂函数接收到的参数不一致: "
        f"期望 {kwargs}, 实际 {captured_kwargs}"
    )


# Feature: scene-graph-integration, Property 5: PluginRegistry 工厂参数注入
# **Validates: Requirements 3.1, 3.2, 3.3**
@settings(max_examples=100)
@given(
    plugin_id=plugin_id_st,
    kind=kind_st,
    extra_kwargs=_extra_kwargs_st,
)
def test_configure_plugin_kwargs_passed_to_factory(plugin_id, kind, extra_kwargs):
    """Property 5b: 通过 configure_plugin 注入额外 kwargs 后，
    resolve 时工厂函数接收到注入的参数。

    验证流程：
    1. 注册无参插件
    2. 通过 configure_plugin 注入随机 kwargs
    3. 调用 resolve()，断言工厂函数接收到注入的参数
    """
    registry = PluginRegistry()

    # 捕获工厂函数接收到的参数
    captured_kwargs = {}

    def mock_factory(**kw):
        captured_kwargs.update(kw)
        return object()

    # 先注册无参插件
    registry.register(plugin_id, mock_factory, kind)

    # 通过 configure_plugin 注入额外参数
    registry.configure_plugin(plugin_id, **extra_kwargs)

    # resolve 触发工厂调用
    registry.resolve(plugin_id)

    # 断言工厂接收到 configure_plugin 注入的参数
    for key, value in extra_kwargs.items():
        assert key in captured_kwargs, (
            f"configure_plugin 注入的参数 '{key}' 未传入工厂函数"
        )
        assert captured_kwargs[key] == value, (
            f"参数 '{key}' 值不一致: 期望 {value}, 实际 {captured_kwargs[key]}"
        )


# Feature: scene-graph-integration, Property 5: PluginRegistry 工厂参数注入
# **Validates: Requirements 3.1, 3.2, 3.3**
@settings(max_examples=100)
@given(
    plugin_id=plugin_id_st,
    kind=kind_st,
    register_kwargs=_kwargs_st,
    extra_kwargs=_extra_kwargs_st,
)
def test_register_and_configure_kwargs_merged(plugin_id, kind, register_kwargs, extra_kwargs):
    """Property 5c: register 的 factory_kwargs 与 configure_plugin 注入的参数合并后，
    resolve 时工厂函数接收到完整的合并参数。

    验证流程：
    1. 通过 register(factory_kwargs=kwargs1) 注册插件
    2. 通过 configure_plugin 注入额外 kwargs2
    3. 调用 resolve()，断言工厂函数接收到 kwargs1 | kwargs2 的合并结果
    """
    registry = PluginRegistry()

    # 捕获工厂函数接收到的参数
    captured_kwargs = {}

    def mock_factory(**kw):
        captured_kwargs.update(kw)
        return object()

    # 注册插件，附带初始 factory_kwargs
    registry.register(plugin_id, mock_factory, kind, factory_kwargs=dict(register_kwargs))

    # 通过 configure_plugin 注入额外参数
    registry.configure_plugin(plugin_id, **extra_kwargs)

    # resolve 触发工厂调用
    registry.resolve(plugin_id)

    # 期望结果：register_kwargs 与 extra_kwargs 合并（extra 覆盖同名键）
    expected = {**register_kwargs, **extra_kwargs}

    assert captured_kwargs == expected, (
        f"合并参数不一致: 期望 {expected}, 实际 {captured_kwargs}"
    )
