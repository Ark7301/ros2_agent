# Implementation Plan: MOSAIC 初期验证 Demo 骨架

## Overview

基于设计文档的分层架构，按自底向上的顺序实现：数据模型 → 抽象接口 → 基础服务（配置/地名） → Agent 核心（Registry/Parser/Planner/Executor） → AI Provider → Mock Capability → CLI → 集成串联。每步增量构建，测试紧跟实现。

## Tasks

- [x] 1. 搭建项目结构与核心数据模型
  - [x] 1.1 创建项目目录结构和 `__init__.py` 文件
    - 创建 `mosaic_demo/` 及其子目录：`interfaces_abstract/`、`agent_core/`、`model_providers/`、`capabilities/`、`interfaces/`、`config/`
    - 每个 Python 包创建 `__init__.py`
    - 创建 `mosaic_demo/main.py` 入口文件（空骨架）
    - _Requirements: 1.5_

  - [x] 1.2 实现核心数据模型 `data_models.py`
    - 在 `mosaic_demo/interfaces_abstract/data_models.py` 中实现所有数据结构
    - 包含 `TaskStatus`、`CapabilityStatus` 枚举
    - 包含 `TaskContext`、`TaskResult`、`Task`、`PlannedAction`、`ExecutionPlan`、`ExecutionResult`、`CapabilityInfo` dataclass
    - 实现 `TaskResult.to_dict` 和 `TaskResult.from_dict` 方法
    - 实现 `ExecutionPlan.peek_next`、`advance`、`is_complete` 方法
    - _Requirements: 12.1, 12.2, 12.3_

  - [x] 1.3 编写 TaskResult 序列化 round-trip 属性测试
    - 在 `test/mosaic_demo/test_data_models.py` 中编写
    - **Property 12: TaskResult 序列化 round-trip**
    - **Validates: Requirements 12.3**

  - [x] 1.4 编写数据模型单元测试
    - 测试 `TaskStatus`、`CapabilityStatus` 枚举值
    - 测试 `ExecutionPlan` 的 `peek_next`、`advance`、`is_complete` 逻辑
    - 测试 `TaskResult.to_dict` 和 `TaskResult.from_dict` 基本用例
    - _Requirements: 12.1, 12.2_

- [x] 2. 实现抽象接口层
  - [x] 2.1 实现 ModelProvider 抽象基类
    - 在 `mosaic_demo/interfaces_abstract/model_provider.py` 中定义
    - 定义 `parse_task` 异步抽象方法和 `get_supported_intents` 方法
    - _Requirements: 1.1, 1.2_

  - [x] 2.2 实现 Capability 抽象基类
    - 在 `mosaic_demo/interfaces_abstract/capability.py` 中定义
    - 定义 `get_name`、`get_supported_intents`、`execute`、`cancel`、`get_status`、`get_capability_description` 抽象方法
    - _Requirements: 1.3, 1.4_

  - [x] 2.3 实现 CapabilityRegistry
    - 在 `mosaic_demo/interfaces_abstract/capability_registry.py` 中实现
    - 实现 `register`、`unregister`、`resolve`、`list_capabilities` 方法
    - `resolve` 未注册意图时抛出包含明确错误信息的异常
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 2.4 编写 CapabilityRegistry 注册-解析 round-trip 属性测试
    - **Property 1: CapabilityRegistry 注册-解析 round-trip**
    - **Validates: Requirements 2.1, 2.2**

  - [x] 2.5 编写 CapabilityRegistry 注销后不可解析属性测试
    - **Property 2: CapabilityRegistry 注销后不可解析**
    - **Validates: Requirements 2.3, 2.4**

  - [x] 2.6 编写未注册意图解析错误属性测试
    - **Property 3: 未注册意图解析错误**
    - **Validates: Requirements 2.3**

- [x] 3. Checkpoint - 确保基础层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 实现配置管理与地名服务
  - [x] 4.1 实现 ConfigManager
    - 在 `mosaic_demo/config/` 下创建 `config_manager.py`
    - 实现 YAML 配置加载、`get` 方法（支持默认值）
    - 配置文件格式错误或不存在时报告明确错误并拒绝启动
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 4.2 编写 ConfigManager 查询默认值属性测试
    - **Property 16: ConfigManager 查询默认值**
    - **Validates: Requirements 11.2**

  - [x] 4.3 创建配置文件
    - 创建 `mosaic_demo/config/agent_config.yaml`（model_provider、capabilities、retry、logging 配置）
    - 创建 `mosaic_demo/config/locations.yaml`（厨房、客厅、卧室、充电桩、大门坐标映射）
    - _Requirements: 9.4, 11.1_

  - [x] 4.4 实现 LocationService
    - 在 `mosaic_demo/capabilities/location_service.py` 中实现
    - 实现 `load`（从 YAML 加载）、`resolve_location`、`add_location`、`list_locations` 方法
    - 未注册地名返回 None
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 4.5 编写 LocationService 添加-查询 round-trip 属性测试
    - **Property 10: LocationService 添加-查询 round-trip**
    - **Validates: Requirements 8.2, 8.4**

  - [x] 4.6 编写 LocationService 未注册地名返回 None 属性测试
    - **Property 11: LocationService 未注册地名返回 None**
    - **Validates: Requirements 8.3**

