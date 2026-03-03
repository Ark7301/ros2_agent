"""配置管理器 — 读取和管理 YAML 配置文件"""

from typing import Any

import yaml


class ConfigManager:
    """配置管理器 — 从 YAML 文件加载配置并提供查询接口

    支持:
    - 从指定路径加载 YAML 配置
    - 通过点号分隔的 key 查询嵌套配置项
    - 文件不存在或格式错误时抛出明确异常
    """

    def __init__(self, config_path: str = "config/agent_config.yaml"):
        """初始化配置管理器

        Args:
            config_path: YAML 配置文件路径
        """
        self._config_path = config_path
        self._config: dict = {}

    def load(self) -> None:
        """加载 YAML 配置文件

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置文件格式错误或内容为空
        """
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"配置文件不存在: {self._config_path}"
            )
        except yaml.YAMLError as e:
            raise ValueError(
                f"配置文件格式错误: {self._config_path} — {e}"
            )

        # yaml.safe_load 对空文件返回 None，对非字典内容返回其他类型
        if not isinstance(data, dict):
            raise ValueError(
                f"配置文件内容无效（期望字典格式）: {self._config_path}"
            )

        self._config = data

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项，支持点号分隔的嵌套 key

        例如 get("model_provider.config.model") 会依次查找
        config["model_provider"]["config"]["model"]

        Args:
            key: 配置项的 key，支持点号分隔嵌套访问
            default: key 不存在时返回的默认值

        Returns:
            配置项的值，或 default
        """
        parts = key.split(".")
        current = self._config

        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default

        return current
