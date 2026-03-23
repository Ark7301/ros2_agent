"""Agent 路由器 — 多层级优先匹配

根据多层级规则将请求路由到对应 Agent，支持多 Agent 协作场景。
匹配按 RouteBinding 的 priority 值升序进行（数值越小优先级越高）。

匹配优先级（由 priority 值控制）:
    1. 显式 session 绑定
    2. 场景绑定（厨房 → 厨房 Agent）
    3. 意图模式匹配（navigate_* → 导航 Agent）
    4. 通道绑定（ROS2 → 机器人 Agent）
    5. 默认 Agent（无匹配时兜底）
"""

import re
from dataclasses import dataclass


@dataclass
class RouteBinding:
    """路由绑定规则

    定义一条路由匹配规则，将特定条件映射到目标 agent_id。
    match_type 决定匹配方式，priority 决定匹配顺序。

    Attributes:
        agent_id: 目标 Agent ID
        match_type: 匹配类型，支持 "session" | "scene" | "intent" | "channel" | "capability"
        pattern: 正则匹配模式（仅 intent 类型使用）
        channel: 通道名称（仅 channel 类型使用）
        scene: 场景名称（仅 scene 类型使用）
        priority: 优先级，数值越小越先匹配，默认 99
    """
    agent_id: str
    match_type: str  # "session" | "scene" | "intent" | "channel" | "capability"
    pattern: str = ""
    channel: str = ""
    scene: str = ""
    priority: int = 99


@dataclass
class ResolvedRoute:
    """路由解析结果

    Attributes:
        agent_id: 匹配到的 Agent ID
        session_key: 会话键，格式为 "{agent_id}:{channel}"
        matched_by: 匹配方式描述，如 "binding.channel" 或 "default"
    """
    agent_id: str
    session_key: str
    matched_by: str


class AgentRouter:
    """多 Agent 路由器 — 按优先级多层级匹配

    根据 context 中的信息（session、scene、intent、channel）与预配置的
    RouteBinding 列表进行匹配，返回第一个命中的路由结果。
    所有 binding 按 priority 升序排列，确保高优先级规则先匹配。

    确定性保证: 相同的 context 和 bindings 配置始终返回相同的 ResolvedRoute。

    Args:
        bindings: 路由绑定规则列表，初始化时按 priority 排序
        default_agent_id: 无匹配时的默认 Agent ID
    """

    def __init__(
        self,
        bindings: list[RouteBinding] | None = None,
        default_agent_id: str = "default",
    ):
        # 按 priority 升序排列，数值越小越先匹配
        self._bindings = sorted(bindings or [], key=lambda b: b.priority)
        self._default_agent_id = default_agent_id

    def resolve(self, context: dict) -> ResolvedRoute:
        """解析路由 — 按优先级逐条匹配 binding

        遍历已排序的 binding 列表，返回第一个匹配的路由结果。
        若无任何 binding 匹配，返回默认路由。

        Args:
            context: 路由上下文，可包含 channel、scene、intent、session_binding 等字段

        Returns:
            ResolvedRoute 包含 agent_id、session_key 和匹配方式
        """
        for binding in self._bindings:
            if self._matches(binding, context):
                return ResolvedRoute(
                    agent_id=binding.agent_id,
                    session_key=f"{binding.agent_id}:{context.get('channel', 'unknown')}",
                    matched_by=f"binding.{binding.match_type}",
                )
        # 无匹配 → 返回默认路由
        return ResolvedRoute(
            agent_id=self._default_agent_id,
            session_key=f"{self._default_agent_id}:default",
            matched_by="default",
        )

    def _matches(self, binding: RouteBinding, context: dict) -> bool:
        """判断单条 binding 是否匹配 context

        根据 binding.match_type 选择不同的匹配策略:
        - session: context 中的 session_binding 等于 binding.agent_id
        - scene: context 中的 scene 等于 binding.scene
        - intent: context 中的 intent 与 binding.pattern 正则匹配
        - channel: context 中的 channel 等于 binding.channel

        Args:
            binding: 路由绑定规则
            context: 路由上下文

        Returns:
            True 表示匹配成功
        """
        if binding.match_type == "session":
            # 显式 session 绑定：context 中指定了目标 agent
            return context.get("session_binding", "") == binding.agent_id
        if binding.match_type == "scene":
            # 场景绑定：如 "厨房" → 厨房 Agent
            return binding.scene == context.get("scene", "")
        if binding.match_type == "intent":
            # 意图模式匹配：正则匹配 intent 字段
            intent = context.get("intent", "")
            if not binding.pattern or not intent:
                return False
            return bool(re.match(binding.pattern, intent))
        if binding.match_type == "channel":
            # 通道绑定：如 ROS2 → 机器人 Agent
            return binding.channel == context.get("channel", "")
        # 未知 match_type 不匹配
        return False
