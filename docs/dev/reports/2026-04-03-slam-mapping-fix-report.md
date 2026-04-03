- title: SLAM Mapping Fix Report
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, dev, report, slam

# SLAM 建图问题修复报告

## 问题现象
1. 机器人旋转时地图大幅偏移/跳飞
2. 地图只在一侧生成（180x61 畸形比例），机器人不在地图中心
3. 自动探索时频繁碰撞障碍物
4. 狭窄通道行进极慢

## 根因定位

### 地图偏移/只在一侧
Isaac Sim Nova Carter 的 RTX LiDAR 是 360° 旋转式，每帧只输出 ~60° 扇区（~61 rays）。旧方案在 `base_link` 坐标系下累积多帧，机器人旋转时各帧坐标系不同，累积后 scan 畸变。

同时 Isaac Sim 不发布 `base_link→front_3d_lidar` 的 `/tf_static`，SLAM 无法正确做坐标变换。

### 碰撞/窄通道慢
- costmap 膨胀半径 0.8m 过大，窄通道（~0.8m）被完全堵死
- collision_monitor 减速圆 0.6m 在窄通道两侧持续触发
- auto_explore frontier 选点离墙太近（检测半径仅 0.1m）

## 修复方案

### isaac_ros_bridge.py (v9)
- 在 `front_3d_lidar` frame 下累积 6 帧点云（LiDAR 内部已做旋转补偿，不受机器人运动影响）
- scan frame = `base_link`，累积后直接在 base_link 坐标系下发布
- odom 强制修正 frame_id 为 `odom→base_link`
- /scan QoS 改为 RELIABLE（兼容 SLAM Toolbox）
- LiDAR 盲区（1°~59°、-180°~-120°）保持 inf（unknown），不再填充 range_max，避免误标 free space

### nav2_params.yaml
- inflation_radius: 0.8→0.55m，cost_scaling_factor: 1.5→2.5
- MPPI CostCritic weight: 3.81→10.0
- collision_monitor: 去掉 0.6m 减速圆，保留 0.3m 紧急停车 + FootprintApproach

### auto_explore.py
- 墙壁检测半径 2→6 格，frontier 目标点回退 0.5m 安全距离
- 引入信息增益评分，优先选 unknown 区域大的 frontier

### slam_toolbox_params.yaml
- 适配 360° 累积 scan，minimum_travel_heading=0.15rad

## 涉及文件
- `scripts/isaac_ros_bridge.py`
- `scripts/auto_explore.py`
- `config/nav2/nav2_params.yaml`
- `config/nav2/slam_toolbox_params.yaml`
