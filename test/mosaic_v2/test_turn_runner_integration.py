# test/mosaic_v2/test_turn_runner_integration.py
"""TurnRunner 三大集成点 — 属性基测试（Property 9-16）

覆盖场景图子图提取、prompt 输出结构、动作效果、PlanVerifier 正确性等。

# Feature: scene-graph-integration, Property 9-16
"""

import copy

import pytest
from hypothesis import given, settings, assume, strategies as st

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.plan_verifier import PlanVerifier
from mosaic.runtime.action_rules import (
    get_builtin_action_rules, apply_effect, check_precondition,
)


# ── 公共辅助函数 ──

def _build_test_graph() -> SceneGraph:
    """构建测试用场景图：2个房间 + 家具 + 物品 + agent"""
    g = SceneGraph()
    # 房间
    g.add_node(SceneNode("kitchen", NodeType.ROOM, "厨房", position=(0, 0)))
    g.add_node(SceneNode("bedroom", NodeType.ROOM, "卧室", position=(5, 0)))
    g.add_edge(SceneEdge("kitchen", "bedroom", EdgeType.REACHABLE))
    g.add_edge(SceneEdge("bedroom", "kitchen", EdgeType.REACHABLE))
    # 家具
    g.add_node(SceneNode("table", NodeType.FURNITURE, "桌子"))
    g.add_edge(SceneEdge("kitchen", "table", EdgeType.CONTAINS))
    # 物品（可抓取）
    g.add_node(SceneNode("cup", NodeType.OBJECT, "杯子", affordances=["graspable"]))
    g.add_edge(SceneEdge("table", "cup", EdgeType.ON_TOP))
    # 家电
    g.add_node(SceneNode("coffee_machine", NodeType.APPLIANCE, "咖啡机", state={"power": "off"}))
    g.add_edge(SceneEdge("kitchen", "coffee_machine", EdgeType.CONTAINS))
    # Agent
    g.add_node(SceneNode("robot", NodeType.AGENT, "机器人"))
    g.add_edge(SceneEdge("robot", "kitchen", EdgeType.AT))
    # Person
    g.add_node(SceneNode("user", NodeType.PERSON, "用户"))
    g.add_edge(SceneEdge("user", "kitchen", EdgeType.AT))
    return g


# 有效浮点坐标策略
_coord_st = st.floats(
    min_value=-100.0, max_value=100.0,
    allow_nan=False, allow_infinity=False,
)


# ── Property 9: 场景图子图提取包含关键词匹配节点 ──

# 节点标签前缀，确保互不包含
_LABEL_PREFIXES = [
    "alpha_room", "beta_furn", "gamma_obj", "delta_app",
    "epsilon_room", "zeta_furn", "eta_obj", "theta_app",
]


@st.composite
def scene_graph_with_labeled_node(draw):
    """生成包含多个带标签节点的场景图，随机选择一个节点用于关键词匹配。

    返回 (SceneGraph, 选中节点的 label, 选中节点的 node_id)
    """
    count = draw(st.integers(min_value=2, max_value=8))
    type_choices = [NodeType.ROOM, NodeType.FURNITURE, NodeType.OBJECT, NodeType.APPLIANCE]

    graph = SceneGraph()
    node_labels = []

    for i in range(count):
        prefix = _LABEL_PREFIXES[i % len(_LABEL_PREFIXES)]
        label = f"{prefix}_{i:03d}"
        ntype = draw(st.sampled_from(type_choices))
        pos = draw(st.tuples(_coord_st, _coord_st)) if ntype == NodeType.ROOM else None
        node = SceneNode(
            node_id=f"n_{i:03d}",
            node_type=ntype,
            label=label,
            position=pos,
        )
        graph.add_node(node)
        node_labels.append((label, f"n_{i:03d}"))

    # 确保至少有一个 ROOM 节点（子图提取会包含所有 ROOM）
    rooms = graph.find_by_type(NodeType.ROOM)
    if not rooms:
        room = SceneNode("fallback_room", NodeType.ROOM, "fallback_room_label", position=(0, 0))
        graph.add_node(room)

    # 添加 agent 节点
    agent = SceneNode("robot", NodeType.AGENT, "机器人")
    graph.add_node(agent)

    # 随机选择一个非 agent 节点
    chosen_idx = draw(st.integers(min_value=0, max_value=len(node_labels) - 1))
    chosen_label, chosen_id = node_labels[chosen_idx]

    return graph, chosen_label, chosen_id


