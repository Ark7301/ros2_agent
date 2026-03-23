# 滑动窗口上下文引擎插件测试
# Validates: Requirements 2.5, 3.1

import pytest
import pytest_asyncio

from plugins.context_engines.sliding_window import (
    SlidingWindowContextEngine,
    create_plugin,
    _estimate_tokens,
)
from mosaic.plugin_sdk.types import (
    AssembleResult,
    CompactResult,
    ContextEnginePlugin,
    PluginMeta,
)


class TestSlidingWindowContextEngine:
    """SlidingWindowContextEngine 单元测试"""

    def test_create_plugin_returns_instance(self):
        """create_plugin 工厂函数应返回 SlidingWindowContextEngine 实例"""
        plugin = create_plugin()
        assert isinstance(plugin, SlidingWindowContextEngine)

    def test_satisfies_context_engine_protocol(self):
        """实例应满足 ContextEnginePlugin Protocol"""
        plugin = create_plugin()
        assert isinstance(plugin, ContextEnginePlugin)

    def test_meta_kind_is_context_engine(self):
        """meta.kind 应为 'context-engine'"""
        plugin = create_plugin()
        assert plugin.meta.kind == "context-engine"
        assert isinstance(plugin.meta, PluginMeta)

    @pytest.mark.asyncio
    async def test_ingest_stores_message(self):
        """ingest 应将消息存入对应 session"""
        engine = create_plugin()
        msg = {"role": "user", "content": "hello"}
        await engine.ingest("s1", msg)
        assert engine._sessions["s1"] == [msg]

    @pytest.mark.asyncio
    async def test_ingest_multiple_sessions(self):
        """不同 session 的消息应隔离存储"""
        engine = create_plugin()
        await engine.ingest("s1", {"role": "user", "content": "a"})
        await engine.ingest("s2", {"role": "user", "content": "b"})
        assert len(engine._sessions["s1"]) == 1
        assert len(engine._sessions["s2"]) == 1

    @pytest.mark.asyncio
    async def test_assemble_empty_session(self):
        """空 session 应返回空结果"""
        engine = create_plugin()
        result = await engine.assemble("nonexistent", 1000)
        assert isinstance(result, AssembleResult)
        assert result.messages == []
        assert result.token_count == 0

    @pytest.mark.asyncio
    async def test_assemble_within_budget(self):
        """token 预算充足时应返回所有消息"""
        engine = create_plugin()
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        for m in msgs:
            await engine.ingest("s1", m)

        result = await engine.assemble("s1", token_budget=10000)
        assert len(result.messages) == 2
        # 消息顺序应保持（旧 → 新）
        assert result.messages[0]["role"] == "user"
        assert result.messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_assemble_respects_token_budget(self):
        """token 预算不足时应从尾部截取"""
        engine = create_plugin()
        # 插入多条消息
        for i in range(20):
            await engine.ingest("s1", {"role": "user", "content": f"message {i}" * 10})

        # 用较小的 budget
        result = await engine.assemble("s1", token_budget=50)
        assert result.token_count <= 50
        # 应该只返回尾部的部分消息
        assert len(result.messages) < 20

    @pytest.mark.asyncio
    async def test_assemble_preserves_order(self):
        """assemble 返回的消息应保持时间顺序"""
        engine = create_plugin()
        for i in range(5):
            await engine.ingest("s1", {"role": "user", "content": str(i)})

        result = await engine.assemble("s1", token_budget=10000)
        contents = [m["content"] for m in result.messages]
        assert contents == ["0", "1", "2", "3", "4"]

    @pytest.mark.asyncio
    async def test_compact_no_action_below_threshold(self):
        """消息数未超阈值且 force=False 时不压缩"""
        engine = SlidingWindowContextEngine(compact_threshold=100)
        for i in range(10):
            await engine.ingest("s1", {"role": "user", "content": str(i)})

        result = await engine.compact("s1")
        assert isinstance(result, CompactResult)
        assert result.removed_count == 0
        assert result.remaining_count == 10

    @pytest.mark.asyncio
    async def test_compact_force(self):
        """force=True 时应强制压缩"""
        engine = create_plugin()
        for i in range(10):
            await engine.ingest("s1", {"role": "user", "content": str(i)})

        result = await engine.compact("s1", force=True)
        assert result.removed_count == 5  # 移除前半部分
        assert result.remaining_count == 5

    @pytest.mark.asyncio
    async def test_compact_exceeds_threshold(self):
        """消息数超过阈值时自动压缩"""
        engine = SlidingWindowContextEngine(compact_threshold=5)
        for i in range(10):
            await engine.ingest("s1", {"role": "user", "content": str(i)})

        result = await engine.compact("s1")
        assert result.removed_count == 5
        assert result.remaining_count == 5

    @pytest.mark.asyncio
    async def test_compact_empty_session(self):
        """空 session 压缩应返回零"""
        engine = create_plugin()
        result = await engine.compact("nonexistent")
        assert result.removed_count == 0
        assert result.remaining_count == 0

    def test_estimate_tokens(self):
        """token 估算函数基本验证"""
        # 空字典的字符串表示 "{}" 长度为 2，// 4 = 0，但 max(..., 1) = 1
        assert _estimate_tokens({}) >= 1
        # 较长内容应有更多 token
        long_msg = {"role": "user", "content": "a" * 400}
        assert _estimate_tokens(long_msg) > 50
