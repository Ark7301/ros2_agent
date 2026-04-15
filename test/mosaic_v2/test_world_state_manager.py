# test/mosaic_v2/test_world_state_manager.py
"""ARIA 三层记忆架构属性基测试

包含 Property 21-24 四个属性测试。

# Feature: scene-graph-integration, Property 21: WorkingMemory 状态往返一致性
# Feature: scene-graph-integration, Property 22: 工作记忆→语义记忆位姿同步
# Feature: scene-graph-integration, Property 23: EpisodicMemory 存储→召回往返
# Feature: scene-graph-integration, Property 24: WorldStateManager MemoryPlugin 接口兼容
"""

import asyncio
import time

import pytest
from hypothesis import given, settings, strategies as st, assume

from mosaic.runtime.scene_graph import (
    SceneGraph, SceneNode, SceneEdge, NodeType, EdgeType,
)
from mosaic.runtime.scene_graph_manager import SceneGraphManager
from mosaic.runtime.world_state_manager import (
    RobotState, TaskEpisode, PlanningContext,
    WorkingMemory, SemanticMemory, EpisodicMemory, WorldStateManager,
)
from mosaic.runtime.human_surrogate_models import CheckpointNode, MemoryTargetIndex
from mosaic.plugin_sdk.types import MemoryEntry


# ── 有效浮点坐标策略 ──
_coord_st = st.floats(
    min_value=-500.0, max_value=500.0,
    allow_nan=False, allow_infinity=False,
)

_velocity_st = st.floats(
    min_value=-10.0, max_value=10.0,
    allow_nan=False, allow_infinity=False,
)

_orientation_st = st.floats(
    min_value=-1.0, max_value=1.0,
    allow_nan=False, allow_infinity=False,
)


# ── 辅助函数 ──

def _make_sgm_with_agent(agent_id: str = "robot") -> SceneGraphManager:
    """创建包含 agent 节点和一个房间的 SceneGraphManager"""
    sgm = SceneGraphManager()
    # 添加房间
    room = SceneNode(
        node_id="living_room",
        node_type=NodeType.ROOM,
        label="客厅",
        position=(0.0, 0.0),
    )
    sgm._graph.add_node(room)
    # 添加 agent
    agent = SceneNode(
        node_id=agent_id,
        node_type=NodeType.AGENT,
        label="机器人",
        position=(0.0, 0.0),
    )
    sgm._graph.add_node(agent)
    # AT 边
    sgm._graph.add_edge(SceneEdge(
        source_id=agent_id,
        target_id="living_room",
        edge_type=EdgeType.AT,
    ))
    return sgm