# Feature: scene-graph-integration, Property 9: 场景图子图提取包含关键词匹配节点
# **Validates: Requirements 5.2**
@settings(max_examples=100)
@given(data=scene_graph_with_labeled_node())
def test_subgraph_contains_keyword_matched_node(data):
    """Property 9: 对包含某节点 label 的任务描述，
    get_task_subgraph 返回的子图包含该节点。

    验证流程：
    1. 构建随机场景图，每个节点有唯一标签
    2. 随机选择一个节点
    3. 构造包含该节点 label 的任务描述
    4. 调用 get_task_subgraph，断言子图包含该节点
    """
    graph, chosen_label, chosen_id = data

    sgm = SceneGraphManager()
    sgm._graph = graph

    # 构造包含选中节点 label 的任务描述
    task_description = f"请帮我处理 {chosen_label} 的任务"

    subgraph = sgm.get_task_subgraph(task_description)

    # 断言子图包含选中节点
    node_in_subgraph = subgraph.get_node(chosen_id)
    assert node_in_subgraph is not None, (
        f"子图应包含节点 '{chosen_label}' (id={chosen_id})，"
        f"但子图中未找到该节点。子图节点数={subgraph.node_count}"
    )


# ── Property 10: to_prompt_text 输出结构完整性 ──

@st.composite
def scene_graph_with_required_sections(draw):
    """生成包含 ROOM、FURNITURE/OBJECT、AGENT 和 REACHABLE 边的场景图。

    确保 to_prompt_text 输出应包含四个部分。
    返回 SceneGraph
    """
    # 至少 2 个房间（用于 REACHABLE 边）
    room_count = draw(st.integers(min_value=2, max_value=4))
    graph = SceneGraph()

    room_ids = []
    for i in range(room_count):
        room = SceneNode(
            node_id=f"room_{i}",
            node_type=NodeType.ROOM,
            label=f"房间_{i:02d}",
            position=draw(st.tuples(_coord_st, _coord_st)),
        )
        graph.add_node(room)
        room_ids.append(f"room_{i}")

    # 添加 REACHABLE 边（至少一条）
    for i in range(room_count - 1):
        graph.add_edge(SceneEdge(room_ids[i], room_ids[i + 1], EdgeType.REACHABLE))
        graph.add_edge(SceneEdge(room_ids[i + 1], room_ids[i], EdgeType.REACHABLE))

    # 添加家具节点 + CONTAINS 边 + 物品在家具上
    furn_type = draw(st.sampled_from([NodeType.FURNITURE, NodeType.APPLIANCE]))
    furn = SceneNode(
        node_id="furn_0",
        node_type=furn_type,
        label="测试家具",
        state={"power": "off"} if furn_type == NodeType.APPLIANCE else {},
    )
    graph.add_node(furn)
    graph.add_edge(SceneEdge(room_ids[0], "furn_0", EdgeType.CONTAINS))

    # 添加物品在家具上
    obj = SceneNode(
        node_id="obj_0",
        node_type=NodeType.OBJECT,
        label="测试物品",
        affordances=["graspable"],
    )
    graph.add_node(obj)
    graph.add_edge(SceneEdge("furn_0", "obj_0", EdgeType.ON_TOP))

    # 添加 AGENT 节点 + AT 边
    agent = SceneNode("robot", NodeType.AGENT, "机器人")
    graph.add_node(agent)
    graph.add_edge(SceneEdge("robot", room_ids[0], EdgeType.AT))

    return graph


