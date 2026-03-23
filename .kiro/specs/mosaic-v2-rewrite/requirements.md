# 需求文档：MOSAIC v2 全面架构重构

## 简介

本文档定义 MOSAIC v2 的功能需求。v2 是对 v1 线性管道 Demo 的全面重建，目标是构建事件驱动、插件优先、支持多 Agent 协作的机器人智能体框架。采用四层架构：Control Plane → Agent Runtime → Plugin Layer → Node Layer，通过异步 EventBus 解耦所有组件。所有需求从设计文档派生，遵循 EARS 模式和 INCOSE 质量标准。

## 术语表

- **EventBus**: 异步事件总线，系统神经中枢，所有组件通过事件解耦通信
- **Event**: 不可变事件对象，包含 type、payload、source、priority 等字段
- **EventPriority**: 事件优先级枚举（CRITICAL=0, HIGH=1, NORMAL=2, LOW=3）
- **EventHandler**: 异步事件处理函数
- **PluginSDK**: 插件公共接口边界，基于 Python Protocol 定义
- **PluginMeta**: 插件元数据（id, name, version, kind 等）
- **PluginRegistry**: 插件注册表，管理插件的发现、注册、实例化和生命周期
- **PluginFactory**: 返回插件实例的工厂函数
- **CapabilityPlugin**: 能力插件协议（导航/运动/视觉等）
- **ProviderPlugin**: LLM 提供者插件协议（MiniMax/OpenAI/Ollama）
- **ChannelPlugin**: 通道插件协议（CLI/WebSocket/ROS2 Topic）
- **MemoryPlugin**: 记忆插件协议（文件/向量/场景记忆）
- **ContextEnginePlugin**: 上下文引擎插件协议（滑动窗口/摘要/RAG）
- **SessionManager**: 会话管理器，管理 Session 的完整生命周期和并发控制
- **Session**: 会话对象，包含 session_id、agent_id、state、turn_count 等
- **SessionState**: 会话状态枚举（INITIALIZING/READY/RUNNING/WAITING/SUSPENDED/CLOSED）
- **TurnRunner**: Turn 级原子执行器，实现 ReAct 循环
- **TurnResult**: Turn 执行结果，包含 response、tool_calls、execution_results 等
- **AgentRouter**: 多 Agent 路由器，支持多层级优先匹配
- **RouteBinding**: 路由绑定规则
- **ResolvedRoute**: 路由解析结果
- **NodeRegistry**: 节点注册表，管理分布式能力节点
- **NodeInfo**: 节点信息（node_id, capabilities, status 等）
- **NodeStatus**: 节点状态枚举（CONNECTED/HEARTBEAT_MISS/DISCONNECTED）
- **HookManager**: 生命周期钩子管理器
- **ConfigManager**: 配置管理器，支持 YAML 加载和点分路径取值
- **ExecutionContext**: 执行上下文（session_id, turn_id）
- **ExecutionResult**: 执行结果（success, data, message, error）
- **ProviderConfig**: Provider 配置（model, temperature, max_tokens）
- **ProviderResponse**: Provider 响应（content, tool_calls, usage）

## 需求

### 需求 1：异步事件总线

**用户故事：** 作为开发者，我希望系统通过异步事件总线解耦所有组件通信，以便各组件独立演进且支持优先级调度。

#### 验收标准

1. THE EventBus SHALL 提供 `on(event_type, handler)` 方法注册事件处理函数，并返回取消订阅的回调
2. THE EventBus SHALL 提供 `emit(event)` 方法将事件放入优先级队列
3. WHEN EventBus 分发事件时，THE EventBus SHALL 按 EventPriority 值从小到大的顺序出队（CRITICAL 先于 LOW）
4. WHEN 两个 Event 的 priority 相同时，THE EventBus SHALL 按 timestamp 先后顺序出队
5. WHEN 订阅模式为通配符（如 "a.*"）时，THE EventBus SHALL 匹配所有以 "a." 开头的事件类型
6. WHEN 订阅模式为 "*" 时，THE EventBus SHALL 匹配所有事件类型
7. WHEN 中间件链中任一中间件返回 None 时，THE EventBus SHALL 丢弃该事件，不放入队列
8. WHEN 所有中间件返回非 None 时，THE EventBus SHALL 将事件放入优先级队列
9. THE EventBus SHALL 按中间件注册顺序依次执行中间件链

