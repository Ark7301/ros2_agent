# mosaic/runtime/slam_map_detector.py
"""SLAM 地图文件自动检测器 — 自动发现并验证 SLAM 输出的地图文件

核心功能：
1. 配置路径优先检测（支持 ~ 展开）
2. 默认目录扫描回退（按修改时间降序）
3. .yaml + .pgm 文件对完整性验证

使用场景：GatewayServer 启动时自动检测可用的 SLAM 地图文件，
将房间拓扑融合到场景图中。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class SlamMapDetector:
    """SLAM 地图文件自动检测器

    支持两级检测策略：
    1. 配置路径优先（configured_path）
    2. 默认目录扫描回退（default_map_dir 中最新的有效地图）
    """

    def __init__(self, default_map_dir: str = "~/mosaic_maps") -> None:
        """初始化检测器

        Args:
            default_map_dir: 默认地图扫描目录，支持 ~ 展开。
                             当配置路径无效时，扫描此目录寻找最新地图。
        """
        # 展开用户目录符号，存储为绝对路径
        self._default_map_dir: str = os.path.expanduser(default_map_dir)

    def validate_map_files(self, yaml_path: str) -> bool:
        """验证地图文件完整性（.yaml + 对应 .pgm 均存在）

        解析 .yaml 文件中的 image 字段，处理相对路径（基于 yaml 所在目录），
        检查对应的图像文件是否存在。

        Args:
            yaml_path: .yaml 地图元数据文件路径

        Returns:
            True 当且仅当 .yaml 存在且其引用的图像文件也存在；
            任何异常均返回 False 而非抛出。
        """
        try:
            # 检查 .yaml 文件是否存在
            if not os.path.exists(yaml_path):
                return False

            import yaml

            # 解析 .yaml 文件，提取 image 字段
            with open(yaml_path, "r") as f:
                meta = yaml.safe_load(f)

            # 元数据为空或不是字典，视为无效
            if not isinstance(meta, dict):
                return False

            image_path = meta.get("image", "")
            if not image_path:
                return False

            # 处理相对路径：基于 yaml 文件所在目录拼接
            if not os.path.isabs(image_path):
                image_path = os.path.join(os.path.dirname(yaml_path), image_path)

            # 检查图像文件是否存在
            return os.path.exists(image_path)

        except Exception:
            # 任何异常（文件读取、YAML 解析等）均返回 False
            return False

    def detect(self, configured_path: str = "") -> str | None:
        """检测可用的 SLAM 地图文件

        优先级：
        1. configured_path 指定的文件（如果存在且有效）
        2. default_map_dir 中最新的有效 .yaml 文件
        3. 返回 None（无可用地图）

        整个方法用 try-except 包裹，确保永不抛出异常。

        Args:
            configured_path: 配置文件中指定的地图路径（可为空字符串）

        Returns:
            有效的 .yaml 地图文件路径，或 None
        """
        try:
            # 步骤 1：尝试配置路径（优先级最高）
            if configured_path:
                expanded = os.path.expanduser(configured_path)
                if self.validate_map_files(expanded):
                    logger.info("使用配置路径的 SLAM 地图: %s", expanded)
                    return expanded

            # 步骤 2：扫描默认目录
            if not os.path.isdir(self._default_map_dir):
                logger.debug("默认地图目录不存在: %s", self._default_map_dir)
                return None

            # 收集所有 .yaml 文件，按修改时间降序排列
            candidates: list[tuple[float, str]] = []
            for filename in os.listdir(self._default_map_dir):
                if filename.endswith(".yaml"):
                    full_path = os.path.join(self._default_map_dir, filename)
                    if self.validate_map_files(full_path):
                        mtime = os.path.getmtime(full_path)
                        candidates.append((mtime, full_path))

            # 按修改时间降序排序，最新的排前面
            candidates.sort(reverse=True)

            # 步骤 3：返回最新有效地图路径或 None
            if candidates:
                newest_path = candidates[0][1]
                logger.info(
                    "从目录 %s 检测到最新 SLAM 地图: %s",
                    self._default_map_dir,
                    newest_path,
                )
                return newest_path

            logger.debug("默认地图目录中无有效地图: %s", self._default_map_dir)
            return None

        except Exception as e:
            # 确保永不抛出异常
            logger.warning("SLAM 地图检测过程中发生异常: %s", e)
            return None
