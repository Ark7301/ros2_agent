"""属性测试 — NodeRegistry 注册-查找 round-trip

属性 11: Node 注册-查找 round-trip
- 注册节点后，通过其 capability 可以查找到该节点
- 注册多个具有相同 capability 的节点，查找返回所有节点
- 注册具有多个 capability 的节点，通过任意 capability 均可查找到
- 仅 CONNECTED 状态的节点会被 resolve_nodes_for_capability 返回

**Validates: Requirement 7.3**
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st, assume

from mosaic.nodes.node_registry import NodeRegistry, NodeInfo, NodeStatus


# ── Hypothesis 策略 ──

# 节点 ID 策略：合法的标识符字符串
node_id_st = st.from_regex(r"[a-z][a-z0-9_]{1,15}", fullmatch=True)

# 节点类型策略
node_type_st = st.sampled_from(["ros2_bridge", "hardware_driver", "sensor", "remote"])

# 能力名称策略
capability_st = st.from_regex(r"[a-z][a-z0-9_]{1,12}", fullmatch=True)

# 非空能力列表策略
capabilities_st = st.lists(capability_st, min_size=1, max_size=5, unique=True)

# 多个不同节点 ID 的策略
unique_node_ids_st = st.lists(node_id_st, min_size=2, max_size=8, unique=True)


def _make_node(node_id: str, capabilities: list[str],
               node_type: str = "sensor",
               status: NodeStatus = NodeStatus.CONNECTED) -> NodeInfo:
    """辅助函数：创建 NodeInfo 实例"""
    return NodeInfo(
        node_id=node_id,
        node_type=node_type,
        capabilities=capabilities,
        status=status,
    )


class TestNodeRegistryRoundTrip:
    """属性 11: Node 注册-查找 round-trip

    注册节点后，通过 resolve_nodes_for_capability 可以查找到该节点。

    **Validates: Requirement 7.3**
    """

    @given(
        node_id=node_id_st,
        node_type=node_type_st,
        capability=capability_st,
    )
    @settings(max_examples=200)
    def test_register_then_resolve_by_capability(
        self,
        node_id: str,
        node_type: str,
        capability: str,
    ):
        """注册节点后，通过其 capability 查找应返回该节点（Req 7.3）。

        验证：
        1. register 存储节点并建立 capability 索引
        2. resolve_nodes_for_capability 返回包含该节点的列表
        3. 返回的节点 node_id 与注册时一致
        """
        registry = NodeRegistry()
        node = _make_node(node_id, [capability], node_type)

        registry.register(node)

        # 通过 capability 查找应返回该节点
        found = registry.resolve_nodes_for_capability(capability)
        found_ids = [n.node_id for n in found]
        assert node_id in found_ids, (
            f"注册节点 '{node_id}' 后，通过 capability '{capability}' "
            f"应能查找到该节点，实际返回: {found_ids}"
        )

    @given(
        node_ids=unique_node_ids_st,
        capability=capability_st,
        node_type=node_type_st,
    )
    @settings(max_examples=200)
    def test_multiple_nodes_same_capability_all_found(
        self,
        node_ids: list[str],
        capability: str,
        node_type: str,
    ):
        """注册多个具有相同 capability 的节点，查找应返回所有节点（Req 7.3）。

        验证：
        1. 多个节点注册同一 capability
        2. resolve_nodes_for_capability 返回所有这些节点
        3. 返回数量与注册数量一致
        """
        registry = NodeRegistry()

        for nid in node_ids:
            node = _make_node(nid, [capability], node_type)
            registry.register(node)

        found = registry.resolve_nodes_for_capability(capability)
        found_ids = {n.node_id for n in found}

        assert found_ids == set(node_ids), (
            f"注册 {len(node_ids)} 个节点后，查找 capability '{capability}' "
            f"应返回所有节点，期望 {set(node_ids)}，实际 {found_ids}"
        )

    @given(
        node_id=node_id_st,
        capabilities=capabilities_st,
        node_type=node_type_st,
    )
    @settings(max_examples=200)
    def test_node_with_multiple_capabilities_findable_by_any(
        self,
        node_id: str,
        capabilities: list[str],
        node_type: str,
    ):
        """注册具有多个 capability 的节点，通过任意 capability 均可查找到（Req 7.3）。

        验证：
        1. 节点注册多个 capability
        2. 通过每个 capability 都能查找到该节点
        """
        registry = NodeRegistry()
        node = _make_node(node_id, capabilities, node_type)

        registry.register(node)

        # 通过每个 capability 都应能查找到该节点
        for cap in capabilities:
            found = registry.resolve_nodes_for_capability(cap)
            found_ids = [n.node_id for n in found]
            assert node_id in found_ids, (
                f"节点 '{node_id}' 注册了 capabilities {capabilities}，"
                f"但通过 '{cap}' 查找未返回该节点，实际返回: {found_ids}"
            )

    @given(
        connected_ids=st.lists(node_id_st, min_size=1, max_size=4, unique=True),
        disconnected_ids=st.lists(node_id_st, min_size=1, max_size=4, unique=True),
        capability=capability_st,
    )
    @settings(max_examples=200)
    def test_only_connected_nodes_returned(
        self,
        connected_ids: list[str],
        disconnected_ids: list[str],
        capability: str,
    ):
        """仅 CONNECTED 状态的节点会被 resolve_nodes_for_capability 返回（Req 7.3）。

        验证：
        1. 注册 CONNECTED 和非 CONNECTED 状态的节点
        2. resolve_nodes_for_capability 仅返回 CONNECTED 节点
        3. 非 CONNECTED 节点不在返回结果中
        """
        # 确保两组 ID 不重叠
        assume(not set(connected_ids) & set(disconnected_ids))

        registry = NodeRegistry()

        # 注册 CONNECTED 节点
        for nid in connected_ids:
            node = _make_node(nid, [capability], status=NodeStatus.CONNECTED)
            registry.register(node)

        # 注册非 CONNECTED 节点（HEARTBEAT_MISS 和 DISCONNECTED）
        non_connected_statuses = [NodeStatus.HEARTBEAT_MISS, NodeStatus.DISCONNECTED]
        for i, nid in enumerate(disconnected_ids):
            status = non_connected_statuses[i % len(non_connected_statuses)]
            node = _make_node(nid, [capability], status=status)
            registry.register(node)

        found = registry.resolve_nodes_for_capability(capability)
        found_ids = {n.node_id for n in found}

        # 仅 CONNECTED 节点应被返回
        assert found_ids == set(connected_ids), (
            f"应仅返回 CONNECTED 节点 {set(connected_ids)}，"
            f"实际返回 {found_ids}"
        )

        # 非 CONNECTED 节点不应出现
        for nid in disconnected_ids:
            assert nid not in found_ids, (
                f"非 CONNECTED 节点 '{nid}' 不应出现在查找结果中"
            )


class TestNodeUnregisterNotFindable:
    """属性 12: Node 注销后不可查找

    注销节点后，通过 resolve_nodes_for_capability 不再返回该节点，
    且注销操作不影响其他已注册节点。

    **Validates: Requirement 7.4**
    """

    @given(
        node_id=node_id_st,
        capabilities=capabilities_st,
        node_type=node_type_st,
    )
    @settings(max_examples=200)
    def test_unregister_then_resolve_returns_empty(
        self,
        node_id: str,
        capabilities: list[str],
        node_type: str,
    ):
        """注册后注销节点，resolve_nodes_for_capability 对该节点的所有 capability 返回空（Req 7.4）。

        验证：
        1. 注册节点后注销
        2. 通过该节点的任意 capability 查找均不再返回该节点
        """
        registry = NodeRegistry()
        node = _make_node(node_id, capabilities, node_type)

        registry.register(node)
        registry.unregister(node_id)

        # 注销后，通过任意 capability 查找均不应返回该节点
        for cap in capabilities:
            found = registry.resolve_nodes_for_capability(cap)
            found_ids = [n.node_id for n in found]
            assert node_id not in found_ids, (
                f"节点 '{node_id}' 已注销，但通过 capability '{cap}' "
                f"仍能查找到，实际返回: {found_ids}"
            )

    @given(
        target_id=node_id_st,
        other_ids=st.lists(node_id_st, min_size=1, max_size=5, unique=True),
        capability=capability_st,
        node_type=node_type_st,
    )
    @settings(max_examples=200)
    def test_unregister_one_does_not_affect_others(
        self,
        target_id: str,
        other_ids: list[str],
        capability: str,
        node_type: str,
    ):
        """注销一个节点不影响其他已注册节点（Req 7.4）。

        验证：
        1. 注册多个节点（共享同一 capability）
        2. 注销其中一个节点
        3. 其他节点仍可通过 capability 查找到
        """
        # 确保 target_id 不在 other_ids 中
        assume(target_id not in other_ids)

        registry = NodeRegistry()

        # 注册目标节点和其他节点
        registry.register(_make_node(target_id, [capability], node_type))
        for nid in other_ids:
            registry.register(_make_node(nid, [capability], node_type))

        # 注销目标节点
        registry.unregister(target_id)

        # 其他节点仍应可查找
        found = registry.resolve_nodes_for_capability(capability)
        found_ids = {n.node_id for n in found}

        assert found_ids == set(other_ids), (
            f"注销 '{target_id}' 后，其他节点 {set(other_ids)} 应仍可查找，"
            f"实际返回: {found_ids}"
        )
        assert target_id not in found_ids, (
            f"已注销的节点 '{target_id}' 不应出现在查找结果中"
        )

    @given(
        node_id=node_id_st,
        capabilities=capabilities_st,
        node_type=node_type_st,
    )
    @settings(max_examples=200)
    def test_unregister_cleans_all_capability_indices(
        self,
        node_id: str,
        capabilities: list[str],
        node_type: str,
    ):
        """注销节点应清理其所有 capability 索引（Req 7.4）。

        验证：
        1. 注册具有多个 capability 的节点
        2. 注销后，每个 capability 的索引中均不再包含该节点
        3. 对每个 capability 查找结果均为空
        """
        registry = NodeRegistry()
        node = _make_node(node_id, capabilities, node_type)

        registry.register(node)
        registry.unregister(node_id)

        # 每个 capability 的查找结果均应为空
        for cap in capabilities:
            found = registry.resolve_nodes_for_capability(cap)
            assert len(found) == 0, (
                f"节点 '{node_id}' 注销后，capability '{cap}' 的查找结果应为空，"
                f"实际返回 {len(found)} 个节点: {[n.node_id for n in found]}"
            )

    @given(
        node_id=node_id_st,
        existing_id=node_id_st,
        capability=capability_st,
        node_type=node_type_st,
    )
    @settings(max_examples=200)
    def test_unregister_nonexistent_is_noop(
        self,
        node_id: str,
        existing_id: str,
        capability: str,
        node_type: str,
    ):
        """注销不存在的 node_id 是无操作，不抛异常也不影响已有节点（Req 7.4）。

        验证：
        1. 注册一个节点
        2. 注销一个不存在的 node_id，不抛出异常
        3. 已注册节点不受影响
        """
        # 确保两个 ID 不同
        assume(node_id != existing_id)

        registry = NodeRegistry()
        registry.register(_make_node(existing_id, [capability], node_type))

        # 注销不存在的 node_id，不应抛出异常
        registry.unregister(node_id)

        # 已注册节点不受影响
        found = registry.resolve_nodes_for_capability(capability)
        found_ids = [n.node_id for n in found]
        assert existing_id in found_ids, (
            f"注销不存在的 '{node_id}' 后，已注册节点 '{existing_id}' "
            f"应仍可查找，实际返回: {found_ids}"
        )
