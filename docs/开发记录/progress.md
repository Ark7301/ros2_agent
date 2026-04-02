## 阶段性总结

### 已完成 ✅

| 项目 | 说明 |
|------|------|
| Python 3.11 | deadsnakes PPA 安装，Isaac Sim 5.1 要求 |
| ROS2 Jazzy | 桌面版 + Nav2 + SLAM Toolbox，381 个包 |
| Isaac Sim 5.1 | pip 安装到 ~/env_isaacsim 虚拟环境 |
| InteriorAgent 场景 | kujiale_0021 下载完成，5 个房间 |
| home.yaml 坐标对齐 | 用 rooms.json 中心点替换原手动坐标 |
| mosaic.yaml 扩展 | 新增 ros2 桥接 + simulation + scene_graph + vlm + aria 配置段 |
| 文档 Humble → Jazzy | 全量替换匹配 Ubuntu 24.04 |
| ROS2BridgeManager | mosaic/nodes/ros2_bridge.py — rclpy 独立线程桥接 asyncio |
| SensorBridge | mosaic/nodes/sensor_bridge.py — 订阅 /odom、/amcl_pose |
| NavigationCapability 改造 | mock → Nav2 双模式，保留向后兼容 |
| 启动脚本 | scripts/launch_isaac_sim.py |
| Isaac Sim GUI 启动验证 | 场景加载成功，RTX 渲染正常 |
| v2 核心框架 | protocol + core + plugin_sdk + gateway + runtime 全部实现 |
| 场景图体系 | SceneGraph + SceneGraphManager + PlanVerifier + ActionRules |
| 全部 8 个插件 | navigation/motion/manipulation/appliance/minimax/cli/file_memory/sliding_window |
| 测试覆盖 | 16 个测试文件覆盖 v2 核心模块 |

### 当前卡点

Nova Carter 模型从 NVIDIA S3 加载失败（空 Xform），需手动从 Content 面板拖入场景。

---

## 接下来的工作安排

通过代码审查，发现以下精确断点：

### 断点分析

| # | 断点 | 位置 | 现状 | 影响 |
|---|------|------|------|------|
| 1 | GatewayServer 未接入 SceneGraphManager | `server.py:__init__` | TurnRunner 创建时 `scene_graph_mgr=None`，场景图体系完全旁路 | LLM 看不到场景信息，PlanVerifier 不工作 |
| 2 | 缺少 SpatialProvider | NavigationCapability | Nav2 模式需要 `spatial_provider.resolve_location("厨房")` 将语义地名转坐标，目前无实现 | Nav2 模式下导航必定失败 |
| 3 | NavigationCapability 工厂函数无参 | `create_plugin()` | PluginRegistry.discover 调用 `create_plugin()` 无参，永远是 Mock 模式 | 即使有 ROS2 环境也无法切换到 Nav2 |
| 4 | SensorBridge 未接入 SceneGraph | 独立运行 | SensorBridge 更新 RobotState，但不同步到 SceneGraph 的 agent AT 边 | 场景图中机器人位置永远是初始值 |
| 5 | Isaac Sim 缺 Nova Carter | `launch_isaac_sim.py` | S3 远程 USD 引用加载失败 | 无机器人 → 无传感器数据 → 无法建图 |
| 6 | 缺 Action Graph 配置 | Isaac Sim 场景 | 无 OG 节点发布 /scan、/odom、/tf、/clock | ROS2 话题为空 |
| 7 | 缺地图文件 | Nav2 依赖 | 未建图，无 mosaic_house_map.yaml | Nav2 无法启动定位和路径规划 |

---

### 工作计划（按依赖关系排序）

---

#### 任务 1：GatewayServer 接入 SceneGraphManager
- 解决断点：#1
- 改动位置：`mosaic/gateway/server.py` 的 `__init__`
- 具体做什么：
  1. 加载 `config/environments/home.yaml`
  2. 创建 SceneGraphManager 实例，调用 `initialize_from_config()`
  3. 将 `scene_graph_mgr` 传入 TurnRunner 构造函数
- 完成后效果：
  - LLM 的 system prompt 中会自动注入场景图文本（房间、家具、物品、可达性）
  - PlanVerifier 在每次工具调用前验证计划可行性
  - 工具执行后场景图自动更新（机器人位置、持有物品等）
- 验证方式：启动 Gateway → CLI 输入 "帮我去厨房" → 观察日志中是否出现 `[场景图]` 文本和计划验证信息
- 不依赖仿真环境，Mock 模式即可验证

---

#### 任务 2：实现 SpatialProvider（语义地名 → 坐标）
- 解决断点：#2
- 新建文件：`mosaic/runtime/spatial_provider.py`
- 具体做什么：
  1. 从 SceneGraph 中查询节点的 position 属性
  2. 支持模糊匹配（"厨房" → kitchen 节点 → `[12.97, -0.75]`）
  3. 实现 `resolve_location(name: str) -> tuple[float, float]` 接口
- 数据来源：`config/environments/home.yaml` 中每个 room/furniture 的 position 字段
- 完成后效果：NavigationCapability 在 Nav2 模式下能将 "厨房" 解析为 `(12.97, -0.75)` 发送给 Nav2
- 验证方式：单元测试，输入语义地名，断言返回正确坐标

---

#### 任务 3：改造插件工厂函数支持参数注入
- 解决断点：#3
- 改动位置：
  - `mosaic/plugin_sdk/registry.py` 的 `discover()` 和 `resolve()`
  - `plugins/capabilities/navigation/__init__.py` 的 `create_plugin()`
