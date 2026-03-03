# 需求文档

## 简介

本需求文档聚焦于"面向 ROS 2 架构的 AI Agent 机器人任务调度系统"项目初期代码骨架搭建阶段。核心目标是建立 Agent 调度框架的抽象接口体系、插件化架构骨架和基本通信管道，为后续功能迭代提供坚实的架构基础。

重点在于 Agent 化智能调用与调度的框架设计，底层机器人能力（导航、SLAM 等）使用开源方案做 demo 验证。

## 术语表

- **Agent_Core**: AI Agent 核心调度层，负责任务解析、规划和执行调度，仅依赖抽象接口
- **ModelProvider**: AI 模型提供者抽象接口，定义任务解析的统一契约
- **LLMProvider**: ModelProvider 的当前实现，基于 OpenAI GPT Function Calling
- **Capability**: 机器人能力抽象接口，定义能力插件的统一契约（execute, cancel, get_status 等）
- **CapabilityRegistry**: 能力注册中心，管理 Capability 插件的注册、注销和意图解析
- **ROS2_Adapter**: ROS 2 通信适配层抽象接口，隔离 Topic/Service/Action 的版本差异
- **TaskContext**: 任务上下文数据结构，承载用户输入及环境信息
- **TaskResult**: 任务解析结果，包含意图类型和结构化参数
- **ExecutionResult**: 任务执行结果，包含执行状态和反馈信息
- **Intent**: 意图类型标识符，如 navigate_to、patrol、stop 等
- **Function_Calling**: OpenAI GPT 的函数调用机制，将已注册 Capability 暴露为 LLM 可调用函数
- **Location_Service**: 语义地名服务，维护语义地名到地图坐标的映射

## 需求

### 需求 1: 抽象接口层定义

**用户故事:** 作为开发者，我希望系统定义清晰的抽象接口层（ModelProvider、Capability、CapabilityRegistry、ROS2 Adapter），以便所有模块通过接口契约解耦，支持独立替换和扩展。

#### 验收标准

1. THE interfaces_abstract 模块 SHALL 定义 ModelProvider 抽象基类，包含 parse_task(context: TaskContext) -> TaskResult 和 get_supported_intents() -> list[str] 两个抽象方法
2. THE interfaces_abstract 模块 SHALL 定义 Capability 抽象基类，包含 get_name()、get_supported_intents()、execute(task)、cancel() 和 get_status() 五个抽象方法
3. THE interfaces_abstract 模块 SHALL 定义 CapabilityRegistry 接口，包含 register(capability)、unregister(name)、resolve(intent) 和 list_capabilities() 四个方法
4. THE interfaces_abstract 模块 SHALL 定义 ROS2 通信适配器抽象接口，覆盖 Topic 订阅/发布、Service 调用和 Action Client 三种通信模式
5. THE interfaces_abstract 模块 SHALL 定义 TaskContext、TaskResult、ExecutionResult 和 CapabilityStatus 等核心数据结构
6. WHEN 任何具体实现模块导入接口时，THE interfaces_abstract 模块 SHALL 不依赖任何具体实现模块（依赖方向：具体实现 → 抽象接口）

### 需求 2: Agent 核心调度骨架

**用户故事:** 作为开发者，我希望 Agent 核心层实现任务解析、规划和执行的调度骨架，以便自然语言指令能通过标准管道流转到 Capability 执行。

#### 验收标准

1. THE Agent_Core 的 TaskParser SHALL 通过调用 ModelProvider.parse_task() 将自然语言输入转化为结构化的 TaskResult
2. THE Agent_Core 的 TaskPlanner SHALL 通过调用 CapabilityRegistry.resolve(intent) 将 TaskResult 中的意图映射到对应的 Capability 实例
3. WHEN 用户输入包含多步骤复合指令时，THE TaskPlanner SHALL 将其分解为有序的子任务序列
4. THE Agent_Core 的 TaskExecutor SHALL 通过调用 Capability.execute(task) 统一调度任务执行，不直接操作 ROS 2 通信接口
5. THE Agent_Core 的 TaskQueue SHALL 维护待执行任务的优先级队列，支持任务的入队、取消和按序调度
6. WHEN 任务执行状态发生变化时，THE TaskExecutor SHALL 跟踪状态流转：PENDING → EXECUTING → SUCCEEDED / FAILED / CANCELLED
7. IF 任务执行失败，THEN THE TaskExecutor SHALL 根据配置的重试策略进行自动重试

