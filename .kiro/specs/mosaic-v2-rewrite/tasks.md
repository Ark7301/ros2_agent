# Implementation Plan: MOSAIC v2 全面架构重构

## Overview

基于设计文档的四层架构，按自底向上顺序实现：协议层 → 核心基础设施（EventBus/Hooks/Config）→ 插件 SDK → 控制面（Session/Router）→ 运行时（TurnRunner）→ 节点层 → 插件实现 → 集成串联。每步增量构建，属性测试紧跟实现，使用 Python + pytest + pytest-asyncio + hypothesis。

## Tasks

- [ ] 1. 搭建项目结构与协议层
  - [x] 1.1 创建 v2 项目目录结构
    - 创建 `mosaic/` 包及子目录：`protocol/`、`core/`、`plugin_sdk/`、`gateway/`、`runtime/`、`nodes/`、`observability/`
    - 创建 `plugins/` 目录及子目录：`channels/`、`capabilities/`、`providers/`、`memory/`、`context_engines/`
    - 创建 `config/mosaic.yaml` 配置文件骨架
    - 每个 Python 包创建 `__init__.py`
    - _Requirements: 全局_

  - [x] 1.2 实现协议层数据定义
    - 在 `mosaic/protocol/events.py` 中定义 `EventPriority` 枚举、`Event` frozen dataclass（含 `__lt__`）、`EventHandler` 类型别名
    - 在 `mosaic/protocol/messages.py` 中定义事件类型常量（INBOUND_MESSAGE、OUTBOUND_MESSAGE、TURN_COMPLETE 等）
    - 在 `mosaic/protocol/errors.py` 中定义错误码枚举
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.3 编写 Event 优先级排序属性测试
    - 在 `test/mosaic_v2/test_event_priority.py` 中编写
    - **属性 1: Event 优先级排序**
    - **Validates: Requirements 1.3, 1.4**

- [ ] 2. 实现核心基础设施
  - [x] 2.1 实现 EventBus 异步事件总线
    - 在 `mosaic/core/event_bus.py` 中实现
    - 实现 `on(event_type, handler)` 订阅方法，返回取消订阅回调
    - 实现 `emit(event)` 方法，经过中间件链后放入优先级队列
    - 实现 `start()` 事件分发循环和 `stop()` 停止方法
    - 实现 `use(middleware)` 中间件注册
    - 实现 `_dispatch(event)` 分发逻辑，支持通配符匹配（`*` 和 `a.*`）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9_

  - [x] 2.2 编写 EventBus 中间件拦截属性测试
    - 在 `test/mosaic_v2/test_event_bus.py` 中编写
    - **属性 2: EventBus 中间件拦截**
    - **Validates: Requirements 1.7, 1.8**

  - [x] 2.3 编写 EventBus 通配符匹配属性测试
    - 在 `test/mosaic_v2/test_event_bus.py` 中编写
    - **属性 17: EventBus 通配符匹配**
    - **Validates: Requirements 1.5, 1.6**

  - [x] 2.4 实现 HookManager 生命周期钩子
    - 在 `mosaic/core/hooks.py` 中实现
    - 实现 `on(point, handler, priority)` 注册方法，按 priority 升序排列
    - 实现 `emit(point, context)` 触发方法，支持拦截（handler 返回 False 停止链）
    - 实现 5 秒超时保护和异常跳过
    - 预定义所有钩子点常量
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [x] 2.5 编写 Hook 拦截语义属性测试
    - 在 `test/mosaic_v2/test_hook_manager.py` 中编写
    - **属性 13: Hook 拦截语义**
    - **Validates: Requirement 8.4**

  - [x] 2.6 实现 ConfigManager 配置管理
    - 在 `mosaic/core/config.py` 中实现
    - 实现 `load()` 从 YAML 加载配置
    - 实现 `get(dotpath, default)` 点分路径取值
    - 实现 `reload()` 热重载并通知 listener
    - 实现 `on_change(listener)` 注册变更监听
    - 支持 `${ENV_VAR}` 环境变量引用
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 11.1_

  - [x] 2.7 编写 Config 点分路径等价属性测试
    - 在 `test/mosaic_v2/test_config_manager.py` 中编写
    - **属性 14: Config 点分路径等价**
    - **Validates: Requirement 9.2**

  - [x] 2.8 编写 Config 默认值回退属性测试
    - 在 `test/mosaic_v2/test_config_manager.py` 中编写
    - **属性 15: Config 默认值回退**
    - **Validates: Requirement 9.3**

