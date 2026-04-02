# MOSAIC 仿真环境搭建指南 — NVIDIA Isaac Sim

> 目标：在 NVIDIA Isaac Sim 中验证 MOSAIC 场景图 + ARIA + TurnRunner 的完整管道。
> 机器人在光照真实的室内家庭环境中执行 LLM 规划的导航/操作任务，场景图实时更新。
> 仿真平台：NVIDIA Isaac Sim 5.1（开源，PhysX 5 GPU 加速，RTX 光线追踪）
> ROS2 发行版：Jazzy Jalisco（匹配 Ubuntu 24.04）

## TL;DR

- 仿真平台：Isaac Sim 5.1（pip 安装），机器人：Nova Carter，场景：InteriorAgent USD 数据集
- 桥接方式：Isaac Sim 进程内 ROS2 Bridge 发布传感器话题 → MOSAIC 独立进程通过 rclpy 对接 Nav2
- 分 5 个 Phase：导航管道 → 多步任务 → 异常重规划 → VLM 场景图 → VLA 端到端
- Phase 1 改动：NavigationCapability mock→Nav2、新增 ros2_bridge 节点、home.yaml 坐标对齐

---

## 一、为什么选择 NVIDIA Isaac Sim

### 1.1 与 Gazebo Classic 的本质差距

| 维度 | Gazebo Classic 11 | NVIDIA Isaac Sim 5.1 |
|------|-------------------|----------------------|
| 物理引擎 | ODE（CPU 单线程） | PhysX 5（GPU 并行加速） |
| 渲染质量 | OpenGL 光栅化 | RTX 光线追踪（光照真实） |
| 传感器仿真 | 简单模型 | GPU 加速 LiDAR/RGB-D/IMU |
| VLM 适配性 | 渲染质量不足以驱动 VLM | 光照真实渲染可直接输入 VLM |
| 场景格式 | SDF/URDF | USD（工业标准，可组合场景图） |
| 域随机化 | 需手动脚本 | 内置 Replicator 域随机化 |
| 生态方向 | 已停止维护（EOL） | NVIDIA 持续投入，开源 |
| ROS2 集成 | 原生 | ROS2 Bridge 扩展（Jazzy） |

### 1.2 Isaac Sim 对 MOSAIC 的关键价值

1. **光照真实渲染 → VLM 场景图构建**：RTX 渲染输出可直接送入 GPT-4V/开源 VLM，验证 SceneGraphBuilder 的 VLM 语义填充管道
2. **PhysX 5 GPU 物理 → 操作验证**：未来 ManipulationModule 的抓取/放置可在高精度物理中验证
3. **USD 场景格式 → 结构化环境**：USD 天然是层次化场景图，与 MOSAIC 的 Room→Furniture→Object 三层结构高度契合
4. **域随机化 → 鲁棒性**：Replicator 可自动变换光照/纹理/物体位置，测试 MOSAIC 在环境变化下的适应性
5. **Isaac Lab 演进路径 → VLA 训练**：后续可直接在 Isaac Lab 中训练 VLA 模型，与 MOSAIC 的 VLA Capability 预留对接


---

## 二、硬件要求

### 2.1 系统配置

| 项目 | 最低配置 | 推荐配置 | 理想配置 |
|------|----------|----------|----------|
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04/24.04 LTS | Ubuntu 22.04/24.04 LTS |
| CPU | Intel Core i7（7代） | Intel Core i9 / AMD Ryzen 9 | AMD Threadripper |
| RAM | 32 GB | 64 GB | 64 GB+ |
| GPU | RTX 2070（8GB VRAM） | RTX 3080/4070（12GB+ VRAM） | RTX 4090（24GB VRAM） |
| 存储 | 50 GB SSD | 100 GB NVMe SSD | 200 GB+ NVMe SSD |
| 驱动 | NVIDIA 535.129.03+ | 最新生产分支驱动 | 最新生产分支驱动 |

### 2.2 关键限制

- **必须有 RT Cores**：A100、H100 等计算卡不支持（无 RT Cores）
- **VRAM 是瓶颈**：8GB VRAM 只能运行简单场景；12GB+ 推荐用于多传感器仿真
- **容器仅支持 Linux**：Isaac Sim Docker 容器仅在 Linux 上运行
- **需要网络连接**：首次运行需下载 Isaac Sim 在线资产

### 2.3 硬件确认清单

```bash
# 检查 GPU 型号和 VRAM
nvidia-smi

# 检查驱动版本（需 535.129.03+）
nvidia-smi --query-gpu=driver_version --format=csv,noheader

# 检查是否有 RT Cores（RTX 系列均有）
nvidia-smi --query-gpu=name --format=csv,noheader
# 输出应包含 "RTX" 字样

# 运行 Isaac Sim 兼容性检查器（安装后可用）
# isaacsim compatibility_checker
```

> ⚠️ **请在开始搭建前确认你的 GPU 型号和 VRAM 大小**。如果 VRAM < 8GB 或 GPU 无 RT Cores，需要升级硬件或使用云 GPU 实例。


