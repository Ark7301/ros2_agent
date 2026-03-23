# mosaic/runtime/scene_graph.py
"""三层层次化场景图 — Object → Furniture/Group → Room

基于 SG-Nav（NeurIPS 2024）的三层层次化场景图设计，
融合 VeriGraph 的计划验证、EmbodiedRAG 的子图检索、MomaGraph 的可供性编码。

核心职责：
- 维护节点和边的增删改查
- 提供层次化图查询（子图提取、路径查找、可达性分析）
- 序列化为 LLM 可理解的结构化文本（to_prompt_text）
- 支持动作效果模拟（simulate_action_effect）
- 支持从 YAML 配置初始化和 JSON 序列化

三层层次结构：
  Room（房间）→ Furniture（家具/设备）→ Object（可操作物品）
  + Agent（机器人）、Person（人）、Waypoint（路径点）、Part（部件）
"""

from __future__ import annotations

import copy
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── 节点类型 ──

class NodeType(Enum):
    """场景图节点类型 — 8 种语义类型"""
    ROOM = "room"              # 房间（厨房、客厅、卧室）
    FURNITURE = "furniture"    # 家具（桌子、沙发、柜子）
    APPLIANCE = "appliance"    # 电器（咖啡机、冰箱、微波炉）
    OBJECT = "object"          # 可操作物品（杯子、毛巾、遥控器）
    AGENT = "agent"            # 智能体（机器人自身）
    PERSON = "person"          # 人（用户、其他人）
    WAYPOINT = "waypoint"      # 导航路径点
    PART = "part"              # 物体部件（门把手、按钮、抽屉）


# ── 边类型 ──

class EdgeType(Enum):
    """场景图边类型 — 17 种语义关系"""
    # 层次关系（SG-Nav 的 affiliation）
    CONTAINS = "contains"          # 包含（房间包含家具）
    PART_OF = "part_of"            # 部件关系（按钮是咖啡机的一部分）
    # 空间关系
    ON_TOP = "on_top"              # 在...上面
    INSIDE = "inside"              # 在...里面
    NEXT_TO = "next_to"            # 在...旁边
    FACING = "facing"              # 面向
    REACHABLE = "reachable"        # 可达（导航可达，双向）
    # 功能关系
    SUPPORTS = "supports"          # 支撑（桌子支撑杯子）
    CONNECTED_TO = "connected_to"  # 连接
    # 智能体关系
    AT = "at"                      # 位于（机器人位于客厅）
    HOLDING = "holding"            # 持有（机器人持有杯子）
    NEAR = "near"                  # 靠近
    # 状态关系
    STATE = "state"                # 状态
    AFFORDANCE = "affordance"      # 可供性
    # 因果关系（RoboEXP 启发）
    REVEALS = "reveals"            # 打开后显露
    PRODUCES = "produces"          # 产出
    REQUIRES = "requires"          # 前置依赖


# ── 节点数据结构 ──

@dataclass
class SceneNode:
    """场景图节点 — 综合 SG-Nav + Spark-DSG + MomaGraph 最佳实践

    每个节点代表物理世界中的一个实体（房间、家具、物品、智能体等）。
    """
    node_id: str                          # 唯一标识
    node_type: NodeType                   # 节点类型
    label: str                            # 语义标签（"咖啡机"、"客厅"）

    # 空间属性
    position: tuple[float, float] | None = None   # (x, y) 世界坐标

    # 状态属性（动态变化）
    state: dict[str, str] = field(default_factory=dict)
    # 例: {"power": "on", "mode": "brewing", "fill_level": "80%"}

    # 可供性属性（直接编码在节点上，MomaGraph 风格）
    affordances: list[str] = field(default_factory=list)
    # 例: ["graspable", "openable", "pressable"]

    # 物理属性（相对静态）
    properties: dict[str, Any] = field(default_factory=dict)
    # 例: {"weight_kg": 0.3, "material": "ceramic"}

    # 元数据
    confidence: float = 1.0               # 检测置信度
    last_observed: float = 0.0            # 最后观测时间戳
    source: str = "config"                # 数据来源（config/sensor/inferred）


# ── 边数据结构 ──

@dataclass
class SceneEdge:
    """场景图边 — 节点间的语义关系"""
    source_id: str                 # 源节点 ID
    target_id: str                 # 目标节点 ID
    edge_type: EdgeType            # 边类型
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0


