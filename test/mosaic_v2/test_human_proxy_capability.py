import asyncio
import time

import pytest

from mosaic.core.event_bus import EventBus
from mosaic.core.hooks import HookManager
from mosaic.gateway.session_manager import SessionManager
from mosaic.plugin_sdk.registry import PluginRegistry
from mosaic.plugin_sdk.types import ExecutionContext
from plugins.capabilities.human_proxy import HumanProxyCapability
from mosaic.runtime.operator_console import OperatorConsoleState
from mosaic.runtime.turn_runner import TurnRunner


@pytest.mark.asyncio
async def test_human_proxy_waits_for_submission_and_returns_image_paths():
    console = OperatorConsoleState()
    cap = HumanProxyCapability(console_state=console, timeout_s=2.0)

    async def submit_later():
        await asyncio.sleep(0.05)
        console.submit_result({
            "step_id": "step-01",
            "operator_result": "completed",
            "images": {
                "front": "front.jpg",
                "left": "left.jpg",
                "right": "right.jpg",
                "back": "back.jpg",
            },
            "timestamp": time.time(),
        })

    asyncio.create_task(submit_later())
    result = await cap.execute(
        "request_human_move",
        {"instruction_text": "前进 1.2 米"},
        ExecutionContext(session_id="s1", metadata={"step_id": "step-01"}),
    )

    assert result.success is True
    assert result.data["operator_result"] == "completed"
    assert sorted(result.data["images"].keys()) == ["back", "front", "left", "right"]


@pytest.mark.asyncio
async def test_human_proxy_requires_all_views():
    console = OperatorConsoleState()
    cap = HumanProxyCapability(console_state=console, timeout_s=1.0)

    async def submit_later():
        await asyncio.sleep(0.05)
        console.submit_result({
            "step_id": "step-missing-view",
            "operator_result": "completed",
            "images": {
                "front": "front.jpg",
                "left": "left.jpg",
                "right": "right.jpg",
            },
            "timestamp": time.time(),
        })

    asyncio.create_task(submit_later())
    result = await cap.execute(
        "request_human_move",
        {"instruction_text": "前进 1.2 米"},
        ExecutionContext(session_id="s1", metadata={"step_id": "step-missing-view"}),
    )

    assert result.success is False
    assert "缺少" in (result.error or "")


@pytest.mark.asyncio
async def test_human_proxy_times_out_without_submission():
    console = OperatorConsoleState()
    cap = HumanProxyCapability(console_state=console, timeout_s=0.05)
    result = await cap.execute(
        "request_human_move",
        {"instruction_text": "前进 1.2 米"},
        ExecutionContext(session_id="s1", metadata={"step_id": "step-timeout"}),
    )
    assert result.success is False
    assert "超时" in (result.error or "")


def test_human_proxy_disabled_exposes_no_tools():
    cap = HumanProxyCapability(enabled=False)
    assert cap.get_tool_definitions() == []


