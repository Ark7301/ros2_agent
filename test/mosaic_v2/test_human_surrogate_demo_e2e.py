from pathlib import Path


def test_demo_assets_exist() -> None:
    assert Path("config/demo/human_surrogate_memory.yaml").exists()
    assert Path("scripts/run_human_surrogate_memory_demo.py").exists()
    assert Path("docs/dev/runbooks/human-surrogate-memory-demo.md").exists()