### 需求 2：插件 SDK 与协议定义

**用户故事：** 作为插件开发者，我希望系统提供基于 Python Protocol 的零继承耦合接口，以便编写各类插件而无需继承基类。

#### 验收标准

1. THE CapabilityPlugin Protocol SHALL 定义 `meta`、`get_supported_intents`、`get_tool_definitions`、`execute`、`cancel`、`health_check` 成员
2. THE ProviderPlugin Protocol SHALL 定义 `meta`、`chat`、`stream`、`validate_auth` 成员
3. THE ChannelPlugin Protocol SHALL 定义 `meta`、`start`、`stop`、`send`、`on_message` 成员
4. THE MemoryPlugin Protocol SHALL 定义 `meta`、`store`、`search`、`get`、`delete` 成员
5. THE ContextEnginePlugin Protocol SHALL 定义 `meta`、`ingest`、`assemble`、`compact` 成员
6. THE PluginSDK SHALL 使用 `@runtime_checkable` 装饰器标记所有 Protocol，支持运行时 isinstance 检查
7. THE PluginMeta SHALL 包含 id、name、version、description、kind 字段

### 需求 3：插件注册表

**用户故事：** 作为开发者，我希望通过注册表管理所有插件的发现、注册和实例化，以便实现懒加载和统一管理。

#### 验收标准

1. WHEN 调用 `register(plugin_id, factory, kind)` 时，THE PluginRegistry SHALL 存储工厂函数并建立 kind 索引
2. WHEN 首次调用 `resolve(plugin_id)` 时，THE PluginRegistry SHALL 通过工厂函数创建实例并缓存
3. WHEN 后续调用 `resolve(plugin_id)` 时，THE PluginRegistry SHALL 返回缓存的同一实例（单例语义）
4. WHEN 调用 `resolve(plugin_id)` 且 plugin_id 未注册时，THE PluginRegistry SHALL 抛出 KeyError
5. WHEN 调用 `set_slot(slot_key, plugin_id)` 时，THE PluginRegistry SHALL 设置排他性 Slot（仅 memory 和 context-engine）
6. WHEN 调用 `set_default_provider(plugin_id)` 时，THE PluginRegistry SHALL 设置默认 Provider，且其他已注册 Provider 仍可通过 `resolve(provider_id)` 独立访问
7. WHEN 调用 `discover(package)` 时，THE PluginRegistry SHALL 扫描插件包中的 `create_plugin` 工厂函数并注册
8. WHEN 单个插件加载失败时，THE PluginRegistry SHALL 跳过该插件并继续发现其他插件

### 需求 4：会话管理

**用户故事：** 作为系统，我希望管理 Session 的完整生命周期，以便支持并发控制、状态流转和空闲回收。

#### 验收标准

1. WHEN 调用 `create_session(agent_id, channel_id)` 时，THE SessionManager SHALL 创建状态为 READY 的新 Session
2. WHEN 活跃 Session 数（RUNNING 或 READY 状态）达到 max_concurrent 时，THE SessionManager SHALL 拒绝创建新 Session 并抛出 RuntimeError
3. WHEN 调用 `run_turn(session_id, user_input, turn_runner)` 时，THE SessionManager SHALL 使用 session 级锁保证同一 Session 的 Turn 串行执行
4. WHILE Turn 正在执行，THE SessionManager SHALL 将 Session 状态设为 RUNNING
5. WHEN Turn 执行完成（无论成功或失败）时，THE SessionManager SHALL 将 Session 状态恢复为 WAITING
6. WHEN Turn 执行完成时，THE SessionManager SHALL 将 Session.turn_count 恰好增加 1 并更新 last_active_at
7. WHEN 调用 `run_turn` 且 session_id 不存在时，THE SessionManager SHALL 抛出 KeyError
8. WHEN 调用 `run_turn` 且 Session 状态为 CLOSED 时，THE SessionManager SHALL 抛出 RuntimeError
9. WHEN 调用 `evict_idle_sessions` 时，THE SessionManager SHALL 将状态为 WAITING 且空闲时间超过 idle_timeout_s 的 Session 标记为 SUSPENDED
10. THE Session 状态 SHALL 仅沿以下路径流转：INITIALIZING → READY → RUNNING ⇄ WAITING → CLOSED，或 WAITING → SUSPENDED → CLOSED

