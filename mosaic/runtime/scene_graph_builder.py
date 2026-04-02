# mosaic/runtime/scene_graph_builder.py
"""场景图融合构建器 — 融合 SLAM 空间骨架与 VLM 语义填充

核心功能：
1. merge_room_topology：接收 MapAnalyzer 房间拓扑作为空间骨架
2. merge_detections：融合 VLM 语义识别结果到场景图
   - 根据物体世界坐标判断所属房间（boundary_polygon 点包含测试）
   - 创建 CONTAINS 边和层次关系
   - 节点去重：相同 label 且距离 < 0.5m 时更新已有节点
3. 融合完成后通过 HookManager 发布 scene.graph_updated 事件
"""

from __future__ import annotations

import logging
import time
from typing import Any

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.scene_analyzer import DetectedObject

logger = logging.getLogger(__name__)

# 节点类别映射：VLM category → SceneGraph NodeType
_CATEGORY_TO_NODE_TYPE = {
    "object": NodeType.OBJECT,
    "furniture": NodeType.FURNITURE,
    "appliance": NodeType.APPLIANCE,
}


class SceneGraphBuilder:
    """场景图融合构建器

    融合 MapAnalyzer 的空间骨架与 SceneAnalyzer 的语义填充，
    自动构建和增量更新 SceneGraph。
    """

    def __init__(
        self,
        scene_graph_mgr: SceneGraphManager,
        hooks: Any = None,
        merge_distance_m: float = 0.5,
    ) -> None:
        self._sgm = scene_graph_mgr
        self._hooks = hooks
        self._merge_distance_m = merge_distance_m
        # 自增 ID 计数器
        self._next_id = 1

    def merge_room_topology(self, topology: Any) -> None:
        """委托给 SceneGraphManager.merge_room_topology"""
        self._sgm.merge_room_topology(topology)

    def merge_detections(self, detections: list[DetectedObject]) -> dict:
        """融合 VLM 检测结果到场景图

        对每个 DetectedObject：
        1. 检查是否存在同名且距离 < merge_distance_m 的已有节点
        2. 存在则更新已有节点（位置、last_observed、置信度）
        3. 不存在则创建新节点，确定所属房间，添加 CONTAINS 边

        Returns:
            {"added": int, "updated": int, "total": int}
        """
        graph = self._sgm.get_full_graph()
        added = 0
        updated = 0
        now = time.time()

        for det in detections:
            if not det.label:
                continue

            position = det.world_position
            existing = self._find_existing_node(det.label, position)

            if existing:
                # 更新已有节点
                if position:
                    existing.position = position
                existing.last_observed = now
                existing.confidence = min(1.0, existing.confidence + 0.1)
                updated += 1
            else:
                # 创建新节点
                node_type = _CATEGORY_TO_NODE_TYPE.get(
                    det.category, NodeType.OBJECT,
                )
                node_id = f"vlm_{det.label}_{self._next_id}"
                self._next_id += 1

                node = SceneNode(
                    node_id=node_id,
                    node_type=node_type,
                    label=det.label,
                    position=position,
                    confidence=0.8,
                    last_observed=now,
                    source="vlm",
                )
                graph.add_node(node)

                # 确定所属房间并创建 CONTAINS 边
                if position:
                    room = self._find_room_for_position(position[0], position[1])
                    if room:
                        graph.add_edge(SceneEdge(
                            source_id=room.node_id,
                            target_id=node_id,
                            edge_type=EdgeType.CONTAINS,
                        ))
                    else:
                        logger.warning(
                            "物体 '%s' 坐标 %s 不在任何房间内，挂载到最近房间",
                            det.label, position,
                        )
                        nearest = self._find_nearest_room(position[0], position[1])
                        if nearest:
                            graph.add_edge(SceneEdge(
                                source_id=nearest.node_id,
                                target_id=node_id,
                                edge_type=EdgeType.CONTAINS,
                            ))

                added += 1

        total = graph.node_count

        # 发布 scene.graph_updated 事件
        if self._hooks and (added > 0 or updated > 0):
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                loop.create_task(
                    self._hooks.emit("scene.graph_updated", {
                        "added": added,
                        "updated": updated,
                        "total": total,
                    })
                )
            except RuntimeError:
                # 没有运行中的事件循环时忽略
                pass

        return {"added": added, "updated": updated, "total": total}

    def _find_existing_node(
        self,
        label: str,
        position: tuple[float, float] | None,
    ) -> SceneNode | None:
        """查找同名且距离 < merge_distance_m 的已有节点"""
        if position is None:
            return None

        graph = self._sgm.get_full_graph()
        # 精确匹配 label（大小写不敏感）
        nodes = [
            n for n in graph.find_by_label(label)
            if n.label.lower() == label.lower()
        ]

        for node in nodes:
            if node.position:
                dx = position[0] - node.position[0]
                dy = position[1] - node.position[1]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < self._merge_distance_m:
                    return node
        return None

    def _find_room_for_position(
        self, x: float, y: float,
    ) -> SceneNode | None:
        """根据坐标确定所属房间（使用 boundary_polygon 点包含测试）"""
        return self._sgm._find_room_for_position(x, y)

    def _find_nearest_room(
        self, x: float, y: float,
    ) -> SceneNode | None:
        """查找最近的房间节点（质心最近邻）"""
        graph = self._sgm.get_full_graph()
        rooms = graph.find_by_type(NodeType.ROOM)
        best_room: SceneNode | None = None
        best_dist = float("inf")
        for room in rooms:
            if room.position:
                dx = x - room.position[0]
                dy = y - room.position[1]
                dist = (dx * dx + dy * dy) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_room = room
        return best_room
