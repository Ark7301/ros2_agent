# 需求文档：MOSAIC 初期验证 Demo

## 简介

本文档定义 MOSAIC 初期验证 Demo 的功能需求。Demo 目标是验证 Agent 调度框架的端到端可行性：自然语言输入 → LLM 任务解析 → 能力解析 → Capability 执行 → 结果回传。所有需求从设计文档派生，遵循 EARS 模式和 INCOSE 质量标准。

## 术语表

- **Agent**: MOSAIC 系统中负责任务调度的核心组件
- **TaskParser**: 任务解析器，将自然语言指令转换为结构化 TaskResult
- **TaskPlanner**: 任务规划器，将 TaskResult 映射为 ExecutionPlan
- **TaskExecutor**: 任务执行器，按序执行 ExecutionPlan 中的动作
- **ModelProvider**: AI 模型提供者抽象接口
- **LLMProvider**: 基于 OpenAI Function Calling 的 ModelProvider 实现
- **Capability**: 机器人能力抽象接口
- **CapabilityRegistry**: 能力注册中心，管理 Capability 的注册和意图解析
- **MockNavigationCapability**: Mock 导航能力实现
- **MockMotionCapability**: Mock 运动能力实现
- **LocationService**: 语义地名服务，维护地名到坐标的映射
- **CLIInterface**: 交互式命令行界面
- **ConfigManager**: 配置管理器
- **TaskContext**: 任务上下文数据结构
- **TaskResult**: 任务解析结果数据结构
- **ExecutionPlan**: 有序动作序列数据结构
- **ExecutionResult**: 执行结果数据结构
- **TaskStatus**: 任务状态枚举（PENDING / EXECUTING / SUCCEEDED / FAILED / CANCELLED）
- **Function_Calling**: OpenAI 的函数调用机制，用于结构化 LLM 输出

## 需求

### 需求 1：抽象接口定义

**用户故事：** 作为开发者，我希望系统定义清晰的抽象接口，以便 Agent 核心仅依赖抽象而非具体实现，支持后续替换真实模块。

#### 验收标准

1. THE ModelProvider 接口 SHALL 定义 `parse_task` 异步方法，接收 TaskContext 并返回 TaskResult
2. THE ModelProvider 接口 SHALL 定义 `get_supported_intents` 方法，返回支持的意图类型列表
3. THE Capability 接口 SHALL 定义 `get_name`、`get_supported_intents`、`execute`、`cancel`、`get_status`、`get_capability_description` 方法
4. THE Capability 接口的 `execute` 方法 SHALL 接收 Task 和可选的 feedback_callback 参数，返回 ExecutionResult
5. THE Agent 核心模块 SHALL 仅依赖 ModelProvider 和 Capability 抽象接口，不直接依赖具体实现类

### 需求 2：能力注册中心

**用户故事：** 作为开发者，我希望通过注册中心管理所有 Capability，以便根据意图动态解析到对应能力。

#### 验收标准

1. WHEN 一个 Capability 被注册到 CapabilityRegistry 时，THE CapabilityRegistry SHALL 将该 Capability 支持的所有意图纳入可解析范围
2. WHEN 通过意图名称调用 `resolve` 方法时，THE CapabilityRegistry SHALL 返回支持该意图的已注册 Capability 实例
3. WHEN 通过未注册的意图名称调用 `resolve` 方法时，THE CapabilityRegistry SHALL 抛出包含明确错误信息的异常
4. WHEN 一个 Capability 被注销时，THE CapabilityRegistry SHALL 移除该 Capability 及其关联的所有意图映射
5. WHEN 调用 `list_capabilities` 方法时，THE CapabilityRegistry SHALL 返回所有已注册 Capability 的信息列表

### 需求 3：任务解析

**用户故事：** 作为用户，我希望用自然语言描述任务，系统能将其解析为结构化的意图和参数。

#### 验收标准