# Feature: scene-graph-integration, Property 10: to_prompt_text 输出结构完整性
# **Validates: Requirements 5.3**
@settings(max_examples=100)
@given(graph=scene_graph_with_required_sections())
def test_prompt_text_contains_four_sections(graph):
    """Property 10: 对包含 ROOM、FURNITURE/OBJECT、AGENT 和 REACHABLE 边的场景图，
    to_prompt_text 输出包含"位置层"、"物体层"、"智能体"和"可达性"四个部分。

    验证流程：
    1. 构建包含必要节点类型和 REACHABLE 边的随机场景图
    2. 调用 to_prompt_text()
    3. 断言输出包含四个关键部分标识
    """
    text = graph.to_prompt_text()

    assert "位置层" in text, f"输出应包含'位置层'部分，实际输出:\n{text}"
    assert "物体层" in text, f"输出应包含'物体层'部分，实际输出:\n{text}"
    assert "智能体" in text, f"输出应包含'智能体'部分，实际输出:\n{text}"
    assert "可达性" in text, f"输出应包含'可达性'部分，实际输出:\n{text}"


# ── Property 11: navigate_to 执行后 AT_Edge 正确更新 ──

# Feature: scene-graph-integration, Property 11: navigate_to 执行后 AT_Edge 正确更新
# **Validates: Requirements 5.6**
@settings(max_examples=100)
@given(target_room_idx=st.integers(min_value=0, max_value=1))
def test_navigate_to_updates_at_edge(target_room_idx):
    """Property 11: 成功执行 navigate_to 后，agent 的 AT_Edge 指向目标房间。

    验证流程：
    1. 构建标准测试场景图（agent 在厨房）
    2. 随机选择目标房间（厨房或卧室）
    3. 调用 update_from_execution("navigate_to", ...)
    4. 断言 agent 的 AT_Edge 指向目标房间
    """
    graph = _build_test_graph()
    sgm = SceneGraphManager()
    sgm._graph = graph

    target_rooms = ["厨房", "卧室"]
    target_room_ids = ["kitchen", "bedroom"]
    target = target_rooms[target_room_idx]
    expected_room_id = target_room_ids[target_room_idx]

    # 执行 navigate_to
    sgm.update_from_execution("navigate_to", {"target": target}, success=True)

    # 验证 AT_Edge 指向目标房间
    agent = graph.get_agent_node()
    assert agent is not None

    at_edges = [
        e for e in graph._outgoing.get(agent.node_id, [])
        if e.edge_type == EdgeType.AT
    ]
    assert len(at_edges) == 1, (
        f"agent 应恰好有 1 条 AT 边，实际有 {len(at_edges)} 条"
    )
    assert at_edges[0].target_id == expected_room_id, (
        f"AT 边应指向 {expected_room_id}，实际指向 {at_edges[0].target_id}"
    )


# ── Property 12: pick_up 执行后 HOLDING 边正确更新 ──

