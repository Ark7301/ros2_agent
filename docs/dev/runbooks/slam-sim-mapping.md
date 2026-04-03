- title: SLAM Simulation Mapping Runbook
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, dev, runbook, slam

# Isaac Sim 仿真导航操作指南

## 前置条件

- Isaac Sim 5.1（`~/env_isaacsim`）
- ROS2 Jazzy（`/opt/ros/jazzy`）

```bash
sudo apt install ros-jazzy-nav2-bringup ros-jazzy-pointcloud-to-laserscan
```

## 一、启动 Isaac Sim

```bash
source ~/env_isaacsim/bin/activate
export ROS_DISTRO=jazzy
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:~/env_isaacsim/lib/python3.11/site-packages/isaacsim/exts/isaacsim.ros2.bridge/jazzy/lib
python3 scripts/launch_isaac_sim.py
```

1. `Create → ROS 2 Assets → Nova Carter` 添加机器人
2. 放到场景中合适位置
3. 点击 Play ▶

## 二、SLAM 实时建图

在另一个终端：

```bash
source /opt/ros/jazzy/setup.bash

# 手动建图（WASD 遥控）
bash scripts/launch_slam_mapping.sh

# 或：自主探索建图（Wavefront Frontier 自动导航）
bash scripts/launch_slam_mapping.sh --auto
```

手动模式用 WASD 操控机器人。自动模式机器人会自主寻找未探索区域并导航过去。

按 Ctrl+C 自动保存地图到 `~/mosaic_maps/house_map.yaml`。

### 自主探索建图（可选）

手动遥控之外，也可以用 Wavefront Frontier 自主探索：

```bash
python3 scripts/auto_explore.py
```

脚本通过 TF（map→base_link）获取机器人位置，自动波前扩散寻找 frontier 并导航过去，直到没有 frontier。

## 三、一键启动导航（使用已建好的地图）

确保 Isaac Sim 已启动并 Play（同第一步），在另一个终端：

```bash
source /opt/ros/jazzy/setup.bash
bash scripts/launch_nav2_sim.sh
```

自动启动：Isaac ROS Bridge → Nav2 → AMCL 全局定位 → RViz2

AMCL 会自动定位（粒子均匀撒在地图上，通过 scan 匹配收敛）。机器人稍微移动可加速收敛。

## 架构

`isaac_ros_bridge.py` (v9) 统一桥接 Isaac Sim → Nav2：
- `/tf` → 提取仿真时间戳 → `/clock`
- `/chassis/odom` → `/odom` + `odom→base_link` TF（强制修正 frame_id）
- `/front_3d_lidar/lidar_points` → 在 LiDAR frame 下累积多帧（6帧≈360°）→ `/scan`
- LiDAR 每帧只覆盖 ~60°，在 `front_3d_lidar` frame 下直接累积（硬件内部已做旋转补偿）
- 不在 base_link 下累积，避免机器人运动导致畸变
- scan frame = `base_link`，累积后直接在 base_link 坐标系下发布
- 不再需要额外的 `base_link→front_3d_lidar` TF 变换

Nav2 使用 `use_sim_time:=true`，所有数据保持 Isaac Sim 原始仿真时间戳。

## 故障排查

### Frame [map] does not exist
- AMCL 未定位。确认 `/clock`、`/odom`、`/scan` 有数据
- 手动触发全局定位：`ros2 service call /reinitialize_global_localization std_srvs/srv/Empty {}`

### Failed to make progress
- 机器人没有移动反馈。确认 `/chassis/odom` 有数据：`ros2 topic hz /chassis/odom`

### 强制清理进程
```bash
pkill -9 -f "nav2\|amcl\|map_server\|controller_server\|planner_server\|bt_navigator\|pointcloud_to_laserscan\|isaac_ros_bridge\|rviz2\|component_container"
```