---

## 三、环境安装

### 3.1 前置条件

```bash
# 1. 确认 Python 3.11（Isaac Sim 5.1 要求）
python3.11 --version

# 如果未安装 Python 3.11
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev

# 2. 确认 ROS2 Jazzy 已安装（Ubuntu 24.04 对应 Jazzy）
ros2 --version

# 如果未安装 ROS2 Jazzy，参考官方文档：
# https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html

# 3. 确认 GLIBC 版本（需 2.35+）
ldd --version
# Ubuntu 22.04 默认 GLIBC 2.35，满足要求

# 4. 确认 NVIDIA 驱动
nvidia-smi
```

### 3.2 安装 Isaac Sim 5.1（pip 方式，推荐）

Isaac Sim 5.1 已开源，支持 pip 安装，这是最简洁的安装方式：

```bash
# 创建独立虚拟环境
python3.11 -m venv ~/env_isaacsim
source ~/env_isaacsim/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装完整 Isaac Sim（含所有扩展缓存）
pip install isaacsim[all,extscache]==5.1.0 \
  --extra-index-url https://pypi.nvidia.com

# 验证安装
python -c "import isaacsim; print('Isaac Sim 安装成功')"
```

### 3.3 接受 EULA

首次运行 Isaac Sim 时需要接受 NVIDIA Omniverse 许可协议：

```bash
# 方式一：环境变量（推荐，写入 bashrc 避免每次提示）
echo 'export OMNI_KIT_ACCEPT_EULA=YES' >> ~/.bashrc
source ~/.bashrc

# 方式二：Python 脚本中设置
# import os
# os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"
```

### 3.4 安装 ROS2 Bridge 依赖

Isaac Sim 的 ROS2 Bridge 需要在启动前 source ROS2 环境：

```bash
# 确保 ROS2 Jazzy 环境已 source
source /opt/ros/jazzy/setup.bash

# 安装 Nav2 + SLAM Toolbox（后续导航验证需要）
sudo apt install -y \
  ros-jazzy-navigation2 \
  ros-jazzy-nav2-bringup \
  ros-jazzy-slam-toolbox

# 将 ROS2 source 写入 bashrc（Isaac Sim 启动时需要）
echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc
```

### 3.5 验证 Isaac Sim 启动

```bash
# 激活虚拟环境
source ~/env_isaacsim/bin/activate

# 确保 ROS2 已 source
source /opt/ros/jazzy/setup.bash

# 启动 Isaac Sim GUI（首次启动需下载资产，可能较慢）
isaacsim
```

首次启动预期行为：
- 下载在线资产（需网络，可能需要几分钟）
- 打开 Isaac Sim 编辑器界面
- 左下角状态栏显示 "Ready"


---

## 四、仿真世界搭建

### 4.1 室内家庭环境方案选择

MOSAIC 需要一个多房间家庭环境来验证场景图驱动的导航和操作。以下是三种可选方案：

| 方案 | 来源 | 优点 | 缺点 | 推荐度 |
|------|------|------|------|--------|
| InteriorAgent USD 数据集 | HuggingFace spatialverse/InteriorAgent | 高质量室内场景，含 rooms.json 房间元数据，直接兼容 Isaac Sim | 需下载（~GB 级），部分场景可能过大 | ⭐⭐⭐ **首选** |
| Isaac Sim 内置环境资产 | NVIDIA 官方 | 开箱即用，物理属性完善 | 室内家庭场景有限，多为仓库/办公室 | ⭐⭐ |
| 自建 USD 场景 | Blender → USD 导出 | 完全匹配 home.yaml 配置 | 工作量大，需 3D 建模经验 | ⭐ 后备 |

### 4.2 方案 A：使用 InteriorAgent 数据集（推荐）

InteriorAgent 是专为 Isaac Sim 室内仿真设计的高质量 USD 资产集，包含：
- 多种户型的完整室内场景（客厅、厨房、卧室、卫生间等）
- MDL 材质系统（光照真实渲染）
- `rooms.json` 房间元数据（房间类型 + 多边形边界坐标）
- 兼容 Isaac Sim 4.2/4.5/5.x

```bash
# 下载 InteriorAgent 数据集（需安装 huggingface_hub）
pip install huggingface_hub

# 下载单个场景（选择一个适合的户型）
python -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='spatialverse/InteriorAgent',
    repo_type='dataset',
    local_dir='~/isaac_sim_assets/InteriorAgent',
    allow_patterns=['kujiale_0021/*'],  # 选择一个场景
)
"
```

InteriorAgent 场景结构：
```
kujiale_0021/
├── Materials/          # MDL 材质文件
│   ├── Textures/       # 纹理贴图
│   └── *.mdl           # 材质定义
├── Meshes/             # 网格几何体
├── kujiale_0021.usda   # 顶层 USD 场景文件（加载入口）
├── limpopo_golf_course_4k.hdr  # 环境光照 HDR
└── rooms.json          # 房间元数据（类型 + 多边形边界）
```