- [x] 3. Checkpoint - 确保核心基础设施测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. 实现插件 SDK
  - [x] 4.1 实现插件类型定义
    - 在 `mosaic/plugin_sdk/types.py` 中实现
    - 定义 `PluginMeta` frozen dataclass
    - 定义 `HealthState` 枚举、`HealthStatus`、`ExecutionContext`、`ExecutionResult` dataclass
    - 定义 `CapabilityPlugin` Protocol（@runtime_checkable）：meta、get_supported_intents、get_tool_definitions、execute、cancel、health_check
    - 定义 `ProviderPlugin` Protocol：meta、chat、stream、validate_auth，及 `ProviderConfig`、`ProviderResponse` dataclass
    - 定义 `ChannelPlugin` Protocol：meta、start、stop、send、on_message，及 `OutboundMessage`、`SendResult` dataclass
    - 定义 `MemoryPlugin` Protocol：meta、store、search、get、delete，及 `MemoryEntry` dataclass
    - 定义 `ContextEnginePlugin` Protocol：meta、ingest、assemble、compact，及 `AssembleResult`、`CompactResult` dataclass
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 4.2 实现 PluginRegistry 插件注册表
    - 在 `mosaic/plugin_sdk/registry.py` 中实现
    - 实现 `register(plugin_id, factory, kind)` 注册工厂函数并建立 kind 索引
    - 实现 `resolve(plugin_id)` 懒加载 + 缓存（单例语义）
    - 实现 `set_slot(slot_key, plugin_id)` 排他性 Slot（memory / context-engine）
    - 实现 `resolve_slot(slot_key)` 通过 Slot 解析
    - 实现 `set_default_provider(plugin_id)` 和 `resolve_provider(plugin_id)` 非排他 Provider
    - 实现 `list_by_kind(kind)` 列出指定类型插件
    - 实现 `discover(package)` 自动发现插件（使用工厂函数而非实例）
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_

  - [x] 4.3 编写 Plugin 注册-解析 round-trip 属性测试
    - 在 `test/mosaic_v2/test_plugin_registry.py` 中编写
    - **属性 3: Plugin 注册-解析 round-trip**
    - **Validates: Requirements 3.1, 3.2**

  - [x] 4.4 编写 Plugin 单例语义属性测试
    - 在 `test/mosaic_v2/test_plugin_registry.py` 中编写
    - **属性 4: Plugin 单例语义**
    - **Validates: Requirement 3.3**

  - [x] 4.5 编写 Provider 非排他共存属性测试
    - 在 `test/mosaic_v2/test_plugin_registry.py` 中编写
    - **属性 5: Provider 非排他共存**
    - **Validates: Requirement 3.6**

- [ ] 5. 实现控制面
  - [x] 5.1 实现 SessionManager 会话管理
    - 在 `mosaic/gateway/session_manager.py` 中实现
    - 实现 `SessionState` 枚举和 `Session` dataclass
    - 实现 `create_session(agent_id, channel_id)` 含并发限制检查
    - 实现 `run_turn(session_id, user_input, turn_runner)` 含 session 级锁保护
    - 实现 `close_session(session_id)` 关闭会话
    - 实现 `evict_idle_sessions()` 空闲回收
    - 实现状态流转：INITIALIZING → READY → RUNNING ⇄ WAITING → CLOSED，WAITING → SUSPENDED → CLOSED
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10_

  - [x] 5.2 编写 Session 状态机合法转换属性测试
    - 在 `test/mosaic_v2/test_session_manager.py` 中编写
    - **属性 6: Session 状态机合法转换**
    - **Validates: Requirement 4.10**

  - [x] 5.3 编写 Session 并发限制属性测试
    - 在 `test/mosaic_v2/test_session_manager.py` 中编写
    - **属性 7: Session 并发限制**
    - **Validates: Requirements 4.2, 10.4, 11.3**

  - [x] 5.4 编写 Turn 原子性属性测试
    - 在 `test/mosaic_v2/test_session_manager.py` 中编写
    - **属性 8: Turn 原子性**
    - **Validates: Requirements 4.5, 4.6**

  - [x] 5.5 实现 AgentRouter 多层级路由
    - 在 `mosaic/gateway/agent_router.py` 中实现
    - 实现 `RouteBinding` 和 `ResolvedRoute` dataclass
    - 实现 `resolve(context)` 按 priority 升序匹配：session → scene → intent（正则）→ channel → 默认
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 5.6 编写 Router 确定性属性测试
    - 在 `test/mosaic_v2/test_agent_router.py` 中编写
    - **属性 10: Router 确定性**
    - **Validates: Requirements 6.1, 6.6**

