from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import yaml

from mosaic.gateway.server import GatewayServer

READY_MESSAGE = "Human-surrogate ARIA memory demo is ready."
CONFIG_PATH = "config/demo/human_surrogate_memory.yaml"
OBSERVATION_FRAMES_DIR = "config/demo/observation_frames"


def _load_demo_config() -> dict[str, Any]:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _print_startup_info(demo_config: dict[str, Any]) -> None:
    demo = demo_config.get("demo", {})
    environment = demo.get("environment", {})
    operator = demo.get("operator", {})
    required_views = operator.get("required_views", [])
    print(READY_MESSAGE)
    print(f"Environment: {environment}")
    print(f"Operator required views: {required_views}")
    print(
        f"Observation frame storage: {Path(OBSERVATION_FRAMES_DIR).as_posix()}"
    )
    print("Stop the demo with Ctrl+C.")


async def _run(dry_run: bool) -> None:
    demo_config = _load_demo_config()
    _print_startup_info(demo_config)

    if dry_run:
        return

    server = GatewayServer(config_path="config/mosaic.yaml")
    try:
        await server.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            raise
    finally:
        await server.stop()


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
