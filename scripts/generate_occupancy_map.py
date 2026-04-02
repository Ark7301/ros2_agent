"""从 Isaac Sim USD 场景生成 2D 占据栅格地图

分析场景 Mesh 顶点分布，自动确定地面高度和扫描范围，
将所有在扫描高度范围内的 Mesh 顶点投影到 2D 平面。

用法：
  source ~/env_isaacsim/bin/activate
  python3 scripts/generate_occupancy_map.py
"""
import argparse
import os
import sys
import numpy as np

os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

parser = argparse.ArgumentParser()
parser.add_argument("--scene", default="~/isaac_sim_assets/InteriorAgent/kujiale_0021/kujiale_0021.usda")
parser.add_argument("--output-dir", default="~/mosaic_maps")
parser.add_argument("--name", default="house_map")
parser.add_argument("--resolution", type=float, default=0.01)
parser.add_argument("--z-min", type=float, default=None, help="扫描最低高度，不指定则自动检测")
parser.add_argument("--z-max", type=float, default=None, help="扫描最高高度，不指定则自动检测")
parser.add_argument("--exclude", default="door", help="排除路径包含这些关键词的 Mesh（逗号分隔）")
args = parser.parse_args()

scene_path = os.path.expanduser(args.scene)
output_dir = os.path.expanduser(args.output_dir)
os.makedirs(output_dir, exist_ok=True)

if not os.path.exists(scene_path):
    print(f"错误：场景文件不存在 {scene_path}")
    sys.exit(1)

print("启动 Isaac Sim (headless)...")
from isaacsim import SimulationApp
sim = SimulationApp({"headless": True})

import omni.kit.app
import omni.usd
from pxr import UsdGeom, Gf, Usd
from isaacsim.core.utils.stage import add_reference_to_stage

print(f"加载场景: {scene_path}")
add_reference_to_stage(usd_path=scene_path, prim_path="/World/Environment")
app = omni.kit.app.get_app()
for _ in range(50):
    app.update()

stage = omni.usd.get_context().get_stage()

# 第一遍：收集所有世界坐标顶点，分析分布
print("分析场景顶点分布...")
xform_cache = UsdGeom.XformCache()
all_x, all_y, all_z = [], [], []

# 统计 prim 类型
prim_types = {}
for prim in stage.Traverse():
    t = prim.GetTypeName()
    prim_types[t] = prim_types.get(t, 0) + 1

print("  场景 Prim 类型统计:")
for t, c in sorted(prim_types.items(), key=lambda x: -x[1])[:15]:
    print(f"    {t}: {c}")

