"""Isaac Sim 仿真启动脚本 — 加载家庭场景 + ROS2 Bridge

机器人需要通过 Isaac Sim GUI 手动添加：
  Create → ROS 2 Assets → Nova Carter

用法：
  source ~/env_isaacsim/bin/activate
  export ROS_DISTRO=jazzy
  export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
  export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:~/env_isaacsim/lib/python3.11/site-packages/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib
  python3 scripts/launch_isaac_sim.py [--headless]
"""
import argparse
import os
import sys

os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"
# 跳过 Nucleus 服务器检查，避免 omni.client.stat 阻塞
os.environ["OMNI_NUCLEUS_ALLOW_NO_VERIFICATION"] = "1"
os.environ.setdefault("ISAAC_NUCLEUS_PATH", "")

parser = argparse.ArgumentParser()
parser.add_argument("--headless", action="store_true", help="无 GUI 模式")
args = parser.parse_args()

from isaacsim import SimulationApp
simulation_app = SimulationApp({"headless": args.headless})

import omni.kit.app
import omni.usd
from isaacsim.core.utils.stage import add_reference_to_stage
from pxr import UsdGeom, Gf

print("=" * 50)
print("  MOSAIC Isaac Sim 仿真启动")
print("=" * 50)

# ── 1. 加载家庭场景 ──
scene_path = os.path.expanduser(
    "~/isaac_sim_assets/InteriorAgent/kujiale_0021/kujiale_0021.usda"
)
if not os.path.exists(scene_path):
    print(f"[错误] 场景文件不存在: {scene_path}")
    simulation_app.close()
    sys.exit(1)

add_reference_to_stage(usd_path=scene_path, prim_path="/World/Environment")
print(f"[场景] 已加载: {scene_path}")

# ── 2. 启用 ROS2 Bridge ──
try:
    ext_manager = omni.kit.app.get_app().get_extension_manager()
    ext_manager.set_extension_enabled_immediate("isaacsim.ros2.bridge", True)
    print("[ROS2] Bridge 已启用")
except Exception as e:
    print(f"[ROS2] Bridge 启用失败: {e}")

# ── 2.5 创建 /clock 发布器（OmniGraph）──
# 注意：/clock 由外部 sim_clock_bridge.py 从 /tf 提取时间戳发布
# 不再在 Isaac Sim 内部创建 ClockGraph，避免两个 /clock 源冲突导致 time jump
# 如果需要 Isaac Sim 内部发布 /clock，注释掉 sim_clock_bridge.py 并取消下面的注释
#
# try:
#     import omni.graph.core as og
#     keys = og.Controller.Keys
#     og.Controller.edit(
#         {"graph_path": "/World/ClockGraph", "evaluator_name": "execution"},
#         {
#             keys.CREATE_NODES: [
#                 ("OnPlaybackTick", "omni.graph.action.OnPlaybackTick"),
#                 ("SimTime", "isaacsim.core.nodes.IsaacReadSimulationTime"),
#                 ("PublishClock", "isaacsim.ros2.bridge.ROS2PublishClock"),
#             ],
#             keys.CONNECT: [
#                 ("OnPlaybackTick.outputs:tick", "SimTime.inputs:execIn"),
#                 ("SimTime.outputs:execOut", "PublishClock.inputs:execIn"),
#                 ("SimTime.outputs:simulationTime", "PublishClock.inputs:timeStamp"),
#             ],
#         },
#     )
#     print("[ROS2] /clock 发布器已创建（含仿真时间）")
# except Exception as e:
#     print(f"[ROS2] /clock 发布器创建失败: {e}")
print("[ROS2] /clock 由外部 sim_clock_bridge.py 提供")

# ── 3. 提示用户添加机器人 ──
print("")
print("=" * 50)
print("  请在 Isaac Sim GUI 中添加 Nova Carter ROS:")
print("  Create → ROS 2 Assets → Nova Carter")
print("  然后点击 Play ▶ 启动仿真")
print("=" * 50)
print("")

# ── 4. 禁用 Nucleus 资产路径查找（避免 omni.client 阻塞）──
try:
    import carb.settings
    settings = carb.settings.get_settings()
    # 禁止 ROS2 Bridge 自动创建 OG shortcut 资产（触发 Nucleus 连接）
    settings.set("/exts/isaacsim.ros2.bridge/disableOGShortcuts", True)
    print("[配置] 已禁用 ROS2 Bridge OG Shortcuts（避免 Nucleus 阻塞）")
except Exception as e:
    print(f"[配置] 设置 carb settings 失败（非致命）: {e}")

# ── 5. 创建 World 并启动仿真 ──
from isaacsim.core.api import World
world = World(stage_units_in_meters=1.0)

# ── 6. 主循环 ──
try:
    while simulation_app.is_running():
        world.step(render=not args.headless)
except KeyboardInterrupt:
    print("\n[仿真] 已停止")
finally:
    simulation_app.close()