- [x] 5. 实现 Agent 核心调度层
  - [x] 5.1 实现 TaskParser
    - 在 `mosaic_demo/agent_core/task_parser.py` 中实现
    - 委托 ModelProvider 解析，校验 TaskResult 合法性（intent 非空）
    - intent 为空时返回包含错误信息的结果
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 5.2 编写 TaskParser 空意图拒绝属性测试
    - **Property 4: TaskParser 验证 — 空意图拒绝**
    - **Validates: Requirements 3.2, 3.3**

  - [x] 5.3 实现 TaskPlanner（Demo 简化版）
    - 在 `mosaic_demo/agent_core/task_planner.py` 中实现
    - 单意图 TaskResult → 单动作 ExecutionPlan
    - 多子任务 TaskResult → 有序动作序列
    - 无法解析意图时返回错误
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 5.4 编写 TaskPlanner 单意图映射属性测试
    - **Property 5: TaskPlanner 单意图映射**
    - **Validates: Requirements 4.1**

  - [x] 5.5 编写 TaskPlanner 多子任务映射属性测试
    - **Property 6: TaskPlanner 多子任务映射**
    - **Validates: Requirements 4.2**

  - [x] 5.6 实现 TaskExecutor
    - 在 `mosaic_demo/agent_core/task_executor.py` 中实现
    - 实现优先级队列、按序执行 ExecutionPlan
    - 实现状态流转：PENDING → EXECUTING → SUCCEEDED/FAILED/CANCELLED
    - 实现配置化重试策略和取消功能
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 5.7 编写 TaskExecutor 状态机合法转换属性测试
    - **Property 7: TaskExecutor 状态机合法转换**
    - **Validates: Requirements 5.2, 5.3, 5.7**

  - [x] 5.8 编写 TaskExecutor 执行顺序保持属性测试
    - **Property 8: TaskExecutor 执行顺序保持**
    - **Validates: Requirements 5.1**

  - [x] 5.9 编写 TaskExecutor 重试行为属性测试
    - **Property 9: TaskExecutor 重试行为**
    - **Validates: Requirements 5.4, 5.5**

- [x] 6. Checkpoint - 确保核心调度层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. 实现 AI Provider 层
  - [x] 7.1 实现 OpenAIClient
    - 在 `mosaic_demo/model_providers/openai_client.py` 中实现
    - 使用 httpx 异步 HTTP 调用
    - 实现指数退避重试（最多 3 次）
    - 从 YAML 配置读取 API 参数，从环境变量读取 API 密钥
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 7.2 编写 OpenAIClient 重试次数上限属性测试
    - **Property 17: OpenAIClient 重试次数上限**
    - **Validates: Requirements 9.2, 9.3**

  - [x] 7.3 实现 LLMProvider
    - 在 `mosaic_demo/model_providers/llm_provider.py` 中实现
    - 从 CapabilityRegistry 动态获取意图列表，生成 Function Calling schema
    - 将 Function Calling 响应解析为 TaskResult
    - 重试耗尽后返回包含 "LLM 调用失败" 信息的 ExecutionResult
    - _Requirements: 3.4, 3.5, 13.3_

  - [x] 7.4 编写 Function Calling 响应解析属性测试
    - **Property 19: Function Calling 响应解析**
    - **Validates: Requirements 3.5**

- [x] 8. 实现 Mock Capability 模块
  - [x] 8.1 实现 MockNavigationCapability
    - 在 `mosaic_demo/capabilities/mock_navigation.py` 中实现
    - 支持 `navigate_to` 和 `patrol` 意图
    - 通过 LocationService 解析地名，模拟异步延迟
    - 地名无法解析时返回错误 ExecutionResult
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [x] 8.2 编写 MockNavigationCapability 成功结果包含地名属性测试
    - **Property 18: MockNavigationCapability 成功结果包含地名**
    - **Validates: Requirements 6.3**

  - [x] 8.3 实现 MockMotionCapability
    - 在 `mosaic_demo/capabilities/mock_motion.py` 中实现
    - 支持 `rotate` 和 `stop` 意图
    - 模拟异步执行并返回成功 ExecutionResult
    - _Requirements: 7.1, 7.2_

- [x] 9. 实现 CLI 交互接口
  - [x] 9.1 实现 CLIInterface
    - 在 `mosaic_demo/interfaces/cli_interface.py` 中实现
    - 交互式循环，将用户输入封装为 TaskContext
    - 将 ExecutionResult 格式化为中文可读文本
    - 支持 "退出"/"exit" 安全关闭
    - 异常时显示友好中文错误提示，保持系统可用
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5_

  - [x] 9.2 编写 CLIInterface 输入封装属性测试
    - **Property 14: CLIInterface 输入封装**
    - **Validates: Requirements 10.2**

  - [x] 9.3 编写 CLIInterface 结果格式化属性测试
    - **Property 15: CLIInterface 结果格式化**
    - **Validates: Requirements 10.3**

- [x] 10. 集成串联与端到端管道
  - [x] 10.1 实现 `main.py` 入口文件
    - 初始化 ConfigManager、LocationService、CapabilityRegistry
    - 注册 MockNavigationCapability 和 MockMotionCapability
    - 初始化 OpenAIClient、LLMProvider、TaskParser、TaskPlanner、TaskExecutor
    - 启动 CLIInterface 主循环
    - _Requirements: 1.5, 2.1_

  - [x] 10.2 编写管道错误传播属性测试
    - **Property 13: 管道错误传播**
    - **Validates: Requirements 13.1, 13.2**

  - [x] 10.3 编写端到端管道集成测试
    - 使用全 Mock 组件测试完整管道：输入 → 解析 → 规划 → 执行 → 结果
    - 验证错误处理路径
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [x] 11. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选，可跳过以加速 MVP
- 每个任务引用具体需求条款，确保可追溯性
- 属性测试放在 `test/mosaic_demo/` 目录下，遵循用户规范
- 所有代码注释使用中文，变量和函数名使用英文
- Python 实现，依赖 httpx、pyyaml、hypothesis、pytest、pytest-asyncio