def _run_async(coro):
    """同步运行异步协程"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Property 21: WorkingMemory 状态往返一致性 ──

# Feature: scene-graph-integration, Property 21: WorkingMemory 状态往返一致性
# **Validates: Requirements 8.2**
@settings(max_examples=100)
@given(
    x=_coord_st,
    y=_coord_st,
    z=_coord_st,
    orientation_w=_orientation_st,
    orientation_z=_orientation_st,
    linear_velocity=_velocity_st,
    angular_velocity=_velocity_st,
)
def test_working_memory_roundtrip(
    x, y, z, orientation_w, orientation_z,
    linear_velocity, angular_velocity,
):
    """Property 21: update_robot_state 后 get_robot_state 返回包含最新值的 RobotState。

    验证流程：
    1. 创建 WorkingMemory
    2. 调用 update_robot_state 更新所有字段
    3. 调用 get_robot_state 获取状态
    4. 验证所有字段与更新值一致
    """
    wm = WorkingMemory()

    wm.update_robot_state(
        x=x, y=y, z=z,
        orientation_w=orientation_w,
        orientation_z=orientation_z,
        linear_velocity=linear_velocity,
        angular_velocity=angular_velocity,
    )

    state = wm.get_robot_state()

    assert state.x == x, f"x 应为 {x}，实际为 {state.x}"
    assert state.y == y, f"y 应为 {y}，实际为 {state.y}"
    assert state.z == z, f"z 应为 {z}，实际为 {state.z}"
    assert state.orientation_w == orientation_w
    assert state.orientation_z == orientation_z
    assert state.linear_velocity == linear_velocity
    assert state.angular_velocity == angular_velocity


# ── Property 22: 工作记忆→语义记忆位姿同步 ──

# Feature: scene-graph-integration, Property 22: 工作记忆→语义记忆位姿同步
# **Validates: Requirements 8.3**
@settings(max_examples=100)
@given(
    x=_coord_st,
    y=_coord_st,
)
def test_working_to_semantic_position_sync(x, y):
    """Property 22: 通过 WorldStateManager 更新位姿后，
    SemanticMemory 中 agent 节点 position 一致。

    验证流程：
    1. 创建带 agent 节点的 SceneGraphManager
    2. 创建 WorldStateManager
    3. 调用 update_position(x, y)
    4. 验证 WorkingMemory 中 RobotState 的 x, y 一致
    5. 验证场景图中 agent 节点的 position 一致
    """
    sgm = _make_sgm_with_agent()
    wm = WorkingMemory()
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    wsm.update_position(x, y)

    # 验证工作记忆
    state = wm.get_robot_state()
    assert state.x == x, f"WorkingMemory x 应为 {x}，实际为 {state.x}"
    assert state.y == y, f"WorkingMemory y 应为 {y}，实际为 {state.y}"

    # 验证语义记忆中 agent 节点 position
    agent = sgm.get_full_graph().get_agent_node()
    assert agent is not None, "场景图中应存在 agent 节点"
    assert agent.position == (x, y), (
        f"agent position 应为 ({x}, {y})，实际为 {agent.position}"
    )


# ── Property 23: EpisodicMemory 存储→召回往返 ──

# Feature: scene-graph-integration, Property 23: EpisodicMemory 存储→召回往返
# **Validates: Requirements 8.6**
@settings(max_examples=100)
@given(
    task_desc=st.text(
        alphabet=st.characters(whitelist_categories=("L", "N", "Z")),
        min_size=1, max_size=50,
    ),
)
def test_episodic_memory_store_recall_roundtrip(task_desc):
    """Property 23: 存储 TaskEpisode 后，recall_similar 返回结果中包含该 episode。

    验证流程：
    1. 创建 EpisodicMemory
    2. 记录一条 TaskEpisode
    3. 用相同 task_description 调用 recall_similar
    4. 验证返回结果中包含该 episode
    """
    # 过滤纯空白字符串（分词后无有效 token）
    assume(task_desc.strip())

    em = EpisodicMemory()
    now = time.time()

    episode = TaskEpisode(
        task_description=task_desc,
        plan_steps=[{"action": "test"}],
        success=True,
        timestamp=now,
    )

    em.record_episode(episode)

    results = em.recall_similar(task_desc, top_k=5)

    assert len(results) >= 1, "recall_similar 应至少返回 1 条结果"
    # 验证存储的 episode 在结果中
    found = any(
        r.task_description == task_desc and r.timestamp == now
        for r in results
    )
    assert found, (
        f"recall_similar 结果中应包含刚存储的 episode，"
        f"task_desc='{task_desc}'，结果数={len(results)}"
    )


# ── Property 24: WorldStateManager MemoryPlugin 接口兼容 ──

# Feature: scene-graph-integration, Property 24: WorldStateManager MemoryPlugin 接口兼容
# **Validates: Requirements 8.10**
@settings(max_examples=100)
@given(
    key=st.text(min_size=1, max_size=30, alphabet=st.characters(
        whitelist_categories=("L", "N"),
    )),
    content=st.text(min_size=1, max_size=100),
)
def test_world_state_manager_memory_plugin_compat(key, content):
    """Property 24: store → get 返回相同 content；delete → get 返回 None。

    验证流程：
    1. 创建 WorldStateManager
    2. store(key, content, metadata)
    3. get(key) → 验证 content 匹配
    4. delete(key) → get(key) 返回 None
    """
    sgm = _make_sgm_with_agent()
    wm = WorkingMemory()
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    metadata = {"source": "test"}

    # store → get 往返
    _run_async(wsm.store(key, content, metadata))
    entry = _run_async(wsm.get(key))

    assert entry is not None, f"get('{key}') 应返回非 None"
    assert entry.content == content, (
        f"content 应为 '{content}'，实际为 '{entry.content}'"
    )
    assert entry.key == key, f"key 应为 '{key}'，实际为 '{entry.key}'"

    # delete → get 返回 None
    deleted = _run_async(wsm.delete(key))
    assert deleted is True, f"delete('{key}') 应返回 True"

    entry_after = _run_async(wsm.get(key))
    assert entry_after is None, (
        f"delete 后 get('{key}') 应返回 None，实际为 {entry_after}"
    )


def test_world_state_manager_checkpoint_and_target_metadata() -> None:
    sgm = _make_sgm_with_agent()
    wm = WorkingMemory()
    sm = SemanticMemory(sgm)
    em = EpisodicMemory()
    wsm = WorldStateManager(working=wm, semantic=sm, episodic=em)

    checkpoint = CheckpointNode(
        checkpoint_id="cp-meta",
        parent_checkpoint_id="cp-parent",
        resolved_room_label="测试室",
        known_landmarks=["灯"],
        known_objects=["笔"],
    )
    target_index = MemoryTargetIndex(
        target_label="目标X",
        candidate_room_labels=["测试室"],
        candidate_checkpoint_ids=["cp-meta"],
        supporting_landmarks=["灯"],
        confidence=0.75,
    )

    wsm.store_checkpoint_node(checkpoint)
    wsm.store_target_index(target_index)

    cp_entry = wsm._kv_store.get("checkpoint:cp-meta")
    assert cp_entry is not None, "checkpoint entry 应存在"
    assert cp_entry.key == "checkpoint:cp-meta"
    assert cp_entry.metadata["known_landmarks"] == ["灯"]
    assert cp_entry.metadata["known_objects"] == ["笔"]

    target_entry = wsm._kv_store.get("target:目标X")
    assert target_entry is not None, "target index entry 应存在"
    assert target_entry.metadata["candidate_checkpoint_ids"] == ["cp-meta"]
    assert target_entry.metadata["supporting_landmarks"] == ["灯"]
    assert target_entry.metadata["confidence"] == 0.75