# Feature: scene-graph-integration, Property 12: pick_up 执行后 HOLDING 边和原始位置边正确更新
# **Validates: Requirements 5.7**
@settings(max_examples=100)
@given(data=st.data())
def test_pick_up_updates_holding_edge(data):
    """Property 12: 成功执行 pick_up 后，agent 有 HOLDING 边，
    物品原始 ON_TOP/INSIDE 边被移除。

    验证流程：
    1. 构建标准测试场景图（杯子在桌子上，agent 在厨房）
    2. 调用 update_from_execution("pick_up", {"object_name": "杯子"})
    3. 断言 agent 有指向杯子的 HOLDING 边
    4. 断言杯子的 ON_TOP 边已被移除
    """
    graph = _build_test_graph()
    sgm = SceneGraphManager()
    sgm._graph = graph

    # 执行前验证：杯子有 ON_TOP 边
    cup_on_top_before = graph.has_edge("table", "cup", EdgeType.ON_TOP)
    assert cup_on_top_before, "执行前杯子应有 ON_TOP 边"

    # 执行 pick_up
    sgm.update_from_execution("pick_up", {"object_name": "杯子"}, success=True)

    # 验证 HOLDING 边
    agent = graph.get_agent_node()
    assert agent is not None

    holding_edges = [
        e for e in graph._outgoing.get(agent.node_id, [])
        if e.edge_type == EdgeType.HOLDING
    ]
    assert len(holding_edges) >= 1, "agent 应有至少 1 条 HOLDING 边"
    assert holding_edges[0].target_id == "cup", (
        f"HOLDING 边应指向 cup，实际指向 {holding_edges[0].target_id}"
    )

    # 验证 ON_TOP 边已移除
    cup_on_top_after = graph.has_edge("table", "cup", EdgeType.ON_TOP)
    assert not cup_on_top_after, "pick_up 后杯子的 ON_TOP 边应被移除"


# ── Property 13: PlanVerifier 不修改原始场景图 ──

# 生成随机动作名（包含已注册和未注册的）
_action_names_st = st.sampled_from([
    "navigate_to", "pick_up", "hand_over", "operate_appliance",
    "wait_appliance", "unknown_action_xyz", "custom_dance",
])


@st.composite
def random_plan_steps(draw):
    """生成随机计划步骤列表（1~5 步）。

    混合已注册和未注册的动作名，参数使用场景图中存在的标签。
    返回 list[dict]
    """
    step_count = draw(st.integers(min_value=1, max_value=5))
    steps = []
    # 场景图中可用的标签
    known_targets = ["厨房", "卧室"]
    known_objects = ["杯子", "咖啡机"]

    for _ in range(step_count):
        action = draw(_action_names_st)
        if action == "navigate_to":
            params = {"target": draw(st.sampled_from(known_targets))}
        elif action == "pick_up":
            params = {"object_name": draw(st.sampled_from(known_objects))}
        elif action == "hand_over":
            params = {"object_name": draw(st.sampled_from(known_objects))}
        elif action in ("operate_appliance", "wait_appliance"):
            params = {"appliance_name": "咖啡机"}
        else:
            # 未注册动作，随机参数
            params = {"arg": "value"}
        steps.append({"action": action, "params": params})

    return steps


# Feature: scene-graph-integration, Property 13: PlanVerifier 不修改原始场景图
# **Validates: Requirements 6.2**
@settings(max_examples=100)
@given(plan=random_plan_steps())
def test_plan_verifier_does_not_modify_original_graph(plan):
    """Property 13: verify_plan 后原始场景图的节点数、边数和状态不变。

    验证流程：
    1. 构建标准测试场景图
    2. 记录节点数、边数和所有节点状态
    3. 调用 verify_plan
    4. 断言节点数、边数和状态均未改变
    """
    graph = _build_test_graph()
    rules = get_builtin_action_rules()
    verifier = PlanVerifier(rules)

    # 记录原始状态
    original_node_count = graph.node_count
    original_edge_count = graph.edge_count
    original_states = {
        nid: dict(node.state)
        for nid, node in graph._nodes.items()
    }
    original_dict = graph.to_dict()

    # 执行验证
    verifier.verify_plan(graph, plan)

    # 断言节点数不变
    assert graph.node_count == original_node_count, (
        f"节点数应为 {original_node_count}，实际为 {graph.node_count}"
    )

    # 断言边数不变
    assert graph.edge_count == original_edge_count, (
        f"边数应为 {original_edge_count}，实际为 {graph.edge_count}"
    )

    # 断言所有节点状态不变
    for nid, orig_state in original_states.items():
        current_state = dict(graph._nodes[nid].state)
        assert current_state == orig_state, (
            f"节点 '{nid}' 状态被修改: 原始={orig_state}, 当前={current_state}"
        )


