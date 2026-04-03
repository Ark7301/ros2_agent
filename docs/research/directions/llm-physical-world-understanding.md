- title: How LLMs Understand The Physical World
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, directions, llm
- source_type: note

# MOSAIC 核心议题：如何使 LLM 理解物理世界

> LLM 天生是语言的产物，不是物理世界的产物。
> 本文系统分析 MOSAIC 中"让 LLM 理解物理世界"的完整问题空间，
> 提出分层世界表征架构，并给出 MOSAIC 的具体实现路径。

---

## 一、问题的本质：LLM 的认知鸿沟

### 1.1 LLM 知道什么，不知道什么

LLM 从互联网文本中学到了大量关于物理世界的**常识性知识**：

| LLM 知道的（语言先验） | LLM 不知道的（物理现实） |
|----------------------|----------------------|
| 厨房通常有咖啡机 | 这个厨房的咖啡机在哪个位置 |
| 咖啡需要先磨豆再冲泡 | 这台咖啡机是否有咖啡豆 |
| 杯子可以被拿起来 | 这个杯子现在能不能被机械臂够到 |
| 门可以打开和关闭 | 这扇门现在是开着还是关着 |
| 导航需要路径畅通 | 从当前位置到厨房的路径是否被阻塞 |
| 电池没电了需要充电 | 当前电池电量是 23% 还是 87% |
| 热的东西会烫手 | 咖啡杯表面温度是 85°C |

SayCan 论文用一句话概括了这个问题：

> "语言模型可以告诉你如何清理溢出物，但它不知道你面前有没有海绵。"

### 1.2 当前 MOSAIC 的做法：纯文本桥接

看当前 MOSAIC 的 system prompt 和 TurnRunner，LLM 对物理世界的"理解"完全依赖两个文本通道：

**通道 1：System Prompt 中的静态描述**
```yaml
system_prompt: |
  你是 MOSAIC 智能机器人助手，运行在一个具备物理执行能力的机器人平台上。
  你拥有以下能力：navigate_to, pick_up, operate_appliance...
```

这告诉 LLM "你有一个身体"，但没有告诉它身体的**当前状态**。

**通道 2：工具执行结果的文本反馈**
```python
# TurnRunner 中，工具结果以纯文本形式追加到消息历史
tool_content = tr.message if tr.success else f"错误: {tr.error}"
messages.append({"role": "tool", "content": tool_content})
```

比如 `"已导航到 厨房（速度: 0.5）"` — 这只是一个**结果声明**，
LLM 不知道导航花了多久、路上遇到了什么、当前精确位置在哪。

### 1.3 这种做法的根本缺陷

```
当前 MOSAIC 的 LLM 认知模型:

  LLM 的世界认知 = 语言先验（训练数据）
                   + 静态能力描述（system prompt）
                   + 工具结果文本（"已导航到厨房"）

  缺失的关键信息:
  ├── 当前物理状态（位置、姿态、持有物、电量）
  ├── 环境感知（周围物体、障碍物、人的位置）
  ├── 能力可行性（哪些动作当前可执行）
  ├── 执行过程反馈（进度、异常、中间状态）
  └── 历史经验（上次在这个位置做过什么、失败过什么）
```

LLM 在做决策时，实际上是在**想象**一个物理世界，而不是**感知**真实的物理世界。

---

## 二、前沿研究：四种让 LLM 理解物理世界的范式

学术界和工业界正在从不同角度攻克这个问题。梳理四种主要范式：

### 范式 1：文本化世界状态（Text-based World State）

**代表工作**：SayCan (Google, 2022), Inner Monologue (Google, 2022)

**核心思路**：将物理世界状态转化为结构化文本，注入 LLM 的上下文。

