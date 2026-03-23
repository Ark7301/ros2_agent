# mosaic/runtime/action_rules.py
"""动作前置条件与效果规则引擎 — VeriGraph 思路在 MOSAIC 中的落地

每个 Capability 的每个 intent 都有对应的前置条件和效果规则。
PlanVerifier 使用这些规则在场景图上模拟执行，验证计划可行性。

参考：
- VeriGraph (2024, arXiv:2411.10446) — 迭代式计划验证
- Taskography (CoRL 2021) — PDDL 前置条件/效果映射
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneEdge, NodeType, EdgeType,
)


# ── 前置条件 ──

@dataclass
class Precondition:
    """前置条件 — 场景图上必须满足的条件"""
    condition_type: str    # 条件类型标识
    params: dict[str, Any] = field(default_factory=dict)
    description: str = ""  # 人类可读描述（用于反馈给 LLM）


# ── 动作效果 ──

@dataclass
class Effect:
    """动作效果 — 执行后场景图的变化"""
    effect_type: str       # 效果类型标识
    params: dict[str, Any] = field(default_factory=dict)


# ── 动作规则 ──

@dataclass
class ActionRule:
    """动作规则 — 前置条件 + 效果"""
    action_name: str
    preconditions: list[Precondition] = field(default_factory=list)
    effects: list[Effect] = field(default_factory=list)


def _resolve_param(template: str, params: dict[str, Any]) -> str:
    """解析参数模板 {target} → 实际值"""
    if template.startswith("{") and template.endswith("}"):
        key = template[1:-1]
        return str(params.get(key, template))
    return template


# ── 前置条件检查器 ──

def check_precondition(
    graph: SceneGraph,
    pre: Precondition,
    action_params: dict[str, Any],
) -> tuple[bool, str]:
    """检查单个前置条件是否在场景图上满足

    将 PDDL 风格的前置条件转化为场景图查询。

    Returns:
        (satisfied, reason): 是否满足 + 原因说明
    """
    ctype = pre.condition_type
    # 解析参数模板
    resolved = {
        k: _resolve_param(v, action_params) if isinstance(v, str) else v
        for k, v in pre.params.items()
    }

    if ctype == "node_exists":
        label = resolved.get("label", "")
        nodes = graph.find_by_label(label)
        if nodes:
            return True, f"节点 '{label}' 存在"
        return False, f"场景图中不存在 '{label}'"

    elif ctype == "path_reachable":
        agent = graph.get_agent_node()
        target_label = resolved.get("to", "")
        targets = graph.find_by_label(target_label)
        if not agent:
            return False, "找不到机器人节点"
        if not targets:
            return False, f"找不到目标位置 '{target_label}'"
        agent_loc = graph.get_agent_location()
        if not agent_loc:
            return False, "无法确定机器人当前位置"
        # 目标可能是房间，也可能是物品所在的房间
        target_node = targets[0]
        if target_node.node_type == NodeType.ROOM:
            target_room_id = target_node.node_id
        else:
            target_room = graph.get_location_of(target_node.node_id)
            if not target_room:
                return False, f"无法确定 '{target_label}' 所在位置"
            target_room_id = target_room.node_id
        path = graph.find_path(agent_loc.node_id, target_room_id)
        if path:
            path_labels = [
                graph.get_node(n).label
                for n in path if graph.get_node(n)
            ]
            return True, f"路径: {' → '.join(path_labels)}"
        return False, f"从 {agent_loc.label} 到 {target_label} 无可达路径"

    elif ctype == "agent_at_same_location":
        obj_label = resolved.get("object", "")
        agent = graph.get_agent_node()
        obj_nodes = graph.find_by_label(obj_label)
        if not agent or not obj_nodes:
            return False, f"找不到机器人或 '{obj_label}'"
        agent_loc = graph.get_agent_location()
        obj_loc = graph.get_location_of(obj_nodes[0].node_id)
        if agent_loc and obj_loc and agent_loc.node_id == obj_loc.node_id:
            return True, "机器人与目标在同一位置"
        a_name = agent_loc.label if agent_loc else "未知"
        o_name = obj_loc.label if obj_loc else "未知"
        return False, f"机器人在{a_name}，{obj_label}在{o_name}"

    elif ctype == "node_has_affordance":
        node_label = resolved.get("node", "")
        affordance = resolved.get("affordance", "")
        nodes = graph.find_by_label(node_label)
        if not nodes:
            return False, f"找不到 '{node_label}'"
        if affordance in nodes[0].affordances:
            return True, f"'{node_label}' 具有 {affordance} 能力"
        return False, f"'{node_label}' 不具有 {affordance} 能力"

    elif ctype == "agent_not_holding":
        agent = graph.get_agent_node()
        if not agent:
            return False, "找不到机器人节点"
        holding = graph.get_children(agent.node_id, EdgeType.HOLDING)
        if not holding:
            return True, "机器人手中无物品"
        return False, f"机器人正持有 {holding[0].label}"

    elif ctype == "agent_holding":
        obj_label = resolved.get("object", "")
        agent = graph.get_agent_node()
        if not agent:
            return False, "找不到机器人节点"
        holding = graph.get_children(agent.node_id, EdgeType.HOLDING)
        if holding and obj_label.lower() in holding[0].label.lower():
            return True, f"机器人持有 {holding[0].label}"
        return False, f"机器人未持有 '{obj_label}'"

    elif ctype == "agent_near_person":
        agent = graph.get_agent_node()
        if not agent:
            return False, "找不到机器人节点"
        agent_loc = graph.get_agent_location()
        persons = graph.find_by_type(NodeType.PERSON)
        if not persons:
            return False, "场景中没有用户"
        for p in persons:
            for e in graph._outgoing.get(p.node_id, []):
                if e.edge_type == EdgeType.AT:
                    p_loc = graph.get_node(e.target_id)
                    if p_loc and agent_loc and p_loc.node_id == agent_loc.node_id:
                        return True, f"机器人与{p.label}在同一位置"
        return False, "机器人不在用户附近"

    elif ctype == "node_type_is":
        node_label = resolved.get("node", "")
        expected_type = resolved.get("type", "")
        nodes = graph.find_by_label(node_label)
        if not nodes:
            return False, f"找不到 '{node_label}'"
        if nodes[0].node_type.value == expected_type:
            return True, f"'{node_label}' 是 {expected_type} 类型"
        return False, f"'{node_label}' 不是 {expected_type} 类型"

    elif ctype == "state_equals":
        node_label = resolved.get("node", "")
        key = resolved.get("key", "")
        value = resolved.get("value", "")
        nodes = graph.find_by_label(node_label)
        if not nodes:
            return False, f"找不到 '{node_label}'"
        actual = nodes[0].state.get(key, "")
        if actual == value:
            return True, f"'{node_label}'.{key} == {value}"
        return False, f"'{node_label}'.{key} = {actual}，期望 {value}"

    return False, f"未知条件类型: {ctype}"


# ── 动作效果应用 ──

def apply_effect(
    graph: SceneGraph,
    effect: Effect,
    action_params: dict[str, Any],
) -> None:
    """在场景图上应用动作效果（原地修改）"""
    etype = effect.effect_type
    resolved = {
        k: _resolve_param(v, action_params) if isinstance(v, str) else v
        for k, v in effect.params.items()
    }

    if etype == "move_agent":
        # 移动机器人到新位置
        agent = graph.get_agent_node()
        target_label = resolved.get("to", "")
        targets = graph.find_by_label(target_label)
        if agent and targets:
            target = targets[0]
            # 如果目标不是房间，找到其所在房间
            if target.node_type != NodeType.ROOM:
                room = graph.get_location_of(target.node_id)
                if room:
                    target = room
            # 移除旧 AT 边
            graph.remove_edges(
                source_id=agent.node_id, edge_type=EdgeType.AT,
            )
            # 添加新 AT 边
            graph.add_edge(SceneEdge(
                source_id=agent.node_id,
                target_id=target.node_id,
                edge_type=EdgeType.AT,
            ))

    elif etype == "transfer_holding":
        # 物品从原位置转移到机器人手中
        obj_label = resolved.get("object", "")
        agent = graph.get_agent_node()
        objs = graph.find_by_label(obj_label)
        if agent and objs:
            obj = objs[0]
            # 移除物品的 ON_TOP / INSIDE 边
            graph.remove_edges(target_id=obj.node_id, edge_type=EdgeType.ON_TOP)
            graph.remove_edges(target_id=obj.node_id, edge_type=EdgeType.INSIDE)
            # 添加 HOLDING 边
            graph.add_edge(SceneEdge(
                source_id=agent.node_id,
                target_id=obj.node_id,
                edge_type=EdgeType.HOLDING,
            ))

    elif etype == "remove_holding":
        # 移除机器人持有的物品
        obj_label = resolved.get("object", "")
        agent = graph.get_agent_node()
        if agent:
            graph.remove_edges(
                source_id=agent.node_id, edge_type=EdgeType.HOLDING,
            )

    elif etype == "update_state":
        # 更新节点状态
        node_label = resolved.get("node", "")
        state_update = resolved.get("state", {})
        nodes = graph.find_by_label(node_label)
        if nodes and isinstance(state_update, dict):
            graph.update_node_state(nodes[0].node_id, state_update)


# ── MOSAIC 内置动作规则 ──

def get_builtin_action_rules() -> dict[str, ActionRule]:
    """返回 MOSAIC 内置的动作规则集合

    覆盖 navigate_to、pick_up、hand_over、operate_appliance、wait_appliance
    """
    return {
        "navigate_to": ActionRule(
            action_name="navigate_to",
            preconditions=[
                Precondition(
                    "node_exists",
                    {"label": "{target}"},
                    "目标位置 {target} 必须存在于场景图中",
                ),
                Precondition(
                    "path_reachable",
                    {"to": "{target}"},
                    "从当前位置到 {target} 的路径必须可达",
                ),
            ],
            effects=[
                Effect("move_agent", {"to": "{target}"}),
            ],
        ),
        "pick_up": ActionRule(
            action_name="pick_up",
            preconditions=[
                Precondition(
                    "node_exists",
                    {"label": "{object_name}"},
                    "物品 {object_name} 必须存在于场景图中",
                ),
                Precondition(
                    "agent_at_same_location",
                    {"object": "{object_name}"},
                    "机器人必须在 {object_name} 所在位置",
                ),
                Precondition(
                    "node_has_affordance",
                    {"node": "{object_name}", "affordance": "graspable"},
                    "{object_name} 必须是可抓取的",
                ),
                Precondition(
                    "agent_not_holding",
                    {},
                    "机器人手中不能已有物品",
                ),
            ],
            effects=[
                Effect("transfer_holding", {"object": "{object_name}"}),
            ],
        ),
        "hand_over": ActionRule(
            action_name="hand_over",
            preconditions=[
                Precondition(
                    "agent_holding",
                    {"object": "{object_name}"},
                    "机器人必须持有 {object_name}",
                ),
                Precondition(
                    "agent_near_person",
                    {},
                    "机器人必须在用户附近",
                ),
            ],
            effects=[
                Effect("remove_holding", {"object": "{object_name}"}),
            ],
        ),
        "operate_appliance": ActionRule(
            action_name="operate_appliance",
            preconditions=[
                Precondition(
                    "node_exists",
                    {"label": "{appliance_name}"},
                    "设备 {appliance_name} 必须存在于场景图中",
                ),
                Precondition(
                    "agent_at_same_location",
                    {"object": "{appliance_name}"},
                    "机器人必须在 {appliance_name} 所在位置",
                ),
            ],
            effects=[
                Effect(
                    "update_state",
                    {"node": "{appliance_name}", "state": {"power": "on"}},
                ),
            ],
        ),
        "wait_appliance": ActionRule(
            action_name="wait_appliance",
            preconditions=[
                Precondition(
                    "node_exists",
                    {"label": "{appliance_name}"},
                    "设备 {appliance_name} 必须存在",
                ),
            ],
            effects=[
                Effect(
                    "update_state",
                    {"node": "{appliance_name}", "state": {"task": "done"}},
                ),
            ],
        ),
    }
