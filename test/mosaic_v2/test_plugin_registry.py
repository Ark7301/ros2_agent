"""属性测试 — PluginRegistry 注册-解析 / 单例语义 / Provider 非排他共存

属性 3: 注册工厂后 resolve(plugin_id) 返回 factory() 创建的实例
属性 4: 同一 plugin_id 多次 resolve 返回同一对象实例（id 相同）
属性 5: 所有 Provider 均可通过 resolve 独立访问，设置默认 Provider 不影响其他 Provider

**Validates: Requirements 3.1, 3.2, 3.3, 3.6**
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st, assume

from mosaic.plugin_sdk.registry import PluginRegistry


# ── Hypothesis 策略 ──

# 插件 ID 策略：合法的标识符字符串
plugin_id_st = st.from_regex(r"[a-z][a-z0-9_]{1,15}", fullmatch=True)

# 插件类型策略
kind_st = st.sampled_from(["capability", "provider", "channel", "memory", "context-engine"])

# 多个不同插件 ID 的策略
unique_plugin_ids_st = st.lists(
    plugin_id_st,
    min_size=2,
    max_size=8,
    unique=True,
)


class _FakePlugin:
    """用于测试的假插件，每次实例化生成唯一 id"""

    _counter = 0

    def __init__(self):
        _FakePlugin._counter += 1
        self.instance_id = _FakePlugin._counter


class TestPluginRegistryRoundTrip:
    """属性 3: Plugin 注册-解析 round-trip

    注册工厂后 resolve(plugin_id) 返回 factory() 创建的实例。

    **Validates: Requirements 3.1, 3.2**
    """

    @given(
        plugin_id=plugin_id_st,
        kind=kind_st,
    )
    @settings(max_examples=200)
    def test_register_then_resolve_returns_factory_instance(
        self,
        plugin_id: str,
        kind: str,
    ):
        """注册工厂函数后，resolve 返回该工厂创建的实例（Req 3.1, 3.2）。

        验证：
        1. register 存储工厂函数并建立 kind 索引
        2. resolve 通过工厂函数创建实例
        3. 返回的实例是 _FakePlugin 类型
        """
        registry = PluginRegistry()

        # 注册工厂函数
        registry.register(plugin_id, _FakePlugin, kind)

        # resolve 应返回工厂创建的实例
        instance = registry.resolve(plugin_id)
        assert isinstance(instance, _FakePlugin), (
            f"resolve 应返回 _FakePlugin 实例，实际类型: {type(instance)}"
        )

    @given(
        plugin_id=plugin_id_st,
        kind=kind_st,
    )
    @settings(max_examples=200)
    def test_resolve_unregistered_raises_key_error(
        self,
        plugin_id: str,
        kind: str,
    ):
        """resolve 未注册的 plugin_id 应抛出 KeyError（Req 3.4）。"""
        registry = PluginRegistry()

        try:
            registry.resolve(plugin_id)
            assert False, f"resolve 未注册的 '{plugin_id}' 应抛出 KeyError"
        except KeyError:
            pass  # 预期行为

    @given(
        plugin_ids=unique_plugin_ids_st,
        kind=kind_st,
    )
    @settings(max_examples=200)
    def test_register_multiple_all_resolvable(
        self,
        plugin_ids: list[str],
        kind: str,
    ):
        """注册多个插件后，每个都可以独立 resolve（Req 3.1, 3.2）。"""
        registry = PluginRegistry()

        # 注册所有插件
        for pid in plugin_ids:
            registry.register(pid, _FakePlugin, kind)

        # 每个都应可 resolve
        for pid in plugin_ids:
            instance = registry.resolve(pid)
            assert isinstance(instance, _FakePlugin), (
                f"插件 '{pid}' resolve 应返回 _FakePlugin 实例"
            )

    @given(
        plugin_id=plugin_id_st,
        kind=kind_st,
    )
    @settings(max_examples=200)
    def test_kind_index_updated_on_register(
        self,
        plugin_id: str,
        kind: str,
    ):
        """注册后 kind 索引应包含该 plugin_id（Req 3.1）。"""
        registry = PluginRegistry()
        registry.register(plugin_id, _FakePlugin, kind)

        kind_list = registry.list_by_kind(kind)
        assert plugin_id in kind_list, (
            f"注册后 kind '{kind}' 索引应包含 '{plugin_id}'"
        )



class TestPluginSingletonSemantics:
    """属性 4: Plugin 单例语义

    同一 plugin_id 多次 resolve 返回同一对象实例（id 相同）。

    **Validates: Requirement 3.3**
    """

    @given(
        plugin_id=plugin_id_st,
        kind=kind_st,
        resolve_count=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=200)
    def test_multiple_resolves_return_same_instance(
        self,
        plugin_id: str,
        kind: str,
        resolve_count: int,
    ):
        """同一 plugin_id 多次 resolve 返回同一对象（Req 3.3）。

        验证：
        1. 首次 resolve 创建实例
        2. 后续 resolve 返回缓存的同一实例
        3. 所有返回值的 id() 相同
        """
        registry = PluginRegistry()
        registry.register(plugin_id, _FakePlugin, kind)

        # 多次 resolve
        instances = [registry.resolve(plugin_id) for _ in range(resolve_count)]

        # 所有实例应是同一个对象（id 相同）
        first_id = id(instances[0])
        for i, inst in enumerate(instances):
            assert id(inst) == first_id, (
                f"第 {i+1} 次 resolve 返回的实例 id 应与首次相同，"
                f"期望 {first_id}，实际 {id(inst)}"
            )

    @given(
        plugin_id=plugin_id_st,
        kind=kind_st,
    )
    @settings(max_examples=200)
    def test_factory_called_only_once(
        self,
        plugin_id: str,
        kind: str,
    ):
        """工厂函数只在首次 resolve 时调用一次（懒加载 + 缓存）。"""
        registry = PluginRegistry()

        # 使用计数器追踪工厂调用次数
        call_count = [0]

        def counting_factory():
            call_count[0] += 1
            return _FakePlugin()

        registry.register(plugin_id, counting_factory, kind)

        # 多次 resolve
        registry.resolve(plugin_id)
        registry.resolve(plugin_id)
        registry.resolve(plugin_id)

        assert call_count[0] == 1, (
            f"工厂函数应只调用 1 次，实际调用 {call_count[0]} 次"
        )

    @given(
        plugin_ids=unique_plugin_ids_st,
        kind=kind_st,
    )
    @settings(max_examples=200)
    def test_different_plugins_have_different_instances(
        self,
        plugin_ids: list[str],
        kind: str,
    ):
        """不同 plugin_id 的实例应互相独立（不共享）。"""
        registry = PluginRegistry()

        for pid in plugin_ids:
            registry.register(pid, _FakePlugin, kind)

        instances = [registry.resolve(pid) for pid in plugin_ids]

        # 不同插件的实例 id 应不同
        instance_ids = [id(inst) for inst in instances]
        assert len(set(instance_ids)) == len(plugin_ids), (
            "不同 plugin_id 应返回不同的实例对象"
        )


class TestProviderNonExclusiveCoexistence:
    """属性 5: Provider 非排他共存

    所有 Provider 均可通过 resolve 独立访问，
    设置默认 Provider 不影响其他 Provider。

    **Validates: Requirement 3.6**
    """

    @given(
        provider_ids=st.lists(
            plugin_id_st,
            min_size=2,
            max_size=6,
            unique=True,
        ),
        default_idx=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=200)
    def test_set_default_does_not_affect_other_providers(
        self,
        provider_ids: list[str],
        default_idx: int,
    ):
        """设置默认 Provider 后，其他 Provider 仍可独立 resolve（Req 3.6）。

        验证：
        1. 注册多个 Provider
        2. 设置其中一个为默认
        3. 所有 Provider 仍可通过 resolve(provider_id) 独立访问
        """
        assume(default_idx < len(provider_ids))

        registry = PluginRegistry()

        # 注册所有 Provider
        for pid in provider_ids:
            registry.register(pid, _FakePlugin, "provider")

        # 设置默认 Provider
        default_pid = provider_ids[default_idx]
        registry.set_default_provider(default_pid)

        # 所有 Provider 仍可独立 resolve
        for pid in provider_ids:
            instance = registry.resolve(pid)
            assert isinstance(instance, _FakePlugin), (
                f"设置默认 Provider 后，'{pid}' 仍应可独立 resolve"
            )

    @given(
        provider_ids=st.lists(
            plugin_id_st,
            min_size=2,
            max_size=6,
            unique=True,
        ),
        default_idx=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=200)
    def test_resolve_provider_returns_default_when_no_id(
        self,
        provider_ids: list[str],
        default_idx: int,
    ):
        """resolve_provider() 无参数时返回默认 Provider 实例。"""
        assume(default_idx < len(provider_ids))

        registry = PluginRegistry()

        for pid in provider_ids:
            registry.register(pid, _FakePlugin, "provider")

        default_pid = provider_ids[default_idx]
        registry.set_default_provider(default_pid)

        # 无参数调用应返回默认 Provider
        default_instance = registry.resolve_provider()
        explicit_instance = registry.resolve(default_pid)

        assert id(default_instance) == id(explicit_instance), (
            "resolve_provider() 应返回与 resolve(default_pid) 相同的实例"
        )

    @given(
        provider_ids=st.lists(
            plugin_id_st,
            min_size=2,
            max_size=6,
            unique=True,
        ),
        default_idx=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=200)
    def test_providers_maintain_singleton_after_default_change(
        self,
        provider_ids: list[str],
        default_idx: int,
    ):
        """切换默认 Provider 不影响已缓存的实例（单例不变）。"""
        assume(default_idx < len(provider_ids))

        registry = PluginRegistry()

        for pid in provider_ids:
            registry.register(pid, _FakePlugin, "provider")

        # 先 resolve 所有 Provider，建立缓存
        instances_before = {pid: registry.resolve(pid) for pid in provider_ids}

        # 设置默认 Provider
        registry.set_default_provider(provider_ids[default_idx])

        # 再次 resolve，实例应不变
        for pid in provider_ids:
            instance_after = registry.resolve(pid)
            assert id(instance_after) == id(instances_before[pid]), (
                f"设置默认 Provider 后，'{pid}' 的缓存实例不应改变"
            )

    @given(
        provider_ids=st.lists(
            plugin_id_st,
            min_size=3,
            max_size=6,
            unique=True,
        ),
    )
    @settings(max_examples=200)
    def test_switching_default_provider_preserves_all_access(
        self,
        provider_ids: list[str],
    ):
        """多次切换默认 Provider，所有 Provider 始终可独立访问。"""
        registry = PluginRegistry()

        for pid in provider_ids:
            registry.register(pid, _FakePlugin, "provider")

        # 依次将每个 Provider 设为默认
        for default_pid in provider_ids:
            registry.set_default_provider(default_pid)

            # 验证默认 Provider 正确
            default_instance = registry.resolve_provider()
            expected_instance = registry.resolve(default_pid)
            assert id(default_instance) == id(expected_instance), (
                f"切换默认为 '{default_pid}' 后，resolve_provider() 应返回对应实例"
            )

            # 验证所有 Provider 仍可独立访问
            for pid in provider_ids:
                instance = registry.resolve(pid)
                assert isinstance(instance, _FakePlugin), (
                    f"切换默认 Provider 后，'{pid}' 仍应可独立 resolve"
                )