`rooms.json` 示例：
```json
{
    "room_type": "living_room",
    "polygon": [
        [-0.378, -6.553],
        [4.006, -6.553],
        [4.006, -4.860],
        [-0.378, -4.860]
    ]
}
```

> 这个 `rooms.json` 的房间多边形数据可以直接用于更新 `config/environments/home.yaml` 中的坐标。

### 4.3 方案 B：使用 Isaac Sim 内置资产

Isaac Sim 提供了一些内置环境，可通过 Nucleus 服务器访问：

```python
# 在 Isaac Sim Python 脚本中加载内置环境
import isaacsim
from isaacsim.core.utils.stage import add_reference_to_stage

# 加载 NVIDIA 提供的室内环境
# 路径格式：omniverse://localhost/NVIDIA/Assets/...
add_reference_to_stage(
    usd_path="omniverse://localhost/NVIDIA/Assets/Isaac/Environments/Simple_Room/simple_room.usd",
    prim_path="/World/Environment"
)
```

### 4.4 方案 C：自建 USD 场景

如果需要完全匹配 `home.yaml` 的房间布局，可以用 Blender 建模后导出 USD：

1. 在 Blender 中按 `home.yaml` 坐标建模（7 个房间 + 家具）
2. 安装 Blender USD 插件，导出为 `.usd` 格式
3. 在 Isaac Sim 中导入，添加物理属性（碰撞体、刚体）
4. 添加光照和材质

> 此方案工作量较大，建议在 Phase 1 使用 InteriorAgent 数据集，Phase 3+ 再考虑自建。


---

## 五、机器人模型选择

### 5.1 候选机器人对比

| 机器人 | 来源 | 传感器 | 操作臂 | Nav2 支持 | 推荐度 |
|--------|------|--------|--------|-----------|--------|
| Nova Carter | NVIDIA 官方 | 多目摄像头 + LiDAR + IMU | 无 | ✅ 官方教程 | ⭐⭐⭐ **首选** |
| Carter V2 | NVIDIA 官方 | 双目 + LiDAR | 无 | ✅ 官方教程 | ⭐⭐ |
| TurtleBot3 Waffle Pi | ROBOTIS | LiDAR + RGB 摄像头 | 无 | ✅ 社区支持 | ⭐⭐ |
| Jetbot | NVIDIA | 单目摄像头 | 无 | 有限 | ⭐ |

### 5.2 推荐：Nova Carter

Nova Carter 是 NVIDIA 官方的室内导航参考机器人，与 Isaac Sim 深度集成：

- **Isaac Perceptor 集成**：基于摄像头的 3D 感知栈，无需 LiDAR 也能导航
- **Nav2 官方教程**：NVIDIA 提供完整的 Isaac Sim + Nav2 导航教程
- **多传感器**：多目摄像头 + LiDAR + IMU，满足 MOSAIC 场景图构建的感知需求
- **USD 模型内置**：Isaac Sim 自带 Nova Carter USD 模型

Isaac Sim 内置的 ROS2 导航工作空间（`jazzy_ws`）包含：
- `carter_navigation`：Carter 导航参数和 launch 文件
- `iw_hub_navigation`：仓库导航示例
- `isaac_ros_navigation_goal`：导航目标发布

### 5.3 加载机器人到场景

```python
# 在 Isaac Sim standalone 脚本中加载 Nova Carter
import isaacsim
from isaacsim.core.utils.stage import add_reference_to_stage

# 加载 Nova Carter 机器人
add_reference_to_stage(
    usd_path="/Isaac/Robots/Carter/nova_carter.usd",
    prim_path="/World/Robot"
)

# 设置初始位置（对应 home.yaml 中 robot 的 at: living_room）
from pxr import UsdGeom, Gf
stage = omni.usd.get_context().get_stage()
robot_prim = stage.GetPrimAtPath("/World/Robot")
xform = UsdGeom.Xformable(robot_prim)
xform.ClearXformOpOrder()
xform.AddTranslateOp().Set(Gf.Vec3d(3.0, 2.0, 0.0))  # 客厅坐标
```

> 如果后续需要操作臂验证（ManipulationModule），可以切换为带操作臂的机器人模型（如 Franka + 移动底盘组合）。


---

## 六、ROS2 Bridge 配置

### 6.1 Isaac Sim ROS2 Bridge 架构

Isaac Sim 通过 `isaacsim.ros2.bridge` 扩展与 ROS2 通信。桥接层将 Isaac Sim 内部的传感器数据、关节状态等发布为 ROS2 话题，同时订阅 ROS2 的控制指令。

