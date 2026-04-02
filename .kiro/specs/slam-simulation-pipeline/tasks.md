# Implementation Plan: SLAM Simulation Pipeline

## Overview

实现 SLAM 仿真全链路：SlamMapDetector 自动检测地图 → GatewayServer 增强加载 → Nav2LaunchConfig 参数生成 → Nav2 参数模板 → 一键启动脚本 → 配置扩展。使用 Python 3.10+，asyncio，pytest + hypothesis 测试。

## Tasks

- [x] 1. 实现 SlamMapDetector 核心类
  - [x] 1.1 创建 `mosaic/runtime/slam_map_detector.py`，定义 SlamMapDetector 类和 `__init__` 方法
    - 接受 `default_map_dir: str = "~/mosaic_maps"` 参数
    - 代码注释使用中文
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 1.2 实现 `validate_map_files(yaml_path: str) -> bool` 方法
    - 验证 .yaml 文件存在性
    - 解析 .yaml 中 `image` 字段，处理相对路径（基于 yaml 所在目录）
    - 验证对应 .pgm 文件存在性
    - 异常时返回 False 而非抛出
    - _Requirements: 1.3_

  - [x] 1.3 实现 `detect(configured_path: str = "") -> str | None` 方法
    - 步骤 1：配置路径优先（expanduser + validate_map_files）
    - 步骤 2：扫描 default_map_dir，收集 .yaml 文件，按 mtime 降序排列
    - 步骤 3：返回最新有效地图路径或 None
    - 整个方法用 try-except 包裹，确保永不抛出异常
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 1.4 编写 SlamMapDetector 属性测试 `test/mosaic_v2/test_slam_map_detector_props.py`
    - **Property 1.1: detect_prefers_configured_path** — 配置路径有效时始终优先返回配置路径
    - **Validates: Requirements 1.1**

  - [x] 1.5 编写 SlamMapDetector 属性测试（续）
    - **Property 1.3: validate_ensures_pair_completeness** — validate_map_files 返回 True 意味着 .yaml 和 .pgm 均存在
    - **Validates: Requirements 1.3**

  - [x] 1.6 编写 SlamMapDetector 属性测试（续）
    - **Property 1.4: detect_never_raises** — detect 方法对任意输入永不抛出异常
    - **Validates: Requirements 1.4**

  - [x] 1.7 编写 SlamMapDetector 单元测试 `test/mosaic_v2/test_slam_map_detector.py`
    - 测试配置路径有效时直接返回
    - 测试配置路径无效时回退到目录扫描，返回最新地图
    - 测试 .pgm 缺失时 validate_map_files 返回 False
    - 测试目录不存在或为空时返回 None
    - 使用 `tmp_path` fixture 创建临时文件
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 2. 增强 GatewayServer 地图加载
  - [x] 2.1 修改 `mosaic/gateway/server.py` 中 `_init_map_and_vlm_pipeline()` 方法
    - 导入 SlamMapDetector
    - 从配置读取 `scene_graph.slam_map_dir`（默认 `~/mosaic_maps`）
    - 用 SlamMapDetector.detect() 替换当前的直接 expanduser 逻辑
    - 检测到地图时：加载 → extract_room_topology → merge_room_topology
    - _Requirements: 2.1, 2.4_

  - [x] 2.2 实现无地图安全降级逻辑
    - detect() 返回 None 时记录 INFO 日志，保持 YAML 静态场景图
    - 地图加载异常时记录 ERROR 日志并降级，不影响系统启动
    - _Requirements: 2.2, 2.3_

  - [x] 2.3 编写 GatewayServer 地图加载集成测试 `test/mosaic_v2/test_gateway_slam_integration.py`
    - 测试有地图时场景图包含 SLAM 拓扑节点
    - 测试无地图时系统正常启动（降级）
    - 测试地图加载异常时降级处理
    - 使用 mock 替代实际文件系统
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 3. Checkpoint — 确保 SlamMapDetector 和 GatewayServer 集成测试通过
  - 运行 `pytest test/mosaic_v2/test_slam_map_detector*.py test/mosaic_v2/test_gateway_slam_integration.py -v`
  - 确保所有测试通过，有问题请询问用户

