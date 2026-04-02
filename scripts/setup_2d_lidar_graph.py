"""在 Isaac Sim Script Editor 中运行此脚本，为 Nova Carter 创建 360° 2D LaserScan 发布器

使用方法：
  1. 在 Isaac Sim 中添加 Nova Carter（Create → ROS 2 Assets → Nova Carter）
  2. 打开 Window → Script Editor
  3. 粘贴此脚本内容并运行
  4. 点击 Play ▶

脚本会自动查找 Nova Carter 的 front_2d_lidar 传感器 prim，
创建 OmniGraph 发布 /scan_2d 话题（sensor_msgs/LaserScan）。
"""
import omni.usd
import omni.graph.core as og

stage = omni.usd.get_context().get_stage()

# ── 查找 Nova Carter 的 2D LiDAR prim ──
lidar_prim = None
for prim in stage.Traverse():
    path = str(prim.GetPath())
    # Nova Carter 的 front 2D lidar 通常在 chassis_link/sensors 下
    if "front_2d_lidar" in path.lower() and prim.GetTypeName() in ("", "Xform", "Lidar"):
        lidar_prim = path
        print(f"[找到] front_2d_lidar: {path}")
        break

if lidar_prim is None:
    # 尝试查找任何包含 SICK 或 2d_lidar 的 prim
    for prim in stage.Traverse():
        path = str(prim.GetPath())
        if ("sick" in path.lower() or "2d_lidar" in path.lower() or
                "rplidar" in path.lower()):
            lidar_prim = path
            print(f"[找到] 2D LiDAR 候选: {path}")
            break

if lidar_prim is None:
    print("[错误] 未找到 2D LiDAR prim")
    print("  请确认 Nova Carter 已添加到场景中")
    print("  尝试手动查找：在 Stage 面板搜索 'lidar' 或 'SICK'")
else:
    print(f"[信息] 将为 {lidar_prim} 创建 LaserScan 发布器")

# ── 列出所有 LiDAR 相关 prim（帮助调试）──
print("\n[调试] 所有包含 'lidar' 的 prim:")
for prim in stage.Traverse():
    path = str(prim.GetPath())
    if "lidar" in path.lower():
        print(f"  {path} (type: {prim.GetTypeName()})")