- 具体做什么：
  1. PluginRegistry.register 支持传入 `factory_kwargs`
  2. GatewayServer 在 discover 后，根据配置判断是否注入 `ros_node` 和 `spatial_provider`
  3. 或者：改为延迟配置模式，插件创建后通过 `configure(ros_node=..., spatial=...)` 注入依赖
- 完成后效果：
  - `ros2.enabled=true` 时，NavigationCapability 自动切换到 Nav2 模式
  - `ros2.enabled=false` 时，保持 Mock 模式（当前行为不变）
- 验证方式：
  - Mock 模式：现有测试不受影响
  - Nav2 模式：需要 ROS2 环境，Phase A 完成后验证

---

#### 任务 4：SensorBridge → SceneGraph 位置同步
- 解决断点：#4
- 改动位置：`mosaic/nodes/sensor_bridge.py` 或新建同步桥接
- 具体做什么：
  1. SensorBridge 的 `_pose_callback` 中，通过回调通知 SceneGraphManager
  2. SceneGraphManager 收到位置更新后：
     - 更新 agent 节点的 position 属性
     - 判断机器人进入了哪个房间（最近邻匹配 room position）
     - 更新 agent 的 AT 边指向新房间
  3. 通过 EventBus 发布 `scene.agent_moved` 事件
- 完成后效果：
  - 场景图中机器人位置实时反映物理世界
  - LLM 每次推理时看到的是真实位置，而非初始位置
  - PlanVerifier 的前置条件检查基于真实位置
- 依赖：任务 1（SceneGraphManager 已接入）+ Phase A（有真实传感器数据）
- 验证方式：Mock 模式下可用单元测试模拟位置更新；真实验证需 Phase A 完成

---

#### 任务 5（物理环境）：Isaac Sim 中加载 Nova Carter
- 解决断点：#5
- 操作方式：手动操作，非代码任务
- 具体步骤：
  1. 打开 Isaac Sim GUI，加载 kujiale_0021 场景
  2. 打开 Content Browser → NVIDIA Assets → Robots → Nova Carter
  3. 拖拽 nova_carter.usd 到场景中 /World/Robot 路径
  4. 设置初始位置 (7.93, -0.39, 0.0)
  5. 保存为本地 USD 文件（避免每次重新加载远程资源）
- 完成后效果：场景中有可控机器人实体
- 验证方式：Isaac Sim 中能看到 Nova Carter 模型，Xform 非空

---

#### 任务 6（物理环境）：配置 Action Graph 发布 ROS2 话题
- 解决断点：#6
- 依赖：任务 5
- 操作方式：Isaac Sim GUI 中配置 OmniGraph
- 具体步骤：
  1. 创建 Action Graph，添加以下 OG 节点：
     - ROS2 Clock Publisher → /clock（use_sim_time 依赖）
     - ROS2 TF Publisher → /tf（坐标变换）
     - ROS2 Odometry Publisher → /odom（里程计）
     - ROS2 Lidar Publisher → /scan（激光雷达）
  2. 连接 Nova Carter 的传感器 prim 到对应 OG 节点
  3. 配置 frame_id: "base_link", child_frame_id: "odom"
- 完成后效果：
  - `ros2 topic list` 能看到 /clock、/tf、/odom、/scan
  - `ros2 topic echo /odom` 有数据流
- 验证方式：终端执行 `ros2 topic hz /odom` 确认频率 > 0

---

#### 任务 7（物理环境）：SLAM 建图
- 解决断点：#7
- 依赖：任务 6
- 具体步骤：
  1. 启动 SLAM Toolbox：`ros2 launch slam_toolbox online_async_launch.py`
  2. 启动键盘遥控：`ros2 run teleop_twist_keyboard teleop_twist_keyboard`
  3. 在 Isaac Sim 中遥控机器人遍历所有房间
  4. RViz2 中观察地图构建过程
  5. 保存地图：`ros2 run nav2_map_server map_saver_cli -f ~/mosaic_house_map`
- 完成后效果：生成 `mosaic_house_map.yaml` + `mosaic_house_map.pgm`
- 验证方式：RViz2 中加载地图，5 个房间轮廓清晰可辨

---

#### 任务 8（物理环境）：Nav2 全链路验证
- 依赖：任务 7
- 具体步骤：
  1. 启动 Nav2：`ros2 launch nav2_bringup bringup_launch.py map:=~/mosaic_house_map.yaml use_sim_time:=true`
  2. RViz2 中设置初始位姿（2D Pose Estimate）
  3. 手动发送导航目标测试 Nav2 本身是否工作
  4. 通过 MOSAIC 的 NavigationCapability（Nav2 模式）发送导航指令
- 完成后效果：MOSAIC → Nav2 → Isaac Sim 全链路打通
- 验证方式：CLI 输入 "导航到厨房" → 机器人在 Isaac Sim 中移动到厨房区域

---

### 执行策略

```
软件层（可立即开始，不依赖仿真）     物理层（需要 Isaac Sim GUI 操作）
─────────────────────────────     ──────────────────────────────
任务1: Gateway接入SceneGraph ──┐
                               │   任务5: 加载Nova Carter
任务2: SpatialProvider ────────┤        │
                               │   任务6: Action Graph配置
任务3: 插件工厂改造 ───────────┤        │
                               │   任务7: SLAM建图
任务4: 传感器→场景图同步 ──────┘        │
                                   任务8: Nav2全链路验证
                                        │
                          ┌──────────────┘
                          ▼
                  端到端集成验证
          "帮我去厨房做杯咖啡送过来"
```

任务 1-4 是纯软件工作，可以在 Mock 模式下开发和测试，不需要等仿真环境。
任务 5-8 是物理环境搭建，需要在 Isaac Sim 机器上手动操作。
两条线可以并行推进，最终在任务 8 完成后做端到端集成验证。
