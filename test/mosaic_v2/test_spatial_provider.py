# test/mosaic_v2/test_spatial_provider.py
"""SpatialProvider 属性基测试

# Feature: scene-graph-integration, Property 1: SpatialProvider 坐标解析往返一致性
"""

import pytest
from hypothesis import given, settings, strategies as st

from mosaic.runtime.scene_graph import (
    EdgeType,
    NodeType,
    SceneEdge,
    SceneGraph,
    SceneNode,
)
from mosaic.runtime.spatial_provider import LocationNotFoundError, SpatialProvider


# ── Hypothesis 策略 ──

# 生成唯一标签列表（避免模糊匹配歧义）
# 使用纯 ASCII 字母标签，确保互不包含
def _unique_labels_strategy(min_size: int = 1, max_size: int = 10):
    """生成互不包含的唯一标签列表

    为避免 find_by_label 的子串匹配导致歧义，
    每个标签使用 'node_XX' 格式，确保互不为子串关系。
    """
    return st.integers(min_value=min_size, max_value=max_size).flatmap(
        lambda n: st.just([f"node_{i:04d}" for i in range(n)])
    )


# 有效浮点坐标（排除 NaN、Inf）
_coord_strategy = st.floats(
    min_value=-1000.0, max_value=1000.0,
    allow_nan=False, allow_infinity=False,
)

_position_strategy = st.tuples(_coord_strategy, _coord_strategy)


# 生成带有 position 的随机场景图
@st.composite
def scene_graph_with_positioned_nodes(draw):
    """生成包含至少一个有 position 节点的随机场景图

    返回 (SceneGraph, 有 position 的节点列表)
    """
    labels = draw(_unique_labels_strategy(min_size=1, max_size=8))
    node_types = [NodeType.ROOM, NodeType.FURNITURE, NodeType.OBJECT, NodeType.APPLIANCE]

    graph = SceneGraph()
    positioned_nodes = []

    for i, label in enumerate(labels):
        node_type = draw(st.sampled_from(node_types))
        position = draw(_position_strategy)
        node = SceneNode(
            node_id=f"id_{i:04d}",
            node_type=node_type,
            label=label,
            position=position,
        )
        graph.add_node(node)
        positioned_nodes.append(node)

    return graph, positioned_nodes


# ── Property 1: SpatialProvider 坐标解析往返一致性 ──

# Feature: scene-graph-integration, Property 1: SpatialProvider 坐标解析往返一致性
# **Validates: Requirements 2.1, 2.2, 2.7**
@settings(max_examples=100)
@given(data=scene_graph_with_positioned_nodes())
def test_resolve_location_roundtrip_consistency(data):
    """Property 1: 对所有具有 position 的节点，
    resolve_location(node.label) 返回的坐标与直接查询 position 一致。

    验证 SpatialProvider 的坐标解析往返一致性：
    - 构建随机场景图，所有节点都有 position
    - 对每个节点调用 resolve_location(label)
    - 断言返回坐标与节点 position 完全一致
    """
    graph, positioned_nodes = data
    provider = SpatialProvider(graph)

    for node in positioned_nodes:
        # 通过 SpatialProvider 解析坐标
        resolved = provider.resolve_location(node.label)
        # 直接从节点获取坐标
        expected = node.position

        assert resolved == expected, (
            f"节点 '{node.label}' 坐标不一致: "
            f"resolve_location 返回 {resolved}, 期望 {expected}"
        )


# ── Property 2 辅助策略 ──

# 房间类型前缀，用于生成足够长且有意义的标签
_ROOM_PREFIXES = [
    "room_kitchen", "room_bedroom", "room_bathroom",
    "room_living", "room_garage", "room_office",
    "room_dining", "room_hallway", "room_balcony",
    "room_laundry",
]


