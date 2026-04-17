# MOSAIC — 面向 ROS 2 的具身智能 Agent 编排系统

MOSAIC（Modular Orchestration System for Agent-driven Intelligent Control）是一个面向 ROS 2 生态的 AI Agent 机器人任务调度与具身智能编排系统。当前主线聚焦于：

- 以 LLM/ReAct 作为任务决策与工具编排核心
- 以 ARIA 三层记忆作为世界状态与长期记忆中枢
- 以插件化 Capability 封装导航、操作、视觉、人工代理等能力
- 以 VLM 和拓扑语义记忆验证真实世界感知与记忆能力

仓库中仍保留早期 `mosaic_demo/`，用于简单自然语言任务调度管线验证；但当前主要开发主线已经迁移到 `mosaic/`、`plugins/` 和 `docs/dev/` 下的 MOSAIC v2 架构。

## 当前主线

当前已实现的第一阶段 demo 是 **human-surrogate ARIA memory validation**：

- 开发者手持摄像头，临时充当“机器人身体”
- MOSAIC 向执行人下达移动与观察指令
- 执行人保存并回传 `front / left / right / back` 四向图像路径
- VLM 对四向观察进行语义解析
- ARIA 构建拓扑优先的语义记忆
- 后续任务可以基于记忆选择候选 checkpoint 进行回访

这个阶段不依赖真实机器人本体、Nav2 或 SLAM，目标是先验证 MOSAIC 的真实世界记忆能力与细粒度任务编排能力。

## 快速运行

查看当前 demo 启动信息：

```bash
PYTHONPATH=. python3 scripts/run_human_surrogate_memory_demo.py --dry-run
```

正常启动 human-surrogate demo：

```bash
PYTHONPATH=. python3 scripts/run_human_surrogate_memory_demo.py
```

停止 demo：

```bash
Ctrl+C
```

操作员流程见：

- [Human-surrogate memory demo runbook](docs/dev/runbooks/human-surrogate-memory-demo.md)

## 文档入口

- [Documentation Hub](docs/README.md)
- [Developer Documentation](docs/dev/README.md)
- [Research Documentation](docs/research/README.md)
- [Archive](docs/archive/README.md)
- [ARIA-centric architecture status](docs/dev/architecture/2026-04-08-aria-centric-architecture-status.md)
- [Embodied demo brain CTO review](docs/dev/architecture/2026-04-08-embodied-demo-brain-cto-review.md)
- [Human-surrogate ARIA memory validation spec](docs/superpowers/specs/2026-04-12-human-surrogate-aria-memory-validation-design-zh.md)

## 当前架构概览

```text
用户任务
  -> Gateway / Session / TurnRunner
  -> ARIA / WorldStateManager
  -> Capability Plugins
       - human_proxy     # 真人代机执行层
       - vlm_observe     # 四向图像语义观察
       - navigation      # Nav2 / mock 导航能力
       - manipulation    # mock 操作能力
       - appliance       # mock 家电能力
       - motion          # mock 运动能力
  -> ARIA 记忆更新 / 回访候选选择
```

核心运行时模块：

| 模块 | 路径 | 职责 |
|---|---|---|
| GatewayServer | `mosaic/gateway/server.py` | 系统入口，装配插件、会话、路由、TurnRunner、ARIA |
| TurnRunner | `mosaic/runtime/turn_runner.py` | ReAct 循环、工具调用、ARIA 上下文注入 |
| WorldStateManager / ARIA | `mosaic/runtime/world_state_manager.py` | WorkingMemory + SemanticMemory + EpisodicMemory 统一门面 |
| SceneGraphManager | `mosaic/runtime/scene_graph_manager.py` | 场景图生命周期、子图检索、计划验证、执行后更新 |
| Operator Console | `mosaic/runtime/operator_console.py` | 本地 human proxy 操作台状态与 HTTP 控制台 |
| TopologySemanticMapper | `mosaic/runtime/topology_semantic_mapper.py` | checkpoint 拓扑语义地图与目标索引 |
| VLM Pipeline | `mosaic/runtime/vlm_pipeline/` | VLM 结构化观察解析 |
| Plugin Registry | `mosaic/plugin_sdk/registry.py` | 插件发现、slot/provider 管理、依赖注入 |