@pytest.mark.asyncio
async def test_turn_runner_populates_step_id_for_human_proxy():
    class CapturingConsole(OperatorConsoleState):
        def __init__(self) -> None:
            super().__init__()
            self.published_step_id = None

        def publish_step(self, payload):
            self.published_step_id = payload.get("step_id")
            super().publish_step(payload)

    class CapturingProvider:
        def __init__(self):
            from mosaic.plugin_sdk.types import PluginMeta

            self.meta = PluginMeta(
                id="prov",
                name="Provider",
                version="0.1.0",
                description="",
                kind="provider",
            )
            self.calls = 0

        async def chat(self, messages, tools, config):
            from mosaic.plugin_sdk.types import ProviderResponse

            if self.calls == 0:
                self.calls += 1
                return ProviderResponse(
                    content="",
                    tool_calls=[{
                        "id": "tool-99",
                        "name": "request_human_move",
                        "arguments": {"instruction_text": "前进 1.2 米"},
                    }],
                    usage={},
                )
            return ProviderResponse(content="完成", tool_calls=[], usage={})

        async def stream(self, messages, tools, config):
            from mosaic.plugin_sdk.types import ProviderResponse

            yield ProviderResponse(content="完成", tool_calls=[], usage={})

        async def validate_auth(self):
            return True

    class ContextEngine:
        def __init__(self):
            from mosaic.plugin_sdk.types import PluginMeta

            self.meta = PluginMeta(
                id="ce",
                name="ContextEngine",
                version="0.1.0",
                description="",
                kind="context-engine",
            )

        async def ingest(self, session_id, message):
            return None

        async def assemble(self, session_id, token_budget):
            from mosaic.plugin_sdk.types import AssembleResult

            return AssembleResult(messages=[], token_count=0)

        async def compact(self, session_id, force=False):
            raise AssertionError("compact should not be called")

    console = CapturingConsole()
    cap = HumanProxyCapability(console_state=console, timeout_s=1.0)

    registry = PluginRegistry()
    registry.register("prov", CapturingProvider, "provider")
    registry.set_default_provider("prov")
    registry.register("ce", ContextEngine, "context-engine")
    registry.set_slot("context-engine", "ce")
    registry.register("human-proxy", lambda: cap, "capability")

    async def submit_later():
        await asyncio.sleep(0.05)
        console.submit_result({
            "step_id": "tool-99",
            "operator_result": "completed",
            "images": {
                "front": "front.jpg",
                "left": "left.jpg",
                "right": "right.jpg",
                "back": "back.jpg",
            },
            "timestamp": time.time(),
        })

    asyncio.create_task(submit_later())

    runner = TurnRunner(
        registry=registry,
        event_bus=EventBus(),
        hooks=HookManager(),
        system_prompt="",
    )

    smgr = SessionManager()
    session = await smgr.create_session("default", "cli")
    await smgr.run_turn(session.session_id, "前进 1.2 米", runner)

    assert console.published_step_id == "tool-99"


def test_operator_console_publish_sets_current_step():
    console = OperatorConsoleState()
    payload = {"step_id": "step-publish", "details": "demo"}
    console.publish_step(payload)
    assert console.current_step == payload


@pytest.mark.asyncio
async def test_wait_for_result_returns_pending_submission():
    console = OperatorConsoleState()
    step_id = "step-early"
    payload = {"step_id": step_id, "status": "pending"}
    console.publish_step(payload)
    console.submit_result(payload)

    result = await console.wait_for_result(step_id, timeout_s=0.5)
    assert result == payload


@pytest.mark.asyncio
async def test_timeout_clears_current_step():
    console = OperatorConsoleState()
    step_id = "step-timeout"
    payload = {"step_id": step_id, "status": "pending"}
    console.publish_step(payload)

    with pytest.raises(asyncio.TimeoutError):
        await console.wait_for_result(step_id, timeout_s=0.01)

    assert console.current_step is None


def test_mismatched_submission_does_not_erase_step():
    console = OperatorConsoleState()
    step_id = "step-active"
    payload = {"step_id": step_id, "status": "pending"}
    console.publish_step(payload)

    console.submit_result({"step_id": "other-step"})
    assert console.current_step == payload


@pytest.mark.asyncio
async def test_late_submission_after_timeout_is_buffered():
    console = OperatorConsoleState()
    step_id = "step-late"
    console.publish_step({"step_id": step_id, "status": "pending"})

    future = asyncio.get_running_loop().create_future()
    future.cancel()
    console._futures[step_id] = future

    payload = {"step_id": step_id, "status": "completed"}
    console.submit_result(payload)
    await asyncio.sleep(0)

    result = await console.wait_for_result(step_id, timeout_s=0.05)
    assert result == payload


@pytest.mark.asyncio
async def test_republish_same_step_preserves_active_waiter():
    console = OperatorConsoleState()
    step_id = "step-republish"
    console.publish_step({"step_id": step_id, "revision": 1})

    waiter = asyncio.create_task(console.wait_for_result(step_id, timeout_s=0.2))
    await asyncio.sleep(0)

    console.publish_step({"step_id": step_id, "revision": 2})
    payload = {"step_id": step_id, "status": "completed"}
    console.submit_result(payload)

    result = await waiter
    assert result == payload
