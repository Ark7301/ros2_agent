# 需求文档

## 简介

基于 m-explore-ros2 (explore_lite) 核心算法，纯 Python 重写自主探索建图系统。系统通过 BFS 检测 frontier cell 并聚类，使用 cost 函数选择最优 frontier，通过 Nav2 导航，并引入黑名单机制和 progress 超时检测解决卡住问题。

## 术语表

- **FrontierSearch**：Frontier 检测与聚类模块，负责从 OccupancyGrid 中检测所有 frontier 并聚类为 cluster
- **Frontier**：一个 frontier cluster 数据结构，包含 size、min_distance、cost、centroid、middle、points 属性
- **BlacklistManager**：黑名单管理模块，管理导航失败/超时的 frontier 坐标
- **ProgressMonitor**：进展超时检测模块，检测同一目标是否有进展
- **AutoExploreNode**：ROS2 主节点，协调所有组件执行探索循环
- **OccupancyGrid**：ROS2 nav_msgs 中的栅格地图消息，值域 [-1, 100]
- **Frontier_Cell**：unknown cell（值为 -1）且至少有一个 4-连通 free 邻居的栅格单元
- **Free_Cell**：OccupancyGrid 中值在 [0, 50) 范围内的栅格单元
- **Cost_Function**：frontier 排序函数，公式为 `distance × potential_scale - size × gain_scale`
- **Nav2**：ROS2 Navigation2 导航框架，提供 NavigateToPose action 接口
- **TF2**：ROS2 坐标变换框架，用于获取 map → base_link 变换

## 需求

### 需求 1：Frontier Cell 检测

**用户故事：** 作为机器人探索系统，我需要从 OccupancyGrid 中正确识别 frontier cell，以便确定未探索区域的边界。

#### 验收标准

1. WHEN FrontierSearch 检查一个栅格单元时，THE FrontierSearch SHALL 判定该单元为 Frontier_Cell 当且仅当该单元值为 UNKNOWN（-1）且至少存在一个 4-连通邻居为 Free_Cell
2. WHEN FrontierSearch 检查一个已被标记为 frontier_flag 的单元时，THE FrontierSearch SHALL 判定该单元为非 Frontier_Cell
3. WHEN FrontierSearch 检查一个值不为 UNKNOWN 的单元时，THE FrontierSearch SHALL 判定该单元为非 Frontier_Cell

### 需求 2：Frontier 聚类

**用户故事：** 作为机器人探索系统，我需要将相邻的 frontier cell 聚类为 cluster，以便选择有意义的探索目标而非单个栅格点。

#### 验收标准

1. WHEN FrontierSearch 发现一个新的 Frontier_Cell 时，THE FrontierSearch SHALL 通过 BFS 遍历所有与该 cell 8-连通的 Frontier_Cell 并合并为一个 Frontier cluster
2. THE Frontier SHALL 将 centroid 计算为其所有 points 的算术平均值
3. THE Frontier SHALL 将 min_distance 记录为 cluster 中距参考点最近的点的欧氏距离
4. THE Frontier SHALL 将 middle 记录为 cluster 中距参考点最近的点的世界坐标
5. WHEN 一个 Frontier cluster 的 size × resolution 小于 min_frontier_size 时，THE FrontierSearch SHALL 过滤掉该 cluster

### 需求 3：Frontier 排序与选择

**用户故事：** 作为机器人探索系统，我需要按照 cost 函数对 frontier 排序，以便优先选择近且大的探索目标。

#### 验收标准

1. THE FrontierSearch SHALL 使用公式 `distance × potential_scale - size × gain_scale` 计算每个 Frontier 的 cost 值
2. THE FrontierSearch SHALL 将 search_from 返回的 Frontier 列表按 cost 值升序排列
3. WHEN AutoExploreNode 选择导航目标时，THE AutoExploreNode SHALL 选择排序后第一个不在黑名单中的 Frontier 的 centroid 作为目标


### 需求 4：黑名单管理

**用户故事：** 作为机器人探索系统，我需要将导航失败或超时的目标加入黑名单，以便避免重复尝试不可达的目标。

#### 验收标准

1. WHEN 一个坐标点被添加到 BlacklistManager 时，THE BlacklistManager SHALL 存储该点的世界坐标
2. WHEN BlacklistManager 检查一个点是否在黑名单中时，THE BlacklistManager SHALL 在该点与任一黑名单点的 x 和 y 方向差值均小于 tolerance × resolution 时返回 True
3. WHEN BlacklistManager 检查一个点且该点与所有黑名单点的距离均超出容差范围时，THE BlacklistManager SHALL 返回 False
4. WHEN BlacklistManager 执行 clear 操作时，THE BlacklistManager SHALL 清空所有已存储的黑名单点

### 需求 5：进展超时检测

**用户故事：** 作为机器人探索系统，我需要检测导航是否在同一目标上卡住，以便及时放弃并选择新目标。

#### 验收标准

