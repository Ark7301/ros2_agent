import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts/run_human_surrogate_memory_demo.py"


def test_demo_assets_exist() -> None:
    assert (REPO_ROOT / "config/demo/human_surrogate_memory.yaml").exists()
    assert (REPO_ROOT / "config/demo/observation_frames/README.md").exists()
    assert (REPO_ROOT / "scripts/run_human_surrogate_memory_demo.py").exists()
    assert (REPO_ROOT / "docs/dev/runbooks/human-surrogate-memory-demo.md").exists()

    dev_readme = (REPO_ROOT / "docs/dev/README.md").read_text(encoding="utf-8")
    assert "runbooks/human-surrogate-memory-demo.md" in dev_readme

    runbook = (REPO_ROOT / "docs/dev/runbooks/human-surrogate-memory-demo.md").read_text(
        encoding="utf-8"
    )
    assert "Ctrl+C" in runbook
    assert "config/demo/observation_frames" in runbook
    assert "PYTHONPATH=. python3 scripts/run_human_surrogate_memory_demo.py" in runbook


def test_demo_dry_run_output() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    output = result.stdout
    assert "Human-surrogate ARIA memory demo is ready." in output
    assert "Operator console: http://127.0.0.1:8876" in output
    assert "Observation frame storage: config/demo/observation_frames" in output
    assert "human_proxy enabled in runtime config" in output


def test_demo_dry_run_from_other_cwd(tmp_path: Path) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--dry-run"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=10,
    )
    output = result.stdout
    assert "Human-surrogate ARIA memory demo is ready." in output


def test_demo_stop_error_does_not_mask_start_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.run_human_surrogate_memory_demo as demo

    class StartFailure(Exception):
        pass

    class StopFailure(Exception):
        pass

    class FakeServer:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        async def start(self) -> None:
            raise StartFailure("start failed")

        async def stop(self) -> None:
            raise StopFailure("stop failed")

    temp_config = tmp_path / "runtime.yaml"
    temp_config.write_text("human_proxy: {}", encoding="utf-8")

    monkeypatch.setattr(demo, "GatewayServer", FakeServer)
    monkeypatch.setattr(demo, "_load_demo_config", lambda: {"demo": {"operator": {}}})
    monkeypatch.setattr(demo, "_write_runtime_config", lambda _: str(temp_config))

    with pytest.raises(StartFailure):
        demo.asyncio.run(demo._run(dry_run=False))