# ── Property 14: PlanVerifier 可行性判定正确性 ──

# Feature: scene-graph-integration, Property 14: PlanVerifier 可行性判定正确性
# **Validates: Requirements 6.3, 6.5**
@settings(max_examples=100)
@given(feasible=st.booleans())
def test_plan_verifier_feasibility_correctness(feasible):
    """Property 14: feasible=True 当且仅当所有前置条件在模拟场景图上满足。

    验证流程：
    - feasible=True 场景：navigate_to 可达房间（agent 在厨房，目标卧室，有 REACHABLE 边）
    - feasible=False 场景：pick_up 不在同一位置的物品（agent 在厨房，物品在卧室）
    """
    graph = _build_test_graph()
    rules = get_builtin_action_rules()
    verifier = PlanVerifier(rules)

    if feasible:
        # 可行计划：导航到卧室（从厨房出发，有 REACHABLE 边）
        plan = [{"action": "navigate_to", "params": {"target": "卧室"}}]
        result = verifier.verify_plan(graph, plan)
        assert result.feasible is True, (
            f"计划应可行，但返回 feasible=False，原因: {result.failure_reason}"
        )
        # 所有步骤应通过
        for sr in result.step_results:
            assert sr.passed is True, (
                f"步骤 {sr.step_index} ({sr.action}) 应通过，原因: {sr.reason}"
            )
    else:
        # 不可行计划：在卧室 pick_up 杯子（agent 在厨房，杯子在厨房的桌子上）
        # 先导航到卧室，然后尝试 pick_up 杯子（杯子在厨房，agent 在卧室）
        plan = [
            {"action": "navigate_to", "params": {"target": "卧室"}},
            {"action": "pick_up", "params": {"object_name": "杯子"}},
        ]
        result = verifier.verify_plan(graph, plan)
        assert result.feasible is False, (
            "计划应不可行（agent 在卧室但杯子在厨房），但返回 feasible=True"
        )
        assert result.failure_step >= 0, "应有失败步骤索引"
        assert result.failure_reason != "", "应有失败原因"


# ── Property 15: PlanVerifier 未注册动作跳过验证 ──

@st.composite
def plan_with_unregistered_actions(draw):
    """生成包含未注册动作名的计划步骤。

    动作名使用 'unregistered_' 前缀 + 随机后缀，确保不在内置规则中。
    返回 list[dict]
    """
    count = draw(st.integers(min_value=1, max_value=5))
    steps = []
    for i in range(count):
        suffix = draw(st.integers(min_value=0, max_value=9999))
        action_name = f"unregistered_{suffix:04d}"
        steps.append({
            "action": action_name,
            "params": {"arg": f"val_{i}"},
        })
    return steps


# Feature: scene-graph-integration, Property 15: PlanVerifier 未注册动作跳过验证
# **Validates: Requirements 6.6**
@settings(max_examples=100)
@given(plan=plan_with_unregistered_actions())
def test_plan_verifier_skips_unregistered_actions(plan):
    """Property 15: 未注册的动作名被标记为 passed=True。

    验证流程：
    1. 构建标准测试场景图
    2. 生成仅包含未注册动作的计划
    3. 调用 verify_plan
    4. 断言所有步骤 passed=True，整体 feasible=True
    """
    graph = _build_test_graph()
    rules = get_builtin_action_rules()
    verifier = PlanVerifier(rules)

    # 确保动作名确实未注册
    for step in plan:
        assert step["action"] not in rules, (
            f"动作 '{step['action']}' 不应在内置规则中"
        )

    result = verifier.verify_plan(graph, plan)

    # 整体应可行（所有未注册动作被跳过）
    assert result.feasible is True, (
        f"仅含未注册动作的计划应 feasible=True，"
        f"实际 feasible={result.feasible}，原因: {result.failure_reason}"
    )

    # 每一步应 passed=True
    assert len(result.step_results) == len(plan), (
        f"步骤结果数应为 {len(plan)}，实际为 {len(result.step_results)}"
    )
    for sr in result.step_results:
        assert sr.passed is True, (
            f"未注册动作 '{sr.action}' 应 passed=True，实际 passed={sr.passed}"
        )


