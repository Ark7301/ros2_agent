"""
CapabilityRegistry 单元测试

验证 register、unregister、resolve、list_capabilities 方法的正确性。
**Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.5**
"""

import sys
import os

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from typing import Callable, Optional

from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.capability_registry import CapabilityRegistry
from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus,
    ExecutionResult,
    Task,
)


# ---- 测试用 Mock Capability ----


class FakeCapability(Capability):
    """用于测试的 Capability 假实现"""

    def __init__(self, name: str, intents: list[str], description: str = ""):
        self._name = name
        self._intents = intents
        self._description = description

    def get_name(self) -> str:
        return self._name

    def get_supported_intents(self) -> list[str]:
        return self._intents

    async def execute(
        self, task: Task, feedback_callback: Callable = None
    ) -> ExecutionResult:
        return ExecutionResult(task_id=task.task_id, success=True, message="ok")

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return self._description


# ---- 单元测试 ----


class TestCapabilityRegistryRegister:
    """测试 register 方法"""

    def test_register_single_capability(self):
        """注册单个能力后可通过意图解析"""
        registry = CapabilityRegistry()
        cap = FakeCapability("nav", ["navigate_to", "patrol"])
        registry.register(cap)

        assert registry.resolve("navigate_to") is cap
        assert registry.resolve("patrol") is cap

    def test_register_multiple_capabilities(self):
        """注册多个能力后各自意图正确解析"""
        registry = CapabilityRegistry()
        nav = FakeCapability("nav", ["navigate_to"])
        motion = FakeCapability("motion", ["rotate", "stop"])

        registry.register(nav)
        registry.register(motion)

        assert registry.resolve("navigate_to") is nav
        assert registry.resolve("rotate") is motion
        assert registry.resolve("stop") is motion


class TestCapabilityRegistryUnregister:
    """测试 unregister 方法"""

    def test_unregister_removes_capability_and_intents(self):
        """注销后该能力的所有意图不可解析"""
        registry = CapabilityRegistry()
        cap = FakeCapability("nav", ["navigate_to", "patrol"])
        registry.register(cap)
        registry.unregister("nav")

        with pytest.raises(KeyError):
            registry.resolve("navigate_to")
        with pytest.raises(KeyError):
            registry.resolve("patrol")

    def test_unregister_nonexistent_does_nothing(self):
        """注销不存在的能力不报错"""
        registry = CapabilityRegistry()
        registry.unregister("nonexistent")  # 不应抛出异常

    def test_unregister_does_not_affect_other_capabilities(self):
        """注销一个能力不影响其他已注册能力"""
        registry = CapabilityRegistry()
        nav = FakeCapability("nav", ["navigate_to"])
        motion = FakeCapability("motion", ["rotate"])

        registry.register(nav)
        registry.register(motion)
        registry.unregister("nav")

        # motion 仍可解析
        assert registry.resolve("rotate") is motion
        # nav 的意图不可解析
        with pytest.raises(KeyError):
            registry.resolve("navigate_to")


class TestCapabilityRegistryResolve:
    """测试 resolve 方法"""

    def test_resolve_unregistered_intent_raises_key_error(self):
        """解析未注册意图时抛出 KeyError"""
        registry = CapabilityRegistry()
        with pytest.raises(KeyError, match="未注册的意图"):
            registry.resolve("unknown_intent")

    def test_resolve_error_message_contains_intent_name(self):
        """错误信息中包含未注册的意图名称"""
        registry = CapabilityRegistry()
        with pytest.raises(KeyError, match="fly_away"):
            registry.resolve("fly_away")


