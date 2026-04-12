import asyncio
import time

import pytest

from mosaic.plugin_sdk.types import ExecutionContext
from plugins.capabilities.human_proxy import HumanProxyCapability
from mosaic.runtime.operator_console import OperatorConsoleState


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