```
Isaac Sim 进程（Python 3.11 venv）
    │
    ├── isaacsim.ros2.bridge 扩展（进程内）
    │       ├── 发布：/scan, /odom, /camera/image_raw, /tf, /clock
    │       └── 订阅：/cmd_vel
    │
    ↕ ROS2 DDS 通信（跨进程）
    │
    ├── Nav2 导航栈（独立进程）
    │       ├── /navigate_to_pose（Action Server）
    │       └── /amcl_pose（定位结果）
    │
    └── MOSAIC Agent 核心（独立进程，系统 Python 3.10 + asyncio）
            ├── NavigationCapability → Nav2 Action Client（rclpy）
            ├── SensorBridge → /scan, /odom, /camera（rclpy）
            └── SceneGraphManager → 场景图更新
```

### 6.2 启用 ROS2 Bridge

在 Isaac Sim 中启用 ROS2 Bridge 有两种方式：

**方式一：GUI 中启用**
1. 启动 Isaac Sim（确保已 source ROS2）
2. 菜单 Window → Extensions
3. 搜索 `isaacsim.ros2.bridge`
4. 点击 Enable

**方式二：Standalone 脚本中启用**
```python
import isaacsim
from isaacsim.core.api import World

# 启用 ROS2 Bridge 扩展
import omni.kit.app
manager = omni.kit.app.get_app().get_extension_manager()
manager.set_extension_enabled_immediate("isaacsim.ros2.bridge", True)
```

### 6.3 配置传感器 ROS2 发布

通过 Action Graph 或 Python API 配置传感器数据发布到 ROS2 话题：

```python
# 配置 LiDAR 发布到 /scan
# 配置里程计发布到 /odom
# 配置摄像头发布到 /camera/image_raw
# 配置 TF 发布到 /tf
# 配置仿真时钟发布到 /clock
```

关键 ROS2 话题（与 MOSAIC 的对接点）：

| 话题 | 类型 | 方向 | MOSAIC 消费者 |
|------|------|------|---------------|
| `/scan` | `sensor_msgs/LaserScan` | Isaac Sim → ROS2 | SensorBridge → 障碍物检测 |
| `/odom` | `nav_msgs/Odometry` | Isaac Sim → ROS2 | SensorBridge → RobotState 位置更新 |
| `/camera/image_raw` | `sensor_msgs/Image` | Isaac Sim → ROS2 | SensorBridge → VLM 场景图构建 |
| `/cmd_vel` | `geometry_msgs/Twist` | ROS2 → Isaac Sim | Nav2 → 机器人运动控制 |
| `/tf` | `tf2_msgs/TFMessage` | Isaac Sim → ROS2 | Nav2 坐标变换 |
| `/clock` | `rosgraph_msgs/Clock` | Isaac Sim → ROS2 | 仿真时间同步 |
| `/navigate_to_pose` | Action (NavigateToPose) | MOSAIC → Nav2 | NavigationCapability 导航目标 |
| `/amcl_pose` | `PoseWithCovarianceStamped` | Nav2 → MOSAIC | NavigationCapability 定位结果 |

### 6.4 仿真时间同步

Isaac Sim 使用自己的物理时钟，所有 ROS2 节点必须使用仿真时间：

```bash
# 启动 Nav2 时指定使用仿真时间
ros2 launch nav2_bringup bringup_launch.py use_sim_time:=True
```

在 MOSAIC 的 ROS2 Bridge 节点中也需要设置：
```python
import rclpy
from rclpy.parameter import Parameter

node = rclpy.create_node('mosaic_bridge')
node.set_parameters([Parameter('use_sim_time', Parameter.Type.BOOL, True)])
```


---

## 七、MOSAIC 与 Isaac Sim 的桥接架构

### 7.1 整体架构

MOSAIC 的设计原则：ROS2 完全封装在 CapabilityModule 内部，Agent 核心不接触 ROS2。Isaac Sim 作为物理仿真后端，通过 ROS2 Bridge 与 MOSAIC 的 Capability 层通信。

```
┌─────────────────────────────────────────────────────────┐
│  MOSAIC Agent 核心（Python asyncio 事件循环）            │
│                                                         │
│  TurnRunner ─→ SceneGraphManager ─→ PlanVerifier        │
│      │                                                  │
│      ↓                                                  │
│  CapabilityRegistry                                     │
│      ├── NavigationCapability ──→ Nav2 Action Client    │
│      ├── ManipulationCapability ──→ MoveIt2（后续）     │
│      └── SensorBridge ──→ ROS2 Topic Subscribers        │
│                                                         │
├─────────────────── ROS2 DDS 通信层 ─────────────────────┤
│                                                         │
│  Nav2 导航栈                                            │
│      ├── AMCL 定位                                      │
│      ├── 路径规划（NavFn / Smac）                       │
│      └── 局部避障（DWB / MPPI）                         │
│                                                         │
├─────────────────── ROS2 Bridge ─────────────────────────┤
│                                                         │
│  NVIDIA Isaac Sim 5.1                                   │
│      ├── PhysX 5 物理引擎（GPU 加速）                   │
│      ├── RTX 渲染器（光线追踪）                         │
│      ├── 传感器仿真（LiDAR / RGB-D / IMU）              │
│      └── USD 场景（InteriorAgent 家庭环境）             │
└─────────────────────────────────────────────────────────┘
```

