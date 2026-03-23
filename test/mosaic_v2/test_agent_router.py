"""属性测试 — AgentRouter 确定性路由

属性 10: 相同 context 和 bindings 总是返回相同 ResolvedRoute

对于任意相同的 context 和相同的 bindings 配置，
AgentRouter.resolve() 总是返回相同的 ResolvedRoute。

**Validates: Requirements 6.1, 6.6**
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st, assume

from mosaic.gateway.agent_router import AgentRouter, RouteBinding, ResolvedRoute


# ── Hypothesis 策略 ──

# Agent ID 策略
agent_id_st = st.from_regex(r"[a-z][a-z0-9_]{1,15}", fullmatch=True)

# 匹配类型策略
match_type_st = st.sampled_from(["session", "scene", "intent", "channel"])

# 通道名称策略
channel_st = st.sampled_from(["cli", "websocket", "ros2", "telegram", "web"])

# 场景名称策略
scene_st = st.sampled_from(["kitchen", "bedroom", "office", "garden", "hallway"])

# 意图模式策略（简单正则，避免生成无效正则）
intent_pattern_st = st.sampled_from([
    "navigate_.*",
    "patrol",
    "rotate_.*",
    "stop",
    "move_.*",
    "look_.*",
])

# 意图值策略（可能匹配上述模式的值）
intent_value_st = st.sampled_from([
    "navigate_to",
    "navigate_home",
    "patrol",
    "rotate_left",
    "stop",
    "move_forward",
    "look_around",
    "unknown_intent",
    "",
])

# 优先级策略
priority_st = st.integers(min_value=1, max_value=99)


# RouteBinding 策略：根据 match_type 生成合理的 binding
@st.composite
def route_binding_st(draw):
    """生成合理的 RouteBinding，确保字段与 match_type 一致"""
    agent_id = draw(agent_id_st)
    match_type = draw(match_type_st)
    priority = draw(priority_st)

    pattern = ""
    channel = ""
    scene = ""

    if match_type == "channel":
        channel = draw(channel_st)
    elif match_type == "scene":
        scene = draw(scene_st)
    elif match_type == "intent":
        pattern = draw(intent_pattern_st)
    # session 类型不需要额外字段

    return RouteBinding(
        agent_id=agent_id,
        match_type=match_type,
        pattern=pattern,
        channel=channel,
        scene=scene,
        priority=priority,
    )


# 路由上下文策略
@st.composite
def context_st(draw):
    """生成路由上下文字典"""
    ctx = {}
    # 随机包含各字段
    if draw(st.booleans()):
        ctx["channel"] = draw(channel_st)
    if draw(st.booleans()):
        ctx["scene"] = draw(scene_st)
    if draw(st.booleans()):
        ctx["intent"] = draw(intent_value_st)
    if draw(st.booleans()):
        ctx["session_binding"] = draw(agent_id_st)
    return ctx


# binding 列表策略
bindings_list_st = st.lists(route_binding_st(), min_size=0, max_size=8)


class TestRouterDeterminism:
    """属性 10: Router 确定性

    相同 context 和 bindings 总是返回相同 ResolvedRoute。

    **Validates: Requirements 6.1, 6.6**
    """

    @given(
        bindings=bindings_list_st,
        context=context_st(),
        default_agent=agent_id_st,
    )
    @settings(max_examples=300)
    def test_same_context_same_bindings_same_result(
        self,
        bindings: list[RouteBinding],
        context: dict,
        default_agent: str,
    ):
        """相同 context 和 bindings 多次 resolve 返回相同结果（Req 6.1, 6.6）。

        验证：
        1. 创建两个配置完全相同的 AgentRouter
        2. 用相同 context 分别调用 resolve
        3. 两次结果的 agent_id、session_key、matched_by 完全一致
        """
        # 创建两个配置相同的 router
        router1 = AgentRouter(bindings=list(bindings), default_agent_id=default_agent)
        router2 = AgentRouter(bindings=list(bindings), default_agent_id=default_agent)

        # 用相同 context 分别 resolve
        result1 = router1.resolve(context)
        result2 = router2.resolve(context)

        assert result1.agent_id == result2.agent_id, (
            f"相同配置和 context 应返回相同 agent_id，"
            f"结果1: {result1.agent_id}，结果2: {result2.agent_id}"
        )
        assert result1.session_key == result2.session_key, (
            f"相同配置和 context 应返回相同 session_key，"
            f"结果1: {result1.session_key}，结果2: {result2.session_key}"
        )
        assert result1.matched_by == result2.matched_by, (
            f"相同配置和 context 应返回相同 matched_by，"
            f"结果1: {result1.matched_by}，结果2: {result2.matched_by}"
        )

    @given(
        bindings=bindings_list_st,
        context=context_st(),
        default_agent=agent_id_st,
        repeat_count=st.integers(min_value=3, max_value=10),
    )
    @settings(max_examples=200)
    def test_repeated_resolve_is_idempotent(
        self,
        bindings: list[RouteBinding],
        context: dict,
        default_agent: str,
        repeat_count: int,
    ):
        """同一 router 多次 resolve 同一 context 结果不变（幂等性）。

        验证 resolve 是纯函数，不依赖内部可变状态。
        """
        router = AgentRouter(bindings=bindings, default_agent_id=default_agent)

        results = [router.resolve(context) for _ in range(repeat_count)]

        first = results[0]
        for i, r in enumerate(results[1:], start=2):
            assert r.agent_id == first.agent_id, (
                f"第 {i} 次 resolve 的 agent_id 应与首次一致"
            )
            assert r.session_key == first.session_key, (
                f"第 {i} 次 resolve 的 session_key 应与首次一致"
            )
            assert r.matched_by == first.matched_by, (
                f"第 {i} 次 resolve 的 matched_by 应与首次一致"
            )

    @given(
        bindings=bindings_list_st,
        default_agent=agent_id_st,
    )
    @settings(max_examples=200)
    def test_empty_context_returns_consistent_result(
        self,
        bindings: list[RouteBinding],
        default_agent: str,
    ):
        """空 context 多次 resolve 结果一致。"""
        router = AgentRouter(bindings=bindings, default_agent_id=default_agent)

        result1 = router.resolve({})
        result2 = router.resolve({})

        assert result1.agent_id == result2.agent_id
        assert result1.session_key == result2.session_key
        assert result1.matched_by == result2.matched_by

    @given(
        bindings=bindings_list_st,
        default_agent=agent_id_st,
    )
    @settings(max_examples=200)
    def test_no_bindings_always_returns_default(
        self,
        bindings: list[RouteBinding],
        default_agent: str,
    ):
        """无 binding 时始终返回默认路由（Req 6.5）。"""
        # 使用空 binding 列表
        router = AgentRouter(bindings=[], default_agent_id=default_agent)

        # 任意 context 都应返回默认
        result = router.resolve({"channel": "cli", "scene": "kitchen"})

        assert result.agent_id == default_agent, (
            f"无 binding 时应返回默认 agent '{default_agent}'，实际: {result.agent_id}"
        )
        assert result.matched_by == "default", (
            f"无 binding 时 matched_by 应为 'default'，实际: {result.matched_by}"
        )

    @given(
        bindings=st.lists(route_binding_st(), min_size=1, max_size=8),
        context=context_st(),
        default_agent=agent_id_st,
    )
    @settings(max_examples=200)
    def test_priority_ordering_is_respected(
        self,
        bindings: list[RouteBinding],
        context: dict,
        default_agent: str,
    ):
        """binding 按 priority 升序匹配（Req 6.1）。

        验证：确保所有 binding 的 priority 唯一时，传入顺序不影响结果。
        当 priority 相同时，sorted 是稳定排序，原始顺序会影响结果，
        因此此测试仅验证 priority 唯一的情况。
        """
        # 确保所有 binding 的 priority 唯一，排除稳定排序的歧义
        priorities = [b.priority for b in bindings]
        assume(len(priorities) == len(set(priorities)))

        # 正序和逆序传入应得到相同结果
        router_forward = AgentRouter(bindings=bindings, default_agent_id=default_agent)
        router_reverse = AgentRouter(
            bindings=list(reversed(bindings)), default_agent_id=default_agent
        )

        result_forward = router_forward.resolve(context)
        result_reverse = router_reverse.resolve(context)

        assert result_forward.agent_id == result_reverse.agent_id, (
            f"priority 唯一时，binding 传入顺序不应影响结果，"
            f"正序: {result_forward.agent_id}，逆序: {result_reverse.agent_id}"
        )
        assert result_forward.matched_by == result_reverse.matched_by, (
            f"priority 唯一时，binding 传入顺序不应影响匹配方式，"
            f"正序: {result_forward.matched_by}，逆序: {result_reverse.matched_by}"
        )