# 收集所有几何体的顶点（Mesh + Cube + Cylinder + Sphere + Capsule）
for prim in stage.Traverse():
    if prim.IsA(UsdGeom.Mesh):
        mesh = UsdGeom.Mesh(prim)
        pts = mesh.GetPointsAttr().Get()
        if pts is None or len(pts) == 0:
            continue
        xf = xform_cache.GetLocalToWorldTransform(prim)
        for pt in pts[::max(1, len(pts)//200)]:
            wp = xf.Transform(Gf.Vec3d(float(pt[0]), float(pt[1]), float(pt[2])))
            all_x.append(wp[0])
            all_y.append(wp[1])
            all_z.append(wp[2])
    elif prim.IsA(UsdGeom.Gprim):
        # Cube, Sphere, Cylinder 等基本几何体 — 用包围盒
        bbox = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render"])
        b = bbox.ComputeWorldBound(prim).ComputeAlignedRange()
        if not b.IsEmpty():
            bmin_p = b.GetMin()
            bmax_p = b.GetMax()
            # 采样包围盒的 8 个角点
            for dx in [0, 1]:
                for dy in [0, 1]:
                    for dz in [0, 1]:
                        x = bmin_p[0] + dx * (bmax_p[0] - bmin_p[0])
                        y = bmin_p[1] + dy * (bmax_p[1] - bmin_p[1])
                        z = bmin_p[2] + dz * (bmax_p[2] - bmin_p[2])
                        all_x.append(x)
                        all_y.append(y)
                        all_z.append(z)

all_x = np.array(all_x)
all_y = np.array(all_y)
all_z = np.array(all_z)

print(f"  采样点数: {len(all_x)}")
print(f"  X 范围: {all_x.min():.2f} ~ {all_x.max():.2f}")
print(f"  Y 范围: {all_y.min():.2f} ~ {all_y.max():.2f}")
print(f"  Z 范围: {all_z.min():.2f} ~ {all_z.max():.2f}")

# 分析 Z 分布，找到地面高度（Z 值最密集的区域）
z_hist, z_edges = np.histogram(all_z, bins=100)
z_centers = (z_edges[:-1] + z_edges[1:]) / 2
floor_z = z_centers[np.argmax(z_hist)]
print(f"  推测地面高度: Z = {floor_z:.2f}")

# 扫描高度：手动指定或自动检测
if args.z_min is not None and args.z_max is not None:
    scan_z_min = args.z_min
    scan_z_max = args.z_max
    print(f"  使用手动指定高度: Z = {scan_z_min:.2f} ~ {scan_z_max:.2f}")
else:
    scan_z_min = floor_z + 0.1
    scan_z_max = floor_z + 2.0
    print(f"  自动扫描高度范围: Z = {scan_z_min:.2f} ~ {scan_z_max:.2f}")

# 排除关键词列表
exclude_keywords = [kw.strip().lower() for kw in args.exclude.split(",") if kw.strip()]
print(f"  排除 Mesh 关键词: {exclude_keywords}")

# 第二遍：用三角形光栅化（不是顶点投影），确保薄墙壁也能检测到
print("生成占据栅格（三角形光栅化）...")
res = args.resolution
margin = 1.0

mask = (all_z >= scan_z_min) & (all_z <= scan_z_max)
if mask.sum() == 0:
    scan_z_min = floor_z
    scan_z_max = floor_z + 3.0
    mask = (all_z >= scan_z_min) & (all_z <= scan_z_max)

valid_x = all_x[mask]
valid_y = all_y[mask]
x_min = valid_x.min() - margin
x_max = valid_x.max() + margin
y_min = valid_y.min() - margin
y_max = valid_y.max() + margin

w = int((x_max - x_min) / res)
h = int((y_max - y_min) / res)
print(f"  地图范围: X=[{x_min:.1f},{x_max:.1f}] Y=[{y_min:.1f},{y_max:.1f}]")
print(f"  地图尺寸: {w} x {h} 像素")

grid = np.full((h, w), 254, dtype=np.uint8)


def rasterize_line(x0, y0, x1, y1):
    """Bresenham 直线光栅化，返回所有经过的像素坐标"""
    pixels = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy
    while True:
        pixels.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy
    return pixels


xform_cache2 = UsdGeom.XformCache()
mesh_count = 0
tri_count = 0
gprim_count = 0

for prim in stage.Traverse():
    if prim.IsA(UsdGeom.Mesh):
        # 排除门等可通行物体
        prim_path_lower = str(prim.GetPath()).lower()
        if any(kw in prim_path_lower for kw in exclude_keywords):
            continue

        mesh = UsdGeom.Mesh(prim)
        pts = mesh.GetPointsAttr().Get()
        indices = mesh.GetFaceVertexIndicesAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        if pts is None or indices is None or counts is None:
            continue

        xf = xform_cache2.GetLocalToWorldTransform(prim)
        mesh_count += 1

        world_pts = []
        for pt in pts:
            wp = xf.Transform(Gf.Vec3d(float(pt[0]), float(pt[1]), float(pt[2])))
            world_pts.append((wp[0], wp[1], wp[2]))

        idx = 0
        for fc in counts:
            face_verts = []
            has_valid_z = False
            for i in range(fc):
                vi = indices[idx + i]
                if vi < len(world_pts):
                    wx, wy, wz = world_pts[vi]
                    # 面的任一顶点在高度范围内，或面跨越高度范围
                    if scan_z_min <= wz <= scan_z_max:
                        has_valid_z = True
                    face_verts.append((wx, wy, wz))

            # 也检查面是否跨越扫描高度（底部在下方，顶部在上方）
            if not has_valid_z and len(face_verts) >= 2:
                z_vals = [v[2] for v in face_verts]
                if min(z_vals) <= scan_z_max and max(z_vals) >= scan_z_min:
                    has_valid_z = True

            if has_valid_z and len(face_verts) >= 2:
                tri_count += 1
                for i in range(len(face_verts)):
                    j = (i + 1) % len(face_verts)
                    ax, ay, _ = face_verts[i]
                    bx, by, _ = face_verts[j]
                    px0 = int((ax - x_min) / res)
                    py0 = int((ay - y_min) / res)
                    px1 = int((bx - x_min) / res)
                    py1 = int((by - y_min) / res)
                    for px, py in rasterize_line(px0, py0, px1, py1):
                        if 0 <= px < w and 0 <= py < h:
                            grid[h - 1 - py, px] = 0
            idx += fc

    elif prim.IsA(UsdGeom.Gprim):
        # 非 Mesh 几何体（Cube 等）— 用包围盒边框光栅化
        from pxr import Usd as _Usd
        bbox = UsdGeom.BBoxCache(_Usd.TimeCode.Default(), ["default", "render"])
        b = bbox.ComputeWorldBound(prim).ComputeAlignedRange()
        if b.IsEmpty():
            continue
        bmin_p = b.GetMin()
        bmax_p = b.GetMax()
        # 检查高度范围
        if bmax_p[2] < scan_z_min or bmin_p[2] > scan_z_max:
            continue
        gprim_count += 1
        # 光栅化包围盒的 4 条水平边
        corners = [
            (bmin_p[0], bmin_p[1]), (bmax_p[0], bmin_p[1]),
            (bmax_p[0], bmax_p[1]), (bmin_p[0], bmax_p[1]),
        ]
        for i in range(4):
            j = (i + 1) % 4
            px0 = int((corners[i][0] - x_min) / res)
            py0 = int((corners[i][1] - y_min) / res)
            px1 = int((corners[j][0] - x_min) / res)
            py1 = int((corners[j][1] - y_min) / res)
            for px, py in rasterize_line(px0, py0, px1, py1):
                if 0 <= px < w and 0 <= py < h:
                    grid[h - 1 - py, px] = 0

print(f"  Mesh: {mesh_count}, 面: {tri_count}, Gprim: {gprim_count}, 占据像素: {np.sum(grid==0)}")

# 膨胀处理：让墙壁线条更粗（1 像素太细看不清）
from scipy.ndimage import binary_dilation
occ_mask = (grid == 0)
dilated = binary_dilation(occ_mask, iterations=2)
grid[dilated] = 0

# 保存 PGM
pgm_path = os.path.join(output_dir, f"{args.name}.pgm")
with open(pgm_path, "wb") as f:
    f.write(f"P5\n{w} {h}\n255\n".encode())
    f.write(grid.tobytes())
print(f"已保存: {pgm_path}")

# 保存 YAML
yaml_path = os.path.join(output_dir, f"{args.name}.yaml")
with open(yaml_path, "w") as f:
    f.write(f"image: {args.name}.pgm\n")
    f.write(f"resolution: {res}\n")
    f.write(f"origin: [{x_min:.4f}, {y_min:.4f}, 0.0]\n")
    f.write(f"negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\n")
print(f"已保存: {yaml_path}")

# 同时保存 PNG 方便查看
try:
    from PIL import Image
    img = Image.fromarray(grid)
    png_path = os.path.join(output_dir, f"{args.name}.png")
    img.save(png_path)
    print(f"已保存: {png_path}")
except ImportError:
    pass

print(f"\n地图生成完成！尺寸 {w}x{h}, 分辨率 {res}m/px")
sim.close()