1. WHEN ProgressMonitor 收到与当前目标相同的 goal 且 distance 未减小时，THE ProgressMonitor SHALL 持续累计经过时间
2. WHEN ProgressMonitor 累计时间超过 timeout 阈值时，THE ProgressMonitor SHALL 返回 True 表示超时
3. WHEN ProgressMonitor 收到新的 goal（与当前目标不同）时，THE ProgressMonitor SHALL 重置计时器并记录新目标
4. WHEN ProgressMonitor 收到相同 goal 但 distance 减小时，THE ProgressMonitor SHALL 重置计时器（表示有进展）

### 需求 6：导航结果处理

**用户故事：** 作为机器人探索系统，我需要根据 Nav2 导航结果采取相应动作，以便在失败时自动恢复。

#### 验收标准

1. WHEN Nav2 返回 SUCCEEDED 状态时，THE AutoExploreNode SHALL 触发 make_plan 寻找新的探索目标
2. WHEN Nav2 返回 ABORTED 状态时，THE AutoExploreNode SHALL 将当前目标加入 BlacklistManager 并立即触发 make_plan 重新规划
3. WHEN Nav2 返回 CANCELED 状态时，THE AutoExploreNode SHALL 不执行额外操作

### 需求 7：探索终止条件

**用户故事：** 作为机器人探索系统，我需要在适当时机停止探索，以便在地图完成或无法继续时正确终止。

#### 验收标准

1. WHEN FrontierSearch 返回空的 frontier 列表时，THE AutoExploreNode SHALL 停止探索
2. WHEN 所有检测到的 Frontier 的 centroid 均在 BlacklistManager 黑名单中时，THE AutoExploreNode SHALL 停止探索

### 需求 8：主规划循环

**用户故事：** 作为机器人探索系统，我需要以固定频率执行规划循环，以便持续推进探索进程。

#### 验收标准

1. THE AutoExploreNode SHALL 以 PLANNER_HZ（0.5Hz）频率定时触发 make_plan
2. WHEN make_plan 被触发时，THE AutoExploreNode SHALL 通过 TF2 获取机器人当前位姿
3. WHEN make_plan 检测到新目标与当前目标不同时，THE AutoExploreNode SHALL 向 Nav2 发送新的 NavigateToPose 目标
4. WHEN make_plan 检测到新目标与当前目标相同时，THE AutoExploreNode SHALL 不重复发送导航目标
5. WHEN ProgressMonitor 报告超时时，THE AutoExploreNode SHALL 将当前目标加入 BlacklistManager 并递归调用 make_plan


### 需求 9：错误处理与恢复

**用户故事：** 作为机器人探索系统，我需要优雅地处理各种异常情况，以便在异常恢复后自动继续探索。

#### 验收标准

1. IF TF2 lookupTransform 抛出异常，THEN THE AutoExploreNode SHALL 记录警告日志并跳过本次 make_plan
2. IF make_plan 被触发时 map_data 为 None，THEN THE AutoExploreNode SHALL 记录信息日志并跳过本次规划
3. IF 机器人位姿转换为 grid 坐标后超出地图范围，THEN THE FrontierSearch SHALL 返回空的 frontier 列表
4. IF Nav2 NavigateToPose action server 不可用，THEN THE AutoExploreNode SHALL 在启动时阻塞等待连接

### 需求 10：邻域计算

**用户故事：** 作为 frontier 检测算法，我需要正确计算栅格单元的邻域，以便支持 BFS 遍历和聚类。

#### 验收标准

1. THE FrontierSearch SHALL 为每个栅格单元计算最多 4 个 4-连通邻居索引，所有索引在 [0, width × height) 范围内
2. THE FrontierSearch SHALL 为每个栅格单元计算最多 8 个 8-连通邻居索引，所有索引在 [0, width × height) 范围内
3. THE FrontierSearch SHALL 确保 8-连通邻居包含所有 4-连通邻居
4. WHEN 栅格单元位于地图边界时，THE FrontierSearch SHALL 正确排除越界的邻居索引

### 需求 11：地图数据订阅与缓存

**用户故事：** 作为 ROS2 节点，我需要订阅并缓存最新的地图数据，以便规划循环使用。

#### 验收标准

1. THE AutoExploreNode SHALL 订阅 /map 话题（OccupancyGrid 类型）
2. WHEN 收到新的 OccupancyGrid 消息时，THE AutoExploreNode SHALL 缓存最新的 map_data、width、height、origin 和 resolution

### 需求 12：坐标转换

**用户故事：** 作为探索系统，我需要在世界坐标和栅格坐标之间正确转换，以便将地图分析结果转化为导航目标。

#### 验收标准

1. THE FrontierSearch SHALL 使用公式 `wx = origin_x + (gx + 0.5) × resolution` 将栅格 x 坐标转换为世界 x 坐标
2. THE FrontierSearch SHALL 使用公式 `wy = origin_y + (gy + 0.5) × resolution` 将栅格 y 坐标转换为世界 y 坐标
3. THE FrontierSearch SHALL 使用公式 `gx = int((wx - origin_x) / resolution)` 将世界 x 坐标转换为栅格 x 坐标
4. THE FrontierSearch SHALL 使用公式 `idx = gy × width + gx` 将栅格坐标转换为一维索引