- [x] 6. Checkpoint - 确保控制面测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. 实现 Agent 运行时
  - [x] 7.1 实现 TurnRunner 执行引擎
    - 在 `mosaic/runtime/turn_runner.py` 中实现
    - 实现 `TurnResult` dataclass
    - 实现 `run(session, user_input)` 入口方法，含超时保护（asyncio.wait_for）
    - 实现 `_run_react_loop()` ReAct 循环核心：组装上下文 → LLM 推理 → 工具调用 → 循环或返回
    - 实现 `_execute_tools()` 并行工具执行（asyncio.gather），异常封装为 ExecutionResult(success=False)
    - 实现 `_collect_tool_definitions()` 从所有 CapabilityPlugin 收集工具定义
    - 实现 `_resolve_capability_for_tool()` 根据工具名查找对应 Capability
    - 触发 turn.start/turn.end/turn.error 和 llm.before_call/llm.after_call 钩子
    - 实现 Provider 调用指数退避重试（最多 3 次）
    - Turn 完成后通过 ContextEnginePlugin.ingest() 持久化消息
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 10.1, 10.2, 10.3_

  - [x] 7.2 编写 Turn ReAct 循环终止属性测试
    - 在 `test/mosaic_v2/test_turn_runner.py` 中编写
    - **属性 9: Turn ReAct 循环终止**
    - **Validates: Requirements 5.3, 5.5, 5.6, 5.7**

  - [x] 7.3 编写工具并行执行结果完整性属性测试
    - 在 `test/mosaic_v2/test_turn_runner.py` 中编写
    - **属性 16: 工具并行执行结果完整性**
    - **Validates: Requirements 5.10, 5.11, 10.3**

- [ ] 8. 实现节点层
  - [x] 8.1 实现 NodeRegistry 节点注册表
    - 在 `mosaic/nodes/node_registry.py` 中实现
    - 实现 `NodeStatus` 枚举和 `NodeInfo` dataclass
    - 实现 `register(node)` 注册节点并建立 capability 索引
    - 实现 `unregister(node_id)` 注销节点并清理索引
    - 实现 `heartbeat(node_id)` 更新心跳
    - 实现 `resolve_nodes_for_capability(capability)` 按能力查找 CONNECTED 节点
    - 实现 `check_health()` 标记超时节点为 HEARTBEAT_MISS
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 8.2 编写 Node 注册-查找 round-trip 属性测试
    - 在 `test/mosaic_v2/test_node_registry.py` 中编写
    - **属性 11: Node 注册-查找 round-trip**
    - **Validates: Requirement 7.3**

  - [x] 8.3 编写 Node 注销后不可查找属性测试
    - 在 `test/mosaic_v2/test_node_registry.py` 中编写
    - **属性 12: Node 注销后不可查找**
    - **Validates: Requirement 7.4**

