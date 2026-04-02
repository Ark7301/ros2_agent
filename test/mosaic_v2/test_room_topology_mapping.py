# test/mosaic_v2/test_room_topology_mapping.py
"""RoomTopology 到 SceneGraph 映射属性基测试

包含 Property 19 和 Property 20 两个属性测试。

# Feature: scene-graph-integration, Property 19: RoomTopology 到 SceneGraph 的映射完整性
# Feature: scene-graph-integration, Property 20: 点包含测试确定房间归属
"""

from hypothesis import given, settings, strategies as st, assume

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.map_analyzer import RoomCandidate, RoomTopology


# ── Hypothesis 策略 ──

# 有效浮点坐标（排除 NaN、Inf）
_coord_st = st.floats(
    min_value=-500.0, max_value=500.0,
    allow_nan=False, allow_infinity=False,
)


def _make_rect_polygon(cx: float, cy: float,
                       half_w: float, half_h: float) -> list[list[float]]:
    """以 (cx, cy) 为中心生成矩形多边形（逆时针顶点序）"""
    return [
        [cx - half_w, cy - half_h],
        [cx + half_w, cy - half_h],
        [cx + half_w, cy + half_h],
        [cx - half_w, cy + half_h],
    ]


# 生成 1~5 个不重叠的 RoomCandidate
# 每个房间用简单矩形多边形，质心即矩形中心
@st.composite
def room_topology_st(draw):
    """生成随机 RoomTopology（1~5 个房间，矩形多边形，随机连接）"""
    n_rooms = draw(st.integers(min_value=1, max_value=5))
    rooms = []
    for i in range(n_rooms):
        cx = draw(st.floats(min_value=-100.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False))
        cy = draw(st.floats(min_value=-100.0, max_value=100.0,
                            allow_nan=False, allow_infinity=False))
        half_w = draw(st.floats(min_value=1.0, max_value=10.0,
                                allow_nan=False, allow_infinity=False))
        half_h = draw(st.floats(min_value=1.0, max_value=10.0,
                                allow_nan=False, allow_infinity=False))
        polygon = _make_rect_polygon(cx, cy, half_w, half_h)
        rooms.append(RoomCandidate(
            room_id=f"room_{i}",
            centroid_world=(cx, cy),
            boundary_polygon=polygon,
            area_m2=4.0 * half_w * half_h,
        ))

    # 生成随机连接（相邻房间对）
    connections = []
    if n_rooms >= 2:
        # 至少连接相邻索引的房间
        for i in range(n_rooms - 1):
            if draw(st.booleans()):
                connections.append((f"room_{i}", f"room_{i+1}"))

    return RoomTopology(rooms=rooms, connections=connections)


# ── Property 19: RoomTopology 到 SceneGraph 映射完整性 ──

# Feature: scene-graph-integration, Property 19: RoomTopology 到 SceneGraph 的映射完整性
# **Validates: Requirements 7.7, 7.8**
@settings(max_examples=100)
@given(topology=room_topology_st())
def test_room_topology_mapping_completeness(topology: RoomTopology):
    """Property 19: 对所有 RoomCandidate，场景图包含对应 ROOM 节点，
    position 和 boundary_polygon 正确。

    验证流程：
    1. 生成随机 RoomTopology（1~5 个房间）
    2. 调用 merge_room_topology
    3. 验证每个房间存在为 ROOM 节点，position == centroid_world
    4. 验证 properties["boundary_polygon"] == boundary_polygon
    5. 验证每个 connection 对应双向 REACHABLE 边
    """
    sgm = SceneGraphManager()

    sgm.merge_room_topology(topology)

    graph = sgm.get_full_graph()

    # 验证每个房间节点
    for room in topology.rooms:
        node = graph.get_node(room.room_id)
        assert node is not None, (
            f"场景图中应包含房间节点 {room.room_id}"
        )
        assert node.node_type == NodeType.ROOM, (
            f"节点 {room.room_id} 类型应为 ROOM，实际为 {node.node_type}"
        )
        assert node.position == room.centroid_world, (
            f"节点 {room.room_id} position 应为 {room.centroid_world}，"
            f"实际为 {node.position}"
        )
        assert node.properties.get("boundary_polygon") == room.boundary_polygon, (
            f"节点 {room.room_id} boundary_polygon 不匹配"
        )

    # 验证连接关系（双向 REACHABLE 边）
    for room_a_id, room_b_id in topology.connections:
        assert graph.has_edge(room_a_id, room_b_id, EdgeType.REACHABLE), (
            f"应存在 {room_a_id} → {room_b_id} 的 REACHABLE 边"
        )
        assert graph.has_edge(room_b_id, room_a_id, EdgeType.REACHABLE), (
            f"应存在 {room_b_id} → {room_a_id} 的 REACHABLE 边"
        )


# ── Property 20: 点包含测试确定房间归属 ──

# Feature: scene-graph-integration, Property 20: 点包含测试确定房间归属
# **Validates: Requirements 7.9, 9.8**
@settings(max_examples=100)
@given(
    cx=st.floats(min_value=-100.0, max_value=100.0,
                 allow_nan=False, allow_infinity=False),
    cy=st.floats(min_value=-100.0, max_value=100.0,
                 allow_nan=False, allow_infinity=False),
    half_w=st.floats(min_value=2.0, max_value=20.0,
                     allow_nan=False, allow_infinity=False),
    half_h=st.floats(min_value=2.0, max_value=20.0,
                     allow_nan=False, allow_infinity=False),
    dx_frac=st.floats(min_value=-0.9, max_value=0.9,
                      allow_nan=False, allow_infinity=False),
    dy_frac=st.floats(min_value=-0.9, max_value=0.9,
                      allow_nan=False, allow_infinity=False),
)
def test_point_in_room_returns_correct_room(
    cx, cy, half_w, half_h, dx_frac, dy_frac,
):
    """Property 20: 对位于某房间 boundary_polygon 内的坐标，
    _find_room_for_position 返回该房间。

    验证流程：
    1. 创建一个矩形房间（中心 cx,cy，半宽 half_w，半高 half_h）
    2. 生成严格在矩形内部的点（用 dx_frac, dy_frac 缩放）
    3. 调用 _find_room_for_position
    4. 断言返回的房间是该房间
    """
    polygon = _make_rect_polygon(cx, cy, half_w, half_h)

    # 生成严格在矩形内部的测试点
    test_x = cx + dx_frac * half_w
    test_y = cy + dy_frac * half_h

    # 构建场景图：单个房间 + boundary_polygon
    sgm = SceneGraphManager()
    room_node = SceneNode(
        node_id="target_room",
        node_type=NodeType.ROOM,
        label="target_room",
        position=(cx, cy),
        properties={"boundary_polygon": polygon},
    )
    sgm._graph.add_node(room_node)

    # 调用 _find_room_for_position
    result = sgm._find_room_for_position(test_x, test_y)

    assert result is not None, (
        f"_find_room_for_position 应返回房间节点，"
        f"测试点=({test_x}, {test_y})，房间中心=({cx}, {cy})"
    )
    assert result.node_id == "target_room", (
        f"应返回 target_room，实际返回 {result.node_id}"
    )