1. WHEN TaskParser 接收到 TaskContext 时，THE TaskParser SHALL 委托 ModelProvider 解析自然语言并返回 TaskResult
2. WHEN ModelProvider 返回解析结果后，THE TaskParser SHALL 校验 TaskResult 的合法性（intent 非空）
3. IF TaskResult 的 intent 为空，THEN THE TaskParser SHALL 返回包含错误信息的结果
4. THE LLMProvider SHALL 从 CapabilityRegistry 动态获取意图列表，自动生成 Function Calling 的函数定义
5. WHEN LLMProvider 调用 OpenAI API 时，THE LLMProvider SHALL 将 Function Calling 响应解析为 TaskResult

### 需求 4：任务规划

**用户故事：** 作为系统，我希望将解析后的 TaskResult 映射为可执行的 ExecutionPlan，以便 TaskExecutor 按序执行。

#### 验收标准

1. WHEN TaskPlanner 接收到单意图 TaskResult 时，THE TaskPlanner SHALL 通过 CapabilityRegistry 解析意图并生成包含单个动作的 ExecutionPlan
2. WHEN TaskPlanner 接收到包含多个子任务的 TaskResult 时，THE TaskPlanner SHALL 将每个子任务逐个映射为有序动作序列
3. WHEN TaskPlanner 无法解析某个意图时，THE TaskPlanner SHALL 返回包含错误信息的结果

### 需求 5：任务执行

**用户故事：** 作为系统，我希望按计划执行任务并跟踪状态变化，以便向用户反馈执行结果。

#### 验收标准

1. WHEN TaskExecutor 接收到 ExecutionPlan 时，THE TaskExecutor SHALL 按动作序列顺序调用对应 Capability 的 `execute` 方法
2. WHILE 任务正在执行，THE TaskExecutor SHALL 将任务状态从 PENDING 转换为 EXECUTING
3. WHEN Capability 执行成功时，THE TaskExecutor SHALL 将任务状态转换为 SUCCEEDED 并返回成功的 ExecutionResult
4. WHEN Capability 执行失败时，THE TaskExecutor SHALL 按配置的重试策略进行重试
5. IF 重试次数耗尽仍然失败，THEN THE TaskExecutor SHALL 将任务状态转换为 FAILED 并返回包含错误信息的 ExecutionResult
6. WHEN 收到取消请求时，THE TaskExecutor SHALL 调用 Capability 的 `cancel` 方法并将任务状态转换为 CANCELLED
7. THE TaskExecutor SHALL 仅允许合法的状态转换路径（PENDING→EXECUTING→SUCCEEDED/FAILED/CANCELLED）

### 需求 6：Mock 导航能力

**用户故事：** 作为用户，我希望通过自然语言指定导航目标，系统能模拟导航执行并返回结果。

#### 验收标准

1. THE MockNavigationCapability SHALL 支持 `navigate_to` 和 `patrol` 两种意图
2. WHEN 执行 `navigate_to` 意图时，THE MockNavigationCapability SHALL 通过 LocationService 解析目标地名为坐标
3. WHEN 导航执行完成时，THE MockNavigationCapability SHALL 返回包含目标地名的成功 ExecutionResult
4. IF 目标地名无法被 LocationService 解析，THEN THE MockNavigationCapability SHALL 返回包含错误信息的 ExecutionResult

### 需求 7：Mock 运动能力

**用户故事：** 作为用户，我希望通过自然语言控制机器人运动（旋转、停止），系统能模拟执行并返回结果。

#### 验收标准

1. THE MockMotionCapability SHALL 支持 `rotate` 和 `stop` 两种意图
2. WHEN 执行运动意图时，THE MockMotionCapability SHALL 模拟异步执行并返回成功的 ExecutionResult

### 需求 8：语义地名服务

**用户故事：** 作为系统，我希望维护语义地名到坐标的映射，以便导航能力能将用户的自然语言地名转换为坐标。

#### 验收标准