```
[机器人状态]
位置: 客厅中央 (x=2.3, y=1.5)
朝向: 面向厨房方向 (yaw=45°)
持有物: 无
电量: 78%
机械臂: 空闲，收起状态

[环境状态]
可见物体: 沙发(左前方2m), 茶几(正前方1.5m), 遥控器(茶几上), 水杯(茶几上)
可通行方向: 前方(厨房), 右方(卧室), 后方(门口)
障碍物: 无
人员: 用户在沙发上

[能力可行性]
navigate_to(厨房): 可行 (路径畅通, 预计12秒)
navigate_to(阳台): 不可行 (门关闭)
pick_up(遥控器): 可行 (在机械臂可达范围内)
pick_up(水杯): 可行 (在机械臂可达范围内)
operate_appliance(灯): 可行 (开关在墙上, 需先导航)
```

**优点**：实现简单，兼容所有 LLM，不需要多模态能力
**缺点**：信息损失大（点云/图像无法完整文本化），token 消耗高，空间关系描述不精确
**适用**：MOSAIC 当前阶段最务实的方案

Inner Monologue 在 SayCan 基础上的关键改进是引入了**闭环反馈**：
将成功检测器、场景描述器、人类反馈等多种信息源持续注入 LLM 的规划提示中，
形成"内心独白"，让 LLM 能根据环境变化调整计划。
（参考：[Inner Monologue](https://inner-monologue.github.io/)）

### 范式 2：场景图表征（Scene Graph Representation）

**代表工作**：VeriGraph (2024), MoMa-LLM (2024), LLM-enhanced Scene Graph (2024)

**核心思路**：将物理环境构建为语义场景图（节点=物体，边=空间/功能关系），
LLM 在场景图上进行推理。

```
场景图示例:
  厨房 ──contains──→ 咖啡机
  厨房 ──contains──→ 冰箱
  咖啡机 ──state:idle──→ ∅
  咖啡机 ──affordance:can_brew──→ true
  茶几 ──on_top──→ 水杯
  茶几 ──on_top──→ 遥控器
  水杯 ──graspable──→ true
  机器人 ──at──→ 客厅
  机器人 ──holding──→ nothing
  用户 ──at──→ 沙发
```

VeriGraph 的创新在于用场景图做**动作可行性验证**：
LLM 生成计划后，在场景图上模拟执行每一步，检查前置条件是否满足。
（参考：[VeriGraph](https://arxiv.org/html/2411.10446v1)）

MoMa-LLM 将场景图与动作空间紧密交织，
在探索环境时动态更新场景图，实现语言落地的移动操作。
（参考：[MoMa-LLM](https://arxiv.org/html/2403.08605v4)）

**优点**：结构化表征，空间关系明确，支持推理验证，可增量更新
**缺点**：场景图构建本身需要视觉感知系统，维护成本高
**适用**：MOSAIC 中期演进方向

### 范式 3：视觉-语言模型直接感知（VLM Direct Perception）

**代表工作**：Physically Grounded VLMs (2023), Goal-VLA (2025), MARVL (2025)

**核心思路**：不再将物理世界转化为文本，而是让模型直接"看"物理世界。
VLM（Vision-Language Model）或 VLA（Vision-Language-Action Model）
直接接收摄像头图像，输出动作决策。

```
输入: 摄像头图像 + 用户指令 "帮我拿桌上的水杯"
  ↓
VLM 直接感知: 识别水杯位置、评估可达性、规划抓取姿态
  ↓
输出: 机械臂轨迹 / 导航目标点
```

Physically Grounded VLMs 的研究发现，
经过物理属性微调的 VLM 能够推理物体的重量、材质、稳定性等物理属性，
从而做出更合理的操作决策。
（参考：[Physically Grounded VLMs](https://arxiv.org/abs/2309.02561)）

**优点**：信息损失最小，端到端，不需要手工设计状态表征
**缺点**：需要多模态模型，计算成本高，可解释性差，当前精度不够
**适用**：MOSAIC 长期方向，但当前技术成熟度不足以作为唯一方案

### 范式 4：世界模型（World Foundation Model）

**代表工作**：NVIDIA Cosmos Reason (2025), Controllable Generative World Model (2025)

**核心思路**：训练一个专门理解物理世界规律的基础模型，
它能预测物理世界的未来状态，为决策提供"如果我这样做，世界会变成什么样"的模拟能力。

NVIDIA Cosmos Reason 是一个 7B 参数的视觉-语言模型，
专门训练用于物理推理：理解空间、时间、物理规律，
能够批判性地评估合成数据的物理合理性。
（参考：[NVIDIA Cosmos](https://nvidianews.nvidia.com/news/nvidia-announces-major-release-of-cosmos-world-foundation-models-and-physical-ai-data-tools)）

```
世界模型的能力:
  当前状态 + 动作 → 预测下一状态
  
  例如: 
  [机器人在客厅] + [navigate_to 厨房] → [机器人在厨房, 电量-3%, 耗时12秒]
  [机械臂伸出] + [抓取杯子] → [杯子在手中, 桌面少了一个杯子]
  [推门] → [门打开, 阳台可通行]
```

**优点**：能预测未来状态，支持"心理模拟"式规划，物理推理能力强
**缺点**：训练成本极高，需要大量物理交互数据，当前仅大公司可用
**适用**：MOSAIC 的远期愿景，当前可关注但不实现

---

## 三、MOSAIC 的分层世界表征架构

综合四种范式，为 MOSAIC 设计一个**分层世界表征架构**，
让 LLM 在不同层次上理解物理世界：

### 3.1 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    LLM 决策引擎                              │
│  接收: 结构化世界状态 + 用户指令 + 历史上下文                  │
│  输出: 任务规划 / 工具调用 / 自然语言响应                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ 文本化的世界表征
┌──────────────────────────┴──────────────────────────────────┐
│              世界表征层（World Representation Layer）         │
│                                                             │
│  ┌─── L3: 任务语境 ──────────────────────────────────────┐  │
│  │  当前任务目标、已完成步骤、待执行步骤、失败历史          │  │
│  │  "正在执行: 做咖啡送给用户, 已完成: 导航到厨房"         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─── L2: 可供性状态（Affordance State）─────────────────┐  │
│  │  每个能力的当前可行性 + 约束条件 + 预估代价              │  │
│  │  navigate_to(厨房): 可行, 12秒, 电量消耗3%              │  │
│  │  pick_up(杯子): 不可行, 原因: 不在机械臂范围内           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─── L1: 环境快照（Environment Snapshot）───────────────┐  │
│  │  物体清单 + 空间关系 + 设备状态 + 人员位置               │  │
│  │  结构化 JSON 或场景图的文本序列化                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─── L0: 机器人自身状态（Robot State）──────────────────┐  │
│  │  位置、朝向、电量、持有物、机械臂状态、运动状态          │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└──────────────────────────┬──────────────────────────────────┘
                           │ 传感器数据 + 内部状态
┌──────────────────────────┴──────────────────────────────────┐
│              物理世界感知层（Physical Perception Layer）       │
│  摄像头、激光雷达、IMU、力传感器、电池监控、ROS2 状态         │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 每一层的职责和数据格式

#### L0: 机器人自身状态

这是最基础的层，告诉 LLM "你的身体现在是什么状态"。

```python
@dataclass
class RobotState:
    """机器人自身状态 — L0 层世界表征"""
    # 位置与姿态
    position: tuple[float, float] = (0.0, 0.0)      # (x, y) 米
    orientation: float = 0.0                          # yaw 角度
    location_name: str = "未知"                       # 语义位置名（客厅/厨房）
    
    # 能量
    battery_percent: float = 100.0
    battery_estimated_minutes: float = 120.0          # 预估剩余时间
    
    # 持有物
    holding_object: str | None = None                 # 当前手持物品
    
    # 机械臂
    arm_state: str = "idle"                           # idle/moving/grasping/error
    arm_payload_kg: float = 0.0                       # 当前负载
    
    # 运动状态
    motion_state: str = "stationary"                  # stationary/navigating/rotating
    current_speed: float = 0.0                        # m/s
    
    def to_prompt_text(self) -> str:
        """转化为 LLM 可理解的文本"""
        lines = [
            "[机器人状态]",
            f"位置: {self.location_name} ({self.position[0]:.1f}, {self.position[1]:.1f})",
            f"朝向: {self.orientation:.0f}°",
            f"电量: {self.battery_percent:.0f}% (预计可用 {self.battery_estimated_minutes:.0f} 分钟)",
            f"手持: {self.holding_object or '无'}",
            f"机械臂: {self.arm_state}",
            f"运动: {self.motion_state}",
        ]
        return "\n".join(lines)
```

#### L1: 环境快照

告诉 LLM "你周围的世界是什么样的"。

```python
@dataclass
class EnvironmentObject:
    """环境中的物体"""
    name: str                                # 物体名称
    category: str                            # 类别（家具/电器/物品/人）
    location: str                            # 所在位置（语义）
    spatial_relation: str                    # 相对机器人的空间关系
    distance_m: float                        # 距离（米）
    state: dict[str, str] = field(default_factory=dict)  # 状态属性

@dataclass
class EnvironmentSnapshot:
    """环境快照 — L1 层世界表征"""
    objects: list[EnvironmentObject]
    accessible_locations: list[str]          # 当前可到达的位置
    blocked_paths: list[str]                 # 被阻塞的路径
    people: list[dict]                       # 人员位置
    
    def to_prompt_text(self) -> str:
        lines = ["[环境状态]"]
        
        # 可见物体
        lines.append("可见物体:")
        for obj in self.objects:
            state_str = ", ".join(f"{k}={v}" for k, v in obj.state.items())
            lines.append(
                f"  - {obj.name} ({obj.category}): "
                f"{obj.spatial_relation} {obj.distance_m:.1f}m"
                f"{', ' + state_str if state_str else ''}"
            )
        
        # 可通行方向
        lines.append(f"可到达位置: {', '.join(self.accessible_locations)}")
        if self.blocked_paths:
            lines.append(f"阻塞路径: {', '.join(self.blocked_paths)}")
        
        # 人员
        for p in self.people:
            lines.append(f"人员: {p.get('name', '用户')} 在 {p.get('location', '未知')}")
        
        return "\n".join(lines)
```

#### L2: 可供性状态

这是 SayCan 的核心——告诉 LLM "你现在能做什么，不能做什么，为什么"。

```python
@dataclass
class AffordanceEntry:
    """单个能力的可供性评估"""
    tool_name: str                           # 工具名
    feasible: bool                           # 是否可行
    confidence: float                        # 可行性置信度 0-1
    reason: str                              # 原因说明
    estimated_duration_s: float = 0.0        # 预估耗时
    estimated_energy_cost: float = 0.0       # 预估能量消耗
    prerequisites: list[str] = field(default_factory=list)  # 前置条件
    risks: list[str] = field(default_factory=list)          # 风险提示

@dataclass
class AffordanceState:
    """可供性状态 — L2 层世界表征"""
    entries: list[AffordanceEntry]
    
    def to_prompt_text(self) -> str:
        lines = ["[能力可行性]"]
        for e in self.entries:
            status = "✓ 可行" if e.feasible else "✗ 不可行"
            line = f"  {e.tool_name}: {status} ({e.confidence:.0%})"
            if e.reason:
                line += f" — {e.reason}"
            if e.estimated_duration_s > 0:
                line += f" [预计 {e.estimated_duration_s:.0f}秒]"
            if e.prerequisites:
                line += f" [前置: {', '.join(e.prerequisites)}]"
            if e.risks:
                line += f" [风险: {', '.join(e.risks)}]"
            lines.append(line)
        return "\n".join(lines)
```

#### L3: 任务语境

告诉 LLM "你正在做什么，做到哪了，之前失败过什么"。

```python
@dataclass
class TaskContext:
    """任务语境 — L3 层世界表征"""
    current_goal: str = ""                   # 当前任务目标
    plan_steps: list[str] = field(default_factory=list)      # 计划步骤
    completed_steps: list[str] = field(default_factory=list)  # 已完成步骤
    current_step: str = ""                   # 当前正在执行的步骤
    failed_attempts: list[dict] = field(default_factory=list) # 失败记录
    
    def to_prompt_text(self) -> str:
        lines = ["[任务状态]"]
        if self.current_goal:
            lines.append(f"目标: {self.current_goal}")
        if self.completed_steps:
            lines.append(f"已完成: {' → '.join(self.completed_steps)}")
        if self.current_step:
            lines.append(f"当前步骤: {self.current_step}")
        remaining = [s for s in self.plan_steps 
                     if s not in self.completed_steps and s != self.current_step]
        if remaining:
            lines.append(f"待执行: {' → '.join(remaining)}")
        if self.failed_attempts:
            lines.append("失败记录:")
            for f in self.failed_attempts[-3:]:  # 只保留最近3次
                lines.append(f"  - {f.get('step', '?')}: {f.get('reason', '?')}")
        return "\n".join(lines)
```

### 3.3 组装完整的世界表征

四层信息在每次 LLM 调用前组装为完整的世界表征，注入 system prompt 或 user message：

```python
class WorldRepresentation:
    """世界表征组装器 — 将四层信息合并为 LLM 可理解的文本"""
    
    def __init__(self):
        self._robot_state = RobotState()
        self._environment = EnvironmentSnapshot(objects=[], accessible_locations=[], 
                                                 blocked_paths=[], people=[])
        self._affordances = AffordanceState(entries=[])
        self._task_context = TaskContext()
    
    def assemble_for_llm(self) -> str:
        """组装完整的世界表征文本，注入 LLM 上下文"""
        sections = [
            self._robot_state.to_prompt_text(),
            self._environment.to_prompt_text(),
            self._affordances.to_prompt_text(),
            self._task_context.to_prompt_text(),
        ]
        return "\n\n".join(s for s in sections if s.strip())
    
    async def update_from_sensors(self, node_registry, capability_plugins):
        """从传感器和插件更新世界表征"""
        # 更新 L0: 从 ROS2 节点获取机器人状态
        # 更新 L1: 从视觉/激光雷达获取环境信息
        # 更新 L2: 从各 Capability 插件评估可供性
        # L3: 由 TurnRunner 在任务执行过程中维护
        pass
```

### 3.4 在 TurnRunner 中的集成点

关键改动：在每次 LLM 调用前，注入最新的世界表征。

```python
# 改进后的 ReAct 循环（伪代码）
async def _run_react_loop(self, session, user_input, turn_id, start):
    
    for iteration in range(self._max_iterations):
        
        # ★ 关键改进：每次 LLM 调用前，刷新世界表征
        world_text = await self._world_repr.assemble_for_llm()
        
        # 将世界表征注入消息（作为 system message 的动态部分）
        dynamic_system = f"{self._system_prompt}\n\n{world_text}"
        messages[0] = {"role": "system", "content": dynamic_system}
        
        response = await provider.chat(messages, tools)
        
        if response.tool_calls:
            results = await self._execute_tools(response.tool_calls, session)
            
            # ★ 关键改进：执行后更新世界表征
            await self._world_repr.update_after_execution(results)
            
            # ★ 关键改进：工具结果包含结构化状态变更，不只是文本
            for tc, tr in zip(response.tool_calls, results):
                tool_content = self._format_rich_result(tc, tr)
                messages.append({"role": "tool", "content": tool_content})
```

---

## 四、执行反馈的细粒度设计

你特别提到了"任务过程的反馈细粒度"。这是当前 MOSAIC 最大的缺失。

### 4.1 当前的反馈：二元结果

```python
# 当前 ExecutionResult — 只有成功/失败 + 一句话
@dataclass
class ExecutionResult:
    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    message: str = ""          # "已导航到 厨房（速度: 0.5）"
    error: str | None = None   # "路径被阻塞"
```

LLM 看到的是：`"已导航到 厨房（速度: 0.5）"` — 一个黑盒结果。

### 4.2 需要的反馈：多维度结构化

```python
@dataclass
class RichExecutionResult:
    """丰富的执行结果 — 多维度反馈"""
    
    # 基础结果
    success: bool
    message: str = ""
    error: str | None = None
    
    # 状态变更（执行前后的差异）
    state_changes: list[str] = field(default_factory=list)
    # 例: ["位置: 客厅 → 厨房", "电量: 78% → 75%", "耗时: 12.3秒"]
    
    # 观察到的新信息（执行过程中发现的）
    observations: list[str] = field(default_factory=list)
    # 例: ["厨房门是开着的", "咖啡机在料理台左侧", "地上有水渍（注意防滑）"]
    
    # 异常事件（执行过程中遇到的）
    anomalies: list[str] = field(default_factory=list)
    # 例: ["导航中途遇到障碍物，自动绕行", "到达位置偏差0.3m"]
    
    # 对后续步骤的影响
    implications: list[str] = field(default_factory=list)
    # 例: ["咖啡机在视野内，可以直接操作", "需要先清理地上的水"]
    
    # 可供性变更（执行后哪些能力的可行性变了）
    affordance_updates: dict[str, str] = field(default_factory=dict)
    # 例: {"pick_up(咖啡杯)": "可行，在机械臂范围内", 
    #       "operate_appliance(咖啡机)": "可行，面前1.2m"}
    
    def to_llm_text(self) -> str:
        """转化为 LLM 可理解的丰富反馈文本"""
        parts = []
        
        # 结果
        if self.success:
            parts.append(f"✓ {self.message}")
        else:
            parts.append(f"✗ 失败: {self.error}")
        
        # 状态变更
        if self.state_changes:
            parts.append("状态变更: " + "; ".join(self.state_changes))
        
        # 新观察
        if self.observations:
            parts.append("观察到: " + "; ".join(self.observations))
        
        # 异常
        if self.anomalies:
            parts.append("注意: " + "; ".join(self.anomalies))
        
        # 后续影响
        if self.implications:
            parts.append("影响: " + "; ".join(self.implications))
        
        # 可供性更新
        if self.affordance_updates:
            updates = [f"{k}: {v}" for k, v in self.affordance_updates.items()]
            parts.append("能力更新: " + "; ".join(updates))
        
        return "\n".join(parts)
```

### 4.3 反馈粒度的三个层次

| 层次 | 触发时机 | 内容 | LLM 是否需要看到 |
|------|---------|------|-----------------|
| 结果反馈 | 动作完成后 | 成功/失败 + 状态变更 + 观察 | ✅ 必须 |
| 进度反馈 | 动作执行中 | 进度百分比、当前位置、预计剩余时间 | ⚠️ 长时间动作需要 |
| 异常反馈 | 异常发生时 | 异常类型、当前状态、可选恢复策略 | ✅ 需要立即决策时 |

**结果反馈**是每次工具调用后必须提供的，对应上面的 `RichExecutionResult`。

**进度反馈**用于长时间动作（导航 30 秒、等待咖啡 3 分钟）。
当前 TurnRunner 的阻塞式 `await execute()` 无法提供进度反馈。
需要改为非阻塞模型：

```python
# 长时间动作的进度反馈模型
async def execute_with_progress(self, intent, params, ctx):
    """非阻塞执行，支持进度回调"""
    
    if intent == "navigate_to":
        # 启动导航（非阻塞）
        nav_handle = await self._start_navigation(params["target"])
        
        while not nav_handle.is_complete():
            progress = nav_handle.get_progress()
            
            # 如果执行时间超过阈值，生成中间反馈给 LLM
            if progress.elapsed_s > 5.0 and progress.percent < 80:
                yield ProgressUpdate(
                    percent=progress.percent,
                    message=f"导航中... {progress.percent:.0f}%, "
                            f"距目标 {progress.remaining_m:.1f}m",
                )
            
            await asyncio.sleep(0.5)
        
        return nav_handle.get_result()
```

**异常反馈**是最关键的——当执行过程中发生意外，需要 LLM 立即介入决策：

```python
# 异常反馈需要中断当前 ReAct 循环，让 LLM 重新决策
@dataclass
class ExecutionAnomaly:
    """执行异常 — 需要 LLM 介入决策"""
    severity: str                    # "warning" | "error" | "critical"
    description: str                 # "导航路径被阻塞"
    current_state: str               # "机器人停在走廊中间"
    recovery_options: list[str]      # ["等待5秒后重试", "绕行", "放弃当前任务"]
    
    def to_llm_text(self) -> str:
        options = "\n".join(f"  {i+1}. {o}" for i, o in enumerate(self.recovery_options))
        return (
            f"⚠️ 执行异常 [{self.severity}]\n"
            f"问题: {self.description}\n"
            f"当前状态: {self.current_state}\n"
            f"可选恢复策略:\n{options}\n"
            f"请选择恢复策略或提出新的方案。"
        )
```

---

## 五、多模态融合的演进路径

### 5.1 阶段一（当前）：纯文本世界表征

```
传感器数据 → 文本化 → 注入 LLM 上下文
```

实现 L0-L3 四层文本化世界表征，改进 ExecutionResult 为 RichExecutionResult。
这在当前纯文本 LLM（MiniMax-Text-01）上就能工作。

**工作量**：~500 行新增代码（WorldRepresentation + RichExecutionResult）
**效果**：LLM 从"盲人摸象"变为"看地图决策"

### 5.2 阶段二（中期）：文本 + 场景图

```
传感器数据 → 场景图构建 → 文本序列化 → 注入 LLM 上下文
                        → 可行性验证引擎（独立于 LLM）
```

引入场景图作为环境的结构化表征。
场景图不仅用于生成 L1 环境快照文本，还用于独立验证 LLM 生成的计划是否可行。

**工作量**：~1500 行（场景图构建 + 维护 + 验证引擎）
**效果**：LLM 的计划在执行前经过物理可行性验证

### 5.3 阶段三（远期）：多模态直接感知

```
摄像头图像 + 传感器数据 → VLM 直接感知 → 决策
```

当 VLM/VLA 技术成熟后，可以让模型直接"看"物理世界。
MOSAIC 的插件架构天然支持这种演进——只需要将 Provider 插件从纯文本 LLM 替换为 VLM。

**前提**：VLM 的物理推理能力达到实用水平（当前还不够）
**MOSAIC 需要的改动**：Provider 插件支持多模态输入（图像 + 文本）

---

## 六、对 MOSAIC 架构的具体改动建议

### 6.1 新增组件

| 组件 | 位置 | 职责 |
|------|------|------|
| `WorldRepresentation` | `mosaic/runtime/world_repr.py` | 四层世界表征的组装和维护 |
| `RobotState` | `mosaic/runtime/world_repr.py` | L0 机器人自身状态 |
| `EnvironmentSnapshot` | `mosaic/runtime/world_repr.py` | L1 环境快照 |
| `AffordanceState` | `mosaic/runtime/world_repr.py` | L2 可供性评估 |
| `TaskContext` | `mosaic/runtime/world_repr.py` | L3 任务语境 |
| `RichExecutionResult` | `mosaic/plugin_sdk/types.py` | 丰富的执行反馈 |
| `AffordanceEvaluator` | `mosaic/runtime/affordance.py` | 可供性评估引擎 |

### 6.2 需要修改的组件

| 组件 | 改动 |
|------|------|
| `TurnRunner` | 每次 LLM 调用前注入世界表征；工具结果使用 RichExecutionResult |
| `CapabilityPlugin` Protocol | 新增 `evaluate_affordance()` 方法 |
| `ExecutionResult` | 扩展为 `RichExecutionResult`（向后兼容） |
| 各 Capability 插件 | 实现 `evaluate_affordance()` 和丰富的执行反馈 |

### 6.3 CapabilityPlugin 协议扩展

```python
@runtime_checkable
class CapabilityPlugin(Protocol):
    """能力插件接口 — 扩展可供性评估"""
    meta: PluginMeta

    def get_supported_intents(self) -> list[str]: ...
    def get_tool_definitions(self) -> list[dict[str, Any]]: ...
    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult: ...
    async def cancel(self) -> bool: ...
    async def health_check(self) -> HealthStatus: ...
    
    # ★ 新增：可供性评估
    async def evaluate_affordance(
        self, intent: str, params: dict, robot_state: dict
    ) -> AffordanceEntry: ...
```

---

## 七、一个完整的例子

用户说："帮我做杯咖啡送过来"

### 第 1 轮 LLM 调用

LLM 收到的上下文：
```
[系统提示] 你是 MOSAIC 智能机器人助手...

[机器人状态]
位置: 客厅 (2.3, 1.5)
电量: 78%
手持: 无
机械臂: 空闲

[环境状态]
可见物体:
  - 沙发 (家具): 左前方 2.0m
  - 茶几 (家具): 正前方 1.5m
  - 水杯 (物品): 茶几上 1.5m
可到达位置: 厨房, 卧室, 门口, 充电站
人员: 用户 在 沙发

[能力可行性]
  navigate_to(厨房): ✓ 可行 (95%) — 路径畅通 [预计 12秒]
  navigate_to(卧室): ✓ 可行 (90%) [预计 8秒]
  pick_up(水杯): ✓ 可行 (85%) — 在机械臂范围内
  operate_appliance(咖啡机): ✗ 不可行 — 不在咖啡机附近 [前置: 先导航到厨房]

[任务状态]
目标: (无)

[用户] 帮我做杯咖啡送过来
```

LLM 决策：调用 `navigate_to(厨房)`

### 第 1 轮工具执行后

LLM 收到的工具反馈：
```
✓ 已导航到厨房
状态变更: 位置: 客厅 → 厨房; 电量: 78% → 75%; 耗时: 12.3秒
观察到: 咖啡机在料理台左侧(正前方0.8m); 咖啡机状态:待机; 水槽在右侧
影响: operate_appliance(咖啡机) 现在可行
能力更新: operate_appliance(咖啡机): 可行(92%), 面前0.8m; pick_up(咖啡杯): 不可行, 未看到咖啡杯
```

### 第 2 轮 LLM 调用

世界表征已自动更新：
```
[机器人状态]
位置: 厨房 (5.1, 3.2)
电量: 75%
手持: 无

[能力可行性]
  operate_appliance(咖啡机): ✓ 可行 (92%) — 面前0.8m [预计 3秒操作 + 180秒等待]
  pick_up(咖啡杯): ✗ 不可行 — 未看到咖啡杯 [需要先制作咖啡]
  navigate_to(客厅): ✓ 可行 (95%) [预计 12秒]

[任务状态]
目标: 做咖啡送给用户
已完成: 导航到厨房
当前步骤: (等待决策)
```

LLM 看到了完整的物理世界状态，做出合理决策：调用 `operate_appliance(咖啡机, 启动)`

**这就是"让 LLM 理解物理世界"的具体含义：不是让 LLM 拥有物理直觉，
而是在每个决策点为 LLM 提供充分的、结构化的物理世界信息，
让它的语言推理能力在正确的物理约束下工作。**

---

## 八、结论

### 8.1 核心观点

LLM 理解物理世界不是一个"能不能"的问题，而是一个"给它什么信息"的问题。

LLM 的语言推理能力是强大的——它知道做咖啡需要先去厨房，知道拿东西需要先到物品旁边。
它缺的不是推理能力，而是**关于当前物理世界的事实性信息**。

MOSAIC 的职责是：
1. 从物理世界中提取信息（感知层）
2. 将信息组织为 LLM 可理解的结构（世界表征层）
3. 在每个决策点提供最新的世界状态（注入机制）
4. 将执行结果以丰富的形式反馈给 LLM（反馈机制）

### 8.2 MOSAIC 的独特定位

这个分层世界表征架构是 MOSAIC 区别于普通 Agent 框架的核心：

- 普通 Agent 框架：LLM + 工具 → 工具返回文本 → LLM 继续
- MOSAIC：LLM + 物理世界表征 + 可供性评估 + 丰富反馈 → 具身决策

这也是论文的核心贡献点之一：**如何系统性地将物理世界状态桥接到 LLM 的决策过程中**。

### 8.3 优先级

1. **立即做**：实现 L0 RobotState + L2 AffordanceState + RichExecutionResult
2. **短期做**：实现 L1 EnvironmentSnapshot + L3 TaskContext
3. **中期做**：场景图构建 + 可行性验证引擎
4. **远期做**：VLM 多模态直接感知
