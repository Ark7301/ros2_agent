# MOSAIC Demo — 智能机器人 Agent 交互系统

MOSAIC（Modular Open-Source Agent for Intelligent Control）初期验证 Demo，演示基于 LLM 的机器人自然语言任务调度系统。

用户通过自然语言下达指令（如"导航到厨房"），系统自动完成 **意图解析 → 任务规划 → 执行调度** 全流程。

## 系统架构

```
用户输入 → CLIInterface → TaskParser(LLM) → TaskPlanner → TaskExecutor → Mock能力模块
                                ↑                ↑              ↑
                         MiniMaxProvider   CapabilityRegistry   重试/退避
                      (Anthropic Tool Use)  (意图→能力映射)
```

核心模块：

| 模块 | 路径 | 职责 |
|------|------|------|
| CLI 交互界面 | `interfaces/cli_interface.py` | 接收自然语言输入，展示执行结果 |
| 任务解析器 | `agent_core/task_parser.py` | 通过 LLM Function Calling 解析意图 |
| 任务规划器 | `agent_core/task_planner.py` | 将意图映射为有序执行计划 |
| 任务执行器 | `agent_core/task_executor.py` | 优先级队列调度，指数退避重试 |
| 能力注册中心 | `interfaces_abstract/capability_registry.py` | 管理能力注册与意图解析 |
| Mock 导航 | `capabilities/mock_navigation.py` | 模拟导航能力（navigate_to / patrol） |
| Mock 运动 | `capabilities/mock_motion.py` | 模拟运动能力（rotate / stop） |
| 地名服务 | `capabilities/location_service.py` | 语义地名 → 坐标映射 |
| MiniMax Provider | `model_providers/minimax_provider.py` | MiniMax Anthropic Tool Use 意图解析（单轮 Function Call） |
| MiniMax 客户端 | `model_providers/minimax_client.py` | MiniMax Anthropic 兼容 API 客户端（支持 Thinking / Tool Use） |
| LLM Provider | `model_providers/llm_provider.py` | 美的 AIMP Claude API 调用封装（备用） |
| 美的 AIMP 客户端 | `model_providers/midea_client.py` | 美的 AIMP Claude API 异步客户端（指数退避重试） |
| 配置管理 | `config/config_manager.py` | YAML 配置加载与嵌套查询 |

## 环境要求

- Python 3.10+
- 依赖包：
  - `pyyaml` — YAML 配置解析
  - `httpx` — 异步 HTTP 客户端（调用 OpenAI API）

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd ros2_agent

# 安装依赖
pip install pyyaml httpx
```

## 配置

### 1. 设置 API Key

系统通过环境变量读取 API 密钥，禁止硬编码：

```bash
# 美的 AIMP（默认使用）
export MIDEA_API_KEY="your-midea-api-key-here"

# OpenAI（如需切换回 OpenAI 时使用）
export OPENAI_API_KEY="your-api-key-here"

# MiniMax（如需使用 MiniMax API）
export MINIMAX_API_KEY="your-minimax-api-key-here"
```

### 2. 模型配置

编辑 `mosaic_demo/config/agent_config.yaml`：

```yaml
model_provider:
  type: "llm"
  config:
    model: "gpt-4"              # 模型名称，支持 gpt-4 / gpt-3.5-turbo 等
    api_base: "https://api.openai.com/v1"  # API 地址，可替换为兼容接口
    temperature: 0.1            # 生成温度，越低越确定
    timeout: 30                 # 请求超时（秒）

retry:
  max_retries: 3                # 最大重试次数
  backoff_base: 2               # 指数退避基数

logging:
  level: "INFO"                 # 日志级别：DEBUG / INFO / WARNING / ERROR
```

> 如果使用兼容 OpenAI 接口的第三方服务（如 Azure OpenAI、本地部署模型），修改 `api_base` 即可。

### 3. 地名配置

编辑 `mosaic_demo/config/locations.yaml` 添加语义地名映射：

```yaml
locations:
  厨房: {x: 2.0, y: 3.5, theta: 0.0}
  客厅: {x: 0.0, y: 0.0, theta: 0.0}
  卧室: {x: -1.0, y: 2.0, theta: 1.57}
  充电桩: {x: 0.0, y: 0.0, theta: 0.0}
  大门: {x: 3.0, y: -1.0, theta: 3.14}