# ── Property 16: PlanVerifier 模拟一致性 ──

# Feature: scene-graph-integration, Property 16: PlanVerifier 模拟一致性
# **Validates: Requirements 6.7**
@settings(max_examples=100)
@given(plan_idx=st.integers(min_value=0, max_value=2))
def test_plan_verifier_simulation_consistency(plan_idx):
    """Property 16: 可行计划的 final_graph 与手动逐步 apply_effect 后的结果一致。

    验证流程：
    1. 构建标准测试场景图
    2. 选择一个已知可行的计划
    3. 调用 verify_plan 获取 final_graph
    4. 在深拷贝上手动逐步 apply_effect
    5. 比较两者的 to_dict() 结果
    """
    # 预定义可行计划列表
    feasible_plans = [
        # 计划 0：导航到卧室
        [{"action": "navigate_to", "params": {"target": "卧室"}}],
        # 计划 1：导航到卧室再回厨房
        [
            {"action": "navigate_to", "params": {"target": "卧室"}},
            {"action": "navigate_to", "params": {"target": "厨房"}},
        ],
        # 计划 2：操作咖啡机（agent 在厨房，咖啡机在厨房）
        [{"action": "operate_appliance", "params": {"appliance_name": "咖啡机"}}],
    ]

    plan = feasible_plans[plan_idx]
    rules = get_builtin_action_rules()
    verifier = PlanVerifier(rules)

    # 方法 A：通过 PlanVerifier 获取 final_graph
    graph_a = _build_test_graph()
    result = verifier.verify_plan(graph_a, plan)
    assert result.feasible is True, (
        f"预定义可行计划应 feasible=True，原因: {result.failure_reason}"
    )
    assert result.final_graph is not None, "可行计划应返回 final_graph"

    # 方法 B：手动深拷贝 + 逐步 apply_effect
    graph_b = _build_test_graph().deep_copy()
    for step in plan:
        action = step["action"]
        params = step["params"]
        rule = rules.get(action)
        if rule:
            for effect in rule.effects:
                apply_effect(graph_b, effect, params)

    # 比较两者的序列化结果
    dict_a = result.final_graph.to_dict()
    dict_b = graph_b.to_dict()

    # 比较节点（按 node_id 排序后比较）
    nodes_a = sorted(dict_a["nodes"], key=lambda n: n["node_id"])
    nodes_b = sorted(dict_b["nodes"], key=lambda n: n["node_id"])
    assert len(nodes_a) == len(nodes_b), (
        f"节点数不一致: verifier={len(nodes_a)}, manual={len(nodes_b)}"
    )
    for na, nb in zip(nodes_a, nodes_b):
        assert na["node_id"] == nb["node_id"], (
            f"节点 ID 不一致: {na['node_id']} vs {nb['node_id']}"
        )
        assert na["state"] == nb["state"], (
            f"节点 '{na['node_id']}' 状态不一致: "
            f"verifier={na['state']}, manual={nb['state']}"
        )

    # 比较边（按 source_id + target_id + edge_type 排序后比较）
    def edge_key(e):
        return (e["source_id"], e["target_id"], e["edge_type"])

    edges_a = sorted(dict_a["edges"], key=edge_key)
    edges_b = sorted(dict_b["edges"], key=edge_key)
    assert len(edges_a) == len(edges_b), (
        f"边数不一致: verifier={len(edges_a)}, manual={len(edges_b)}"
    )
    for ea, eb in zip(edges_a, edges_b):
        assert edge_key(ea) == edge_key(eb), (
            f"边不一致: verifier={edge_key(ea)}, manual={edge_key(eb)}"
        )