### 需求 5：Turn 执行引擎

**用户故事：** 作为系统，我希望通过 ReAct 循环执行 Turn（用户输入 → LLM 推理 → 工具调用 → 响应），以便实现多轮工具调用和自动推理。

#### 验收标准

1. WHEN TurnRunner 接收到用户输入时，THE TurnRunner SHALL 通过 ContextEnginePlugin 组装上下文消息
2. WHEN TurnRunner 接收到用户输入时，THE TurnRunner SHALL 从所有已注册 CapabilityPlugin 收集工具定义
3. WHEN Provider 返回无工具调用的响应时，THE TurnRunner SHALL 终止 ReAct 循环并返回最终响应
4. WHEN Provider 返回包含工具调用的响应时，THE TurnRunner SHALL 并行执行所有工具调用
5. WHEN 工具执行完成时，THE TurnRunner SHALL 将工具结果追加到消息历史并继续 ReAct 循环
6. WHEN ReAct 循环迭代次数达到 max_iterations 时，THE TurnRunner SHALL 抛出 RuntimeError 终止循环
7. WHEN Turn 执行时间超过 turn_timeout_s 时，THE TurnRunner SHALL 通过 asyncio.wait_for 超时终止
8. WHEN Turn 开始和结束时，THE TurnRunner SHALL 通过 HookManager 触发 turn.start 和 turn.end 钩子
9. IF Turn 执行过程中发生异常，THEN THE TurnRunner SHALL 触发 turn.error 钩子
10. WHEN 执行 N 个工具调用时，THE TurnRunner SHALL 返回恰好 N 个结果，顺序与输入一致
11. IF 工具执行抛出异常，THEN THE TurnRunner SHALL 将异常封装为 ExecutionResult(success=False)
12. WHEN Turn 完成时，THE TurnRunner SHALL 通过 ContextEnginePlugin.ingest() 持久化用户消息和助手响应

### 需求 6：Agent 路由

**用户故事：** 作为系统，我希望根据多层级规则将请求路由到对应 Agent，以便支持多 Agent 协作场景。

#### 验收标准

1. THE AgentRouter SHALL 按 RouteBinding 的 priority 值升序匹配（数值越小优先级越高）
2. WHEN context 中的 channel 与 RouteBinding 的 channel 匹配时，THE AgentRouter SHALL 返回该绑定的 agent_id
3. WHEN context 中的 scene 与 RouteBinding 的 scene 匹配时，THE AgentRouter SHALL 返回该绑定的 agent_id
4. WHEN context 中的 intent 与 RouteBinding 的 pattern 正则匹配时，THE AgentRouter SHALL 返回该绑定的 agent_id
5. WHEN 无任何 RouteBinding 匹配时，THE AgentRouter SHALL 返回 default_agent_id
6. THE AgentRouter SHALL 对相同的 context 和 bindings 配置始终返回相同的 ResolvedRoute

### 需求 7：节点注册表

**用户故事：** 作为系统，我希望管理分布在不同硬件上的能力节点，以便根据能力查找可用节点并监控健康状态。

#### 验收标准

