# mosaic/runtime/world_state_manager.py
"""ARIA 三层记忆架构 — WorkingMemory + SemanticMemory + EpisodicMemory

ARIA（Agent with Retrieval-augmented Intelligence Architecture）三层记忆：
1. WorkingMemory：工作记忆，封装 RobotState，内存实时覆写
2. SemanticMemory：语义记忆，以 SceneGraphManager 为核心载体 + VectorStore 索引
3. EpisodicMemory：情景记忆，存储任务执行历史，支持相似经验召回
4. WorldStateManager：统一门面（Facade），实现 MemoryPlugin 兼容接口
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from mosaic.runtime.scene_graph import SceneGraph
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.plugin_sdk.types import PluginMeta, MemoryEntry


# ── 数据结构 ──

@dataclass
class RobotState:
    """机器人实时状态"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    orientation_w: float = 1.0
    orientation_z: float = 0.0
    linear_velocity: float = 0.0
    angular_velocity: float = 0.0


@dataclass
class TaskEpisode:
    """任务执行记录"""
    task_description: str
    plan_steps: list[dict] = field(default_factory=list)
    success: bool = True
    failure_reason: str = ""
    scene_snapshot_summary: dict = field(default_factory=dict)
    timestamp: float = 0.0


@dataclass
class PlanningContext:
    """规划上下文 — 语义记忆检索结果"""
    subgraph: SceneGraph
    scene_text: str
    similar_episodes: list[TaskEpisode] = field(default_factory=list)


# ── 工作记忆 ──

class WorkingMemory:
    """工作记忆 — RobotState 实时覆写

    封装机器人实时状态，提供读写接口。
    数据存储在内存中，每次更新直接覆写对应字段。
    """

    def __init__(self) -> None:
        self._state = RobotState()

    def get_robot_state(self) -> RobotState:
        """获取当前机器人状态"""
        return self._state

    def update_robot_state(self, **kwargs: Any) -> None:
        """更新机器人状态字段

        只更新传入的字段，未传入的字段保持不变。
        """
        for key, value in kwargs.items():
            if hasattr(self._state, key):
                setattr(self._state, key, value)


# ── 语义记忆 ──

class SemanticMemory:
    """语义记忆 — SceneGraph + VectorStore

    以 SceneGraphManager 为核心载体，维护简单的关键词索引。
    MVP 实现使用关键词重叠评分代替向量嵌入。
    """

    def __init__(self, scene_graph_mgr: SceneGraphManager) -> None:
        self._sgm = scene_graph_mgr
        # 简单内存向量存储：node_id → 关键词集合
        self._vector_index: dict[str, set[str]] = {}
        # 初始化索引
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        """重建向量索引（基于节点 label 的关键词分词）"""
        self._vector_index.clear()
        graph = self._sgm.get_full_graph()
        for node_id, node in graph._nodes.items():
            keywords = self._tokenize(node.label)
            self._vector_index[node_id] = keywords

    def _tokenize(self, text: str) -> set[str]:
        """简单分词：按空格和标点分割，转小写"""
        tokens = re.split(r'[\s,，。！？、；：""''（）()]+', text)
        return {t.strip().lower() for t in tokens if t.strip()}

    def update_node_index(self, node_id: str, label: str) -> None:
        """节点写入/更新时自动更新向量索引"""
        self._vector_index[node_id] = self._tokenize(label)

    def retrieve_context(
        self, task_description: str, similar_episodes: list[TaskEpisode] | None = None,
    ) -> PlanningContext:
        """EmbodiedRAG 检索流程

        1. 从任务描述提取关键实体
        2. 在 VectorStore 中检索相似节点
        3. 通过 SceneGraphManager 提取任务子图
        4. 返回 PlanningContext
        """
        # 提取子图
        subgraph = self._sgm.get_task_subgraph(task_description)
        scene_text = subgraph.to_prompt_text()

        return PlanningContext(
            subgraph=subgraph,
            scene_text=scene_text,
            similar_episodes=similar_episodes or [],
        )


# ── 情景记忆 ──