1. WHEN LocationService 启动时，THE LocationService SHALL 从 YAML 配置文件加载地名到坐标的映射
2. WHEN 通过地名查询坐标时，THE LocationService SHALL 返回对应的坐标字典（包含 x、y、theta）
3. WHEN 查询不存在的地名时，THE LocationService SHALL 返回 None
4. WHEN 添加新地名映射时，THE LocationService SHALL 将其纳入可查询范围
5. WHEN 调用 `list_locations` 时，THE LocationService SHALL 返回所有已注册的地名及其坐标

### 需求 9：OpenAI API 客户端

**用户故事：** 作为系统，我希望通过异步客户端调用 OpenAI API，以便完成自然语言解析。

#### 验收标准

1. THE OpenAIClient SHALL 使用 httpx 进行异步 HTTP 调用
2. WHEN API 调用失败时，THE OpenAIClient SHALL 使用指数退避策略重试，最多重试 3 次
3. IF 重试次数耗尽仍然失败，THEN THE OpenAIClient SHALL 返回包含错误信息的异常
4. THE OpenAIClient SHALL 从 YAML 配置文件读取 API 参数（model、api_base、temperature、timeout）
5. THE OpenAIClient SHALL 从环境变量 `OPENAI_API_KEY` 读取 API 密钥，禁止硬编码

### 需求 10：CLI 交互接口

**用户故事：** 作为用户，我希望通过命令行与 Agent 交互，输入自然语言指令并查看执行结果。

#### 验收标准

1. WHEN CLIInterface 启动时，THE CLIInterface SHALL 进入交互式循环，等待用户输入
2. WHEN 用户输入自然语言指令时，THE CLIInterface SHALL 将输入封装为 TaskContext 并传递给 TaskParser
3. WHEN 收到 ExecutionResult 时，THE CLIInterface SHALL 将其格式化为中文可读文本并展示给用户
4. WHEN 用户输入 "退出" 或 "exit" 时，THE CLIInterface SHALL 安全关闭系统
5. IF CLIInterface 处理过程中发生异常，THEN THE CLIInterface SHALL 显示友好的中文错误提示并保持系统可用

### 需求 11：配置管理

**用户故事：** 作为开发者，我希望通过 YAML 配置文件管理系统参数，以便灵活调整系统行为。

#### 验收标准

1. WHEN ConfigManager 初始化时，THE ConfigManager SHALL 从指定路径加载 YAML 配置文件
2. WHEN 通过 key 查询配置项时，THE ConfigManager SHALL 返回对应的值，若不存在则返回默认值
3. IF 配置文件格式错误或不存在，THEN THE ConfigManager SHALL 在启动时报告明确错误并拒绝启动

### 需求 12：数据模型序列化

**用户故事：** 作为开发者，我希望核心数据模型支持序列化和反序列化，以便在系统组件间传递和持久化。

#### 验收标准

1. THE TaskResult SHALL 提供 `to_dict` 方法将实例序列化为字典
2. THE TaskResult SHALL 提供 `from_dict` 类方法从字典反序列化为实例
3. FOR ALL 合法的 TaskResult 实例，序列化后再反序列化 SHALL 产生等价对象（round-trip 属性）

### 需求 13：错误处理与传播

**用户故事：** 作为用户，我希望系统在任何阶段出错时都能返回友好的错误信息，而非崩溃。

#### 验收标准

1. WHEN 管道中任何阶段发生异常时，THE Agent SHALL 将异常封装为包含错误信息的 ExecutionResult 回传给用户
2. THE Agent SHALL 确保不产生未处理异常，所有错误最终通过 ExecutionResult 传达
3. WHEN LLM API 调用失败时，THE LLMProvider SHALL 在重试耗尽后返回包含 "LLM 调用失败" 信息的 ExecutionResult
4. WHEN 意图解析失败时，THE TaskParser SHALL 返回包含 "请重新输入" 提示的 ExecutionResult
