# CLI Channel 插件单元测试
# 验证 CLIChannel 实现 ChannelPlugin Protocol 的所有方法

from __future__ import annotations

import asyncio
import pytest

from plugins.channels.cli import CLIChannel, create_plugin
from mosaic.plugin_sdk.types import (
    ChannelPlugin,
    OutboundMessage,
    SendResult,
    PluginMeta,
)


class TestCLIChannelProtocol:
    """验证 CLIChannel 满足 ChannelPlugin Protocol"""

    def test_isinstance_check(self):
        """CLIChannel 应通过 ChannelPlugin 的 runtime_checkable 检查"""
        plugin = create_plugin()
        assert isinstance(plugin, ChannelPlugin)

    def test_meta_kind(self):
        """meta.kind 应为 'channel'"""
        plugin = create_plugin()
        assert plugin.meta.kind == "channel"
        assert plugin.meta.id == "cli"

    def test_meta_is_plugin_meta(self):
        """meta 应为 PluginMeta 实例"""
        plugin = create_plugin()
        assert isinstance(plugin.meta, PluginMeta)

    def test_create_plugin_factory(self):
        """create_plugin 工厂函数应返回 CLIChannel 实例"""
        plugin = create_plugin()
        assert isinstance(plugin, CLIChannel)


class TestCLIChannelSend:
    """验证 send 方法"""

    @pytest.mark.asyncio
    async def test_send_success(self, capsys):
        """send 应将消息内容输出到 stdout 并返回成功"""
        plugin = create_plugin()
        msg = OutboundMessage(session_id="test-session", content="你好世界")
        result = await plugin.send(msg)

        assert result.success is True
        assert result.error is None
        captured = capsys.readouterr()
        assert "你好世界" in captured.out

    @pytest.mark.asyncio
    async def test_send_returns_send_result(self):
        """send 返回值应为 SendResult 类型"""
        plugin = create_plugin()
        msg = OutboundMessage(session_id="s1", content="test")
        result = await plugin.send(msg)
        assert isinstance(result, SendResult)


class TestCLIChannelOnMessage:
    """验证 on_message 方法"""

    def test_register_handler(self):
        """on_message 应注册消息处理器"""
        plugin = create_plugin()
        called = []
        plugin.on_message(lambda msg: called.append(msg))
        # 处理器已注册，内部 _handler 不为 None
        assert plugin._handler is not None


class TestCLIChannelLifecycle:
    """验证 start/stop 生命周期"""

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        """未启动时调用 stop 不应报错"""
        plugin = create_plugin()
        await plugin.stop()  # 不应抛出异常

    @pytest.mark.asyncio
    async def test_start_sets_running(self):
        """start 后 _running 应为 True"""
        plugin = create_plugin()
        # start 会创建 input_loop task，但 input() 会阻塞
        # 我们立即 stop 来避免阻塞
        await plugin.start()
        assert plugin._running is True
        await plugin.stop()
        assert plugin._running is False

    @pytest.mark.asyncio
    async def test_double_start_is_safe(self):
        """重复调用 start 不应创建多个任务"""
        plugin = create_plugin()
        await plugin.start()
        task1 = plugin._task
        await plugin.start()  # 第二次调用应被忽略
        task2 = plugin._task
        assert task1 is task2
        await plugin.stop()