# ── 场景图核心类 ──

class SceneGraph:
    """三层层次化语义场景图 — MOSAIC 的结构化世界表征核心

    层次结构：Room → Furniture/Appliance → Object/Part
    + Agent、Person、Waypoint 作为特殊节点

    核心能力：
    1. 节点/边的增删改查 + 类型索引加速
    2. 层次化查询（子节点、父节点、位置追溯）
    3. BFS 可达性分析和路径查找
    4. 任务相关子图提取（EmbodiedRAG 思路）
    5. LLM 提示词序列化（SG-Nav 风格）
    6. 深拷贝（用于动作效果模拟）
    7. JSON 序列化/反序列化
    """

    def __init__(self) -> None:
        self._nodes: dict[str, SceneNode] = {}
        self._edges: list[SceneEdge] = []
        # 索引：加速查询
        self._outgoing: dict[str, list[SceneEdge]] = {}   # node_id → 出边
        self._incoming: dict[str, list[SceneEdge]] = {}   # node_id → 入边
        self._type_index: dict[NodeType, set[str]] = {}   # 类型 → node_ids

    # ── 节点操作 ──

    def add_node(self, node: SceneNode) -> None:
        """添加节点，同时更新类型索引"""
        self._nodes[node.node_id] = node
        self._type_index.setdefault(node.node_type, set()).add(node.node_id)
        self._outgoing.setdefault(node.node_id, [])
        self._incoming.setdefault(node.node_id, [])

    def remove_node(self, node_id: str) -> None:
        """移除节点及其所有关联边"""
        if node_id not in self._nodes:
            return
        node = self._nodes.pop(node_id)
        self._type_index.get(node.node_type, set()).discard(node_id)
        # 移除关联边
        self._edges = [
            e for e in self._edges
            if e.source_id != node_id and e.target_id != node_id
        ]
        self._outgoing.pop(node_id, None)
        self._incoming.pop(node_id, None)
        # 清理其他节点的索引
        for edges in self._outgoing.values():
            edges[:] = [e for e in edges if e.target_id != node_id]
        for edges in self._incoming.values():
            edges[:] = [e for e in edges if e.source_id != node_id]

    def update_node_state(self, node_id: str, state: dict[str, str]) -> None:
        """更新节点状态"""
        if node_id in self._nodes:
            self._nodes[node_id].state.update(state)

    def get_node(self, node_id: str) -> SceneNode | None:
        """获取节点"""
        return self._nodes.get(node_id)

    # ── 边操作 ──

    def add_edge(self, edge: SceneEdge) -> None:
        """添加边，同时更新索引"""
        self._edges.append(edge)
        self._outgoing.setdefault(edge.source_id, []).append(edge)
        self._incoming.setdefault(edge.target_id, []).append(edge)

    def remove_edges(
        self,
        source_id: str | None = None,
        target_id: str | None = None,
        edge_type: EdgeType | None = None,
    ) -> int:
        """移除匹配条件的边，返回移除数量"""
        def matches(e: SceneEdge) -> bool:
            if source_id is not None and e.source_id != source_id:
                return False
            if target_id is not None and e.target_id != target_id:
                return False
            if edge_type is not None and e.edge_type != edge_type:
                return False
            return True

        to_remove = [e for e in self._edges if matches(e)]
        for e in to_remove:
            self._edges.remove(e)
            if e.source_id in self._outgoing:
                try:
                    self._outgoing[e.source_id].remove(e)
                except ValueError:
                    pass
            if e.target_id in self._incoming:
                try:
                    self._incoming[e.target_id].remove(e)
                except ValueError:
                    pass
        return len(to_remove)

    def has_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType | None = None,
    ) -> bool:
        """检查是否存在指定边"""
        for e in self._outgoing.get(source_id, []):
            if e.target_id == target_id:
                if edge_type is None or e.edge_type == edge_type:
                    return True
        return False

    # ── 图查询 ──

    def get_children(
        self, node_id: str, edge_type: EdgeType | None = None,
    ) -> list[SceneNode]:
        """获取指定节点的子节点（沿出边方向）"""
        result = []
        for e in self._outgoing.get(node_id, []):
            if edge_type is None or e.edge_type == edge_type:
                node = self._nodes.get(e.target_id)
                if node:
                    result.append(node)
        return result

    def get_parent(
        self, node_id: str, edge_type: EdgeType,
    ) -> SceneNode | None:
        """获取指定节点的父节点（沿入边方向）"""
        for e in self._incoming.get(node_id, []):
            if e.edge_type == edge_type:
                return self._nodes.get(e.source_id)
        return None

    def find_by_label(self, label: str) -> list[SceneNode]:
        """按语义标签模糊查找节点（大小写不敏感）"""
        label_lower = label.lower()
        return [
            n for n in self._nodes.values()
            if label_lower in n.label.lower()
        ]

    def find_by_type(self, node_type: NodeType) -> list[SceneNode]:
        """按类型查找所有节点"""
        ids = self._type_index.get(node_type, set())
        return [self._nodes[nid] for nid in ids if nid in self._nodes]

    def get_location_of(self, node_id: str) -> SceneNode | None:
        """查找物体所在的房间（沿 CONTAINS 边向上追溯）

        从当前节点出发，沿入边方向查找 CONTAINS 关系，
        直到找到 ROOM 类型节点。
        """
        visited = set()
        current = node_id
        while current and current not in visited:
            visited.add(current)
            # 检查当前节点是否是房间
            node = self._nodes.get(current)
            if node and node.node_type == NodeType.ROOM:
                return node
            # 沿 CONTAINS 入边向上
            parent = self.get_parent(current, EdgeType.CONTAINS)
            if parent:
                current = parent.node_id
            else:
                # 也检查 AT 边（智能体/人的位置）
                for e in self._incoming.get(current, []):
                    if e.edge_type == EdgeType.AT:
                        target = self._nodes.get(e.source_id)
                        if target and target.node_type == NodeType.ROOM:
                            return target
                break
        return None

    def get_agent_location(self) -> SceneNode | None:
        """获取机器人当前所在房间"""
        agent = self.get_agent_node()
        if not agent:
            return None
        # 查找 AT 边
        for e in self._outgoing.get(agent.node_id, []):
            if e.edge_type == EdgeType.AT:
                return self._nodes.get(e.target_id)
        return None

    def get_objects_at(self, location_id: str) -> list[SceneNode]:
        """查找指定位置的所有物体（递归包含）"""
        result = []
        for child in self.get_children(location_id, EdgeType.CONTAINS):
            if child.node_type in (NodeType.OBJECT, NodeType.APPLIANCE):
                result.append(child)
            elif child.node_type in (NodeType.FURNITURE,):
                # 递归查找家具上/里的物品
                for obj in self.get_children(child.node_id, EdgeType.ON_TOP):
                    result.append(obj)
                for obj in self.get_children(child.node_id, EdgeType.INSIDE):
                    result.append(obj)
                # 家具本身也算（如冰箱既是家具又是电器）
        return result

    def get_agent_node(self) -> SceneNode | None:
        """获取机器人自身节点"""
        agents = self.find_by_type(NodeType.AGENT)
        return agents[0] if agents else None

    # ── BFS 可达性分析 ──

    def find_path(
        self, start_id: str, end_id: str,
    ) -> list[str] | None:
        """BFS 查找两个位置节点之间的路径（沿 REACHABLE 边，双向）

        Returns:
            路径节点 ID 列表，或 None（不可达）
        """
        if start_id == end_id:
            return [start_id]
        visited: set[str] = {start_id}
        queue: deque[tuple[str, list[str]]] = deque([(start_id, [start_id])])
        while queue:
            current, path = queue.popleft()
            # 检查所有 REACHABLE 边（双向）
            for e in self._edges:
                if e.edge_type != EdgeType.REACHABLE:
                    continue
                neighbor = None
                if e.source_id == current and e.target_id not in visited:
                    neighbor = e.target_id
                elif e.target_id == current and e.source_id not in visited:
                    neighbor = e.source_id
                if neighbor:
                    new_path = path + [neighbor]
                    if neighbor == end_id:
                        return new_path
                    visited.add(neighbor)
                    queue.append((neighbor, new_path))
        return None

    def get_reachable_locations(self, from_id: str) -> list[SceneNode]:
        """获取从指定位置可达的所有位置"""
        reachable = []
        visited: set[str] = {from_id}
        queue: deque[str] = deque([from_id])
        while queue:
            current = queue.popleft()
            for e in self._edges:
                if e.edge_type != EdgeType.REACHABLE:
                    continue
                neighbor = None
                if e.source_id == current and e.target_id not in visited:
                    neighbor = e.target_id
                elif e.target_id == current and e.source_id not in visited:
                    neighbor = e.source_id
                if neighbor:
                    visited.add(neighbor)
                    node = self._nodes.get(neighbor)
                    if node:
                        reachable.append(node)
                    queue.append(neighbor)
        return reachable

    # ── 子图提取（EmbodiedRAG 思路）──

    def extract_task_subgraph(
        self, keywords: list[str], max_hops: int = 2,
    ) -> "SceneGraph":
        """基于任务关键词提取相关子图

        算法（参考 EmbodiedRAG arXiv:2410.23968）：
        1. 找到与关键词匹配的种子节点
        2. 从种子节点出发，BFS 扩展 max_hops 跳
        3. 始终包含机器人节点和用户节点
        4. 包含所有 REACHABLE 边（导航拓扑）
        5. 返回紧凑子图
        """
        # 1. 种子节点：关键词匹配
        seed_ids: set[str] = set()
        for kw in keywords:
            for node in self.find_by_label(kw):
                seed_ids.add(node.node_id)

        # 2. 始终包含 agent 和 person 节点
        for node in self.find_by_type(NodeType.AGENT):
            seed_ids.add(node.node_id)
        for node in self.find_by_type(NodeType.PERSON):
            seed_ids.add(node.node_id)

        # 3. BFS 扩展 max_hops 跳
        included_ids: set[str] = set(seed_ids)
        frontier = set(seed_ids)
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for nid in frontier:
                # 出边
                for e in self._outgoing.get(nid, []):
                    if e.target_id not in included_ids:
                        next_frontier.add(e.target_id)
                # 入边
                for e in self._incoming.get(nid, []):
                    if e.source_id not in included_ids:
                        next_frontier.add(e.source_id)
            included_ids.update(next_frontier)
            frontier = next_frontier

        # 4. 确保包含所有房间节点（导航拓扑完整性）
        for node in self.find_by_type(NodeType.ROOM):
            included_ids.add(node.node_id)

        # 5. 构建子图
        subgraph = SceneGraph()
        for nid in included_ids:
            node = self._nodes.get(nid)
            if node:
                subgraph.add_node(copy.deepcopy(node))
        for e in self._edges:
            if e.source_id in included_ids and e.target_id in included_ids:
                subgraph.add_edge(copy.deepcopy(e))

        return subgraph

    # ── LLM 提示词序列化（SG-Nav 风格）──

    def to_prompt_text(self, max_nodes: int = 50) -> str:
        """序列化为 LLM 可理解的层次化文本

        格式设计原则（综合 SG-Nav + EmbodiedRAG）：
        1. 层次化展示：位置层 → 物体层 → 智能体层 → 可达性
        2. 关系内联：用箭头表示关系，减少 token
        3. 状态标注：用括号标注关键状态和可供性
        4. 可达性单独列出：方便 LLM 做路径规划
        """
        lines = ["[场景图]"]

        # 位置层：Room → 包含的 Furniture/Appliance
        rooms = self.find_by_type(NodeType.ROOM)
        if rooms:
            lines.append("位置层:")
            for room in sorted(rooms, key=lambda r: r.label):
                children = self.get_children(room.node_id, EdgeType.CONTAINS)
                if children:
                    child_labels = [c.label for c in children]
                    lines.append(
                        f"  {room.label} ──contains──→ [{', '.join(child_labels)}]"
                    )
                else:
                    lines.append(f"  {room.label}")

        # 物体层：Furniture → 上面/里面的 Object
        object_lines: list[str] = []
        for nt in (NodeType.FURNITURE, NodeType.APPLIANCE):
            for furn in self.find_by_type(nt):
                objects_on = self.get_children(furn.node_id, EdgeType.ON_TOP)
                objects_in = self.get_children(furn.node_id, EdgeType.INSIDE)
                all_objs = objects_on + objects_in
                if all_objs:
                    items = []
                    for obj in all_objs:
                        desc = obj.label
                        if obj.state:
                            state_str = ",".join(
                                f"{k}={v}" for k, v in obj.state.items()
                            )
                            desc += f"({state_str})"
                        if obj.affordances:
                            desc += f"[{'|'.join(obj.affordances)}]"
                        items.append(desc)
                    object_lines.append(
                        f"  {furn.label} ──on/in──→ [{', '.join(items)}]"
                    )
                # 家具/电器自身的状态
                elif furn.state:
                    state_str = ",".join(
                        f"{k}={v}" for k, v in furn.state.items()
                    )
                    aff_str = (
                        f"[{'|'.join(furn.affordances)}]"
                        if furn.affordances else ""
                    )
                    object_lines.append(
                        f"  {furn.label}({state_str}){aff_str}"
                    )
        if object_lines:
            lines.append("物体层:")
            lines.extend(object_lines)

        # 智能体层
        agent = self.get_agent_node()
        if agent:
            at_node = self.get_agent_location()
            holding_nodes = self.get_children(agent.node_id, EdgeType.HOLDING)
            at_label = at_node.label if at_node else "未知"
            hold_label = (
                holding_nodes[0].label if holding_nodes else "无"
            )
            lines.append(
                f"智能体: 机器人 ──at──→ {at_label}, holding: {hold_label}"
            )

        persons = self.find_by_type(NodeType.PERSON)
        for p in persons:
            p_at = []
            for e in self._outgoing.get(p.node_id, []):
                if e.edge_type == EdgeType.AT:
                    target = self._nodes.get(e.target_id)
                    if target:
                        p_at.append(target.label)
            near = []
            for e in self._outgoing.get(p.node_id, []):
                if e.edge_type == EdgeType.NEAR:
                    target = self._nodes.get(e.target_id)
                    if target:
                        near.append(target.label)
            loc = p_at[0] if p_at else "未知"
            near_str = f"({','.join(near)}附近)" if near else ""
            lines.append(f"  {p.label} ──at──→ {loc}{near_str}")

        # 可达性
        pairs: set[tuple[str, str]] = set()
        for e in self._edges:
            if e.edge_type == EdgeType.REACHABLE:
                src = self._nodes.get(e.source_id)
                tgt = self._nodes.get(e.target_id)
                if src and tgt:
                    pair = tuple(sorted([src.label, tgt.label]))
                    pairs.add(pair)
        if pairs:
            lines.append("可达性:")
            for a, b in sorted(pairs):
                lines.append(f"  {a} ←→ {b}")

        return "\n".join(lines)

    # ── 深拷贝（用于动作效果模拟）──

    def deep_copy(self) -> "SceneGraph":
        """深拷贝场景图（不修改原图）"""
        return copy.deepcopy(self)

    # ── 序列化 ──

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "nodes": [
                {
                    "node_id": n.node_id,
                    "node_type": n.node_type.value,
                    "label": n.label,
                    "position": list(n.position) if n.position else None,
                    "state": n.state,
                    "affordances": n.affordances,
                    "properties": n.properties,
                    "confidence": n.confidence,
                    "source": n.source,
                }
                for n in self._nodes.values()
            ],
            "edges": [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type.value,
                    "properties": e.properties,
                    "confidence": e.confidence,
                }
                for e in self._edges
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SceneGraph":
        """从字典反序列化"""
        graph = cls()
        for nd in data.get("nodes", []):
            pos = tuple(nd["position"]) if nd.get("position") else None
            node = SceneNode(
                node_id=nd["node_id"],
                node_type=NodeType(nd["node_type"]),
                label=nd["label"],
                position=pos,
                state=nd.get("state", {}),
                affordances=nd.get("affordances", []),
                properties=nd.get("properties", {}),
                confidence=nd.get("confidence", 1.0),
                source=nd.get("source", "config"),
            )
            graph.add_node(node)
        for ed in data.get("edges", []):
            edge = SceneEdge(
                source_id=ed["source_id"],
                target_id=ed["target_id"],
                edge_type=EdgeType(ed["edge_type"]),
                properties=ed.get("properties", {}),
                confidence=ed.get("confidence", 1.0),
            )
            graph.add_edge(edge)
        return graph

    # ── 统计信息 ──

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def __repr__(self) -> str:
        return f"SceneGraph(nodes={self.node_count}, edges={self.edge_count})"
