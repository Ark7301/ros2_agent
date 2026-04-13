from pathlib import Path


def test_demo_assets_exist() -> None:
    assert Path("config/demo/human_surrogate_memory.yaml").exists()
    assert Path("config/demo/observation_frames/README.md").exists()
    assert Path("scripts/run_human_surrogate_memory_demo.py").exists()
    assert Path("docs/dev/runbooks/human-surrogate-memory-demo.md").exists()

    dev_readme = Path("docs/dev/README.md").read_text(encoding="utf-8")
    assert "runbooks/human-surrogate-memory-demo.md" in dev_readme

    runbook = Path("docs/dev/runbooks/human-surrogate-memory-demo.md").read_text(
        encoding="utf-8"
    )
    assert "Ctrl+C" in runbook
    assert "config/demo/observation_frames" in runbook
    assert "PYTHONPATH=. python3 scripts/run_human_surrogate_memory_demo.py" in runbook
