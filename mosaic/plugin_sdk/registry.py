# mosaic/plugin_sdk/registry.py
"""插件注册表 — 工厂模式 + 懒加载 + Slot/Provider 管理 + 自动发现"""

from typing import Any, Callable

# 返回插件实例的工厂函数类型
PluginFactory = Callable[[], Any]


class PluginRegistry:
    """插件注册表 — 工厂模式 + 懒加载

    职责：
    - 注册插件工厂函数并建立 kind 索引
    - 懒加载 + 缓存（单例语义）
    - 排他性 Slot（仅 memory / context-engine）
    - 非排他 Provider（多 Provider 共存，配置选择默认）
    - 自动发现插件包中的 create_plugin 工厂函数
    """

    def __init__(self):
        self._factories: dict[str, PluginFactory] = {}       # plugin_id → 工厂函数
        self._instances: dict[str, Any] = {}                  # plugin_id → 缓存实例
        self._kind_index: dict[str, list[str]] = {}           # kind → [plugin_id]
        # 排他性 Slot（仅 memory 和 context-engine）
        self._slots: dict[str, str] = {}                      # slot_key → active_plugin_id
        # Provider 注册表（非排他，多 Provider 共存）
        self._default_provider: str = ""

    def register(self, plugin_id: str, factory: PluginFactory, kind: str):
        """注册插件工厂函数并建立 kind 索引"""
        self._factories[plugin_id] = factory
        self._kind_index.setdefault(kind, []).append(plugin_id)

    def resolve(self, plugin_id: str) -> Any:
        """解析并实例化插件（懒加载 + 缓存，单例语义）

        首次调用时通过工厂函数创建实例并缓存，
        后续调用直接返回缓存的同一实例。
        """
        if plugin_id not in self._instances:
            factory = self._factories.get(plugin_id)
            if not factory:
                raise KeyError(f"插件未注册: {plugin_id}")
            self._instances[plugin_id] = factory()
        return self._instances[plugin_id]

    def set_slot(self, slot_key: str, plugin_id: str):
        """设置排他性 Slot（仅 memory / context-engine）"""
        self._slots[slot_key] = plugin_id

    def resolve_slot(self, slot_key: str) -> Any:
        """通过 Slot 解析当前活跃插件"""
        plugin_id = self._slots.get(slot_key, "")
        if not plugin_id:
            raise KeyError(f"Slot 未配置: {slot_key}")
        return self.resolve(plugin_id)

    def set_default_provider(self, plugin_id: str):
        """设置默认 Provider（非排他，其他 Provider 仍可通过 resolve 独立访问）"""
        self._default_provider = plugin_id

    def resolve_provider(self, plugin_id: str | None = None) -> Any:
        """解析 Provider（指定 plugin_id 或使用默认）"""
        pid = plugin_id or self._default_provider
        return self.resolve(pid)

    def list_by_kind(self, kind: str) -> list[str]:
        """列出指定类型的所有插件 ID"""
        return self._kind_index.get(kind, [])

    def discover(self, package: str = "plugins"):
        """自动发现插件包中的 create_plugin 工厂函数并注册

        扫描 channels/capabilities/providers/memory/context_engines 五个分类目录，
        单个插件加载失败不影响其他插件的发现。

        目录名到 kind 的映射使用显式字典，避免 rstrip("s") 对
        capabilities → "capabilitie" 和 context_engines → "context_engine" 的错误处理。
        plugin_id 中的下划线统一转为连字符，与配置文件命名约定一致。
        """
        import importlib
        import pkgutil

        # 显式映射：目录名 → 插件 kind（修正 rstrip("s") 的 bug）
        _CATEGORY_TO_KIND = {
            "channels": "channel",
            "capabilities": "capability",
            "providers": "provider",
            "memory": "memory",
            "context_engines": "context-engine",
        }

        for category, kind in _CATEGORY_TO_KIND.items():
            try:
                pkg = importlib.import_module(f"{package}.{category}")
                for _, name, _ in pkgutil.iter_modules(pkg.__path__):
                    try:
                        mod = importlib.import_module(f"{package}.{category}.{name}")
                        if hasattr(mod, "create_plugin"):
                            # 下划线转连字符，与配置文件命名约定一致
                            plugin_id = name.replace("_", "-")
                            self.register(plugin_id, mod.create_plugin, kind)
                    except Exception:
                        pass  # 单个插件加载失败不影响系统
            except ModuleNotFoundError:
                pass
