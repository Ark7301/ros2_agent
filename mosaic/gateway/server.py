# mosaic/gateway/server.py
"""Gateway Server 入口 — 系统启动、组件编排、消息处理

初始化所有核心组件（ConfigManager、EventBus、HookManager、PluginRegistry），
自动发现插件，配置 Slot 和 Provider，启动事件循环，
连接 Channel 插件的消息事件到 Gateway 处理流程。

数据流: 用户输入 → Channel → EventBus → Gateway → Router → Session → TurnRunner → 响应
"""

from __future__ import annotations

import asyncio
import logging

from mosaic.core.config import ConfigManager
from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.gateway.session_manager import SessionManager
from mosaic.gateway.agent_router import AgentRouter, RouteBinding
from mosaic.runtime.turn_runner import TurnRunner
from mosaic.protocol.events import Event, EventPriority
from mosaic.protocol.messages import INBOUND_MESSAGE, OUTBOUND_MESSAGE
from mosaic.plugin_sdk.types import OutboundMessage

logger = logging.getLogger(__name__)


class GatewayServer:
    """Gateway Server — 系统入口，编排所有组件

    职责：
    - 初始化核心基础设施（Config、EventBus、Hooks、Registry）
    - 自动发现并注册插件，配置 Slot 和默认 Provider
    - 初始化控制面组件（SessionManager、AgentRouter、TurnRunner）
    - 启动 EventBus 事件循环和 Channel 插件
    - 连接 Channel 入站消息到 Gateway 处理流程
    """

    def __init__(self, config_path: str = "config/mosaic.yaml"):
        # ── 1. 加载配置 ──
        self._config = ConfigManager(config_path)
        self._config.load()

        # ── 2. 初始化核心基础设施 ──
        self._event_bus = EventBus()
        self._hooks = HookManager()
        self._registry = PluginRegistry()

        # ── 3. 自动发现插件 ──
        self._registry.discover("plugins")

        # ── 4. 配置 Slot 和默认 Provider ──
        self._registry.set_slot(
            "memory",
            self._config.get("plugins.slots.memory", "file-memory"),
        )
        self._registry.set_slot(
            "context-engine",
            self._config.get("plugins.slots.context-engine", "sliding-window"),
        )
        self._registry.set_default_provider(
            self._config.get("plugins.providers.default", "minimax"),
        )

        # ── 5. 初始化控制面组件 ──
        self._session_manager = SessionManager(
            max_concurrent=self._config.get(
                "gateway.max_concurrent_sessions", 10,
            ),
            idle_timeout_s=self._config.get(
                "gateway.idle_session_timeout_s", 300,
            ),
        )

        # 从配置构建路由绑定
        bindings = self._build_route_bindings()
        self._router = AgentRouter(
            bindings=bindings,
            default_agent_id=self._config.get(
                "routing.default_agent", "default",
            ),
        )

        self._turn_runner = TurnRunner(
            registry=self._registry,
            event_bus=self._event_bus,
            hooks=self._hooks,
            max_iterations=self._config.get(
                "agents.default.max_turn_iterations", 10,
            ),
            turn_timeout_s=self._config.get(
                "agents.default.turn_timeout_s", 120,
            ),
            system_prompt=self._config.get(
                "agents.default.system_prompt", "",
            ),
        )

        # EventBus 事件循环任务引用
        self._bus_task: asyncio.Task | None = None

    def _build_route_bindings(self) -> list[RouteBinding]:
        """从配置文件构建路由绑定列表"""
        raw_bindings = self._config.get("routing.bindings", [])
        bindings = []
        for b in raw_bindings or []:
            bindings.append(RouteBinding(
                agent_id=b.get("agent_id", "default"),
                match_type=b.get("match_type", "channel"),
                pattern=b.get("pattern", ""),
                channel=b.get("channel", ""),
                scene=b.get("scene", ""),
                priority=b.get("priority", 99),
            ))
        return bindings

    async def start(self) -> None:
        """启动 Gateway Server

        1. 触发 gateway.start 钩子
        2. 启动 EventBus 事件分发循环
        3. 注册入站消息事件处理器
        4. 启动所有已启用的 Channel 插件
        """
        logger.info("Gateway Server 启动中...")

        # 触发 gateway.start 钩子
        await self._hooks.emit("gateway.start", {})

        # 启动 EventBus 事件循环（后台任务）
        self._bus_task = asyncio.create_task(self._event_bus.start())

        # 注册入站消息事件处理器
        self._event_bus.on(INBOUND_MESSAGE, self._handle_inbound_message)

        # 启动 Channel 插件并连接消息回调
        await self._start_channels()

        logger.info("Gateway Server 已启动")

    async def stop(self) -> None:
        """停止 Gateway Server

        1. 停止所有 Channel 插件
        2. 停止 EventBus 事件循环
        3. 触发 gateway.stop 钩子
        """
        logger.info("Gateway Server 停止中...")

        # 停止 Channel 插件
        await self._stop_channels()

        # 停止 EventBus
        await self._event_bus.stop()
        if self._bus_task and not self._bus_task.done():
            self._bus_task.cancel()
            try:
                await self._bus_task
            except asyncio.CancelledError:
                pass

        # 触发 gateway.stop 钩子
        await self._hooks.emit("gateway.stop", {})

        logger.info("Gateway Server 已停止")

    async def _start_channels(self) -> None:
        """启动所有已启用的 Channel 插件，并连接消息回调到 EventBus"""
        channel_ids = self._registry.list_by_kind("channel")
        channels_config = self._config.get("channels", {}) or {}

        for cid in channel_ids:
            # 检查该 channel 是否在配置中启用
            ch_config = channels_config.get(cid, {})
            if not (ch_config and ch_config.get("enabled", False)):
                continue

            try:
                channel = self._registry.resolve(cid)

                # 连接 channel 的入站消息到 EventBus
                channel.on_message(
                    self._create_channel_handler(cid),
                )

                # 启动 channel
                await channel.start()
                logger.info("Channel 已启动: %s", cid)
            except Exception as e:
                logger.error("Channel 启动失败: %s — %s", cid, e)

    async def _stop_channels(self) -> None:
        """停止所有已启动的 Channel 插件"""
        channel_ids = self._registry.list_by_kind("channel")
        for cid in channel_ids:
            try:
                channel = self._registry.resolve(cid)
                await channel.stop()
                logger.info("Channel 已停止: %s", cid)
            except Exception as e:
                logger.error("Channel 停止失败: %s — %s", cid, e)

    def _create_channel_handler(self, channel_id: str):
        """为指定 Channel 创建入站消息处理函数

        将用户输入封装为 Event 并发射到 EventBus。
        """
        async def handler(user_input: str) -> None:
            event = Event(
                type=INBOUND_MESSAGE,
                payload={
                    "content": user_input,
                    "channel_id": channel_id,
                },
                source=f"channel.{channel_id}",
            )
            await self._event_bus.emit(event)

        return handler

    async def _handle_inbound_message(self, event: Event) -> None:
        """处理入站消息事件 — Gateway 核心处理流程

        数据流: Event → Router → Session → TurnRunner → 响应 → OutboundMessage
        """
        payload = event.payload
        content = payload.get("content", "")
        channel_id = payload.get("channel_id", "unknown")

        try:
            # 1. 路由解析：确定目标 Agent
            route = self._router.resolve({"channel": channel_id})

            # 2. 获取或创建 Session
            session = await self._get_or_create_session(
                route.agent_id, channel_id, route.session_key,
            )

            # 3. 执行 Turn
            result = await self._session_manager.run_turn(
                session.session_id, content, self._turn_runner,
            )

            # 4. 发射出站消息事件
            out_event = Event(
                type=OUTBOUND_MESSAGE,
                payload={
                    "content": result.response,
                    "channel_id": channel_id,
                    "session_id": session.session_id,
                },
                source="gateway",
                session_id=session.session_id,
            )
            await self._event_bus.emit(out_event)

            # 5. 通过 Channel 发送响应
            await self._send_response(channel_id, session.session_id, result.response)

        except Exception as e:
            logger.error("处理入站消息失败: %s", e)
            # 尝试发送错误响应
            await self._send_response(
                channel_id, "", f"处理消息时发生错误: {e}",
            )

    async def _get_or_create_session(
        self,
        agent_id: str,
        channel_id: str,
        session_key: str,
    ):
        """获取已有 Session 或创建新 Session

        通过 SessionManager 公共接口查找已有活跃 Session，避免重复创建。
        """
        # 通过公共方法查找已有活跃 Session
        session = self._session_manager.find_active_session(agent_id, channel_id)
        if session:
            return session

        # 创建新 Session
        return await self._session_manager.create_session(agent_id, channel_id)

    async def _send_response(
        self,
        channel_id: str,
        session_id: str,
        content: str,
    ) -> None:
        """通过指定 Channel 发送响应消息"""
        try:
            channel = self._registry.resolve(channel_id)
            message = OutboundMessage(
                session_id=session_id,
                content=content,
            )
            await channel.send(message)
        except Exception as e:
            logger.error("发送响应失败 [channel=%s]: %s", channel_id, e)

    # ── 公共属性，便于测试和外部访问 ──

    @property
    def config(self) -> ConfigManager:
        return self._config

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def hooks(self) -> HookManager:
        return self._hooks

    @property
    def registry(self) -> PluginRegistry:
        return self._registry

    @property
    def session_manager(self) -> SessionManager:
        return self._session_manager

    @property
    def router(self) -> AgentRouter:
        return self._router

    @property
    def turn_runner(self) -> TurnRunner:
        return self._turn_runner


async def run_gateway(config_path: str = "config/mosaic.yaml") -> None:
    """运行 Gateway Server（异步入口）

    启动 Gateway 并等待中断信号（Ctrl+C）后优雅停止。
    """
    server = GatewayServer(config_path)
    try:
        await server.start()
        # 保持运行直到被中断
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        await server.stop()


def main(config_path: str = "config/mosaic.yaml") -> None:
    """Gateway Server 同步入口（main 函数）

    使用 asyncio.run 启动异步 Gateway Server。
    """
    asyncio.run(run_gateway(config_path))


if __name__ == "__main__":
    main()
