from __future__ import annotations

"""
CapabilityRegistry — 能力注册中心

管理 Capability 的注册、注销和意图解析。
内部维护 name → Capability 和 intent → Capability 的双重映射。
"""

from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.data_models import CapabilityInfo


class CapabilityRegistry:
    """能力注册中心 — 管理 Capability 的注册、注销和意图解析"""

    def __init__(self) -> None:
        # name → Capability 实例映射
        self._capabilities: dict[str, Capability] = {}
        # intent → Capability 实例映射
        self._intent_map: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        """注册 Capability，自动纳入其支持的意图

        Args:
            capability: 待注册的能力实例
        """
        name = capability.get_name()
        self._capabilities[name] = capability
        # 遍历该能力支持的所有意图，建立意图 → 能力映射
        for intent in capability.get_supported_intents():
            self._intent_map[intent] = capability

    def unregister(self, name: str) -> None:
        """注销 Capability，移除该能力及其所有意图映射

        Args:
            name: 待注销的能力名称
        """
        capability = self._capabilities.pop(name, None)
        if capability is None:
            return
        # 移除该能力关联的所有意图映射
        intents_to_remove = [
            intent
            for intent, cap in self._intent_map.items()
            if cap is capability
        ]
        for intent in intents_to_remove:
            del self._intent_map[intent]

    def resolve(self, intent: str) -> Capability:
        """根据意图解析到对应 Capability

        Args:
            intent: 意图名称

        Returns:
            支持该意图的 Capability 实例

        Raises:
            KeyError: 未找到支持该意图的已注册 Capability
        """
        if intent not in self._intent_map:
            raise KeyError(f"未注册的意图: '{intent}'，无法解析到对应的 Capability")
        return self._intent_map[intent]

    def list_capabilities(self) -> list[CapabilityInfo]:
        """返回所有已注册 Capability 的信息列表

        Returns:
            CapabilityInfo 列表，包含每个能力的名称、支持意图和描述
        """
        result = []
        for name, capability in self._capabilities.items():
            info = CapabilityInfo(
                name=name,
                supported_intents=capability.get_supported_intents(),
                description=capability.get_capability_description(),
            )
            result.append(info)
        return result