@st.composite
def scene_graph_with_long_label_nodes(draw):
    """生成包含长标签节点的随机场景图，用于模糊匹配测试

    标签格式如 "room_kitchen_001"，确保足够长以产生有意义的子串。
    每个标签互不包含（通过不同前缀 + 唯一编号实现）。
    返回 (SceneGraph, 有 position 的节点列表)
    """
    # 随机选择 1~8 个节点
    count = draw(st.integers(min_value=1, max_value=8))
    node_types = [NodeType.ROOM, NodeType.FURNITURE, NodeType.OBJECT, NodeType.APPLIANCE]

    graph = SceneGraph()
    positioned_nodes = []

    for i in range(count):
        # 使用不同前缀 + 唯一编号，确保标签互不包含
        prefix = _ROOM_PREFIXES[i % len(_ROOM_PREFIXES)]
        label = f"{prefix}_{i:03d}"
        node_type = draw(st.sampled_from(node_types))
        position = draw(_position_strategy)
        node = SceneNode(
            node_id=f"long_{i:04d}",
            node_type=node_type,
            label=label,
            position=position,
        )
        graph.add_node(node)
        positioned_nodes.append(node)

    return graph, positioned_nodes


# ── Property 2: SpatialProvider 模糊匹配返回有效坐标 ──

# Feature: scene-graph-integration, Property 2: SpatialProvider 模糊匹配返回有效坐标
# **Validates: Requirements 2.3**
@settings(max_examples=100)
@given(data=scene_graph_with_long_label_nodes(), rand=st.randoms(use_true_random=False))
def test_fuzzy_match_returns_valid_coordinates(data, rand):
    """Property 2: 对所有具有 position 的节点 label 的任意非空子串，
    resolve_location 返回有效的 (x, y) 坐标元组，不抛出异常。

    验证 SpatialProvider 的模糊匹配能力：
    - 构建随机场景图，所有节点都有 position 和足够长的标签
    - 对每个节点，取其 label 的随机非空子串
    - 调用 resolve_location(子串)，断言返回有效坐标
    """
    graph, positioned_nodes = data
    provider = SpatialProvider(graph)

    for node in positioned_nodes:
        label = node.label
        # 生成随机非空子串
        start = rand.randint(0, len(label) - 1)
        end = rand.randint(start + 1, len(label))
        substring = label[start:end]

        assert len(substring) > 0, "子串不应为空"

        # 调用 resolve_location，不应抛出异常
        result = provider.resolve_location(substring)

        # 断言返回值是包含两个浮点数的元组
        assert isinstance(result, tuple), (
            f"resolve_location('{substring}') 应返回 tuple，实际返回 {type(result)}"
        )
        assert len(result) == 2, (
            f"resolve_location('{substring}') 应返回长度为 2 的元组，实际长度 {len(result)}"
        )
        assert isinstance(result[0], (int, float)), (
            f"坐标 x 应为数值类型，实际为 {type(result[0])}"
        )
        assert isinstance(result[1], (int, float)), (
            f"坐标 y 应为数值类型，实际为 {type(result[1])}"
        )


# ── Property 3 辅助策略 ──

@st.composite
def scene_graph_with_hierarchy_fallback(draw):
    """生成包含层次回退场景的场景图

    构建一个 ROOM 父节点（有 position）和一个 FURNITURE 子节点（无 position），
    通过 CONTAINS 边连接。用于测试 SpatialProvider 的层次回退逻辑。
    返回 (SceneGraph, parent_node, child_node)
    """
    # 生成随机父节点 position
    parent_position = draw(_position_strategy)

    # 生成随机但互不包含的标签
    parent_idx = draw(st.integers(min_value=0, max_value=999))
    child_idx = draw(st.integers(min_value=1000, max_value=1999))
    parent_label = f"room_{parent_idx:04d}"
    child_label = f"furn_{child_idx:04d}"

    # 创建父节点（ROOM，有 position）
    parent_node = SceneNode(
        node_id=f"parent_{parent_idx}",
        node_type=NodeType.ROOM,
        label=parent_label,
        position=parent_position,
    )

    # 创建子节点（FURNITURE，无 position）
    child_node = SceneNode(
        node_id=f"child_{child_idx}",
        node_type=NodeType.FURNITURE,
        label=child_label,
        position=None,
    )

    # 构建场景图，添加 CONTAINS 边（parent → child）
    graph = SceneGraph()
    graph.add_node(parent_node)
    graph.add_node(child_node)
    graph.add_edge(SceneEdge(
        source_id=parent_node.node_id,
        target_id=child_node.node_id,
        edge_type=EdgeType.CONTAINS,
    ))

    return graph, parent_node, child_node