### 7.2 asyncio + rclpy 桥接模式

MOSAIC 使用 Python asyncio 事件循环，rclpy 使用自己的回调机制。需要在独立线程中运行 rclpy spin。

核心设计（将实现在 `mosaic/nodes/ros2_bridge.py`）：

```python
class ROS2BridgeManager:
    """ROS2 桥接管理器 — 在独立线程中运行 rclpy

    关键接口：
    - start(): 初始化 rclpy + MultiThreadedExecutor，启动 daemon spin 线程
    - register_node(node): 注册 ROS2 节点到执行器
    - shutdown(): 关闭 rclpy

    桥接原理：rclpy 回调在 spin 线程中触发，
    通过 loop.call_soon_threadsafe() 将结果投递到 asyncio 事件循环。
    """
```

### 7.3 NavigationCapability 改造要点

当前 `plugins/capabilities/navigation/__init__.py` 是 mock 实现，需要改造为 ROS2 Nav2 版本：

```python
# 改造核心逻辑（关键接口不变，内部实现替换）
class NavigationCapability:
    """导航能力插件 — 对接 Nav2 NavigateToPose Action

    设计原则：
    - 对外接口不变（execute/cancel/health_check）
    - 内部通过 ROS2 Action Client 与 Nav2 通信
    - 坐标解析通过 SpatialQueryProvider 抽象接口
    """

    def __init__(self, ros_node, spatial_provider) -> None:
        # Nav2 Action Client
        self._nav_client = ActionClient(
            ros_node, NavigateToPose, 'navigate_to_pose'
        )
        # 空间查询（从场景图解析语义地名到坐标）
        self._spatial = spatial_provider

    async def execute(self, intent, params, ctx):
        if intent == "navigate_to":
            target = params["target"]
            # 通过 SpatialQueryProvider 解析目标坐标
            coord = self._spatial.resolve_location(target)
            # 构造 Nav2 目标
            goal = NavigateToPose.Goal()
            goal.pose.header.frame_id = "map"
            goal.pose.pose.position.x = coord[0]
            goal.pose.pose.position.y = coord[1]
            goal.pose.pose.orientation.w = 1.0
            # 发送目标并等待结果
            goal_handle = await self._send_goal(goal)
            result = await goal_handle.get_result_async()
            return ExecutionResult(
                success=(result.status == GoalStatus.STATUS_SUCCEEDED),
                data={"target": target, "final_pose": ...},
                message=f"已导航到 {target}",
            )
```

关键改造点：
1. `_execute_navigate_to` 从返回 mock 结果改为调用 Nav2 Action
2. 坐标解析通过 `SpatialQueryProvider.resolve_location()` 而非硬编码
3. 异步等待通过 `asyncio.Future` 桥接 rclpy 回调
4. 取消操作通过 `goal_handle.cancel_goal_async()` 实现


---

## 八、仿真世界与场景图的映射

### 8.1 坐标系对齐

Isaac Sim 使用右手坐标系（Z 轴向上），与 ROS2 的 REP-103 标准一致：
- X 轴：前方
- Y 轴：左方
- Z 轴：上方

`config/environments/home.yaml` 中的 position 字段需要与 Isaac Sim 世界坐标对齐。

> ⚠️ **坐标对齐注意事项**：
> - home.yaml 当前坐标是手动设定的相对坐标（单位：米），原点在环境左下角附近
> - InteriorAgent rooms.json 的坐标也是米制 2D 坐标，但原点和朝向可能不同
> - 对齐步骤：①加载 USD 场景到 Isaac Sim → ②读取 rooms.json 多边形 → ③在 Isaac Sim 中确认坐标原点位置 → ④用 rooms.json 中心点直接替换 home.yaml 的 position 字段
> - InteriorAgent 的 rooms.json 只有 X-Y 平面坐标，Z 轴高度默认为 0（地面层），与 Nav2 的 2D 导航一致
> - 家具坐标需要从 USD 场景的 Prim 层次结构中提取（通过 `UsdGeom.Xformable` 读取 translate）

### 8.2 InteriorAgent rooms.json → home.yaml 映射

InteriorAgent 的 `rooms.json` 提供了每个房间的多边形边界，可以自动计算中心点坐标：

```python
# 工具脚本：从 rooms.json 生成 home.yaml 坐标
from shapely.geometry import Polygon
import json
import yaml

with open("rooms.json", "r") as f:
    rooms = json.load(f)

room_centers = {}
for room in rooms:
    poly = Polygon(room["polygon"])
    centroid = poly.centroid
    room_centers[room["room_type"]] = [
        round(centroid.x, 2),
        round(centroid.y, 2),
    ]
    print(f"{room['room_type']}: center=({centroid.x:.2f}, {centroid.y:.2f}), area={poly.area:.2f}m²")

# 输出示例：
# living_room: center=(1.81, -5.71), area=19.32m²
# kitchen: center=(5.23, -3.45), area=12.67m²
# bedroom: center=(-2.10, -1.89), area=15.44m²
```

