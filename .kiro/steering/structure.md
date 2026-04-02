---
inclusion: always
---

# 项目结构

```
├── mosaic/                    # v2 核心框架（事件驱动 + 插件架构）
│   ├── protocol/              #   协议层：事件、消息类型、错误码
│   ├── core/                  #   基础设施：EventBus、HookManager、ConfigManager
│   ├── plugin_sdk/            #   插件 SDK：Protocol 接口定义、PluginRegistry
│   ├── gateway/               #   控制面：GatewayServer、SessionManager、AgentRouter
│   ├── runtime/               #   运行时：TurnRunner（ReAct 循环）、SceneGraph
│   ├── nodes/                 #   节点层：NodeRegistry（ROS2 桥接等）
│   └── observability/         #   可观测性（预留）
│
├── plugins/                   # v2 插件实现（按类型分目录）
│   ├── capabilities/          #   能力插件：navigation、motion、manipulation、appliance
│   ├── providers/             #   LLM Provider：minimax
│   ├── channels/              #   通道插件：cli
│   ├── memory/                #   记忆插件：file_memory
│   └── context_engines/       #   上下文引擎：sliding_window
│
├── mosaic_demo/               # v1 验证 Demo（单体架构）
│   ├── agent_core/            #   TaskParser、TaskPlanner、TaskExecutor
│   ├── capabilities/          #   Mock 能力模块
│   ├── model_providers/       #   LLM 客户端封装
│   ├── interfaces/            #   CLI 交互界面
│   ├── interfaces_abstract/   #   抽象基类与数据模型
│   └── config/                #   Demo 配置文件
│
├── config/                    # v2 全局配置
│   └── mosaic.yaml            #   统一配置文件
│
├── test/                      # 测试目录（所有测试必须放这里）
│   ├── mosaic_v2/             #   v2 框架测试
│   └── mosaic_demo/           #   v1 Demo 测试
│
├── docs/                      # 全局文档
├── landing/                   # 项目展示页
└── start.sh                   # v2 Gateway 启动脚本
```

## 约定
- 插件目录名使用下划线（如 `file_memory`），注册后 plugin_id 使用连字符（如 `file-memory`）
- 插件 kind 映射：`capabilities/` → `capability`，`context_engines/` → `context-engine`
- 测试文件只允许放在 `test/` 目录下对应子目录中
- 文档放入对应模块的 `docs/` 文件夹，全局文档放根目录 `docs/`
