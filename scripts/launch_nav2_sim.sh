#!/bin/bash
# ============================================================================
# Nav2 导航一键启动（Isaac Sim 需已启动并 Play）
#
# 方案：use_sim_time:=true，由 isaac_ros_bridge.py 统一提供：
#   - /clock（从 /tf 提取仿真时间）
#   - odom→base_link TF + /odom（Isaac Sim 不发布）
#   - 点云桥接（供 pointcloud_to_laserscan 转换）
#
# 前置：
#   - Isaac Sim 已 Play，Nova Carter 已添加
#   - sudo apt install ros-jazzy-nav2-bringup ros-jazzy-pointcloud-to-laserscan
#   - 已建图：~/mosaic_maps/house_map.yaml
#
# 用法：
#   source /opt/ros/jazzy/setup.bash
#   bash scripts/launch_nav2_sim.sh
# ============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAV2_PARAMS="${SCRIPT_DIR}/config/nav2/nav2_params.yaml"
RVIZ_CONFIG="${SCRIPT_DIR}/config/nav2/nav2_rviz.rviz"
MAP_FILE="${HOME}/mosaic_maps/house_map.yaml"
PIDS=()
NAMES=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
    echo ""
    echo -e "${YELLOW}[清理]${NC}"
    for i in "${!PIDS[@]}"; do
        kill -SIGTERM "${PIDS[$i]}" 2>/dev/null && echo "  停止 ${NAMES[$i]}"
    done
    sleep 2
    for pid in "${PIDS[@]}"; do kill -9 "$pid" 2>/dev/null; done
    echo -e "${GREEN}[完成]${NC}"
    exit 0
}
trap cleanup SIGINT SIGTERM

launch() {
    local n="$1"
    shift
    echo -e "${GREEN}[启动] ${n}${NC}"
    eval "$@" &
    PIDS+=("$!")
    NAMES+=("$n")
}

# ── 检查 ──
echo "============================================"
echo "  MOSAIC Nav2 导航"
echo "============================================"
[ ! -f "$MAP_FILE" ] && echo -e "${RED}地图不存在: ${MAP_FILE}${NC}" && exit 1
[ ! -f "$NAV2_PARAMS" ] && echo -e "${RED}参数不存在: ${NAV2_PARAMS}${NC}" && exit 1

echo -e "${YELLOW}[等待] Isaac Sim /tf...${NC}"
if ! timeout 10 ros2 topic echo /tf --once > /dev/null 2>&1; then
    echo -e "${RED}未检测到 /tf${NC}"; exit 1
fi
echo -e "${GREEN}[就绪]${NC}"
echo ""

# ── 1. Isaac ROS Bridge（/clock + /odom + 360° /scan）──
launch "Isaac ROS Bridge" "python3 ${SCRIPT_DIR}/scripts/isaac_ros_bridge.py"
sleep 3

# ── 2. Nav2 ──
launch "Nav2" \
    "ros2 launch nav2_bringup bringup_launch.py \
        use_sim_time:=true \
        map:=${MAP_FILE} \
        params_file:=${NAV2_PARAMS}"
sleep 8

# ── 3.5 触发 AMCL 全局定位（粒子均匀撒在地图上，自动收敛）──
echo -e "${YELLOW}[定位] 触发 AMCL 全局定位...${NC}"
ros2 service call /reinitialize_global_localization std_srvs/srv/Empty {} 2>/dev/null &
sleep 1

# ── 4. RViz2 ──
if [ -f "$RVIZ_CONFIG" ]; then
    launch "RViz2" "rviz2 -d ${RVIZ_CONFIG} --ros-args -p use_sim_time:=true"
else
    launch "RViz2" "rviz2 --ros-args -p use_sim_time:=true"
fi

# ── 摘要 ──
echo ""
echo "============================================"
echo -e "${GREEN}  已启动${NC}"
echo "============================================"
for i in "${!PIDS[@]}"; do echo "  ${NAMES[$i]}: PID=${PIDS[$i]}"; done
echo ""
echo "  RViz: 2D Pose Estimate 设置初始位姿"
echo "  Ctrl+C 停止"
echo "============================================"
wait
