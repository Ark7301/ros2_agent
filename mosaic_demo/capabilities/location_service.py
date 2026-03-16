from __future__ import annotations

"""
语义地名服务 — 维护地名到坐标的 YAML 映射

支持从 YAML 配置文件加载地名映射，运行时查询、添加地名。
"""

from typing import Optional

import yaml


class LocationService:
    """语义地名服务 — 维护地名到坐标的 YAML 映射"""

    def __init__(self, config_path: str = "config/locations.yaml"):
        self._locations: dict[str, dict[str, float]] = {}
        self._config_path = config_path

    def load(self) -> None:
        """从 YAML 文件加载地名映射"""
        with open(self._config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        # 读取 locations 字段，若不存在则为空字典
        raw = data.get("locations", {}) if data else {}
        self._locations = {
            name: {k: float(v) for k, v in coords.items()}
            for name, coords in raw.items()
        }

    def resolve_location(self, name: str) -> Optional[dict[str, float]]:
        """语义地名 → 坐标，未注册返回 None"""
        coords = self._locations.get(name)
        if coords is None:
            return None
        # 返回副本，防止外部修改内部状态
        return dict(coords)

    def add_location(self, name: str, coords: dict[str, float]) -> None:
        """添加地名映射，将新地名纳入可查询范围"""
        self._locations[name] = {k: float(v) for k, v in coords.items()}

    def list_locations(self) -> dict[str, dict[str, float]]:
        """列出所有已注册地名及坐标，返回副本"""
        return {
            name: dict(coords)
            for name, coords in self._locations.items()
        }
