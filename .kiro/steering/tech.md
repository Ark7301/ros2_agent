---
inclusion: always
---

# 技术栈与构建

## 语言与运行时
- Python 3.10+
- 异步编程：asyncio 贯穿全栈

## 核心依赖
- `httpx`：异步 HTTP 客户端（调用 LLM API）
- `pyyaml`：YAML 配置解析
- `pytest` + `pytest-asyncio`：测试框架
- `hypothesis`：属性基测试（Property-Based Testing）

## 架构模式（v2）
- 事件驱动：所有组件通过 EventBus 解耦通信
- 插件协议：基于 Python `Protocol`（零继承耦合），支持 `@runtime_checkable`
- 插件类型：capability / provider / channel / memory / context-engine
- Slot 机制：memory 和 context-engine 为排他性 Slot，provider 支持多实例共存
- ReAct 循环：TurnRunner 实现 LLM 推理 → 工具调用 → 结果反馈的迭代循环
- 场景图（SceneGraph）：用于物理世界状态表征和计划验证

## 配置
- 统一配置文件：`config/mosaic.yaml`
- 支持点分路径查询、环境变量 `${ENV_VAR}` 替换、热重载
- Demo 配置：`mosaic_demo/config/agent_config.yaml` 和 `locations.yaml`

## 常用命令

```bash
# 启动 v1 Demo
python -m mosaic_demo.main

# 启动 v2 Gateway
python3 -c "from mosaic.gateway.server import main; main()"

# 运行测试
pytest test/ -v

# 运行特定模块测试
pytest test/mosaic_v2/ -v
pytest test/mosaic_demo/ -v
```

## 环境变量
```bash
export MINIMAX_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
export MIDEA_API_KEY="your-key"
```
