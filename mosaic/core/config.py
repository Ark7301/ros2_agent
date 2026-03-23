# mosaic/core/config.py
"""配置管理器 — YAML 加载 + 点分路径取值 + 环境变量替换 + 热重载"""

import os
import re
import yaml
from pathlib import Path
from typing import Any, Callable


class ConfigManager:
    """配置管理器

    功能：
    - 从 YAML 文件加载配置
    - 点分路径取值（如 'gateway.port' → 8765）
    - ${ENV_VAR} 环境变量引用替换
    - 热重载并通知已注册的 listener
    """

    def __init__(self, config_path: str = "config/mosaic.yaml"):
        self._path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._listeners: list[Callable[[dict, dict], None]] = []

    def load(self) -> dict[str, Any]:
        """从 YAML 文件加载配置

        Raises:
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: 配置文件格式错误
        """
        with open(self._path) as f:
            raw = yaml.safe_load(f)
        self._config = self._resolve_env_vars(raw or {})
        return self._config

    def get(self, dotpath: str, default: Any = None) -> Any:
        """点分路径取值

        Args:
            dotpath: 点分隔的键路径，如 'gateway.port'
            default: 路径不存在时返回的默认值

        Returns:
            对应路径的值，不存在则返回 default
        """
        keys = dotpath.split(".")
        val = self._config
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default

    def on_change(self, listener: Callable[[dict, dict], None]) -> None:
        """注册配置变更监听器

        Args:
            listener: 回调函数，接收 (old_config, new_config) 两个参数
        """
        self._listeners.append(listener)

    def reload(self) -> None:
        """热重载配置文件并通知所有 listener"""
        old = self._config.copy()
        self.load()
        for listener in self._listeners:
            listener(old, self._config)

    def _resolve_env_vars(self, obj: Any) -> Any:
        """递归替换 ${ENV_VAR} 环境变量引用

        未设置的环境变量保留原始 ${ENV_VAR} 字符串不替换
        """
        if isinstance(obj, str):
            return re.sub(
                r'\$\{(\w+)\}',
                lambda m: os.environ.get(m.group(1), m.group(0)),
                obj,
            )
        elif isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        return obj