### 需求 3: Capability 能力插件机制

**用户故事:** 作为开发者，我希望系统提供可插拔的 Capability 插件机制，以便新增机器人能力只需实现 Capability 接口并注册，无需修改 Agent 核心代码。

#### 验收标准

1. THE CapabilityRegistry SHALL 支持运行时动态注册和注销 Capability 插件
2. WHEN 新的 Capability 注册到 CapabilityRegistry 时，THE CapabilityRegistry SHALL 自动将该 Capability 支持的意图类型纳入可解析范围
3. WHEN CapabilityRegistry.resolve(intent) 被调用时，THE CapabilityRegistry SHALL 返回能处理该意图的 Capability 实例
4. IF resolve(intent) 找不到匹配的 Capability，THEN THE CapabilityRegistry SHALL 返回明确的错误信息，指明该意图无已注册的处理能力
5. THE CapabilityRegistry.list_capabilities() SHALL 返回所有已注册 Capability 的名称及其支持的意图列表
6. WHEN 系统启动时，THE CapabilityRegistry SHALL 根据配置文件（agent_config.yaml）中声明的 Capability 列表自动加载并注册对应插件


### 需求 4: ModelProvider 与 LLM 集成骨架

**用户故事:** 作为开发者，我希望系统提供 ModelProvider 插件机制和 LLMProvider 的骨架实现，以便通过 OpenAI Function Calling 实现自然语言到结构化任务的转换。

#### 验收标准

1. THE LLMProvider SHALL 实现 ModelProvider 抽象接口，通过 OpenAI GPT Function Calling 机制解析自然语言指令
2. THE LLMProvider SHALL 从 CapabilityRegistry 动态获取已注册 Capability 的意图列表，自动生成 Function Calling 的函数定义
3. THE llm_client 模块 SHALL 封装 OpenAI API 的异步 HTTP 调用，支持配置 API endpoint、API key、模型选择和超时时间
4. THE llm_client 模块 SHALL 通过 YAML 配置文件管理所有 API 参数，API 密钥通过环境变量注入，禁止硬编码
5. IF LLM API 调用失败，THEN THE llm_client SHALL 执行指数退避重试策略，最多重试 3 次
6. IF 重试耗尽仍失败，THEN THE LLMProvider SHALL 返回明确的错误结果，包含失败原因，系统进入降级状态但不崩溃

### 需求 5: ROS 2 通信适配层骨架

**用户故事:** 作为开发者，我希望系统提供 ROS 2 通信适配层的骨架实现（Topic/Service/Action Adapter），以便 Capability 插件通过统一接口与 ROS 2 交互，隔离版本差异。

#### 验收标准

1. THE TopicAdapter SHALL 提供统一的 Topic 订阅和发布接口，封装 rclpy 的 Publisher/Subscription 创建和消息收发
2. THE ServiceAdapter SHALL 提供统一的 Service 客户端接口，封装 rclpy 的 Service Client 创建和异步调用
3. THE ActionAdapter SHALL 提供统一的 Action Client 接口，封装目标发送、反馈监听、结果获取和取消操作
4. THE ActionAdapter SHALL 支持动态注册新的 Action 类型，Capability 插件通过 ActionAdapter 与 ROS 2 Action Server 交互
5. THE ROS2_Adapter 层 SHALL 仅使用 rclpy 稳定公共 API，显式声明 QoS Profile，不依赖 ROS 2 发行版的默认值
6. WHEN Capability 插件调用 ROS2_Adapter 时，THE ROS2_Adapter SHALL 隔离所有与 ROS 2 版本相关的实现细节，上层代码不直接调用 rclpy