### 8.3 home.yaml 坐标更新流程

1. 选择 InteriorAgent 场景，加载到 Isaac Sim
2. 解析 `rooms.json` 获取房间中心坐标
3. 更新 `config/environments/home.yaml` 中各房间的 position 字段
4. 在 Isaac Sim 中手动标定家具位置（或通过 USD 层次结构自动提取）
5. 验证场景图的 REACHABLE 边与实际通道对应

### 8.4 与 MOSAIC 场景图配置的对应关系

| home.yaml 房间 | InteriorAgent 房间类型 | 说明 |
|---|---|---|
| living_room（客厅） | living_room | 主活动区域，含沙发、茶几 |
| kitchen（厨房） | kitchen | 含料理台、冰箱、咖啡机 |
| bedroom（卧室） | bedroom / master_bedroom | 含床 |
| bathroom（卫生间） | bathroom | 含毛巾架 |
| entrance（门口） | entrance / hallway | 起始位置附近 |
| charging_station（充电站） | 自定义标记点 | 需在场景中手动放置标记 |

### 8.5 SLAM 建图与坐标标定

如果使用 Nav2 AMCL 定位，需要先建图：

```bash
# 终端 1：Isaac Sim 仿真（已加载场景 + 机器人 + ROS2 Bridge）
source ~/env_isaacsim/bin/activate
isaacsim  # 或运行 standalone 脚本

# 终端 2：SLAM Toolbox 建图
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=True

# 终端 3：RViz2 可视化
rviz2

# 终端 4：键盘遥控机器人遍历各房间
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# 建图完成后保存
ros2 run nav2_map_server map_saver_cli -f ~/mosaic_house_map
```

> 建图完成后，在 RViz2 中使用 "Publish Point" 工具记录各房间中心坐标，更新 home.yaml。


---

## 九、分阶段验证计划

### Phase 1：导航管道验证（最小可行）

**目标**：MOSAIC 通过场景图规划导航路径，在 Isaac Sim 中实际执行。

**验证链路**：
```
用户输入 "导航到厨房"
  → TurnRunner 注入场景图上下文
  → LLM 规划 navigate_to(厨房)
  → PlanVerifier 验证（前置条件：path_reachable）
  → NavigationCapability → Nav2 Action Client
  → Nav2 路径规划 + 局部避障
  → Isaac Sim PhysX 物理执行
  → 机器人到达厨房
  → 场景图更新（robot AT 边移到 kitchen）
```

**需要的改动**：

| 文件 | 改动内容 |
|------|----------|
| `plugins/capabilities/navigation/__init__.py` | mock → ROS2 Nav2 Action Client |
| `config/environments/home.yaml` | position 字段更新为 Isaac Sim 世界坐标 |
| `config/mosaic.yaml` | 新增 `ros2` 配置段（bridge 参数） |
| 新增 `mosaic/nodes/ros2_bridge.py` | ROS2 节点管理（rclpy 初始化、spin 线程） |
| 新增 `mosaic/nodes/sensor_bridge.py` | 传感器数据订阅（/odom → RobotState） |

**验证标准**：
- ✅ 机器人在 Isaac Sim 中从客厅导航到厨房
- ✅ 场景图中机器人的 AT 边正确更新为 kitchen
- ✅ PlanVerifier 能正确验证导航计划
- ✅ RViz2 中可视化导航路径

### Phase 2：多步任务验证

**目标**：验证复合任务的完整 ReAct 循环。

**测试用例**："帮我去卫生间拿个毛巾过来，然后去充电"

预期执行序列：
1. `navigate_to(卫生间)` → Nav2 执行 → Isaac Sim 物理移动 → 场景图更新
2. `pick_up(黄色毛巾)` → mock 执行 → 场景图更新（HOLDING 边）
3. `navigate_to(客厅)` → Nav2 执行 → Isaac Sim 物理移动 → 场景图更新
4. `hand_over(黄色毛巾)` → mock 执行 → 场景图更新
5. `navigate_to(充电站)` → Nav2 执行 → Isaac Sim 物理移动 → 场景图更新

**验证标准**：
- ✅ LLM 正确分解多步任务
- ✅ PlanVerifier 逐步验证通过
- ✅ 每步执行后场景图状态正确
- ✅ 导航步骤在 Isaac Sim 中实际执行，操作步骤 mock

### Phase 3：异常处理与重规划

**目标**：验证场景图驱动的 LLM 重规划。

**测试场景**：
- 在 Isaac Sim 中动态添加障碍物 → Nav2 返回路径阻塞 → 场景图更新 → LLM 重规划绕行
- 修改场景图中物品位置 → LLM 重新搜索

**Isaac Sim 优势**：可以通过 Python API 在运行时动态修改场景（添加/移除物体），比 Gazebo 更灵活。

### Phase 4：VLM 场景图自动构建

**目标**：利用 Isaac Sim 的 RTX 渲染输出驱动 VLM 自动构建场景图。

