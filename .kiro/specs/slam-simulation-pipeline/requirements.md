# Requirements: SLAM Simulation Pipeline

## Requirement 1: SLAM 地图自动检测

### Description
实现 SlamMapDetector 类，自动检测可用的 SLAM 地图文件。支持配置路径优先 + 默认目录扫描回退策略，确保 GatewayServer 启动时能找到最合适的地图文件。

### Acceptance Criteria
- 1.1 Given 配置路径 `scene_graph.slam_map` 指向有效的 .yaml+.pgm 文件对, When 调用 detect(), Then 返回该配置路径
- 1.2 Given 配置路径无效或为空, When `~/mosaic_maps/` 目录中存在多个有效地图文件, Then 返回修改时间最新的地图路径
- 1.3 Given .yaml 文件存在但其引用的 .pgm 文件不存在, When 调用 validate_map_files(), Then 返回 False
- 1.4 Given 配置路径无效且默认目录不存在或为空, When 调用 detect(), Then 返回 None 且不抛出异常

### Correctness Properties
```
Property 1.1: detect_prefers_configured_path
  ∀ configured_path, default_dir:
    validate_map_pair(configured_path) = True
    ⟹ detect(configured_path) = configured_path
  (配置路径有效时始终优先返回配置路径)

Property 1.2: detect_returns_newest_from_dir
  ∀ default_dir containing valid maps [m1, m2, ...]:
    detect("") = argmax(mtime, valid_maps_in(default_dir))
  (无配置路径时返回目录中最新的有效地图)

Property 1.3: validate_ensures_pair_completeness
  ∀ yaml_path:
    validate_map_pair(yaml_path) = True
    ⟹ os.path.exists(yaml_path) ∧ os.path.exists(resolve_pgm(yaml_path))
  (验证通过意味着 .yaml 和 .pgm 均存在)

Property 1.4: detect_never_raises
  ∀ configured_path, default_dir:
    detect(configured_path) ∈ {str, None} ∧ no exception raised
  (detect 方法永不抛出异常)
```

---

## Requirement 2: GatewayServer 增强地图加载

### Description
增强 GatewayServer._init_map_and_vlm_pipeline() 方法，集成 SlamMapDetector 实现自动检测 + 加载 SLAM 地图。无地图时安全降级为 YAML 静态场景图。

### Acceptance Criteria
- 2.1 Given SLAM 地图文件存在, When GatewayServer 初始化, Then 场景图包含 SLAM 拓扑提取的房间节点和连接关系
- 2.2 Given 无任何 SLAM 地图文件, When GatewayServer 初始化, Then 场景图仅包含 YAML 配置的静态节点，系统正常运行
- 2.3 Given SLAM 地图加载过程中发生异常, When GatewayServer 初始化, Then 记录 ERROR 日志并降级为 YAML 配置，不影响系统启动
- 2.4 Given mosaic.yaml 中新增 `scene_graph.slam_map_dir` 配置项, When 值为 `~/mosaic_maps`, Then SlamMapDetector 使用该目录作为扫描路径

---

## Requirement 3: Nav2 仿真参数配置

### Description
实现 Nav2LaunchConfig 类，生成适配 Isaac Sim 仿真环境的 Nav2 和 SLAM Toolbox 参数文件。所有参数必须设置 use_sim_time: true。

### Acceptance Criteria
- 3.1 Given 调用 generate_nav2_params(), When 生成参数文件, Then 文件包含 amcl、controller_server、planner_server、local_costmap、global_costmap 配置段，且所有段均设置 use_sim_time: true
- 3.2 Given Nav2SimParams 中 inflation_radius <= robot_radius, When 参数验证, Then 抛出 ValueError
- 3.3 Given 调用 generate_slam_params(), When 生成 SLAM Toolbox 参数文件, Then 文件包含正确的 scan_topic、odom_frame、map_frame、base_frame 配置
- 3.4 Given 调用 get_launch_command(map_path), When map_path 为有效路径, Then 返回包含 use_sim_time:=True 和 map 参数的完整 ros2 launch 命令

---

## Requirement 4: SLAM 建图启动脚本

### Description
提供 `scripts/launch_slam_mapping.sh` 一键启动脚本，编排 Isaac Sim + SLAM Toolbox + RViz2 + 键盘遥控的多终端启动流程，并在建图完成后自动保存地图到 `~/mosaic_maps/` 目录。

### Acceptance Criteria
- 4.1 Given 执行 launch_slam_mapping.sh, When Isaac Sim、SLAM Toolbox、键盘遥控均正常启动, Then 用户可通过键盘控制机器人在仿真环境中移动建图
- 4.2 Given 建图完成用户按 Ctrl+C, When 脚本收到中断信号, Then 自动执行 map_saver_cli 保存地图到 ~/mosaic_maps/house_map.yaml 和 .pgm
- 4.3 Given 任一子进程启动失败, When 脚本检测到失败, Then 清理已启动的子进程并输出错误信息
- 4.4 Given ~/mosaic_maps/ 目录不存在, When 脚本启动, Then 自动创建该目录

---

## Requirement 5: Nav2 导航启动脚本

### Description
提供 `scripts/launch_nav2_sim.sh` 一键启动脚本，编排 Isaac Sim + Nav2 导航栈 + MOSAIC Gateway 的多终端启动流程，使用已建好的 SLAM 地图进行导航。

### Acceptance Criteria
- 5.1 Given 执行 launch_nav2_sim.sh 且 SLAM 地图存在, When 所有组件正常启动, Then Nav2 使用指定地图进行定位和导航
- 5.2 Given 执行 launch_nav2_sim.sh 但无 SLAM 地图, When 脚本检测到无地图, Then 输出提示信息建议先执行建图脚本
- 5.3 Given Nav2 导航栈启动完成, When MOSAIC Gateway 启动, Then NavigationCapability 能通过 Nav2 Action Client 发送导航目标

---

## Requirement 6: mosaic.yaml 配置扩展

### Description
在 mosaic.yaml 中新增 SLAM 地图目录配置项和 Nav2 参数文件路径配置，确保所有路径可配置。

### Acceptance Criteria
- 6.1 Given mosaic.yaml 中 `scene_graph.slam_map_dir` 设置为 `~/mosaic_maps`, When GatewayServer 读取配置, Then SlamMapDetector 使用该目录
- 6.2 Given mosaic.yaml 中 `scene_graph.slam_map` 路径更新为 `~/mosaic_maps/house_map.yaml`, When 该文件存在, Then GatewayServer 优先加载该地图
- 6.3 Given mosaic.yaml 中新增 `nav2.params_dir` 配置项, When 值为 `config/nav2`, Then Nav2LaunchConfig 在该目录生成参数文件

---

## Requirement 7: Nav2 参数文件模板

### Description
在 `config/nav2/` 目录下提供预配置的 Nav2 参数文件和 SLAM Toolbox 参数文件，适配 Isaac Sim + Nova Carter 仿真环境。

### Acceptance Criteria
- 7.1 Given config/nav2/nav2_params.yaml 文件, When Nav2 bringup 使用该文件启动, Then 所有节点 use_sim_time 为 true，costmap 参数适配 Nova Carter 尺寸
- 7.2 Given config/nav2/slam_toolbox_params.yaml 文件, When SLAM Toolbox 使用该文件启动, Then scan_topic 为 /scan，use_sim_time 为 true
- 7.3 Given config/nav2/slam_rviz.rviz 文件, When RViz2 加载该配置, Then 显示地图、激光扫描、机器人模型和 TF 树