- [x] 4. 实现 Nav2LaunchConfig 和数据模型
  - [x] 4.1 创建 `mosaic/runtime/nav2_launch_config.py`，定义 Nav2SimParams 和 SlamToolboxParams 数据类
    - Nav2SimParams: use_sim_time, robot_radius, inflation_radius, scan_topic 等字段
    - SlamToolboxParams: use_sim_time, mode, scan_topic, odom_frame, map_frame, base_frame 等字段
    - 实现 `__post_init__` 参数验证：inflation_radius > robot_radius, max_particles > min_particles, 正数校验
    - _Requirements: 3.2_

  - [x] 4.2 实现 Nav2LaunchConfig 类及 `generate_nav2_params(output_path: str) -> str` 方法
    - 生成包含 amcl、controller_server、planner_server、local_costmap、global_costmap 配置段的 YAML 文件
    - 所有段设置 use_sim_time: true
    - 自动创建输出目录（如不存在）
    - _Requirements: 3.1_

  - [x] 4.3 实现 `generate_slam_params(output_path: str) -> str` 方法
    - 生成 SLAM Toolbox 参数 YAML，包含 scan_topic、odom_frame、map_frame、base_frame
    - _Requirements: 3.3_

  - [x] 4.4 实现 `get_launch_command(map_path: str) -> str` 方法
    - 返回包含 `use_sim_time:=True` 和 `map` 参数的完整 `ros2 launch nav2_bringup bringup_launch.py` 命令
    - _Requirements: 3.4_

  - [x] 4.5 编写 Nav2SimParams 属性测试 `test/mosaic_v2/test_nav2_launch_config_props.py`
    - **Property 6: Nav2 参数有效性** — 生成的参数文件中 use_sim_time = True 且 inflation_radius > robot_radius 且 max_particles > min_particles
    - **Validates: Requirements 3.1, 3.2**

  - [x] 4.6 编写 Nav2LaunchConfig 单元测试 `test/mosaic_v2/test_nav2_launch_config.py`
    - 测试 generate_nav2_params 生成的 YAML 包含所有必需配置段
    - 测试 Nav2SimParams 参数验证（inflation_radius <= robot_radius 时抛出 ValueError）
    - 测试 generate_slam_params 生成正确的 SLAM 参数
    - 测试 get_launch_command 返回正确的 ros2 launch 命令格式
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 5. 创建 Nav2 参数文件模板
  - [x] 5.1 创建 `config/nav2/` 目录和 `config/nav2/nav2_params.yaml`
    - 包含 amcl、controller_server、planner_server、local_costmap、global_costmap 完整配置
    - 所有节点 use_sim_time: true
    - costmap 参数适配 Nova Carter 尺寸（robot_radius: 0.22, inflation_radius: 0.55）
    - _Requirements: 7.1_

  - [x] 5.2 创建 `config/nav2/slam_toolbox_params.yaml`
    - scan_topic: /scan, use_sim_time: true
    - 配置 odom_frame, map_frame, base_frame
    - 适配 Isaac Sim 仿真环境
    - _Requirements: 7.2_

  - [x] 5.3 创建 `config/nav2/slam_rviz.rviz`
    - 配置显示 /map 话题（地图）
    - 配置显示 /scan 话题（激光扫描）
    - 配置显示 RobotModel 和 TF 树
    - _Requirements: 7.3_

- [x] 6. Checkpoint — 确保 Nav2LaunchConfig 测试通过
  - 运行 `pytest test/mosaic_v2/test_nav2_launch_config*.py -v`
  - 确保所有测试通过，有问题请询问用户

- [x] 7. 创建 SLAM 建图启动脚本
  - [x] 7.1 创建 `scripts/launch_slam_mapping.sh`
    - 编排 Isaac Sim + SLAM Toolbox + RViz2 + 键盘遥控的多终端启动
    - 使用 `config/nav2/slam_toolbox_params.yaml` 和 `config/nav2/slam_rviz.rviz`
    - _Requirements: 4.1_

  - [x] 7.2 实现 Ctrl+C 信号处理（trap）
    - 捕获 SIGINT/SIGTERM
    - 自动执行 `map_saver_cli -f ~/mosaic_maps/house_map` 保存地图
    - 清理所有子进程
    - _Requirements: 4.2_

  - [x] 7.3 实现子进程失败检测和 `~/mosaic_maps/` 目录自动创建
    - 检测子进程启动失败，清理已启动进程并输出错误信息
    - 脚本启动时自动 `mkdir -p ~/mosaic_maps`
    - _Requirements: 4.3, 4.4_

- [x] 8. 创建 Nav2 导航启动脚本
  - [x] 8.1 创建 `scripts/launch_nav2_sim.sh`
    - 编排 Isaac Sim + Nav2 + MOSAIC Gateway 的多终端启动
    - 使用 `config/nav2/nav2_params.yaml` 参数文件
    - _Requirements: 5.1, 5.3_

  - [x] 8.2 实现地图文件存在性检查和子进程管理
    - 启动前检查 SLAM 地图文件是否存在
    - 不存在时输出提示信息，建议先执行 `launch_slam_mapping.sh`
    - 实现子进程管理和清理逻辑
    - _Requirements: 5.2_

- [x] 9. 更新 mosaic.yaml 配置
  - [x] 9.1 在 `config/mosaic.yaml` 的 `scene_graph` 段新增配置项
    - 新增 `slam_map_dir: "~/mosaic_maps"`
    - 更新 `slam_map` 路径为 `~/mosaic_maps/house_map.yaml`
    - _Requirements: 6.1, 6.2_

  - [x] 9.2 在 `config/mosaic.yaml` 中新增 `nav2` 配置段
    - 新增 `nav2.params_dir: "config/nav2"` 配置项
    - _Requirements: 6.3_

- [x] 10. 集成联调和最终验证
  - [x] 10.1 连接 Nav2LaunchConfig 与 mosaic.yaml 配置
    - Nav2LaunchConfig 从 `nav2.params_dir` 读取输出目录
    - 确保 SlamMapDetector 使用 `scene_graph.slam_map_dir` 配置
    - _Requirements: 6.1, 6.3_

  - [x] 10.2 编写端到端集成测试 `test/mosaic_v2/test_slam_pipeline_e2e.py`
    - 创建模拟 SLAM 地图文件 → 验证 SlamMapDetector 检测 → 验证 MapAnalyzer 加载 → 验证场景图包含拓扑节点
    - 验证 Nav2LaunchConfig 生成的参数文件可被正确解析
    - 使用 tmp_path 和 mock 隔离文件系统
    - _Requirements: 2.1, 3.1, 6.1_

- [x] 11. Final Checkpoint — 确保所有测试通过
  - 运行 `pytest test/mosaic_v2/test_slam_*.py test/mosaic_v2/test_nav2_*.py test/mosaic_v2/test_gateway_slam_*.py -v`
  - 确保所有测试通过，有问题请询问用户

## Notes

- 标记 `*` 的子任务为可选测试任务，可跳过以加速 MVP
- 每个任务引用了具体的 Requirements 编号，确保可追溯
- Property 测试使用 hypothesis 库，单元测试使用 pytest
- 所有测试文件放在 `test/mosaic_v2/` 目录下
- 所有代码注释使用中文
- Checkpoints 用于阶段性验证，确保增量正确性