**验证链路**：
```
Isaac Sim RTX 渲染 → /camera/image_raw
  → SensorBridge 接收 RGB 图像
  → SceneAnalyzer 调用 VLM API（GPT-4V / 开源 VLM）
  → VLM 识别物体、表面、容器及空间关系
  → SceneGraphBuilder 融合 SLAM 拓扑 + VLM 语义
  → 自动构建场景图（替代 YAML 手动配置）
```

**Isaac Sim 关键优势**：RTX 光线追踪渲染的图像质量接近真实照片，VLM 的识别准确率远高于 Gazebo 的 OpenGL 渲染输出。

### Phase 5（远期）：VLA 端到端操作

**目标**：在 Isaac Lab 中训练 VLA 模型，接入 MOSAIC 的 VLAManipulationCapability。

- Isaac Lab 提供 GPU 并行强化学习环境
- 训练好的 VLA 模型通过 Capability 接口接入 MOSAIC
- 与 MoveIt2 方案并列，通过配置切换


---

## 十、Isaac Sim Standalone 启动脚本

### 10.1 最小启动脚本

Isaac Sim 支持 Standalone 模式（无 GUI 头模式），适合自动化测试：

```bash
# GUI 模式启动
python scripts/launch_isaac_sim.py

# Headless 模式（无 GUI，适合 CI/自动化测试）
python scripts/launch_isaac_sim.py --headless

# 或直接使用 isaacsim CLI
isaacsim --headless
```

```python
# scripts/launch_isaac_sim.py — Isaac Sim 仿真启动脚本
"""
启动 Isaac Sim 仿真环境，加载家庭场景 + 机器人 + ROS2 Bridge。
用于 MOSAIC 导航管道验证。

用法：
  source ~/env_isaacsim/bin/activate
  source /opt/ros/jazzy/setup.bash
  python scripts/launch_isaac_sim.py
"""
import os
os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"

import isaacsim
from isaacsim.core.api import World
from isaacsim.core.utils.stage import add_reference_to_stage

# 创建仿真世界
world = World(stage_units_in_meters=1.0)

# 加载家庭环境（InteriorAgent USD 场景）
SCENE_PATH = os.path.expanduser(
    "~/isaac_sim_assets/InteriorAgent/kujiale_0021/kujiale_0021.usda"
)
add_reference_to_stage(usd_path=SCENE_PATH, prim_path="/World/Environment")

# 加载机器人
add_reference_to_stage(
    usd_path="/Isaac/Robots/Carter/nova_carter.usd",
    prim_path="/World/Robot"
)

# 启用 ROS2 Bridge
import omni.kit.app
manager = omni.kit.app.get_app().get_extension_manager()
manager.set_extension_enabled_immediate("isaacsim.ros2.bridge", True)

# 重置并开始仿真
world.reset()

# 仿真主循环
while True:
    world.step(render=True)  # headless 模式下设为 render=False
```

### 10.2 完整仿真启动流程（多终端）

```bash
# 终端 1：启动 Isaac Sim 仿真
source ~/env_isaacsim/bin/activate
source /opt/ros/jazzy/setup.bash
python scripts/launch_isaac_sim.py

# 终端 2：启动 Nav2 导航栈（使用预建地图）
source /opt/ros/jazzy/setup.bash
ros2 launch nav2_bringup bringup_launch.py \
  use_sim_time:=True \
  map:=$HOME/mosaic_house_map.yaml

# 终端 3：RViz2 可视化
source /opt/ros/jazzy/setup.bash
rviz2

# 终端 4：启动 MOSAIC Gateway
source /opt/ros/jazzy/setup.bash
cd ros2_agent
python -c "from mosaic.gateway.server import main; main()"
```

### 10.3 SLAM 建图模式

```bash
# 终端 1：Isaac Sim 仿真
source ~/env_isaacsim/bin/activate
source /opt/ros/jazzy/setup.bash
python scripts/launch_isaac_sim.py

# 终端 2：SLAM Toolbox
source /opt/ros/jazzy/setup.bash
ros2 launch slam_toolbox online_async_launch.py use_sim_time:=True

# 终端 3：RViz2
source /opt/ros/jazzy/setup.bash
rviz2

# 终端 4：键盘遥控
source /opt/ros/jazzy/setup.bash
ros2 run teleop_twist_keyboard teleop_twist_keyboard

# 建图完成后保存
ros2 run nav2_map_server map_saver_cli -f ~/mosaic_house_map
```


---

## 十一、mosaic.yaml 配置扩展

Phase 1 需要在 `config/mosaic.yaml` 中新增 ROS2 和仿真相关配置段。

> ⚠️ **待合并**：以下配置段在 Phase 1 开发时合并到 `config/mosaic.yaml`。注意当前 mosaic.yaml 已有 `channels.ros2_topic` 配置（用于 Agent 消息通道），与下面的 `ros2` 配置段（用于物理执行桥接）是不同层面的概念，不冲突。