### 需求 6: Demo 级 Capability 实现

**用户故事:** 作为开发者，我希望系统提供基于开源方案（Nav2、SLAM Toolbox）的 Demo 级 Capability 实现，以便验证 Agent 调度框架的端到端可行性。

#### 验收标准

1. THE NavigationCapability SHALL 实现 Capability 接口，内部封装 Nav2 的 NavigateToPose Action 调用，支持 navigate_to 和 patrol 意图
2. THE MappingCapability SHALL 实现 Capability 接口，内部封装 SLAM Toolbox 的建图启停和地图保存操作，支持 start_mapping、save_map 和 stop_mapping 意图
3. THE MotionCapability SHALL 实现 Capability 接口，支持 rotate 和 stop 基础运动意图
4. THE Location_Service SHALL 维护语义地名到地图坐标的 YAML 映射表（locations.yaml），支持运行时查询、添加和修改
5. WHEN NavigationCapability 接收到包含语义地名的任务时，THE NavigationCapability SHALL 通过 Location_Service 将语义地名解析为地图坐标

### 需求 7: 配置管理与项目结构

**用户故事:** 作为开发者，我希望项目具备规范的 ROS 2 包结构和 YAML 配置体系，以便系统可通过配置文件管理 Provider 选择、Capability 加载列表和运行参数。

#### 验收标准

1. THE 项目 SHALL 遵循 ROS 2 Python 包规范，包含 setup.py、package.xml 和标准目录结构
2. THE agent_config.yaml SHALL 声明系统运行配置，包括 ModelProvider 选择、Capability 加载列表、重试策略和日志级别
3. THE locations.yaml SHALL 定义语义地名到坐标的映射，支持运行时热加载
4. THE launch 目录 SHALL 包含 Agent 核心启动文件（版本无关）和按 ROS 2 发行版分离的仿真启动文件
5. WHEN 系统启动时，THE Agent_Core SHALL 读取 agent_config.yaml 加载配置，根据配置初始化 ModelProvider 和 CapabilityRegistry

### 需求 8: CLI 交互接口骨架

**用户故事:** 作为操作员，我希望通过命令行界面输入自然语言指令与机器人交互，以便无需编程即可控制机器人执行任务。

#### 验收标准

1. THE CLI_Interface SHALL 提供交互式命令行界面，接收用户自然语言输入并传递给 Agent_Core 处理
2. THE CLI_Interface SHALL 支持中文和英文指令输入
3. WHEN Agent_Core 返回执行结果或反馈信息时，THE CLI_Interface SHALL 将其转化为用户可读的中文文本输出
4. WHEN 用户输入 "退出" 或 "exit" 时，THE CLI_Interface SHALL 安全关闭系统，释放所有 ROS 2 资源
5. IF Agent_Core 处理过程中发生异常，THEN THE CLI_Interface SHALL 向用户显示友好的错误提示，系统保持可用状态

### 需求 9: 核心数据流端到端贯通

**用户故事:** 作为开发者，我希望骨架代码能实现从"自然语言输入 → 任务解析 → 能力解析 → Capability 执行"的端到端数据流贯通，以便验证架构设计的可行性。

#### 验收标准

1. WHEN 用户通过 CLI 输入自然语言指令时，THE 系统 SHALL 按以下管道顺序处理：CLI_Interface → TaskParser → TaskPlanner → TaskQueue → TaskExecutor → Capability.execute()
2. THE TaskContext SHALL 在整个管道中传递，包含原始用户输入、解析后的意图、参数和执行上下文
3. WHEN Capability.execute() 完成执行时，THE ExecutionResult SHALL 沿管道回传至 CLI_Interface，向用户展示执行结果
4. FOR ALL 合法的 TaskResult 对象，将其序列化为 JSON 再反序列化 SHALL 产生等价的对象（round-trip 属性）
5. IF 管道中任一环节发生错误，THEN THE 系统 SHALL 将错误信息封装为 ExecutionResult 回传给用户，不产生未处理异常