class TestCapabilityRegistryListCapabilities:
    """测试 list_capabilities 方法"""

    def test_empty_registry_returns_empty_list(self):
        """空注册中心返回空列表"""
        registry = CapabilityRegistry()
        assert registry.list_capabilities() == []

    def test_list_returns_all_registered(self):
        """返回所有已注册能力的信息"""
        registry = CapabilityRegistry()
        nav = FakeCapability("nav", ["navigate_to", "patrol"], "导航能力")
        motion = FakeCapability("motion", ["rotate", "stop"], "运动能力")

        registry.register(nav)
        registry.register(motion)

        infos = registry.list_capabilities()
        assert len(infos) == 2

        names = {info.name for info in infos}
        assert names == {"nav", "motion"}

    def test_list_capability_info_fields(self):
        """验证 CapabilityInfo 字段正确填充"""
        registry = CapabilityRegistry()
        cap = FakeCapability("nav", ["navigate_to", "patrol"], "导航能力")
        registry.register(cap)

        infos = registry.list_capabilities()
        assert len(infos) == 1

        info = infos[0]
        assert info.name == "nav"
        assert info.supported_intents == ["navigate_to", "patrol"]
        assert info.description == "导航能力"

    def test_list_after_unregister(self):
        """注销后 list_capabilities 不再包含该能力"""
        registry = CapabilityRegistry()
        cap = FakeCapability("nav", ["navigate_to"])
        registry.register(cap)
        registry.unregister("nav")

        assert registry.list_capabilities() == []


# ---- 属性测试（Hypothesis） ----

from hypothesis import given, settings, assume
from hypothesis import strategies as st


# 生成非空字符串的策略（用于能力名称和意图名称）
non_empty_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "P")),
    min_size=1,
    max_size=30,
).filter(lambda s: s.strip() != "")

# 生成非空意图列表的策略
non_empty_intent_list = st.lists(non_empty_text, min_size=1, max_size=10).map(
    lambda lst: list(dict.fromkeys(lst))  # 去重并保持顺序
).filter(lambda lst: len(lst) >= 1)


class TestCapabilityRegistryRoundTripProperty:
    """
    属性 1：CapabilityRegistry 注册-解析 round-trip

    对于任意 Capability 实例及其支持的意图列表，注册到 CapabilityRegistry 后，
    通过任意一个支持的意图调用 resolve 应返回该 Capability 实例。

    **Validates: Requirements 2.1, 2.2**
    """

    @given(
        name=non_empty_text,
        intents=non_empty_intent_list,
    )
    @settings(max_examples=100)
    def test_register_resolve_round_trip(self, name: str, intents: list[str]):
        """注册后通过每个意图 resolve 应返回同一实例"""
        registry = CapabilityRegistry()
        cap = FakeCapability(name, intents)
        registry.register(cap)

        # 验证：通过每个支持的意图 resolve 都应返回同一实例
        for intent in intents:
            resolved = registry.resolve(intent)
            assert resolved is cap, (
                f"通过意图 '{intent}' 解析到的实例不是注册的 Capability"
            )


class TestCapabilityRegistryUnregisterProperty:
    """
    属性 2：CapabilityRegistry 注销后不可解析

    对于任意已注册的 Capability，注销后通过其之前支持的任意意图调用 resolve 应抛出异常。

    **Validates: Requirements 2.3, 2.4**
    """

    @given(
        name=non_empty_text,
        intents=non_empty_intent_list,
    )
    @settings(max_examples=100)
    def test_unregister_then_resolve_raises(self, name: str, intents: list[str]):
        """注册后注销，再通过每个意图 resolve 应抛出 KeyError"""
        registry = CapabilityRegistry()
        cap = FakeCapability(name, intents)

        # 先注册
        registry.register(cap)
        # 确认注册成功
        for intent in intents:
            assert registry.resolve(intent) is cap

        # 注销
        registry.unregister(name)

        # 验证：注销后通过每个意图 resolve 都应抛出 KeyError
        for intent in intents:
            with pytest.raises(KeyError):
                registry.resolve(intent)


class TestCapabilityRegistryUnregisteredIntentProperty:
    """
    属性 3：未注册意图解析错误

    对于任意不在 CapabilityRegistry 中的意图字符串，调用 resolve 应抛出包含明确错误信息的异常。

    **Validates: Requirements 2.3**
    """

    @given(
        intent=non_empty_text,
    )
    @settings(max_examples=100)
    def test_resolve_unregistered_intent_raises_with_message(self, intent: str):
        """空注册中心中 resolve 任意意图应抛出包含错误信息的 KeyError"""
        registry = CapabilityRegistry()

        with pytest.raises(KeyError, match="未注册的意图"):
            registry.resolve(intent)