核心能力插件：

| 插件 | 路径 | 职责 |
|---|---|---|
| Human Proxy | `plugins/capabilities/human_proxy/` | 将移动指令交给真人代机执行，并接收四向图像路径 |
| VLM Observe | `plugins/capabilities/vlm_observe/` | 对四向图像做 VLM 语义观察并聚合结果 |
| Navigation | `plugins/capabilities/navigation/` | Nav2/mock 导航能力 |
| Manipulation | `plugins/capabilities/manipulation/` | mock 物品拿取与递交 |
| Appliance | `plugins/capabilities/appliance/` | mock 家电操作与等待 |
| Motion | `plugins/capabilities/motion/` | mock 旋转与停止 |

## 环境要求

- Python 3.10+
- Python 依赖：
  - `pyyaml`
  - `httpx`
  - `pytest`
  - `hypothesis`
- 如需真实 VLM 调用，需要配置对应 API key。当前仓库已有 MiniMax provider 与 VLM 分析器基础模块。

## 配置

常用配置文件：

| 文件 | 用途 |
|---|---|
| `config/mosaic.yaml` | MOSAIC v2 主配置，含 gateway、plugins、routing、ARIA、VLM、human_proxy 等配置 |
| `config/demo/human_surrogate_memory.yaml` | 第一阶段 human-surrogate demo 配置 |
| `config/demo/human_proxy_protocol.yaml` | 真人代机操作协议默认配置 |
| `config/environments/home.yaml` | 静态家庭环境场景图配置 |

API key 通过环境变量配置，禁止硬编码：

```bash
export MINIMAX_API_KEY="your-minimax-api-key-here"
export MIDEA_API_KEY="your-midea-api-key-here"
export OPENAI_API_KEY="your-openai-api-key-here"
```

## 测试

第一阶段 human-surrogate demo 的 focused suite：

```bash
pytest \
  test/mosaic_v2/test_atomic_action_schema.py \
  test/mosaic_v2/test_human_proxy_capability.py \
  test/mosaic_v2/test_vlm_observe_capability.py \
  test/mosaic_v2/test_topology_semantic_mapper.py \
  test/mosaic_v2/test_recall_revisit_orchestrator.py \
  test/mosaic_v2/test_aria_context_integration.py \
  test/mosaic_v2/test_human_surrogate_demo_e2e.py -q
```

全仓库历史测试入口：

```bash
pytest test/ -v
```

## 当前实现结构

```text
mosaic/
├── gateway/
│   └── server.py
├── runtime/
│   ├── atomic_action_schema.py
│   ├── human_surrogate_models.py
│   ├── operator_console.py
│   ├── planning_context_formatter.py
│   ├── recall_revisit_orchestrator.py
│   ├── scene_graph.py
│   ├── scene_graph_manager.py
│   ├── topology_semantic_mapper.py
│   ├── vlm_pipeline/
│   └── world_state_manager.py
plugins/
├── capabilities/
│   ├── human_proxy/
│   ├── vlm_observe/
│   ├── navigation/
│   ├── manipulation/
│   ├── appliance/
│   └── motion/
├── channels/
├── context_engines/
├── memory/
└── providers/
config/
├── demo/
├── environments/
└── nav2/
docs/
├── dev/
├── research/
├── archive/
└── superpowers/
```

## 历史 Demo

早期 demo 仍保留在 `mosaic_demo/` 下，用于简单自然语言任务调度验证：

```bash
python -m mosaic_demo.main
```

早期 demo 流程：

```text
用户输入 -> CLIInterface -> TaskParser -> TaskPlanner -> TaskExecutor -> Mock能力模块
```

该路径不代表当前主要架构，只作为兼容和历史参考。

## 下一阶段方向

第一阶段已经完成“真人代机 + VLM 在环 + ARIA 记忆构建 + 记忆驱动回访”的可运行闭环。后续建议优先推进：

- 失败反馈后的完整重规划能力
- 记忆召回解释能力
- operator console 产品化
- 更强的 VLM 观察与证据管理
- 真实机器人底盘替换 `HumanProxyCapability`