1. WHEN 调用 `register(node)` 时，THE NodeRegistry SHALL 存储节点信息并建立 capability 到 node_id 的索引
2. WHEN 调用 `unregister(node_id)` 时，THE NodeRegistry SHALL 移除节点及其所有 capability 索引
3. WHEN 调用 `resolve_nodes_for_capability(capability)` 时，THE NodeRegistry SHALL 返回所有状态为 CONNECTED 且具备该能力的节点列表
4. WHEN 节点已注销时，THE NodeRegistry SHALL 确保通过该节点的 capability 查找不再返回该节点
5. WHEN 调用 `heartbeat(node_id)` 时，THE NodeRegistry SHALL 更新节点的 last_heartbeat 并将状态设为 CONNECTED
6. WHEN 调用 `check_health()` 且节点 last_heartbeat 超过 heartbeat_timeout_s 时，THE NodeRegistry SHALL 将该节点状态标记为 HEARTBEAT_MISS

### 需求 8：生命周期钩子

**用户故事：** 作为开发者，我希望在系统关键生命周期点注册钩子，以便实现日志、监控、权限控制等横切关注点。

#### 验收标准

1. THE HookManager SHALL 支持以下钩子点：gateway.start/stop、session.create/close/idle、turn.start/end/error、llm.before_call/after_call、tool.before_exec/after_exec/permission、node.connect/disconnect/health_change、context.compact/overflow、config.reload
2. WHEN 注册钩子时，THE HookManager SHALL 按 priority 值升序排列（数值越小越先执行）
3. WHEN 触发钩子链时，THE HookManager SHALL 按优先级顺序依次执行 handler
4. WHEN 钩子链中某个 handler 返回 False 时，THE HookManager SHALL 停止执行后续 handler 并返回 False
5. IF 单个 hook handler 执行超过 5 秒，THEN THE HookManager SHALL 超时跳过该 handler 并继续执行后续 handler
6. IF 单个 hook handler 抛出异常，THEN THE HookManager SHALL 跳过该 handler 并继续执行后续 handler

### 需求 9：配置管理

**用户故事：** 作为开发者，我希望通过 YAML 配置文件管理系统参数，并支持点分路径取值和热重载。

#### 验收标准

1. WHEN 调用 `load()` 时，THE ConfigManager SHALL 从指定路径加载 YAML 配置文件
2. WHEN 通过点分路径（如 "gateway.port"）调用 `get(dotpath)` 时，THE ConfigManager SHALL 返回嵌套字典中对应的值
3. WHEN 点分路径指向不存在的键时，THE ConfigManager SHALL 返回指定的默认值
4. WHEN 调用 `reload()` 时，THE ConfigManager SHALL 重新加载配置文件并通知所有已注册的 listener
5. IF 配置文件格式错误或不存在，THEN THE ConfigManager SHALL 抛出异常

### 需求 10：错误处理与恢复

**用户故事：** 作为用户，我希望系统在各阶段出错时能优雅降级并返回有意义的错误信息。

#### 验收标准

1. WHEN Provider API 调用失败时，THE TurnRunner SHALL 使用指数退避策略重试（最多 3 次）
2. IF 重试次数耗尽仍然失败，THEN THE TurnRunner SHALL 返回包含错误信息的 TurnResult
3. WHEN Capability 执行抛出异常时，THE TurnRunner SHALL 通过 asyncio.gather 捕获异常并封装为 ExecutionResult(success=False)
4. WHEN 并发 Session 数达到上限时，THE SessionManager SHALL 拒绝新 Session 并抛出 RuntimeError
5. WHEN 配置文件格式错误时，THE ConfigManager SHALL 在启动时报告明确错误并拒绝启动

### 需求 11：安全与权限

**用户故事：** 作为系统管理员，我希望系统保护敏感信息并支持权限控制，以便防止未授权操作。

#### 验收标准

1. THE ConfigManager SHALL 支持通过 `${ENV_VAR}` 语法引用环境变量，禁止在配置文件中硬编码 API 密钥
2. WHEN 工具执行前，THE HookManager SHALL 触发 tool.permission 钩子，支持权限审批
3. THE SessionManager SHALL 通过 max_concurrent 限制并发 Session 数量，防止资源耗尽
