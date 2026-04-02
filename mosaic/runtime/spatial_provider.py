# mosaic/runtime/spatial_provider.py
"""语义地名到世界坐标的解析器

将用户提到的语义地名（如"厨房"、"茶几"）解析为 (x, y) 世界坐标，
供 NavigationCapability 在 Nav2 模式下发送精确导航目标。

查找策略：
1. 精确匹配 label（大小写不敏感）
2. 模糊匹配（find_by_label 子串匹配）
3. 取最佳匹配节点的 position
4. 若无 position，沿 CONTAINS 边向上查找父节点坐标
"""

from __future__ import annotations

from mosaic.runtime.scene_graph import EdgeType, SceneGraph, SceneNode


class LocationNotFoundError(Exception):
    """语义地名无法解析为坐标"""

    def __init__(self, location_name: str, reason: str = ""):
        self.location_name = location_name
        super().__init__(f"无法解析位置 '{location_name}': {reason}")


class SpatialProvider:
    """语义地名到世界坐标的解析器"""

    def __init__(self, scene_graph: SceneGraph) -> None:
        self._graph = scene_graph

    def resolve_location(self, name: str) -> tuple[float, float]:
        """将语义地名解析为 (x, y) 世界坐标

        查找策略：
        1. 精确匹配 label（大小写不敏感）
        2. 模糊匹配（find_by_label 子串匹配）
        3. 取最佳匹配节点的 position
        4. 若无 position，沿 CONTAINS 边向上查找父节点
        """
        # 第一步：尝试精确匹配（大小写不敏感）
        name_lower = name.lower()
        exact_matches = [
            n for n in self._graph.find_by_label(name)
            if n.label.lower() == name_lower
        ]
        if exact_matches:
            return self._get_position_with_fallback(exact_matches[0])

        # 第二步：模糊匹配（find_by_label 做子串匹配）
        fuzzy_matches = self._graph.find_by_label(name)
        if fuzzy_matches:
            return self._get_position_with_fallback(fuzzy_matches[0])

        # 无匹配节点
        raise LocationNotFoundError(name, "场景图中无匹配节点")

    def _get_position_with_fallback(self, node: SceneNode) -> tuple[float, float]:
        """获取节点坐标，无坐标时沿 CONTAINS 层次向上回退

        Args:
            node: 目标场景图节点

        Returns:
            (x, y) 世界坐标元组

        Raises:
            LocationNotFoundError: 节点及其所有祖先均无 position 属性
        """
        if node.position is not None:
            return node.position

        # 沿 CONTAINS 边向上查找父节点
        parent = self._graph.get_parent(node.node_id, EdgeType.CONTAINS)
        if parent is not None:
            return self._get_position_with_fallback(parent)

        raise LocationNotFoundError(
            node.label, "节点及其所有祖先均无 position 属性"
        )