- [x] 9. Checkpoint - 确保运行时和节点层测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. 实现插件实现层
  - [x] 10.1 实现 SlidingWindowContextEngine 上下文引擎插件
    - 在 `plugins/context_engines/sliding_window/` 下实现
    - 实现 `ContextEnginePlugin` Protocol：ingest、assemble（token_budget 裁剪）、compact
    - 提供 `create_plugin()` 工厂函数
    - _Requirements: 2.5, 3.1_

  - [x] 10.2 实现 FileMemory 记忆插件
    - 在 `plugins/memory/file_memory/` 下实现
    - 实现 `MemoryPlugin` Protocol：store、search、get、delete
    - 提供 `create_plugin()` 工厂函数
    - _Requirements: 2.4, 3.5_

  - [x] 10.3 实现 MiniMax Provider 插件
    - 在 `plugins/providers/minimax/` 下实现
    - 实现 `ProviderPlugin` Protocol：chat、stream、validate_auth
    - 使用 httpx 异步 HTTP 调用，API 密钥从环境变量读取
    - 提供 `create_plugin()` 工厂函数
    - _Requirements: 2.2, 11.1_

  - [x] 10.4 实现 CLI Channel 插件
    - 在 `plugins/channels/cli/` 下实现
    - 实现 `ChannelPlugin` Protocol：start、stop、send、on_message
    - 交互式循环，支持 "退出"/"exit" 安全关闭
    - 提供 `create_plugin()` 工厂函数
    - _Requirements: 2.3_

  - [x] 10.5 实现 NavigationCapability 导航能力插件
    - 在 `plugins/capabilities/navigation/` 下实现
    - 实现 `CapabilityPlugin` Protocol：get_supported_intents（navigate_to、patrol）、get_tool_definitions、execute、cancel、health_check
    - 提供 `create_plugin()` 工厂函数
    - _Requirements: 2.1_

  - [x] 10.6 实现 MotionCapability 运动控制能力插件
    - 在 `plugins/capabilities/motion/` 下实现
    - 实现 `CapabilityPlugin` Protocol：get_supported_intents（rotate、stop）、get_tool_definitions、execute、cancel、health_check
    - 提供 `create_plugin()` 工厂函数
    - _Requirements: 2.1_

- [ ] 11. 实现 Gateway 网关与配置文件
  - [x] 11.1 创建 YAML 配置文件
    - 创建 `config/mosaic.yaml`，包含 gateway、agents、plugins、channels、nodes、routing 完整配置
    - Provider API 密钥使用 `${ENV_VAR}` 引用
    - _Requirements: 9.1, 11.1_

  - [x] 11.2 实现 Gateway Server 入口
    - 在 `mosaic/gateway/server.py` 中实现
    - 初始化 ConfigManager、EventBus、HookManager、PluginRegistry
    - 调用 `registry.discover()` 自动发现插件
    - 配置 Slot（memory、context-engine）和默认 Provider
    - 初始化 SessionManager、AgentRouter、TurnRunner
    - 启动 EventBus 事件循环
    - 连接 Channel 插件的消息事件到 Gateway 处理流程
    - _Requirements: 全局集成_

- [x] 12. Checkpoint - 确保插件和网关测试通过
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. 集成串联与端到端测试
  - [x] 13.1 实现端到端管道连接
    - 在 `mosaic/__init__.py` 中导出公共 API
    - 确保完整数据流：用户输入 → Channel → EventBus → Gateway → Router → Session → TurnRunner → Provider → Capability → 响应
    - 所有组件通过 EventBus 解耦通信
    - _Requirements: 全局集成_

  - [x] 13.2 编写端到端管道集成测试
    - 在 `test/mosaic_v2/test_e2e_pipeline.py` 中编写
    - 使用全 Mock 组件测试完整管道
    - 验证错误处理路径（Provider 失败、工具执行失败、Session 超限）
    - 验证多 Session 并发控制和隔离
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 11.2, 11.3_

- [x] 14. Final Checkpoint - 确保所有测试通过
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 标记 `*` 的子任务为可选，可跳过以加速 MVP
- 每个任务引用具体需求条款，确保可追溯性
- 属性测试放在 `test/mosaic_v2/` 目录下，遵循用户规范
- 所有代码注释使用中文，变量和函数名使用英文
- Python 实现，依赖 httpx、pyyaml、websockets、hypothesis、pytest、pytest-asyncio
- 代码放在 `mosaic/` 包下（非 `mosaic_demo/`），插件放在 `plugins/` 下
- 属性测试紧跟对应实现任务，确保尽早发现错误
- 17 个正确性属性全部覆盖，每个属性对应独立的测试子任务
