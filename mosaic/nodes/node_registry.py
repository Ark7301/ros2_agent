# 节点注册表 — 注册/注销/心跳/能力查找/健康检查
import time
from dataclasses import dataclass, field
from enum import Enum


class NodeStatus(Enum):
    """节点状态枚举"""
    CONNECTED = "connected"
    HEARTBEAT_MISS = "heartbeat_miss"
    DISCONNECTED = "disconnected"


@dataclass
class NodeInfo:
    """节点信息 — 包含节点标识、类型、能力列表、状态和心跳时间"""
    node_id: str
    node_type: str  # "ros2_bridge" | "hardware_driver" | "sensor" | "remote"
    capabilities: list[str] = field(default_factory=list)
    status: NodeStatus = NodeStatus.CONNECTED
    last_heartbeat: float = field(default_factory=time.time)
    metadata: dict = field(default_factory=dict)


class NodeRegistry:
    """节点注册表 — 管理分布式能力节点的注册、注销、心跳和能力查找

    核心功能：
    - register/unregister: 节点注册与注销，维护 capability → node_id 索引
    - heartbeat: 更新节点心跳时间，恢复为 CONNECTED 状态
    - resolve_nodes_for_capability: 按能力查找所有 CONNECTED 状态的节点
    - check_health: 检查所有节点心跳，标记超时节点为 HEARTBEAT_MISS
    """

    def __init__(self, heartbeat_timeout_s: float = 30):
        self._nodes: dict[str, NodeInfo] = {}
        self._heartbeat_timeout = heartbeat_timeout_s
        # 能力索引：capability 名称 → 拥有该能力的 node_id 集合
        self._capability_index: dict[str, set[str]] = {}

    def register(self, node: NodeInfo) -> None:
        """注册节点并建立 capability 索引"""
        self._nodes[node.node_id] = node
        for cap in node.capabilities:
            self._capability_index.setdefault(cap, set()).add(node.node_id)

    def unregister(self, node_id: str) -> None:
        """注销节点并清理所有 capability 索引"""
        node = self._nodes.pop(node_id, None)
        if node:
            for cap in node.capabilities:
                self._capability_index.get(cap, set()).discard(node_id)

    def heartbeat(self, node_id: str) -> None:
        """更新节点心跳时间，将状态恢复为 CONNECTED"""
        node = self._nodes.get(node_id)
        if node:
            node.last_heartbeat = time.time()
            node.status = NodeStatus.CONNECTED

    def resolve_nodes_for_capability(self, capability: str) -> list[NodeInfo]:
        """根据能力查找所有状态为 CONNECTED 的可用节点"""
        node_ids = self._capability_index.get(capability, set())
        return [
            self._nodes[nid] for nid in node_ids
            if nid in self._nodes and self._nodes[nid].status == NodeStatus.CONNECTED
        ]

    def check_health(self) -> dict[str, NodeStatus]:
        """检查所有节点健康状态，超时节点标记为 HEARTBEAT_MISS"""
        now = time.time()
        results = {}
        for node_id, node in self._nodes.items():
            if now - node.last_heartbeat > self._heartbeat_timeout:
                node.status = NodeStatus.HEARTBEAT_MISS
            results[node_id] = node.status
        return results
