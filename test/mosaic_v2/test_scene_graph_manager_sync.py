# test/mosaic_v2/test_scene_graph_manager_sync.py
"""SceneGraphManager 位置同步与房间切换属性基测试

包含 Property 7 和 Property 8 两个属性测试。

# Feature: scene-graph-integration, Property 7: SceneGraphManager 位置更新后 agent 坐标一致
# Feature: scene-graph-integration, Property 8: SceneGraphManager 房间切换正确性
"""

import math

from hypothesis import given, settings, strategies as st

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.scene_graph_manager import SceneGraphManager


# ── Hypothesis 策略 ──

# 有效浮点坐标（排除 NaN、Inf）
_coord_st = st.floats(
    min_value=-1000.0, max_value=1000.0,
    allow_nan=False, allow_infinity=False,
)


def _build_simple_graph(room_positions: list[tuple[float, float]],
                        agent_at_room_idx: int = 0) -> SceneGraphManager:
    """构建包含 agent 和多个房间的最小场景图。

    Args:
        room_positions: 每个房间的 (x, y) 坐标列表
        agent_at_room_idx: agent 初始所在房间的索引
    Returns:
        已注入场景图的 SceneGraphManager
    """
    sgm = SceneGraphManager()
    graph = SceneGraph()

    # 创建房间节点
    for i, (rx, ry) in enumerate(room_positions):
        room = SceneNode(
            node_id=f"room{i}",
            node_type=NodeType.ROOM,
            label=f"room{i}",
            position=(rx, ry),
        )
        graph.add_node(room)

    # 创建相邻房间之间的 REACHABLE 边
    for i in range(len(room_positions) - 1):
        graph.add_edge(SceneEdge(
            source_id=f"room{i}",
            target_id=f"room{i+1}",
            edge_type=EdgeType.REACHABLE,
        ))

    # 创建 agent 节点
    agent = SceneNode(
        node_id="robot",
        node_type=NodeType.AGENT,
        label="机器人",
    )
    graph.add_node(agent)

    # agent AT 初始房间
    graph.add_edge(SceneEdge(
        source_id="robot",
        target_id=f"room{agent_at_room_idx}",
        edge_type=EdgeType.AT,
    ))

    sgm._graph = graph
    return sgm


# ── Property 7: SceneGraphManager 位置更新后 agent 坐标一致 ──

# Feature: scene-graph-integration, Property 7: SceneGraphManager 位置更新后 agent 坐标一致
# **Validates: Requirements 4.3**
@settings(max_examples=100)
@given(x=_coord_st, y=_coord_st)
def test_agent_position_updated_after_update_agent_position(x, y):
    """Property 7: 对所有坐标 (x, y)，update_agent_position 后 agent 节点 position 等于 (x, y)。

    验证流程：
    1. 构建包含 agent 和至少一个房间的最小场景图
    2. 生成随机 (x, y) 坐标
    3. 调用 update_agent_position(x, y)
    4. 断言 agent.position == (x, y)
    """
    # 构建最小场景图：1 个房间 + 1 个 agent
    sgm = _build_simple_graph([(0.0, 0.0)])

    # 调用位置更新
    sgm.update_agent_position(x, y)

    # 获取 agent 节点并验证坐标
    agent = sgm._graph.get_agent_node()
    assert agent is not None, "场景图中应存在 agent 节点"
    assert agent.position == (x, y), (
        f"agent.position 应为 ({x}, {y})，实际为 {agent.position}"
    )


# ── Property 8: SceneGraphManager 房间切换正确性 ──

def _euclidean_dist(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """计算两点之间的欧氏距离"""
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def _find_nearest_room_id(x: float, y: float,
                          room_positions: list[tuple[float, float]]) -> str:
    """根据最近邻匹配找到最近的房间 ID"""
    best_idx = 0
    best_dist = float("inf")
    for i, (rx, ry) in enumerate(room_positions):
        dist = _euclidean_dist((x, y), (rx, ry))
        if dist < best_dist:
            best_dist = dist
            best_idx = i
    return f"room{best_idx}"


# Feature: scene-graph-integration, Property 8: SceneGraphManager 房间切换正确性
# **Validates: Requirements 4.4, 4.5**
@settings(max_examples=100)
@given(x=_coord_st, y=_coord_st)
def test_room_switch_correctness_after_position_update(x, y):
    """Property 8: 当最近房间与当前 AT_Edge 不同时，AT_Edge 被正确更新。

    验证流程：
    1. 构建包含 2 个房间（(0,0) 和 (10,10)）和 agent（AT room0）的场景图
    2. 生成随机坐标 (x, y)
    3. 调用 update_agent_position(x, y)
    4. 计算期望的最近房间
    5. 断言 AT_Edge 指向最近房间，且旧的 AT_Edge 已被移除（只有一条 AT 边）
    """
    room_positions = [(0.0, 0.0), (10.0, 10.0)]
    sgm = _build_simple_graph(room_positions, agent_at_room_idx=0)

    # 调用位置更新
    sgm.update_agent_position(x, y)

    # 计算期望的最近房间
    expected_room_id = _find_nearest_room_id(x, y, room_positions)

    # 获取 agent 当前的 AT_Edge 目标
    agent = sgm._graph.get_agent_node()
    assert agent is not None, "场景图中应存在 agent 节点"

    # 收集所有从 agent 出发的 AT 边
    at_edges = [
        e for e in sgm._graph._outgoing.get(agent.node_id, [])
        if e.edge_type == EdgeType.AT
    ]

    # 断言：只有一条 AT 边（旧的已被移除）
    assert len(at_edges) == 1, (
        f"agent 应恰好有 1 条 AT 边，实际有 {len(at_edges)} 条"
    )

    # 断言：AT 边指向最近房间
    actual_room_id = at_edges[0].target_id
    assert actual_room_id == expected_room_id, (
        f"agent AT 边应指向 {expected_room_id}，实际指向 {actual_room_id}。"
        f" 坐标=({x}, {y})，"
        f" 到 room0 距离={_euclidean_dist((x, y), room_positions[0]):.4f}，"
        f" 到 room1 距离={_euclidean_dist((x, y), room_positions[1]):.4f}"
    )
