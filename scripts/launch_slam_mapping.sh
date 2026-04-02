#!/bin/bash
# ============================================================================
# SLAM 实时建图一键启动（Isaac Sim 需已启动并 Play）
#
# 两种模式：
#   手动模式（默认）：WASD 操控机器人探索
#   自动模式（--auto）：Wavefront Frontier 自主探索
#
# Ctrl+C 自动保存地图到 ~/mosaic_maps/house_map.yaml 并退出。
#
# 用法：
#   source /opt/ros/jazzy/setup.bash
#   bash scripts/launch_slam_mapping.sh          # 手动 WASD
#   bash scripts/launch_slam_mapping.sh --auto   # 自主探索
# ============================================================================
set -e

AUTO_MODE=false
if [ "$1" = "--auto" ]; then
    AUTO_MODE=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SLAM_PARAMS="${SCRIPT_DIR}/config/nav2/slam_toolbox_params.yaml"
RVIZ_CONFIG="${SCRIPT_DIR}/config/nav2/slam_rviz.rviz"
MAP_DIR="${HOME}/mosaic_maps"
PIDS=()
NAMES=()

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cleanup() {
    # 先屏蔽信号，防止重复触发
    trap '' SIGINT SIGTERM

    echo ""
    echo -e "${YELLOW}[保存] 正在保存地图（请等待）...${NC}"

    # map_saver 需要 SLAM Toolbox 的 /map 话题还在发布
    # 给 map_saver 足够时间，超时 10 秒
    timeout 10 ros2 run nav2_map_server map_saver_cli \
        -f "${MAP_DIR}/house_map" \
        --ros-args -p use_sim_time:=true 2>/dev/null \
        && echo -e "${GREEN}[地图] 已保存到 ${MAP_DIR}/house_map${NC}" \
        || echo -e "${RED}[地图] 保存失败，尝试备用方式...${NC}"

    # 如果失败，尝试用 SLAM Toolbox 的 serialize 服务保存
    if [ ! -f "${MAP_DIR}/house_map.pgm" ]; then
        ros2 service call /slam_toolbox/serialize_map slam_toolbox/srv/SerializePoseGraph \
            "{filename: '${MAP_DIR}/house_map_serialized'}" 2>/dev/null \
            && echo -e "${GREEN}[地图] 序列化保存成功${NC}" \
            || echo -e "${RED}[地图] 序列化也失败${NC}"
    fi

    echo -e "${YELLOW}[清理] 终止子进程...${NC}"
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
echo "  MOSAIC SLAM 实时建图"
echo "============================================"

mkdir -p "${MAP_DIR}"

echo -e "${YELLOW}[等待] Isaac Sim /tf...${NC}"
if ! timeout 10 ros2 topic echo /tf --once > /dev/null 2>&1; then
    echo -e "${RED}未检测到 /tf，请确认 Isaac Sim 已 Play${NC}"
    exit 1
fi
echo -e "${GREEN}[就绪]${NC}"
echo ""

# ── 1. Isaac ROS Bridge（/clock + /odom + 360° /scan）──
launch "Isaac ROS Bridge" "python3 ${SCRIPT_DIR}/scripts/isaac_ros_bridge.py"
sleep 3

# ── 2. SLAM Toolbox ──
launch "SLAM Toolbox" \
    "ros2 launch slam_toolbox online_async_launch.py \
        slam_params_file:=${SLAM_PARAMS} \
        use_sim_time:=true"
sleep 3

# ── 3. RViz2 ──
if [ -f "$RVIZ_CONFIG" ]; then
    launch "RViz2" "rviz2 -d ${RVIZ_CONFIG} --ros-args -p use_sim_time:=true"
else
    launch "RViz2" "rviz2 --ros-args -p use_sim_time:=true"
fi
sleep 1

# ── 摘要 ──
echo ""
echo "============================================"
echo -e "${GREEN}  SLAM 建图已启动${NC}"
echo "============================================"
for i in "${!PIDS[@]}"; do echo "  ${NAMES[$i]}: PID=${PIDS[$i]}"; done
echo ""
if [ "$AUTO_MODE" = true ]; then
    echo "  模式：自主探索（Wavefront Frontier）"
else
    echo "  模式：手动 WASD 遥控"
fi
echo "  Ctrl+C 保存地图并退出"
echo "============================================"
echo ""

# ── 4. 探索模式 ──
if [ "$AUTO_MODE" = true ]; then
    # 自主探索需要 Nav2 导航栈（只启动 navigation，不启动 localization）
    NAV2_PARAMS="${SCRIPT_DIR}/config/nav2/nav2_params.yaml"
    echo -e "${GREEN}[启动] Nav2 Navigation${NC}"
    launch "Nav2" \
        "ros2 launch nav2_bringup navigation_launch.py \
            use_sim_time:=true \
            params_file:=${NAV2_PARAMS}"
    sleep 8
    # 自主探索（前台）
    python3 "${SCRIPT_DIR}/scripts/auto_explore.py"
else
    # 手动 WASD 遥控（前台）
    python3 "${SCRIPT_DIR}/scripts/wasd_teleop.py"
fi