# ── Property 3: SpatialProvider 层次回退 ──

# Feature: scene-graph-integration, Property 3: SpatialProvider 层次回退
# **Validates: Requirements 2.5**
@settings(max_examples=100)
@given(data=scene_graph_with_hierarchy_fallback())
def test_hierarchy_fallback_returns_parent_position(data):
    """Property 3: 对无 position 但有带 position 祖先的节点，
    resolve_location 返回最近祖先的 position 坐标。

    验证 SpatialProvider 的层次回退逻辑：
    - 构建 ROOM（有 position）→ CONTAINS → FURNITURE（无 position）的层次
    - 对子节点调用 resolve_location(child.label)
    - 断言返回的坐标等于父节点的 position
    """
    graph, parent_node, child_node = data
    provider = SpatialProvider(graph)

    # 子节点无 position，应回退到父节点的 position
    resolved = provider.resolve_location(child_node.label)
    expected = parent_node.position

    assert resolved == expected, (
        f"层次回退失败: 子节点 '{child_node.label}' 应返回父节点 "
        f"'{parent_node.label}' 的坐标 {expected}，实际返回 {resolved}"
    )


# ── Property 4 辅助策略 ──

@st.composite
def scene_graph_with_nonexistent_name(draw):
    """生成一个随机场景图和一个不在场景图中的字符串

    使用 'nonexistent_' 前缀 + 随机后缀，确保不会匹配到任何节点的 label。
    返回 (SceneGraph, nonexistent_name)
    """
    # 生成随机场景图（1~5 个节点）
    count = draw(st.integers(min_value=1, max_value=5))
    node_types = [NodeType.ROOM, NodeType.FURNITURE, NodeType.OBJECT, NodeType.APPLIANCE]

    graph = SceneGraph()
    for i in range(count):
        node_type = draw(st.sampled_from(node_types))
        position = draw(_position_strategy)
        node = SceneNode(
            node_id=f"exist_{i:04d}",
            node_type=node_type,
            label=f"node_{i:04d}",
            position=position,
        )
        graph.add_node(node)

    # 生成不存在的名称：'nonexistent_' + 随机后缀
    suffix = draw(st.integers(min_value=0, max_value=99999))
    nonexistent_name = f"nonexistent_{suffix:05d}"

    return graph, nonexistent_name


# ── Property 4: SpatialProvider 不存在地名抛出异常 ──

# Feature: scene-graph-integration, Property 4: SpatialProvider 不存在地名抛出异常
# **Validates: Requirements 2.4**
@settings(max_examples=100)
@given(data=scene_graph_with_nonexistent_name())
def test_nonexistent_location_raises_error(data):
    """Property 4: 对不在场景图任何节点 label 中出现的字符串，
    resolve_location 抛出 LocationNotFoundError 异常。

    验证 SpatialProvider 的异常处理：
    - 构建随机场景图（节点标签为 'node_XXXX' 格式）
    - 生成 'nonexistent_XXXXX' 格式的字符串（不可能匹配任何节点）
    - 调用 resolve_location，断言抛出 LocationNotFoundError
    """
    graph, nonexistent_name = data
    provider = SpatialProvider(graph)

    with pytest.raises(LocationNotFoundError) as exc_info:
        provider.resolve_location(nonexistent_name)

    # 验证异常包含输入的地名信息
    assert exc_info.value.location_name == nonexistent_name, (
        f"异常中的 location_name 应为 '{nonexistent_name}'，"
        f"实际为 '{exc_info.value.location_name}'"
    )
