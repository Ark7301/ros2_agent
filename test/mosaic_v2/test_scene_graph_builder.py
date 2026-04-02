# test/mosaic_v2/test_scene_graph_builder.py
"""SceneGraphBuilder 属性基测试 — Property 25 & 26

Property 25: 节点去重 — 同名且距离 < 0.5m 的检测结果不增加节点总数，last_observed 被更新
Property 26: 融合完整性 — 融合后 to_prompt_text() 包含每个物体的 label 和所属房间信息
"""

from __future__ import annotations

import time

from hypothesis import given, settings, strategies as st

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.scene_graph_builder import SceneGraphBuilder
from mosaic.runtime.scene_analyzer import DetectedObject


# ── 辅助函数 ──

def _make_sgm_with_room(
    room_id: str = "room_1",
    room_label: str = "客厅",
    room_position: tuple[float, float] = (5.0, 5.0),
    boundary_polygon: list[list[float]] | None = None,
) -> SceneGraphManager:
    """创建包含一个房间的 SceneGraphManager"""
    sgm = SceneGraphManager()
    graph = sgm.get_full_graph()

    if boundary_polygon is None:
        boundary_polygon = [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]]

    room = SceneNode(
        node_id=room_id,
        node_type=NodeType.ROOM,
        label=room_label,
        position=room_position,
        properties={"boundary_polygon": boundary_polygon},
    )
    graph.add_node(room)
    return sgm


def _make_existing_object(
    sgm: SceneGraphManager,
    node_id: str,
    label: str,
    position: tuple[float, float],
    room_id: str = "room_1",
) -> SceneNode:
    """在场景图中添加一个已有物体节点"""
    graph = sgm.get_full_graph()
    node = SceneNode(
        node_id=node_id,
        node_type=NodeType.OBJECT,
        label=label,
        position=position,
        last_observed=1000.0,
        source="vlm",
    )
    graph.add_node(node)
    graph.add_edge(SceneEdge(
        source_id=room_id,
        target_id=node_id,
        edge_type=EdgeType.CONTAINS,
    ))
    return node


# ── Property 25: SceneGraphBuilder 节点去重 ──

# 策略：生成距离 < 0.5m 的偏移量
small_offset = st.floats(min_value=-0.3, max_value=0.3, allow_nan=False, allow_infinity=False)


@settings(max_examples=100)
@given(
    base_x=st.floats(min_value=1.0, max_value=9.0, allow_nan=False, allow_infinity=False),
    base_y=st.floats(min_value=1.0, max_value=9.0, allow_nan=False, allow_infinity=False),
    dx=st.floats(min_value=-0.2, max_value=0.2, allow_nan=False, allow_infinity=False),
    dy=st.floats(min_value=-0.2, max_value=0.2, allow_nan=False, allow_infinity=False),
)
def test_property_25_node_deduplication(base_x, base_y, dx, dy):
    """Property 25: SceneGraphBuilder 节点去重

    对已存在的同名且距离 < 0.5m 的检测结果，节点总数不增加，last_observed 被更新。

    **Validates: Requirements 9.9**
    """
    # Feature: scene-graph-integration, Property 25: SceneGraphBuilder 节点去重
    sgm = _make_sgm_with_room()

    # 添加已有物体节点
    existing = _make_existing_object(
        sgm, "obj_cup_1", "杯子", (base_x, base_y),
    )
    old_last_observed = existing.last_observed

    builder = SceneGraphBuilder(sgm, merge_distance_m=0.5)

    # 记录融合前节点总数
    count_before = sgm.get_full_graph().node_count

    # 创建距离 < 0.5m 的同名检测结果
    new_x = base_x + dx
    new_y = base_y + dy
    dist = (dx * dx + dy * dy) ** 0.5
    assert dist < 0.5, f"测试前提：偏移距离 {dist} 应 < 0.5m"

    detection = DetectedObject(
        label="杯子",
        category="object",
        bbox_pixels=(100, 100, 200, 200),
        world_position=(new_x, new_y),
    )

    result = builder.merge_detections([detection])

    # 验证：节点总数不增加
    count_after = sgm.get_full_graph().node_count
    assert count_after == count_before, (
        f"节点去重失败：融合前 {count_before}，融合后 {count_after}"
    )

    # 验证：last_observed 被更新
    assert existing.last_observed > old_last_observed, (
        f"last_observed 未更新：旧值 {old_last_observed}，新值 {existing.last_observed}"
    )

    # 验证：result 报告 updated=1, added=0
    assert result["updated"] == 1
    assert result["added"] == 0


# ── Property 26: SceneGraphBuilder 融合完整性 ──

# 策略：生成随机物体标签和位置
object_label = st.sampled_from(["杯子", "遥控器", "书本", "台灯", "花瓶", "手机"])
object_category = st.sampled_from(["object", "furniture", "appliance"])
world_x = st.floats(min_value=1.0, max_value=9.0, allow_nan=False, allow_infinity=False)
world_y = st.floats(min_value=1.0, max_value=9.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=100)
@given(
    label=object_label,
    category=object_category,
    wx=world_x,
    wy=world_y,
)
def test_property_26_merge_completeness(label, category, wx, wy):
    """Property 26: SceneGraphBuilder 融合完整性

    对所有 DetectedObject，融合后 to_prompt_text() 包含其 label 和所属房间信息。

    **Validates: Requirements 9.12**
    """
    # Feature: scene-graph-integration, Property 26: SceneGraphBuilder 融合完整性
    sgm = _make_sgm_with_room(
        room_label="客厅",
        boundary_polygon=[[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0]],
    )

    builder = SceneGraphBuilder(sgm, merge_distance_m=0.5)

    detection = DetectedObject(
        label=label,
        category=category,
        bbox_pixels=(100, 100, 200, 200),
        world_position=(wx, wy),
    )

    builder.merge_detections([detection])

    # 验证：to_prompt_text 包含物体 label
    prompt_text = sgm.get_full_graph().to_prompt_text()
    assert label in prompt_text, (
        f"融合后 to_prompt_text 不包含物体 label '{label}'。\n"
        f"prompt_text:\n{prompt_text}"
    )

    # 验证：to_prompt_text 包含所属房间信息
    assert "客厅" in prompt_text, (
        f"融合后 to_prompt_text 不包含房间信息 '客厅'。\n"
        f"prompt_text:\n{prompt_text}"
    )
