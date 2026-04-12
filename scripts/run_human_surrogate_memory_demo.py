from __future__ import annotations

import asyncio
import yaml

from mosaic.gateway.server import GatewayServer


async def _run() -> None:
    with open("config/demo/human_surrogate_memory.yaml", "r", encoding="utf-8") as f:
        demo_config = yaml.safe_load(f)

    server = GatewayServer(config_path="config/mosaic.yaml")
    try:
        await server.start()
        print("Human-surrogate ARIA memory demo is ready.")
        print(demo_config["demo"]["environment"])
    finally:
        await server.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
