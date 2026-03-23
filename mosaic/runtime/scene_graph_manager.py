# mosaic/runtime/scene_graph_manager.py
"""场景图管理器 — 生命周期管理 + YAML 初始化 + 执行后更新

统一管理场景图的：
1. 初始化：从 YAML 配置构建初始场景图
2. 更新：根据动作执行结果增量更新场景图
3. 查询：为 TurnRunner 提供任务相关子图
4. 验证：为 PlanVerifier 提供场景图快照
5. 事件：场景图变化时通过 HookManager 发布事件

与 ARIA 的关系：
- SceneGraphManager 是 ARIA 语义记忆（SemanticMemory）的核心载体
- 场景图 = ARIA 的结构化世界知识
- 子图提取 = EmbodiedRAG 检索的简化版本
"""

from __future__ import annotations

import re
from typing import Any

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.action_rules import (
    ActionRule, get_builtin_action_rules, apply_effect, Effect,
)
from mosaic.runtime.plan_verifier import PlanVerifier, PlanVerificationResult


class SceneGraphManager:
    """场景图管理器"""

    def __init__(
        self,
        hooks=None,
        action_rules: dict[str, ActionRule] | None = None,
    ) -> None:
        self._graph = SceneGraph()
        self._hooks = hooks
        rules = action_rules or get_builtin_action_rules()
        self._verifier = PlanVerifier(rules)
        self._rules = rules
        self._history: list[dict] = []  # 场景图历史快照（序列化形式）

    # ── 初始化 ──

    def initialize_from_config(self, env_config: dict) -> None:
        """从 YAML 配置初始化场景图

        配置格式参见 config/environments/home.yaml
        """
        self._graph = SceneGraph()
        env = env_config.get("environment", env_config)

        # 解析房间
        for room_cfg in env.get("rooms", []):
            self._parse_room(room_cfg)

        # 解析房间连通性
        for conn in env.get("connections", []):
            if isinstance(conn, list) and len(conn) == 2:
                # 双向 REACHABLE 边
                self._graph.add_edge(SceneEdge(
                    source_id=conn[0], target_id=conn[1],
                    edge_type=EdgeType.REACHABLE,
                ))
                self._graph.add_edge(SceneEdge(
                    source_id=conn[1], target_id=conn[0],
                    edge_type=EdgeType.REACHABLE,
                ))

        # 解析智能体
        for agent_cfg in env.get("agents", []):
            agent_node = SceneNode(
                node_id=agent_cfg["id"],
                node_type=NodeType.AGENT,
                label=agent_cfg.get("label", "机器人"),
            )
            self._graph.add_node(agent_node)
            # AT 边
            at_room = agent_cfg.get("at", "")
            if at_room:
                self._graph.add_edge(SceneEdge(
                    source_id=agent_cfg["id"],
                    target_id=at_room,
                    edge_type=EdgeType.AT,
                ))

        # 解析人员
        for person_cfg in env.get("people", []):
            person_node = SceneNode(
                node_id=person_cfg["id"],
                node_type=NodeType.PERSON,
                label=person_cfg.get("label", "用户"),
            )
            self._graph.add_node(person_node)
            at_room = person_cfg.get("at", "")
            if at_room:
                self._graph.add_edge(SceneEdge(
                    source_id=person_cfg["id"],
                    target_id=at_room,
                    edge_type=EdgeType.AT,
                ))
            near_obj = person_cfg.get("near", "")
            if near_obj:
                self._graph.add_edge(SceneEdge(
                    source_id=person_cfg["id"],
                    target_id=near_obj,
                    edge_type=EdgeType.NEAR,
                ))

    def _parse_room(self, room_cfg: dict) -> None:
        """解析单个房间配置"""
        room_id = room_cfg["id"]
        pos = room_cfg.get("position")
        room_node = SceneNode(
            node_id=room_id,
            node_type=NodeType.ROOM,
            label=room_cfg.get("label", room_id),
            position=tuple(pos) if pos else None,
        )
        self._graph.add_node(room_node)

        # 解析家具
        for furn_cfg in room_cfg.get("furniture", []):
            self._parse_furniture(furn_cfg, room_id)

    def _parse_furniture(self, furn_cfg: dict, parent_id: str) -> None:
        """解析家具/电器配置"""
        furn_id = furn_cfg["id"]
        furn_type_str = furn_cfg.get("type", "furniture")
        furn_type = (
            NodeType.APPLIANCE if furn_type_str == "appliance"
            else NodeType.FURNITURE
        )
        pos = furn_cfg.get("position")
        furn_node = SceneNode(
            node_id=furn_id,
            node_type=furn_type,
            label=furn_cfg.get("label", furn_id),
            position=tuple(pos) if pos else None,
            state=furn_cfg.get("state", {}),
            affordances=furn_cfg.get("affordances", []),
            properties=furn_cfg.get("properties", {}),
        )
        self._graph.add_node(furn_node)
        # CONTAINS 边：父节点包含此家具
        self._graph.add_edge(SceneEdge(
            source_id=parent_id, target_id=furn_id,
            edge_type=EdgeType.CONTAINS,
        ))

        # 解析家具上的物品
        for obj_cfg in furn_cfg.get("objects", []):
            self._parse_object(obj_cfg, furn_id, EdgeType.ON_TOP)

        # 解析部件
        for part_cfg in furn_cfg.get("parts", []):
            part_node = SceneNode(
                node_id=part_cfg["id"],
                node_type=NodeType.PART,
                label=part_cfg.get("label", part_cfg["id"]),
                affordances=part_cfg.get("affordances", []),
            )
            self._graph.add_node(part_node)
            self._graph.add_edge(SceneEdge(
                source_id=part_cfg["id"], target_id=furn_id,
                edge_type=EdgeType.PART_OF,
            ))

    def _parse_object(
        self, obj_cfg: dict, parent_id: str, relation: EdgeType,
    ) -> None:
        """解析物品配置"""
        obj_id = obj_cfg["id"]
        obj_type_str = obj_cfg.get("type", "object")
        obj_type = (
            NodeType.APPLIANCE if obj_type_str == "appliance"
            else NodeType.OBJECT
        )
        obj_node = SceneNode(
            node_id=obj_id,
            node_type=obj_type,
            label=obj_cfg.get("label", obj_id),
            state=obj_cfg.get("state", {}),
            affordances=obj_cfg.get("affordances", []),
            properties=obj_cfg.get("properties", {}),
        )
        self._graph.add_node(obj_node)
        # 关系边：ON_TOP 或 INSIDE
        self._graph.add_edge(SceneEdge(
            source_id=parent_id, target_id=obj_id,
            edge_type=relation,
        ))

        # 递归解析部件
        for part_cfg in obj_cfg.get("parts", []):
            part_node = SceneNode(
                node_id=part_cfg["id"],
                node_type=NodeType.PART,
                label=part_cfg.get("label", part_cfg["id"]),
                affordances=part_cfg.get("affordances", []),
            )
            self._graph.add_node(part_node)
            self._graph.add_edge(SceneEdge(
                source_id=part_cfg["id"], target_id=obj_id,
                edge_type=EdgeType.PART_OF,
            ))

    # ── 查询 ──

    def get_task_subgraph(self, task_description: str) -> SceneGraph:
        """基于任务描述提取相关子图（EmbodiedRAG 思路）

        从任务描述中提取关键词，在场景图中找到相关节点，
        扩展 N 跳邻居，返回紧凑的子图。
        """
        keywords = self._extract_keywords(task_description)
        return self._graph.extract_task_subgraph(keywords, max_hops=2)

    def get_scene_prompt(self, task_description: str = "") -> str:
        """获取场景图的 LLM 提示词文本

        如果提供了任务描述，返回任务相关子图的提示词；
        否则返回完整场景图的提示词。
        """
        if task_description:
            subgraph = self.get_task_subgraph(task_description)
            return subgraph.to_prompt_text()
        return self._graph.to_prompt_text()

    def get_full_graph(self) -> SceneGraph:
        """获取完整场景图"""
        return self._graph

    # ── 验证 ──

    def verify_plan(
        self, plan_steps: list[dict],
    ) -> PlanVerificationResult:
        """验证计划可行性"""
        return self._verifier.verify_plan(self._graph, plan_steps)

    # ── 更新 ──

    def update_from_execution(
        self,
        action: str,
        params: dict[str, Any],
        success: bool,
    ) -> None:
        """根据动作执行结果更新场景图

        只在执行成功时应用效果。
        """
        if not success:
            return
        rule = self._rules.get(action)
        if rule:
            for effect in rule.effects:
                apply_effect(self._graph, effect, params)

    # ── 快照 ──

    def snapshot(self) -> None:
        """保存当前场景图快照"""
        self._history.append(self._graph.to_dict())

    # ── 内部方法 ──

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """从任务描述中提取关键词

        简单实现：按中文/英文分词，过滤停用词。
        后续可接入 LLM 做更智能的关键词提取。
        """
        # 中文分词：按标点和常见停用词分割
        stop_words = {
            "帮我", "帮", "我", "去", "到", "的", "把", "给", "和",
            "然后", "再", "先", "请", "一下", "一个", "个",
            "the", "a", "an", "to", "and", "or", "for", "in", "on",
        }
        # 简单分词：按空格和标点分割
        tokens = re.split(r'[\s,，。！？、；：""''（）\(\)]+', text)
        keywords = [
            t.strip() for t in tokens
            if t.strip() and t.strip() not in stop_words and len(t.strip()) > 0
        ]
        return keywords