```yaml
# ── 新增：ROS2 桥接配置 ──
ros2:
  enabled: true
  bridge:
    # rclpy 执行器线程数
    executor_threads: 4
    # 仿真时间模式
    use_sim_time: true
  # 传感器订阅配置
  sensors:
    lidar:
      topic: "/scan"
      enabled: true
    odometry:
      topic: "/odom"
      enabled: true
    camera:
      topic: "/camera/image_raw"
      enabled: false  # Phase 4 启用
  # Nav2 配置
  navigation:
    action_server: "/navigate_to_pose"
    pose_topic: "/amcl_pose"
    # 导航超时（秒）
    timeout_s: 120

# ── 新增：仿真环境配置 ──
simulation:
  platform: "isaac_sim"  # isaac_sim | gazebo | mock
  # 环境场景文件路径
  scene_path: "~/isaac_sim_assets/InteriorAgent/kujiale_0021/kujiale_0021.usda"
  # 机器人模型
  robot:
    model: "nova_carter"
    usd_path: "/Isaac/Robots/Carter/nova_carter.usd"
    initial_position: [3.0, 2.0, 0.0]  # 对应 home.yaml 中 robot at living_room
  # 地图文件（SLAM 建图后生成）
  map_file: "~/mosaic_house_map.yaml"
```

---

## 十二、已知问题与注意事项

1. **Isaac Sim 首次启动慢**：首次启动需下载在线资产和编译着色器，可能需要 10-20 分钟。后续启动会使用缓存，速度显著提升。

2. **ROS2 环境必须在 Isaac Sim 之前 source**：Isaac Sim 的 ROS2 Bridge 在启动时检测 ROS2 环境。如果未 source，Bridge 扩展将无法加载。建议将 `source /opt/ros/jazzy/setup.bash` 写入 `~/.bashrc`。

3. **Python 版本与进程模型**：Isaac Sim 5.1 要求 Python 3.11，ROS2 Jazzy 默认 Python 3.12。注意区分两个层面：
   - Isaac Sim 进程（Python 3.11 venv）：运行物理仿真 + RTX 渲染 + 内置 ROS2 Bridge 扩展（发布传感器话题、订阅 cmd_vel）
   - MOSAIC 进程（系统 Python 3.12）：运行 Agent 核心 + rclpy 节点（Nav2 Action Client、SensorBridge 订阅）
   - 两个进程通过 ROS2 DDS 通信，不需要同一 Python 环境
   - Isaac Sim 内置的 ROS2 Bridge 扩展在 Isaac Sim 进程内运行，无需外部 rclpy

4. **VRAM 不足**：如果 GPU VRAM < 12GB，可能需要：
   - 降低渲染分辨率
   - 减少场景中的物体数量
   - 使用 Headless 模式（无 GUI 渲染）

5. **asyncio + rclpy 桥接**：MOSAIC 使用 asyncio，rclpy 使用自己的事件循环。必须在独立线程中运行 `rclpy.spin()`，通过 `concurrent.futures` 或 `asyncio.Future` 桥接。参见第七节的 `ROS2BridgeManager` 设计。

6. **Nav2 初始位姿**：Nav2 AMCL 启动后需要设置初始位姿。可以通过 RViz2 手动设置（2D Pose Estimate），或通过代码发布到 `/initialpose` 话题。

7. **USD 坐标系**：Isaac Sim 默认 Z-up 右手坐标系，与 ROS2 REP-103 一致。但 InteriorAgent 的 `rooms.json` 使用 X-Y 平面坐标，Z 轴信息需要从 USD 场景中提取。

8. **Omniverse Launcher 弃用**：NVIDIA 已宣布 Omniverse Launcher 将于 2025 年 10 月 1 日弃用。推荐使用 pip 安装方式，这也是本文档采用的方案。

---

## 十三、参考资源

| 资源 | 链接 |
|------|------|
| Isaac Sim 5.1 官方文档 | https://docs.isaacsim.omniverse.nvidia.com/5.1.0/ |
| Isaac Sim pip 安装指南 | https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/install_python.html |
| Isaac Sim ROS2 Bridge | https://docs.isaacsim.omniverse.nvidia.com/5.1.0/ros2_tutorials/ros2_landing_page.html |
| Isaac Sim ROS2 导航教程 | https://docs.isaacsim.omniverse.nvidia.com/5.1.0/ros2_tutorials/tutorial_ros2_navigation.html |
| Isaac Sim GitHub（开源） | https://github.com/isaac-sim/IsaacSim |
| InteriorAgent USD 数据集 | https://huggingface.co/datasets/spatialverse/InteriorAgent |
| Isaac Lab（强化学习） | https://isaac-sim.github.io/IsaacLab/ |
| Nav2 官方文档 | https://docs.nav2.org/ |
| Nova Carter + Nav2 教程 | https://nvidia-isaac-ros.github.io/reference_workflows/isaac_perceptor/tutorials_on_carter/demo_navigation.html |
| Isaac Sim 系统要求 | https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/requirements.html |
| World Labs Marble（文本→3D 环境） | https://www.isaacworlds.com/ |