class EpisodicMemory:
    """情景记忆 — 任务执行历史

    存储 TaskEpisode，支持基于关键词相似度 + 时间衰减的检索。
    """

    def __init__(self, time_decay_factor: float = 0.95) -> None:
        self._episodes: list[TaskEpisode] = []
        self._time_decay_factor = time_decay_factor

    def record_episode(self, episode: TaskEpisode) -> None:
        """记录一条任务执行经验"""
        if episode.timestamp == 0.0:
            episode.timestamp = time.time()
        self._episodes.append(episode)

    def recall_similar(
        self, task_description: str, top_k: int = 3,
    ) -> list[TaskEpisode]:
        """基于关键词相似度 + 时间衰减检索相似经验

        评分 = keyword_overlap_score * time_decay_weight
        时间衰减：decay_factor ^ (当前时间 - episode时间戳) 的归一化
        """
        if not self._episodes:
            return []

        query_tokens = self._tokenize(task_description)
        if not query_tokens:
            return self._episodes[:top_k]

        now = time.time()
        scored: list[tuple[float, TaskEpisode]] = []

        for ep in self._episodes:
            ep_tokens = self._tokenize(ep.task_description)
            if not ep_tokens:
                continue

            # 关键词重叠评分（Jaccard 相似度）
            intersection = query_tokens & ep_tokens
            union = query_tokens | ep_tokens
            keyword_score = len(intersection) / len(union) if union else 0.0

            # 时间衰减权重（秒级衰减，归一化到合理范围）
            time_diff = max(0.0, now - ep.timestamp)
            # 每小时衰减一次
            hours_diff = time_diff / 3600.0
            time_weight = self._time_decay_factor ** hours_diff

            final_score = keyword_score * time_weight
            scored.append((final_score, ep))

        # 按分数降序排列
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:top_k]]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """简单分词"""
        tokens = re.split(r'[\s,，。！？、；：""''（）()]+', text)
        return {t.strip().lower() for t in tokens if t.strip()}


# ── WorldStateManager（统一门面）──

class WorldStateManager:
    """ARIA 三层记忆统一门面

    持有 WorkingMemory、SemanticMemory、EpisodicMemory 引用，
    实现 MemoryPlugin 兼容接口（store/search/get/delete）。
    """

    meta = PluginMeta(
        id="world-state",
        name="WorldStateManager",
        version="1.0.0",
        description="ARIA 三层记忆统一门面",
        kind="memory",
    )

    def __init__(
        self,
        working: WorkingMemory,
        semantic: SemanticMemory,
        episodic: EpisodicMemory,
    ) -> None:
        self.working = working
        self.semantic = semantic
        self.episodic = episodic
        # MemoryPlugin key-value 存储
        self._kv_store: dict[str, MemoryEntry] = {}

    # ── 位姿同步：SensorBridge → WorkingMemory → SemanticMemory ──

    def update_position(self, x: float, y: float) -> None:
        """位姿同步：更新工作记忆 → 同步到语义记忆 agent 节点"""
        # 更新工作记忆
        self.working.update_robot_state(x=x, y=y)
        # 同步到语义记忆中的 agent 节点 position
        self.semantic._sgm.update_agent_position(x, y)

    # ── LLM 上下文组装 ──

    def assemble_context(
        self, task_description: str, top_k: int = 3,
    ) -> PlanningContext:
        """组装 LLM 上下文：语义记忆（场景子图）+ 情景记忆（相似经验）"""
        similar_episodes = self.episodic.recall_similar(
            task_description, top_k=top_k,
        )
        return self.semantic.retrieve_context(
            task_description, similar_episodes=similar_episodes,
        )

    # ── MemoryPlugin 兼容接口 ──

    async def store(self, key: str, content: str, metadata: dict) -> None:
        """存储记忆条目（key-value 存储）"""
        self._kv_store[key] = MemoryEntry(
            key=key,
            content=content,
            metadata=metadata,
        )

    def store_checkpoint_node(self, checkpoint) -> None:
        key = f"checkpoint:{checkpoint.checkpoint_id}"
        self._kv_store[key] = MemoryEntry(
            key=key,
            content=checkpoint.resolved_room_label,
            metadata={
                "parent_checkpoint_id": checkpoint.parent_checkpoint_id,
                "known_landmarks": checkpoint.known_landmarks,
                "known_objects": checkpoint.known_objects,
            },
        )

    def store_target_index(self, target_index) -> None:
        key = f"target:{target_index.target_label}"
        self._kv_store[key] = MemoryEntry(
            key=key,
            content=target_index.target_label,
            metadata={
                "candidate_room_labels": target_index.candidate_room_labels,
                "candidate_checkpoint_ids": target_index.candidate_checkpoint_ids,
                "supporting_landmarks": target_index.supporting_landmarks,
                "confidence": target_index.confidence,
            },
        )

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """语义搜索 — 委托给 SemanticMemory 检索"""
        # 从 kv_store 中做简单关键词匹配
        query_lower = query.lower()
        scored: list[tuple[float, MemoryEntry]] = []
        for entry in self._kv_store.values():
            content_lower = entry.content.lower()
            # 简单关键词匹配评分
            query_tokens = set(query_lower.split())
            content_tokens = set(content_lower.split())
            if not query_tokens:
                continue
            overlap = len(query_tokens & content_tokens)
            score = overlap / len(query_tokens) if query_tokens else 0.0
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, entry in scored[:top_k]:
            results.append(MemoryEntry(
                key=entry.key,
                content=entry.content,
                metadata=entry.metadata,
                score=score,
            ))
        return results

    async def get(self, key: str) -> MemoryEntry | None:
        """精确获取记忆条目"""
        return self._kv_store.get(key)

    async def delete(self, key: str) -> bool:
        """删除记忆条目"""
        if key in self._kv_store:
            del self._kv_store[key]
            return True
        return False
