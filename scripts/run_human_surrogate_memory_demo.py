from __future__ import annotations

import argparse
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

from mosaic.gateway.server import GatewayServer

READY_MESSAGE = "Human-surrogate ARIA memory demo is ready."
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config/demo/human_surrogate_memory.yaml"
OBSERVATION_FRAMES_DISPLAY = "config/demo/observation_frames"
BASE_MOSAIC_CONFIG = REPO_ROOT / "config/mosaic.yaml"
HUMAN_PROXY_HOST = "127.0.0.1"
HUMAN_PROXY_PORT = 8876
OPERATOR_CONSOLE_URL = f"http://{HUMAN_PROXY_HOST}:{HUMAN_PROXY_PORT}"


def _load_demo_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        demo_config = yaml.safe_load(f)
    if not isinstance(demo_config, dict):
        raise ValueError(
            "Demo config must be a mapping. Check config/demo/human_surrogate_memory.yaml."
        )
    return demo_config


def _print_startup_info(demo_config: dict[str, Any]) -> None:
    demo = demo_config.get("demo", {})
    environment = demo.get("environment", {})
    operator = demo.get("operator", {})
    required_views = operator.get("required_views", [])
    timeout_s = operator.get("timeout_s", 180)
    print(READY_MESSAGE)
    print(f"Environment: {environment}")
    print(f"Operator required views: {required_views}")
    print(f"Observation frame storage: {OBSERVATION_FRAMES_DISPLAY}")
    print(
        "Runtime config: human_proxy enabled in runtime config "
        f"(timeout_s={timeout_s}, host={HUMAN_PROXY_HOST}, port={HUMAN_PROXY_PORT})"
    )
    print(f"Operator console: {OPERATOR_CONSOLE_URL}")
    print("Stop the demo with Ctrl+C.")


def _write_runtime_config(demo_config: dict[str, Any]) -> str:
    with open(BASE_MOSAIC_CONFIG, "r", encoding="utf-8") as f:
        runtime_config = yaml.safe_load(f) or {}

    demo = demo_config.get("demo", {})
    operator = demo.get("operator", {})
    timeout_s = operator.get("timeout_s", 180)

    human_proxy_cfg = runtime_config.get("human_proxy", {}) or {}
    human_proxy_cfg["enabled"] = True
    human_proxy_cfg["host"] = HUMAN_PROXY_HOST
    human_proxy_cfg["port"] = HUMAN_PROXY_PORT
    human_proxy_cfg["timeout_s"] = timeout_s
    runtime_config["human_proxy"] = human_proxy_cfg

    temp_config = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yaml",
        delete=False,
    )
    try:
        yaml.safe_dump(runtime_config, temp_config, sort_keys=False)
        temp_config.flush()
    finally:
        temp_config.close()

    return temp_config.name


async def _run(dry_run: bool) -> None:
    demo_config = _load_demo_config()
    _print_startup_info(demo_config)

    if dry_run:
        return

    runtime_config_path = _write_runtime_config(demo_config)
    start_error: Exception | None = None
    stop_error: Exception | None = None
    try:
        server = GatewayServer(config_path=runtime_config_path)
        try:
            try:
                await server.start()
                await asyncio.Event().wait()
            except Exception as exc:
                start_error = exc
        finally:
            try:
                await server.stop()
            except Exception as exc:
                stop_error = exc
    finally:
        try:
            os.unlink(runtime_config_path)
        except OSError:
            pass
        if start_error:
            raise start_error
        if stop_error:
            raise stop_error


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the human-surrogate ARIA memory demo.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load config and print startup info without starting the server.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(_run(args.dry_run))


if __name__ == "__main__":
    main()