```

## 启动

```bash
python -m mosaic_demo.main
```

启动后进入交互界面：

```
==================================================
  MOSAIC Demo — 智能 Agent 交互系统
  输入自然语言指令，例如：导航到厨房
  输入 '退出' 或 'exit' 关闭系统
==================================================
>>>
```

## 使用示例

### 导航指令

```
>>> 导航到厨房
正在处理...
✓ 已到达厨房

>>> 去卧室
正在处理...
✓ 已到达卧室
```

### 运动指令

```
>>> 旋转
正在处理...
✓ 运动完成

>>> 停止
正在处理...
✓ 运动完成
```

### 错误处理

```
>>> 导航到阳台
正在处理...
✗ 无法解析目标地名: 阳台（错误: 地名 '阳台' 未在 LocationService 中注册）
```

### 退出系统

```
>>> 退出
再见！系统已安全关闭。
```

也可使用 `exit` 或 `Ctrl+C` 退出。

## 支持的意图

| 意图 | 能力模块 | 说明 |
|------|----------|------|
| `navigate_to` | navigation | 导航到指定地点，需要 target 参数 |
| `patrol` | navigation | 巡逻 |
| `rotate` | motion | 旋转 |
| `stop` | motion | 停止运动 |

## 处理流程

1. 用户输入自然语言 → `CLIInterface` 封装为 `TaskContext`
2. `TaskParser` 调用 LLM（Anthropic Tool Use）解析为 `TaskResult`（包含 intent + params），支持多轮 tool call 对话
3. `TaskPlanner` 通过 `CapabilityRegistry` 将意图映射为 `ExecutionPlan`
4. `TaskExecutor` 按序执行计划中的每个动作，失败时指数退避重试
5. 执行结果 `ExecutionResult` 回传至 CLI 展示

## 扩展开发

### 添加新能力

1. 继承 `Capability` 抽象基类：

```python
from mosaic_demo.interfaces_abstract.capability import Capability
from mosaic_demo.interfaces_abstract.data_models import (
    CapabilityStatus, ExecutionResult, Task, TaskStatus,
)

class MyCapability(Capability):
    def get_name(self) -> str:
        return "my_capability"

    def get_supported_intents(self) -> list[str]:
        return ["my_intent"]

    async def execute(self, task, feedback_callback=None) -> ExecutionResult:
        # 实现执行逻辑
        return ExecutionResult(
            task_id=task.task_id,
            success=True,
            message="执行完成",
            status=TaskStatus.SUCCEEDED,
        )

    async def cancel(self) -> bool:
        return True

    async def get_status(self) -> CapabilityStatus:
        return CapabilityStatus.IDLE

    def get_capability_description(self) -> str:
        return "我的自定义能力"
```

2. 在 `main.py` 中注册：

```python
my_capability = MyCapability()
registry.register(my_capability)
```

### 添加新地名

在 `locations.yaml` 中添加条目，或运行时通过 `LocationService.add_location()` 动态添加。

## 运行测试

```bash
pytest test/ -v
```

## 项目结构

```
mosaic_demo/
├── main.py                          # 入口文件
├── config/
│   ├── agent_config.yaml            # Agent 配置
│   ├── locations.yaml               # 地名映射
│   └── config_manager.py            # 配置管理器
├── agent_core/
│   ├── task_parser.py               # 任务解析器（LLM 意图解析）
│   ├── task_planner.py              # 任务规划器（意图→执行计划）
│   └── task_executor.py             # 任务执行器（优先级队列+重试）
├── capabilities/
│   ├── mock_navigation.py           # Mock 导航能力
│   ├── mock_motion.py               # Mock 运动能力
│   └── location_service.py          # 语义地名服务
├── model_providers/
│   ├── llm_provider.py              # LLM Provider（Function Calling）
│   ├── midea_client.py              # 美的 AIMP Claude API 异步客户端
│   ├── minimax_client.py            # MiniMax Anthropic 兼容 API 客户端
│   └── openai_client.py             # OpenAI 异步客户端
├── interfaces/
│   └── cli_interface.py             # CLI 交互界面
└── interfaces_abstract/
    ├── capability.py                # Capability 抽象基类
    ├── capability_registry.py       # 能力注册中心
    ├── data_models.py               # 核心数据模型
    └── model_provider.py            # ModelProvider 抽象基类
```
