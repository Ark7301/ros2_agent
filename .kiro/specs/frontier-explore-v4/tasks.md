# 实现计划：Frontier Explore V4

## 概述

完全重写 `scripts/auto_explore.py`，基于 m-explore-ros2 (explore_lite) 核心算法实现纯 Python 自主探索建图系统。按模块逐步实现：数据结构 → 邻域/坐标工具 → FrontierSearch → BlacklistManager → ProgressMonitor → AutoExploreNode，每步配合属性基测试验证正确性。

## 任务

- [x] 1. 实现基础数据结构与工具函数
  - [x] 1.1 创建 `scripts/auto_explore.py` 基础框架，定义常量和 Frontier dataclass
    - 定义 UNKNOWN、FREE、OCCUPIED_THRESH 等常量
    - 使用 `@dataclass` 定义 Frontier（size, min_distance, cost, centroid, middle, points）
    - _需求: 2.2, 2.3, 2.4_

  - [x] 1.2 实现 nhood4 和 nhood8 邻域计算函数
    - nhood4 返回最多 4 个 4-连通邻居索引，所有索引在有效范围内
    - nhood8 返回最多 8 个 8-连通邻居索引，包含 nhood4 的所有结果
    - 正确处理地图边界（角落、边缘）
    - _需求: 10.1, 10.2, 10.3, 10.4_

  - [x] 1.3 编写 nhood4/nhood8 属性基测试
    - **Property 9: 邻域计算正确性**
    - **验证: 需求 10.1, 10.2, 10.3, 10.4**

  - [x] 1.4 实现坐标转换工具函数（grid↔world, idx↔grid）
    - `idx_to_world(idx, width, origin_x, origin_y, resolution) → (wx, wy)`
    - `world_to_grid(wx, wy, origin_x, origin_y, resolution) → (gx, gy)`
    - `grid_to_idx(gx, gy, width) → idx`
    - _需求: 12.1, 12.2, 12.3, 12.4_

  - [x] 1.5 编写坐标转换 round-trip 属性基测试
    - **Property 10: 坐标转换 round-trip**
    - **验证: 需求 12.1, 12.2, 12.3, 12.4**

- [x] 2. 检查点 — 确保所有测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 3. 实现 FrontierSearch 核心模块
  - [x] 3.1 实现 `_is_new_frontier_cell` 方法
    - 判定 cell 为 Frontier_Cell 当且仅当值为 UNKNOWN 且未标记 frontier_flag 且至少有一个 4-连通 free 邻居
    - _需求: 1.1, 1.2, 1.3_

  - [x] 3.2 编写 frontier cell 判定属性基测试
    - **Property 1: Frontier Cell 判定正确性**
    - **验证: 需求 1.1, 1.2, 1.3**

  - [x] 3.3 实现 `_build_new_frontier` 方法（BFS 聚类）
    - 从初始 frontier cell 出发，BFS 遍历所有 8-连通 frontier cell
    - 计算 centroid（所有点算术平均）、min_distance（最近点距离）、middle（最近点坐标）
    - _需求: 2.1, 2.2, 2.3, 2.4_

  - [x] 3.4 实现 `_frontier_cost` 和 `search_from` 方法
    - cost = min_distance × resolution × potential_scale - size × resolution × gain_scale
    - search_from 从机器人位置 BFS 遍历 free space，检测并聚类 frontier
    - 过滤 size × resolution < min_frontier_size 的 cluster
    - 返回按 cost 升序排列的 frontier 列表
    - 机器人在地图外时返回空列表
    - _需求: 2.5, 3.1, 3.2, 9.3_

  - [x] 3.5 编写 frontier 质心属性基测试
    - **Property 2: Frontier 质心为算术平均**
    - **验证: 需求 2.2**

  - [x] 3.6 编写 frontier min_distance/middle 一致性属性基测试
    - **Property 3: Frontier min_distance 与 middle 一致性**
    - **验证: 需求 2.3, 2.4**

  - [x] 3.7 编写 frontier 最小尺寸过滤属性基测试
    - **Property 4: Frontier 最小尺寸过滤**
    - **验证: 需求 2.5**

  - [x] 3.8 编写 cost 计算与排序属性基测试
    - **Property 5: Cost 计算与排序**
    - **验证: 需求 3.1, 3.2**

  - [x] 3.9 编写地图外坐标返回空列表属性基测试
    - **Property 11: 地图外坐标返回空列表**
    - **验证: 需求 9.3**

- [x] 4. 检查点 — 确保所有测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 5. 实现 BlacklistManager 模块
  - [x] 5.1 实现 BlacklistManager 类
    - `add(point)` 存储世界坐标
    - `is_blacklisted(point)` 使用 tolerance × resolution 容差判定
    - `clear()` 清空所有黑名单点
    - `size` 属性返回当前黑名单大小
    - _需求: 4.1, 4.2, 4.3, 4.4_

  - [x] 5.2 编写黑名单容差判定属性基测试
    - **Property 6: 黑名单容差判定**
    - **验证: 需求 4.1, 4.2, 4.3**

  - [x] 5.3 编写黑名单 clear 属性基测试
    - **Property 7: 黑名单 clear 清空**
    - **验证: 需求 4.4**

- [x] 6. 实现 ProgressMonitor 模块
  - [x] 6.1 实现 ProgressMonitor 类
    - `update(goal, distance, current_time)` 跟踪目标和距离
    - 目标变化或距离减小时重置计时器
    - 超时返回 True
    - `reset()` 重置所有状态
    - _需求: 5.1, 5.2, 5.3, 5.4_

  - [x] 6.2 编写 ProgressMonitor 超时检测属性基测试
    - **Property 8: ProgressMonitor 超时检测**
    - **验证: 需求 5.1, 5.2, 5.3, 5.4**

- [x] 7. 检查点 — 确保所有测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 8. 实现 AutoExploreNode ROS2 主节点
  - [x] 8.1 实现 AutoExploreNode 基础框架
    - 继承 rclpy.Node，初始化 TF2 Buffer、Nav2 ActionClient
    - 订阅 /map (OccupancyGrid)，缓存 map_data、width、height、origin、resolution
    - 启动时阻塞等待 Nav2 action server 连接
    - 创建 PLANNER_HZ 定时器触发 make_plan
    - _需求: 8.1, 9.4, 11.1, 11.2_

  - [x] 8.2 实现 `_get_robot_pose` 和 `_map_callback`
    - 通过 TF2 lookupTransform(map → base_link) 获取机器人位姿
    - TF 异常时记录警告日志并返回 None
    - map_callback 缓存最新地图数据
    - _需求: 8.2, 9.1, 9.2_

  - [x] 8.3 实现 `_make_plan` 主规划循环
    - 获取位姿 → search_from → 遍历 frontier 跳过黑名单 → progress 超时检查 → 发送目标
    - 无 frontier 或全部在黑名单时停止探索
    - 目标未变时不重复发送
    - 超时时拉黑并递归 make_plan
    - _需求: 3.3, 7.1, 7.2, 8.3, 8.4, 8.5_

  - [x] 8.4 实现 `_send_goal` 和 `_goal_result_callback`
    - 发送 NavigateToPose 目标
    - SUCCEEDED 时触发 make_plan
    - ABORTED 时拉黑目标并触发 make_plan
    - CANCELED 时不做额外操作
    - _需求: 6.1, 6.2, 6.3_

  - [x] 8.5 编写 AutoExploreNode 单元测试
    - 测试 make_plan 在无地图时跳过规划
    - 测试 make_plan 在无 frontier 时停止探索
    - 测试导航 ABORTED 时目标被拉黑
    - Mock ROS2 依赖（rclpy、TF2、Nav2 ActionClient）
    - _需求: 6.2, 7.1, 7.2, 9.1, 9.2_

- [x] 9. 集成与入口
  - [x] 9.1 实现 main 入口函数
    - rclpy.init → AutoExploreNode → rclpy.spin → shutdown
    - 添加 `if __name__ == '__main__'` 入口
    - _需求: 8.1_

- [x] 10. 最终检查点 — 确保所有测试通过
  - 确保所有测试通过，如有疑问请询问用户。

## 说明

- 标记 `*` 的任务为可选，可跳过以加速 MVP
- 所有测试文件放在 `test/mosaic_v2/test_auto_explore_v4.py`
- 属性基测试使用 hypothesis 库
- 单元测试使用 pytest + pytest-asyncio
- 每个任务引用具体需求以确保可追溯性
- 检查点确保增量验证
