- title: Scene Graph Representation Architecture
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, survey, scene-graph
- source_type: survey

# MOSAIC 场景图表征架构规划：从文本到结构化世界理解

> 场景图是具身智能体理解物理世界的"结构化语言"。
> 本文基于 VeriGraph、MoMa-LLM、EmbodiedRAG、MomaGraph、GraphPlan 等前沿工作，
> 为 MOSAIC 规划从 L1 文本化环境快照到结构化场景图的演进路径，
> 并设计与当前四层世界表征架构（L0-L3）的集成方案。

---

## 一、为什么需要场景图：文本化表征的天花板

### 1.1 当前 L1 环境快照的局限

在上一份报告中，我们设计了四层世界表征架构，其中 L1 EnvironmentSnapshot 采用纯文本列表：

```
[环境状态]
可见物体:
  - 咖啡机 (电器): 正前方 0.8m, state=待机
  - 冰箱 (电器): 左侧 2.0m, state=关闭
  - 水杯 (物品): 茶几上 1.5m
可到达位置: 厨房, 卧室, 门口
```

这种文本列表有三个根本性缺陷：

**缺陷 1：关系信息丢失**

文本列表只描述了"物体在哪"，没有描述"物体之间的关系"。
"水杯在茶几上"和"水杯在咖啡机旁边"是完全不同的空间关系，
但在扁平列表中它们被压缩为同一种格式。

LLM 需要从文本中推断关系（"茶几上 1.5m"→ 推断水杯在茶几上），
这增加了推理负担，也容易出错。

**缺陷 2：无法表达层次结构**

物理世界是层次化的：房间包含家具，家具上有物品，物品有部件。
"厨房 → 料理台 → 咖啡机 → 咖啡壶"这种层次关系在扁平列表中无法自然表达。

**缺陷 3：无法支持计划验证**

当 LLM 生成计划"先拿杯子，再倒咖啡"时，
我们无法在文本列表上验证"拿杯子"的前置条件是否满足（杯子是否在机械臂可达范围内）。
VeriGraph 的核心贡献正是解决了这个问题——在场景图上模拟执行每一步，验证前置条件。

### 1.2 场景图解决了什么

场景图（Scene Graph）是一种有向图结构：
- **节点（Node）**：物体、位置、智能体、设备
- **边（Edge）**：空间关系、功能关系、状态关系、可供性关系

```
场景图 vs 文本列表:

文本列表:                          场景图:
  - 咖啡机: 厨房, 待机              厨房 ──contains──→ 料理台
  - 水杯: 茶几上                          ──contains──→ 冰箱
  - 茶几: 客厅                     料理台 ──on_top──→ 咖啡机
                                   咖啡机 ──state──→ idle
                                          ──affordance──→ can_brew
                                   客厅 ──contains──→ 茶几
                                   茶几 ──on_top──→ 水杯
                                   水杯 ──graspable──→ true
                                   机器人 ──at──→ 客厅
                                          ──holding──→ nothing
```

场景图的优势：
1. **关系显式化**：空间关系、功能关系、状态关系都是一等公民
2. **层次自然**：contains 边天然表达层次结构
3. **可推理**：可以在图上做路径查询、可达性分析、前置条件检查
4. **可增量更新**：执行动作后只需修改受影响的节点和边，不需要重建整个描述
5. **可验证**：VeriGraph 证明了在场景图上模拟执行可以大幅提升计划成功率

---

## 二、前沿研究综述：场景图在具身智能体中的六种范式

基于对 2024-2025 年最新研究的调研，梳理出六种场景图应用范式：

### 范式 1：静态场景图 + LLM 规划（VeriGraph 路线）

**代表工作**：VeriGraph (2024, arXiv:2411.10446)

**核心机制**：
1. 从图像生成场景图（VLM 如 GPT-4V 做节点/边提取）
2. LLM 基于场景图生成动作计划
3. 在场景图上**模拟执行**每一步，检查前置条件
4. 如果前置条件不满足，反馈给 LLM 修正计划
5. 迭代直到计划通过验证

**关键数据**：
- 使用 GPT-4V 生成场景图：节点 F1=1.0，边 F1=1.0（积木场景）
- 规划成功率：VeriGraph 0.65-0.86 vs SayCan 0.00-0.17 vs ViLa 0.05-0.62
- 当使用真实场景图时，迭代规划器成功率接近 100%

**对 MOSAIC 的启示**：
- 场景图质量直接决定规划质量（真实场景图 → ~100% 成功率）
- 迭代验证机制（plan → verify → correct）是关键创新
- MOSAIC 的 Capability 插件可以提供比 VLM 更精确的场景图（因为有 ROS2 传感器）

### 范式 2：动态场景图 + 探索式更新（MoMa-LLM 路线）

**代表工作**：MoMa-LLM (2024, arXiv:2403.08605)

**核心机制**：
1. 从开放词汇目标检测构建场景图
2. 场景图随环境探索**动态更新**（发现新物体、更新物体状态）
3. 将场景图与**以物体为中心的动作空间**紧密交织
4. LLM 在结构化场景图表征上做规划，而非原始图像

**关键创新**：
- 场景图不是一次性构建的，而是随机器人移动持续演化
- 动作空间直接绑定到场景图节点（"拿起 node_42" 而非 "拿起桌上的杯子"）
- 零样本、开放词汇——不需要预定义物体类别

**对 MOSAIC 的启示**：
- MOSAIC 的 Capability 执行结果应该触发场景图更新
- 动作空间与场景图节点绑定的思路可以增强 affordance 评估
- 探索式更新适合 MOSAIC 的"未知环境"场景

### 范式 3：子图检索 + RAG 增强（EmbodiedRAG 路线）

**代表工作**：EmbodiedRAG (2024, arXiv:2410.23968)

**核心机制**：
1. 构建完整的 3D 场景图
2. 不把整个场景图喂给 LLM（token 太多），而是**动态检索相关子图**
3. 子图随任务进展和环境变化自适应更新
4. 类似 RAG 的思路：只给 LLM 看它当前需要的信息

**关键数据**：
- Token 数量减少一个数量级
- 规划时间减少 70%
- 成功率反而提升（因为减少了无关信息的干扰）

**对 MOSAIC 的启示**：
- 大型环境中不能把整个场景图序列化给 LLM
- 需要基于当前任务和位置做子图检索
- 这与 MOSAIC 的 ContextEngine 插件架构天然契合

### 范式 4：统一场景图 + 功能可供性（MomaGraph 路线）

**代表工作**：MomaGraph (2025, arXiv:2512.16909)

**核心机制**：
1. 统一表征空间关系和功能可供性（不只是"杯子在桌上"，还有"杯子可以被抓取"）
2. 部件级交互元素（不只是"门"，还有"门把手可以被旋转"）
3. 状态感知（物体的当前状态：开/关/满/空）
4. 93 个物体类别，详细的部件级可供性标注

**关键创新**：
- 将 affordance 直接编码为场景图的边属性
- 部件级粒度：不是"操作咖啡机"，而是"按下咖啡机的启动按钮"
- 状态追踪：咖啡机从 idle → brewing → done 的状态转换

**对 MOSAIC 的启示**：
- 这正是 MOSAIC L2 AffordanceState 的图结构化版本
- 部件级粒度对机械臂操作至关重要
- 状态追踪可以替代当前 Capability 插件的内部状态管理

### 范式 5：事件驱动重规划（GraphPlan 路线）

**代表工作**：GraphPlan (2025, OpenReview)

**核心机制**：
1. 动态场景图作为记忆构建
2. 事件驱动的重规划模块
3. 当场景图变化（检测到新物体、物体状态改变）时触发重规划
4. 闭环规划过程：规划 → 执行 → 感知变化 → 重规划

**对 MOSAIC 的启示**：
- 场景图变化事件可以接入 MOSAIC 的 EventBus
- 重规划触发机制与 MOSAIC 的 HookManager 天然契合
- 这解决了上一份报告中提到的"执行中异常反馈"问题

### 范式 6：动作条件场景图（RoboEXP 路线）

**代表工作**：RoboEXP (2024, arXiv:2402.15487)

**核心机制**：
1. 机器人通过交互式探索构建场景图
2. 场景图不只记录"物体在哪"，还记录"对物体做了什么操作会产生什么效果"
3. 动作-条件关系：`open(drawer) → reveals(bowl_inside)`
4. 支持铰接物体、嵌套物体、可变形物体

**对 MOSAIC 的启示**：
- 动作效果预测可以增强 MOSAIC 的任务规划
- "打开抽屉会看到什么"这种因果知识对长时域任务至关重要
- 可以与 MOSAIC 的 RichExecutionResult 结合——执行结果更新场景图的因果边

---

## 三、MOSAIC 场景图架构设计

### 3.1 设计原则

基于前沿研究和 MOSAIC 的具体需求，确定以下设计原则：

1. **渐进式集成**：场景图是 L1 EnvironmentSnapshot 的结构化升级，不是替代
2. **双向绑定**：场景图节点与 Capability 插件的工具定义双向绑定
3. **事件驱动更新**：通过 EventBus 接收传感器数据和执行结果，增量更新场景图
4. **子图序列化**：给 LLM 的不是整个场景图，而是任务相关的子图（EmbodiedRAG 思路）
5. **验证闭环**：LLM 生成计划后，在场景图上模拟验证（VeriGraph 思路）
6. **插件化感知**：场景图的数据源是可插拔的（ROS2 传感器 / 模拟数据 / 手动标注）

### 3.2 场景图数据模型

#### 节点类型体系

```python
class SceneNodeType(Enum):
    """场景图节点类型"""
    ROOM = "room"              # 房间（厨房、客厅、卧室）
    FURNITURE = "furniture"    # 家具（桌子、沙发、柜子）
    APPLIANCE = "appliance"    # 电器（咖啡机、冰箱、微波炉）
    OBJECT = "object"          # 可操作物品（杯子、毛巾、遥控器）
    AGENT = "agent"            # 智能体（机器人自身）
    PERSON = "person"          # 人（用户、其他人）
    WAYPOINT = "waypoint"      # 导航路径点
    PART = "part"              # 物体部件（门把手、按钮、抽屉）

@dataclass
class SceneNode:
    """场景图节点"""
    node_id: str                          # 唯一标识
    node_type: SceneNodeType              # 节点类型
    label: str                            # 语义标签（"咖啡机"、"客厅"）
    
    # 空间属性
    position: tuple[float, float] | None = None   # (x, y) 世界坐标
    bounding_box: dict | None = None              # 包围盒
    
    # 状态属性（动态变化）
    state: dict[str, str] = field(default_factory=dict)
    # 例: {"power": "on", "mode": "brewing", "fill_level": "80%"}
    
    # 可供性属性
    affordances: list[str] = field(default_factory=list)
    # 例: ["graspable", "openable", "pressable"]
    
    # 物理属性（相对静态）
    properties: dict[str, Any] = field(default_factory=dict)
    # 例: {"weight_kg": 0.3, "material": "ceramic", "temperature": "hot"}
    
    # 元数据
    confidence: float = 1.0               # 检测置信度
    last_observed: float = 0.0            # 最后观测时间戳
    source: str = "manual"                # 数据来源（sensor/manual/inferred）
```

#### 边类型体系

```python
class EdgeType(Enum):
    """场景图边类型"""
    # 空间关系
    CONTAINS = "contains"          # 包含（房间包含家具）
    ON_TOP = "on_top"              # 在...上面
    INSIDE = "inside"              # 在...里面
    NEXT_TO = "next_to"            # 在...旁边
    FACING = "facing"              # 面向
    REACHABLE = "reachable"        # 可达（导航可达）
    
    # 功能关系
    SUPPORTS = "supports"          # 支撑（桌子支撑杯子）
    CONNECTED_TO = "connected_to"  # 连接（电源线连接咖啡机）
    PART_OF = "part_of"            # 部件关系（按钮是咖啡机的一部分）
    
    # 智能体关系
    AT = "at"                      # 位于（机器人位于客厅）
    HOLDING = "holding"            # 持有（机器人持有杯子）
    NEAR = "near"                  # 靠近（机器人靠近桌子）
    
    # 状态关系
    STATE = "state"                # 状态（咖啡机 → brewing）
    AFFORDANCE = "affordance"      # 可供性（杯子 → graspable）
    
    # 因果关系（动作条件，RoboEXP 启发）
    REVEALS = "reveals"            # 打开后显露（打开抽屉 → 显露碗）
    PRODUCES = "produces"          # 产出（咖啡机 → 产出咖啡）
    REQUIRES = "requires"          # 前置依赖（倒咖啡 → 需要杯子）

@dataclass
class SceneEdge:
    """场景图边"""
    source_id: str                 # 源节点 ID
    target_id: str                 # 目标节点 ID
    edge_type: EdgeType            # 边类型
    
    # 边属性
    properties: dict[str, Any] = field(default_factory=dict)
    # 例: {"distance_m": 1.5, "direction": "left", "traversable": True}
    
    confidence: float = 1.0        # 关系置信度
    last_updated: float = 0.0      # 最后更新时间
```

#### 场景图核心类

```python
class SceneGraph:
    """语义场景图 — MOSAIC 的结构化世界表征核心
    
    职责：
    - 维护节点和边的增删改查
    - 提供图查询接口（子图提取、路径查找、可达性分析）
    - 支持动作前置条件验证（VeriGraph 思路）
    - 支持动作效果模拟（预测执行后场景图变化）
    - 序列化为 LLM 可理解的文本
    """
    
    def __init__(self):
        self._nodes: dict[str, SceneNode] = {}
        self._edges: list[SceneEdge] = []
        # 索引：加速查询
        self._outgoing: dict[str, list[SceneEdge]] = {}   # node_id → 出边
        self._incoming: dict[str, list[SceneEdge]] = {}   # node_id → 入边
        self._type_index: dict[SceneNodeType, set[str]] = {}  # 类型 → node_ids
    
    # ── 节点操作 ──
    
    def add_node(self, node: SceneNode) -> None: ...
    def remove_node(self, node_id: str) -> None: ...
    def update_node_state(self, node_id: str, state: dict) -> None: ...
    def get_node(self, node_id: str) -> SceneNode | None: ...
    
    # ── 边操作 ──
    
    def add_edge(self, edge: SceneEdge) -> None: ...
    def remove_edges(self, source_id: str, target_id: str, 
                     edge_type: EdgeType | None = None) -> None: ...
    
    # ── 图查询 ──
    
    def get_children(self, node_id: str, edge_type: EdgeType | None = None) -> list[SceneNode]:
        """获取指定节点的子节点（沿出边方向）"""
        ...
    
    def get_parent(self, node_id: str, edge_type: EdgeType) -> SceneNode | None:
        """获取指定节点的父节点（沿入边方向）"""
        ...
    
    def find_by_label(self, label: str) -> list[SceneNode]:
        """按语义标签模糊查找节点"""
        ...
    
    def find_by_type(self, node_type: SceneNodeType) -> list[SceneNode]:
        """按类型查找所有节点"""
        ...
    
    def get_location_of(self, node_id: str) -> SceneNode | None:
        """查找物体所在的房间/位置（沿 contains 边向上追溯）"""
        ...
    
    def get_objects_at(self, location_label: str) -> list[SceneNode]:
        """查找指定位置的所有物体"""
        ...
    
    def get_reachable_locations(self, from_node_id: str) -> list[SceneNode]:
        """查找从指定位置可达的所有位置"""
        ...
    
    def get_agent_node(self) -> SceneNode | None:
        """获取机器人自身节点"""
        ...
    
    # ── 子图提取（EmbodiedRAG 思路）──
    
    def extract_task_subgraph(self, task_keywords: list[str], 
                               max_hops: int = 2) -> 'SceneGraph':
        """基于任务关键词提取相关子图
        
        算法：
        1. 找到与关键词匹配的种子节点
        2. 从种子节点出发，BFS 扩展 max_hops 跳
        3. 始终包含机器人节点和用户节点
        4. 返回子图
        """
        ...
    
    def extract_local_subgraph(self, center_node_id: str, 
                                radius_m: float = 5.0) -> 'SceneGraph':
        """基于空间距离提取局部子图"""
        ...
    
    # ── 动作验证（VeriGraph 思路）──
    
    def verify_preconditions(self, action: str, params: dict) -> tuple[bool, str]:
        """验证动作的前置条件是否在当前场景图上满足
        
        例：
        - navigate_to(厨房): 检查厨房节点存在 + 路径可达
        - pick_up(杯子): 检查杯子节点存在 + 机器人在同一位置 + 杯子 graspable + 机器人未持有物品
        - operate_appliance(咖啡机, 启动): 检查咖啡机存在 + 机器人在附近 + 咖啡机状态允许启动
        
        Returns:
            (satisfied, reason): 是否满足 + 原因说明
        """
        ...
    
    def simulate_action_effect(self, action: str, params: dict) -> 'SceneGraph':
        """模拟动作执行后的场景图变化（不修改原图，返回新图）
        
        例：
        - navigate_to(厨房): 机器人 AT 边从客厅移到厨房
        - pick_up(杯子): 杯子从 on_top 桌子变为 holding 机器人
        - operate_appliance(咖啡机, 启动): 咖啡机状态从 idle → brewing
        
        用于 LLM 计划的预验证：逐步模拟，检查每步后的场景图是否支持下一步。
        """
        ...
    
    # ── 序列化 ──
    
    def to_prompt_text(self, max_nodes: int = 30) -> str:
        """序列化为 LLM 可理解的结构化文本
        
        格式设计（参考 EmbodiedRAG 的 token 优化）：
        
        [场景图]
        位置层:
          厨房 ──contains──→ [料理台, 冰箱, 水槽]
          客厅 ──contains──→ [沙发, 茶几, 电视柜]
        
        物体层:
          料理台 ──on_top──→ [咖啡机(idle), 面包机(off)]
          茶几 ──on_top──→ [水杯(graspable), 遥控器(graspable)]
        
        智能体:
          机器人 ──at──→ 客厅, holding: 无
          用户 ──at──→ 沙发
        
        可达性:
          客厅 ←→ 厨房 ←→ 卧室
          客厅 ←→ 门口
        """
        ...
    
    def to_dict(self) -> dict:
        """序列化为字典（用于持久化和传输）"""
        ...
    
    @classmethod
    def from_dict(cls, data: dict) -> 'SceneGraph':
        """从字典反序列化"""
        ...
```

### 3.3 动作前置条件与效果规则引擎

这是 VeriGraph 的核心思想在 MOSAIC 中的落地。
每个 Capability 插件的每个 intent 都有对应的前置条件和效果规则。

```python
@dataclass
class ActionRule:
    """动作规则 — 前置条件 + 效果"""
    action_name: str                       # 动作名（navigate_to, pick_up, ...）
    
    # 前置条件：场景图上必须满足的条件
    preconditions: list[Precondition]
    
    # 效果：执行后场景图的变化
    effects: list[Effect]

@dataclass
class Precondition:
    """前置条件"""
    condition_type: str    # "node_exists" | "edge_exists" | "state_equals" | 
                           # "agent_at" | "agent_holding" | "agent_not_holding" |
                           # "node_has_affordance" | "path_reachable"
    params: dict[str, Any]
    description: str       # 人类可读描述（用于反馈给 LLM）

@dataclass  
class Effect:
    """动作效果"""
    effect_type: str       # "move_agent" | "add_edge" | "remove_edge" | 
                           # "update_state" | "transfer_holding"
    params: dict[str, Any]
```

#### MOSAIC 内置动作规则

```python
# navigate_to 的规则
ActionRule(
    action_name="navigate_to",
    preconditions=[
        Precondition("node_exists", {"label": "{target}"}, 
                     "目标位置 {target} 必须存在于场景图中"),
        Precondition("path_reachable", {"from": "agent", "to": "{target}"}, 
                     "从当前位置到 {target} 的路径必须可达"),
    ],
    effects=[
        Effect("move_agent", {"to": "{target}"}),
        # 机器人的 AT 边从旧位置移到新位置
    ],
)

# pick_up 的规则
ActionRule(
    action_name="pick_up",
    preconditions=[
        Precondition("node_exists", {"label": "{object_name}"}, 
                     "物品 {object_name} 必须存在于场景图中"),
        Precondition("agent_at_same_location", {"object": "{object_name}"}, 
                     "机器人必须在 {object_name} 所在位置"),
        Precondition("node_has_affordance", {"node": "{object_name}", "affordance": "graspable"}, 
                     "{object_name} 必须是可抓取的"),
        Precondition("agent_not_holding", {}, 
                     "机器人手中不能已有物品"),
    ],
    effects=[
        Effect("transfer_holding", {"object": "{object_name}"}),
        # 移除物品的 on_top/inside 边，添加 agent holding 边
    ],
)

# hand_over 的规则
ActionRule(
    action_name="hand_over",
    preconditions=[
        Precondition("agent_holding", {"object": "{object_name}"}, 
                     "机器人必须持有 {object_name}"),
        Precondition("agent_near_person", {}, 
                     "机器人必须在用户附近"),
    ],
    effects=[
        Effect("remove_holding", {"object": "{object_name}"}),
        # 移除 agent holding 边
    ],
)

# operate_appliance 的规则
ActionRule(
    action_name="operate_appliance",
    preconditions=[
        Precondition("node_exists", {"label": "{appliance_name}"}, 
                     "设备 {appliance_name} 必须存在于场景图中"),
        Precondition("agent_at_same_location", {"object": "{appliance_name}"}, 
                     "机器人必须在 {appliance_name} 所在位置"),
        Precondition("node_type_is", {"node": "{appliance_name}", "type": "appliance"}, 
                     "{appliance_name} 必须是电器设备"),
    ],
    effects=[
        Effect("update_state", {"node": "{appliance_name}", "state": {"power": "{action}"}}),
    ],
)

# wait_appliance 的规则
ActionRule(
    action_name="wait_appliance",
    preconditions=[
        Precondition("node_exists", {"label": "{appliance_name}"}, 
                     "设备 {appliance_name} 必须存在"),
        Precondition("state_equals", {"node": "{appliance_name}", "key": "power", "value": "on"}, 
                     "{appliance_name} 必须处于运行状态"),
    ],
    effects=[
        Effect("update_state", {"node": "{appliance_name}", "state": {"task": "done"}}),
    ],
)
```

### 3.4 计划验证器（PlanVerifier）

VeriGraph 的核心创新——在场景图上逐步模拟执行计划，验证可行性。

```python
class PlanVerifier:
    """计划验证器 — 在场景图上模拟执行，验证计划可行性
    
    核心算法（VeriGraph 思路）：
    1. 复制当前场景图作为模拟环境
    2. 对计划中的每一步：
       a. 检查前置条件是否在当前模拟场景图上满足
       b. 如果不满足，记录失败原因，返回验证失败
       c. 如果满足，应用动作效果，更新模拟场景图
    3. 所有步骤通过 → 计划可行
    
    这个验证器独立于 LLM，是纯规则引擎。
    它的价值在于：LLM 可能生成看似合理但物理上不可行的计划，
    验证器能在执行前发现问题，避免浪费物理执行时间。
    """
    
    def __init__(self, action_rules: dict[str, ActionRule]):
        self._rules = action_rules
    
    def verify_plan(self, scene_graph: SceneGraph, 
                    plan_steps: list[dict]) -> PlanVerificationResult:
        """验证完整计划
        
        Args:
            scene_graph: 当前场景图
            plan_steps: 计划步骤列表，每步 {"action": "navigate_to", "params": {"target": "厨房"}}
        
        Returns:
            PlanVerificationResult: 验证结果，包含每步的验证详情
        """
        sim_graph = scene_graph.deep_copy()  # 不修改原图
        step_results = []
        
        for i, step in enumerate(plan_steps):
            action = step["action"]
            params = step["params"]
            rule = self._rules.get(action)
            
            if not rule:
                step_results.append(StepVerification(
                    step_index=i, action=action, passed=False,
                    reason=f"未知动作: {action}",
                ))
                return PlanVerificationResult(
                    feasible=False, step_results=step_results,
                    failure_step=i, failure_reason=f"未知动作: {action}",
                )
            
            # 检查前置条件
            for pre in rule.preconditions:
                satisfied, reason = self._check_precondition(sim_graph, pre, params)
                if not satisfied:
                    step_results.append(StepVerification(
                        step_index=i, action=action, passed=False,
                        reason=reason,
                    ))
                    return PlanVerificationResult(
                        feasible=False, step_results=step_results,
                        failure_step=i, failure_reason=reason,
                    )
            
            # 应用效果
            for effect in rule.effects:
                self._apply_effect(sim_graph, effect, params)
            
            step_results.append(StepVerification(
                step_index=i, action=action, passed=True, reason="前置条件满足",
            ))
        
        return PlanVerificationResult(
            feasible=True, step_results=step_results,
            final_graph=sim_graph,  # 返回模拟后的最终场景图
        )

@dataclass
class StepVerification:
    """单步验证结果"""
    step_index: int
    action: str
    passed: bool
    reason: str

@dataclass
class PlanVerificationResult:
    """计划验证结果"""
    feasible: bool
    step_results: list[StepVerification]
    failure_step: int = -1
    failure_reason: str = ""
    final_graph: SceneGraph | None = None  # 模拟执行后的最终场景图
    
    def to_llm_feedback(self) -> str:
        """转化为 LLM 可理解的反馈文本
        
        当计划不可行时，告诉 LLM 哪一步失败了、为什么失败、
        当时的场景图状态是什么，让 LLM 修正计划。
        """
        if self.feasible:
            return "✓ 计划验证通过，所有步骤的前置条件均满足。"
        
        lines = [
            f"✗ 计划在第 {self.failure_step + 1} 步失败",
            f"失败动作: {self.step_results[self.failure_step].action}",
            f"原因: {self.failure_reason}",
            "",
            "已通过的步骤:",
        ]
        for sr in self.step_results:
            if sr.passed:
                lines.append(f"  ✓ 第 {sr.step_index + 1} 步: {sr.action}")
            else:
                lines.append(f"  ✗ 第 {sr.step_index + 1} 步: {sr.action} — {sr.reason}")
                break
        
        lines.append("")
        lines.append("请修正计划，确保失败步骤的前置条件被满足。")
        return "\n".join(lines)
```

### 3.5 场景图管理器（SceneGraphManager）

统一管理场景图的生命周期：初始化、更新、查询、序列化。

```python
class SceneGraphManager:
    """场景图管理器 — 场景图的生命周期管理
    
    职责：
    1. 初始化：从配置/传感器/手动标注构建初始场景图
    2. 更新：接收执行结果和传感器数据，增量更新场景图
    3. 查询：为 TurnRunner 提供任务相关子图
    4. 验证：为 PlanVerifier 提供场景图快照
    5. 事件：场景图变化时通过 EventBus 发布事件
    
    与 EventBus 的集成：
    - 监听 tool.after_exec 事件 → 根据执行结果更新场景图
    - 监听 sensor.update 事件 → 根据传感器数据更新场景图
    - 发布 scene_graph.updated 事件 → 触发重规划（GraphPlan 思路）
    """
    
    def __init__(self, event_bus: EventBus, action_rules: dict[str, ActionRule]):
        self._graph = SceneGraph()
        self._event_bus = event_bus
        self._verifier = PlanVerifier(action_rules)
        self._history: list[SceneGraph] = []  # 场景图历史快照
        
        # 注册事件监听
        self._event_bus.on("tool.after_exec", self._on_tool_executed)
    
    def initialize_from_config(self, env_config: dict) -> None:
        """从配置文件初始化场景图（适用于已知环境）
        
        配置格式：
        environment:
          rooms:
            - id: kitchen
              label: 厨房
              objects:
                - {id: coffee_machine, label: 咖啡机, type: appliance, 
                   state: {power: off}, affordances: [operable]}
                - {id: fridge, label: 冰箱, type: appliance}
              furniture:
                - {id: counter, label: 料理台, objects: [coffee_machine]}
          connections:
            - {from: living_room, to: kitchen, bidirectional: true}
        """
        ...
    
    async def update_from_execution(self, action: str, params: dict, 
                                     result: ExecutionResult) -> None:
        """根据动作执行结果更新场景图
        
        这是场景图动态更新的核心入口。
        每次 Capability 执行完成后，根据动作类型和结果更新场景图。
        
        例：
        - navigate_to(厨房) 成功 → 移动机器人 AT 边到厨房
        - pick_up(杯子) 成功 → 杯子从桌上移到机器人手中
        - operate_appliance(咖啡机, 启动) 成功 → 咖啡机状态变为 brewing
        """
        ...
    
    def get_task_subgraph(self, task_description: str) -> SceneGraph:
        """基于任务描述提取相关子图（EmbodiedRAG 思路）
        
        从任务描述中提取关键词，在场景图中找到相关节点，
        扩展 N 跳邻居，返回紧凑的子图。
        
        这样 LLM 只看到与当前任务相关的场景信息，
        而不是整个环境的完整场景图（节省 token，减少干扰）。
        """
        keywords = self._extract_keywords(task_description)
        return self._graph.extract_task_subgraph(keywords, max_hops=2)
    
    def verify_plan(self, plan_steps: list[dict]) -> PlanVerificationResult:
        """验证计划可行性"""
        return self._verifier.verify_plan(self._graph, plan_steps)
    
    def get_full_graph(self) -> SceneGraph:
        """获取完整场景图"""
        return self._graph
    
    def snapshot(self) -> None:
        """保存当前场景图快照（用于回溯和对比）"""
        self._history.append(self._graph.deep_copy())
    
    async def _on_tool_executed(self, event: Event) -> None:
        """EventBus 回调：工具执行完成后更新场景图"""
        payload = event.payload
        action = payload.get("action", "")
        params = payload.get("params", {})
        result = payload.get("result")
        
        if result and result.get("success"):
            await self.update_from_execution(action, params, result)
            
            # 发布场景图更新事件（触发重规划等下游逻辑）
            await self._event_bus.emit(Event(
                type="scene_graph.updated",
                payload={"action": action, "changes": "..."},
                source="scene_graph_manager",
            ))
```

### 3.6 与 TurnRunner 的集成

场景图在 TurnRunner 的 ReAct 循环中有三个集成点：

```python
# 改进后的 TurnRunner ReAct 循环（伪代码）

async def _run_react_loop(self, session, user_input, turn_id, start):
    
    # ★ 集成点 1：组装上下文时注入场景图子图
    task_subgraph = self._scene_graph_mgr.get_task_subgraph(user_input)
    scene_text = task_subgraph.to_prompt_text()
    
    # 将场景图文本注入 system prompt 的动态部分
    dynamic_system = f"{self._system_prompt}\n\n{scene_text}"
    messages[0] = {"role": "system", "content": dynamic_system}
    
    for iteration in range(self._max_iterations):
        response = await provider.chat(messages, tools)
        
        if not response.tool_calls:
            return final_response
        
        # ★ 集成点 2：执行前验证计划（VeriGraph 思路）
        # 将 LLM 的工具调用转化为计划步骤
        plan_steps = [
            {"action": tc["name"], "params": tc.get("arguments", {})}
            for tc in response.tool_calls
        ]
        verification = self._scene_graph_mgr.verify_plan(plan_steps)
        
        if not verification.feasible:
            # 计划不可行 → 将验证反馈注入消息，让 LLM 修正
            feedback = verification.to_llm_feedback()
            messages.append({
                "role": "system", 
                "content": f"[计划验证失败]\n{feedback}"
            })
            continue  # 跳过执行，让 LLM 重新规划
        
        # 验证通过 → 执行工具
        results = await self._execute_tools(response.tool_calls, session)
        
        # ★ 集成点 3：执行后更新场景图
        for tc, result in zip(response.tool_calls, results):
            await self._scene_graph_mgr.update_from_execution(
                tc["name"], tc.get("arguments", {}), result
            )
        
        # 刷新场景图子图（环境已变化）
        task_subgraph = self._scene_graph_mgr.get_task_subgraph(user_input)
        scene_text = task_subgraph.to_prompt_text()
        messages[0] = {"role": "system", "content": f"{self._system_prompt}\n\n{scene_text}"}
        
        # 追加工具结果到消息历史（同现有逻辑）
        ...
```

### 3.7 与四层世界表征的关系

场景图不是替代四层世界表征，而是**升级 L1 和增强 L2**：

```
四层世界表征（原设计）          场景图增强后

L0: RobotState                L0: RobotState（不变）
    位置、电量、持有物              ↕ 同步到场景图的 agent 节点
    
L1: EnvironmentSnapshot       L1: SceneGraph（升级）
    扁平物体列表                   结构化场景图
    ↓ 升级为                       节点 + 边 + 层次 + 关系
    
L2: AffordanceState           L2: 场景图内置 affordance 边（增强）
    独立的可行性列表               affordance 直接编码在场景图边上
    ↓ 融合到                       + PlanVerifier 验证
    
L3: TaskContext                L3: TaskContext（不变）
    任务目标、已完成步骤            ↕ 验证结果反馈到任务上下文
```

具体来说：
- **L0 RobotState** 与场景图的 agent 节点双向同步
  - RobotState.position → agent 节点的 position
  - RobotState.holding_object → agent 的 HOLDING 边
  - RobotState.location_name → agent 的 AT 边
  
- **L1 EnvironmentSnapshot** 被 SceneGraph 完全替代
  - 原来的 `objects: list[EnvironmentObject]` → 场景图节点
  - 原来的 `accessible_locations: list[str]` → REACHABLE 边
  - 原来的 `people: list[dict]` → PERSON 类型节点
  
- **L2 AffordanceState** 融合到场景图
  - 原来的 `AffordanceEntry` → 场景图节点的 affordances 属性 + AFFORDANCE 边
  - 新增 PlanVerifier 做前置条件验证（比简单的 affordance 列表更强）
  
- **L3 TaskContext** 保持独立，但与场景图交互
  - 验证失败信息反馈到 TaskContext.failed_attempts
  - 场景图变化事件可能触发任务重规划

---

## 四、环境配置与场景图初始化

### 4.1 环境配置文件设计

为 MOSAIC 设计环境配置格式，用于初始化场景图：

```yaml
# config/environments/home.yaml
# 家庭环境场景图配置 — 定义房间、家具、物品及其关系

environment:
  name: "家庭环境"
  version: "1.0"
  
  # 房间定义
  rooms:
    - id: living_room
      label: 客厅
      position: [3.0, 2.0]
      furniture:
        - id: sofa
          label: 沙发
          position: [2.0, 1.0]
        - id: coffee_table
          label: 茶几
          position: [3.0, 1.5]
          objects:
            - id: water_cup
              label: 水杯
              type: object
              affordances: [graspable]
              properties: {material: ceramic, weight_kg: 0.3}
            - id: remote
              label: 遥控器
              type: object
              affordances: [graspable]
        - id: tv_cabinet
          label: 电视柜
          position: [4.0, 0.5]
    
    - id: kitchen
      label: 厨房
      position: [7.0, 2.0]
      furniture:
        - id: counter
          label: 料理台
          position: [7.0, 1.0]
          objects:
            - id: coffee_machine
              label: 咖啡机
              type: appliance
              state: {power: "off", mode: "idle"}
              affordances: [operable]
              parts:
                - id: coffee_btn
                  label: 启动按钮
                  affordances: [pressable]
            - id: toaster
              label: 面包机
              type: appliance
              state: {power: "off"}
              affordances: [operable]
        - id: fridge
          label: 冰箱
          type: appliance
          position: [8.0, 2.0]
          state: {power: "on", temperature: "4°C"}
          affordances: [openable]
    
    - id: bedroom
      label: 卧室
      position: [3.0, 6.0]
    
    - id: bathroom
      label: 卫生间
      position: [7.0, 6.0]
      furniture:
        - id: towel_rack
          label: 毛巾架
          objects:
            - id: yellow_towel
              label: 黄色毛巾
              type: object
              affordances: [graspable]
    
    - id: entrance
      label: 门口
      position: [1.0, 0.0]
    
    - id: charging_station
      label: 充电站
      position: [1.0, 2.0]
  
  # 房间连通性（双向）
  connections:
    - [living_room, kitchen]
    - [living_room, bedroom]
    - [living_room, entrance]
    - [kitchen, bathroom]
    - [living_room, charging_station]
  
  # 初始智能体状态
  agents:
    - id: robot
      label: 机器人
      type: agent
      at: living_room
      holding: null
      battery: 85
  
  # 初始人员位置
  people:
    - id: user
      label: 用户
      at: living_room
      near: sofa
```

---

## 五、完整工作流示例

### 用户指令："帮我去卫生间拿个毛巾过来，然后去充电"

#### 第 1 步：初始场景图（子图提取）

TurnRunner 收到用户输入后，SceneGraphManager 提取任务相关子图：

关键词提取：["卫生间", "毛巾", "充电"]

```
[场景图 — 任务相关子图]
位置层:
  客厅 ──contains──→ [沙发, 茶几]
  卫生间 ──contains──→ [毛巾架]
  充电站

物体层:
  毛巾架 ──on_top──→ [黄色毛巾(graspable)]

智能体:
  机器人 ──at──→ 客厅, holding: 无
  用户 ──at──→ 客厅(沙发附近)

可达性:
  客厅 ←→ 卫生间（经由厨房）
  客厅 ←→ 充电站
```

#### 第 2 步：LLM 生成计划

LLM 看到场景图后，生成计划：
1. navigate_to(卫生间)
2. pick_up(黄色毛巾)
3. navigate_to(客厅)  — 回到用户身边
4. hand_over(黄色毛巾)
5. navigate_to(充电站)

#### 第 3 步：PlanVerifier 验证

```
验证第 1 步: navigate_to(卫生间)
  ✓ 节点存在: 卫生间 ✓
  ✓ 路径可达: 客厅 → 厨房 → 卫生间 ✓
  → 模拟效果: 机器人 AT 边移到卫生间

验证第 2 步: pick_up(黄色毛巾)
  ✓ 节点存在: 黄色毛巾 ✓
  ✓ 机器人在同一位置: 机器人@卫生间, 毛巾@卫生间 ✓
  ✓ 可抓取: 黄色毛巾.affordances 包含 graspable ✓
  ✓ 手中无物品: 机器人 holding nothing ✓
  → 模拟效果: 黄色毛巾从毛巾架移到机器人手中

验证第 3 步: navigate_to(客厅)
  ✓ 节点存在: 客厅 ✓
  ✓ 路径可达: 卫生间 → 厨房 → 客厅 ✓
  → 模拟效果: 机器人 AT 边移到客厅

验证第 4 步: hand_over(黄色毛巾)
  ✓ 机器人持有黄色毛巾 ✓
  ✓ 机器人在用户附近: 机器人@客厅, 用户@客厅 ✓
  → 模拟效果: 移除 holding 边

验证第 5 步: navigate_to(充电站)
  ✓ 节点存在: 充电站 ✓
  ✓ 路径可达: 客厅 → 充电站 ✓
  → 模拟效果: 机器人 AT 边移到充电站

✓ 计划验证通过，所有 5 步的前置条件均满足。
```

#### 第 4 步：逐步执行 + 场景图更新

执行 navigate_to(卫生间) 后，场景图自动更新：
- 机器人 AT 边：客厅 → 卫生间
- 新观察到的物体可能被添加到场景图

执行 pick_up(黄色毛巾) 后：
- 黄色毛巾的 on_top(毛巾架) 边被移除
- 新增 机器人 HOLDING 黄色毛巾 边

...以此类推。

#### 第 4b 步：验证失败的情况

假设 LLM 生成了错误计划：
1. pick_up(黄色毛巾)  ← 直接拿，没先去卫生间
2. navigate_to(充电站)

PlanVerifier 会在第 1 步就发现问题：

```
✗ 计划在第 1 步失败
失败动作: pick_up(黄色毛巾)
原因: 机器人必须在 黄色毛巾 所在位置（机器人@客厅, 毛巾@卫生间）

请修正计划，确保失败步骤的前置条件被满足。
提示：需要先导航到卫生间再拿取毛巾。
```

这个反馈注入 LLM 上下文，LLM 修正计划后重新验证。

---

## 六、模块划分与文件结构

```
mosaic/
├── runtime/
│   ├── turn_runner.py          # 修改：集成场景图的三个集成点
│   ├── world_repr.py           # 新增：L0 RobotState + L3 TaskContext（上一份报告设计）
│   ├── scene_graph.py          # 新增：SceneGraph 核心数据结构
│   ├── scene_graph_manager.py  # 新增：场景图生命周期管理
│   ├── plan_verifier.py        # 新增：计划验证器
│   └── action_rules.py         # 新增：动作前置条件与效果规则
├── plugin_sdk/
│   └── types.py                # 修改：CapabilityPlugin 新增 get_action_rules() 方法
├── core/
│   └── event_bus.py            # 不变
│   └── hooks.py                # 不变
├── protocol/
│   └── events.py               # 修改：新增 scene_graph.updated 事件类型
└── ...

config/
├── mosaic.yaml                 # 修改：新增 environment 配置段
└── environments/
    └── home.yaml               # 新增：家庭环境场景图配置

plugins/capabilities/
├── navigation/__init__.py      # 修改：新增 get_action_rules() 返回导航规则
├── manipulation/__init__.py    # 修改：新增 get_action_rules() 返回操作规则
├── appliance/__init__.py       # 修改：新增 get_action_rules() 返回家电规则
└── motion/__init__.py          # 修改：新增 get_action_rules() 返回运动规则
```

### CapabilityPlugin 协议扩展

```python
@runtime_checkable
class CapabilityPlugin(Protocol):
    """能力插件接口 — 扩展场景图支持"""
    meta: PluginMeta

    def get_supported_intents(self) -> list[str]: ...
    def get_tool_definitions(self) -> list[dict[str, Any]]: ...
    async def execute(self, intent: str, params: dict, ctx: ExecutionContext) -> ExecutionResult: ...
    async def cancel(self) -> bool: ...
    async def health_check(self) -> HealthStatus: ...
    
    # ★ 新增：返回该插件所有动作的前置条件和效果规则
    def get_action_rules(self) -> list[ActionRule]: ...
    
    # ★ 新增：可供性评估（上一份报告设计）
    async def evaluate_affordance(
        self, intent: str, params: dict, robot_state: dict
    ) -> AffordanceEntry: ...
```

---

## 七、实现优先级与工作量估算

### Phase 1：核心场景图（~600 行）

| 文件 | 内容 | 行数估算 |
|------|------|---------|
| `scene_graph.py` | SceneNode, SceneEdge, SceneGraph 数据结构 + 基础查询 | ~250 |
| `action_rules.py` | ActionRule, Precondition, Effect + 内置规则 | ~150 |
| `plan_verifier.py` | PlanVerifier + 验证逻辑 | ~200 |

**交付物**：可以在场景图上做前置条件验证的独立模块

### Phase 2：管理器与集成（~400 行）

| 文件 | 内容 | 行数估算 |
|------|------|---------|
| `scene_graph_manager.py` | 生命周期管理 + 配置初始化 + 执行后更新 | ~200 |
| `turn_runner.py` 修改 | 三个集成点 | ~100 |
| `types.py` 修改 | CapabilityPlugin 协议扩展 | ~30 |
| 环境配置 `home.yaml` | 家庭环境配置 | ~80 |

**交付物**：场景图集成到 TurnRunner，LLM 能看到场景图 + 计划验证

### Phase 3：子图检索与优化（~300 行）

| 文件 | 内容 | 行数估算 |
|------|------|---------|
| `scene_graph.py` 扩展 | 子图提取算法（BFS + 关键词匹配） | ~150 |
| `scene_graph.py` 扩展 | to_prompt_text 优化（token 控制） | ~100 |
| 各 Capability 插件修改 | 实现 get_action_rules() | ~50×4 |

**交付物**：完整的场景图表征系统，支持子图检索和 token 优化

### 总工作量：~1500 行新增/修改代码

---

## 八、与论文的关系

### 8.1 论文贡献点

场景图表征为论文提供了两个重要贡献点：

**贡献 1：分层世界表征架构**
> "我们提出了一种分层世界表征架构（L0-L3），
> 其中 L1 层采用语义场景图替代传统的扁平文本描述，
> 将物理环境的空间关系、功能关系和状态信息结构化表达，
> 使 LLM 能够在结构化的世界模型上进行推理。"

**贡献 2：计划验证闭环**
> "借鉴 VeriGraph 的思路，我们在 MOSAIC 中实现了基于场景图的计划验证机制。
> LLM 生成的任务计划在物理执行前，先在场景图上模拟执行每一步，
> 验证前置条件是否满足。验证失败时，将结构化反馈注入 LLM 上下文，
> 形成 '规划-验证-修正' 的闭环，显著提升了计划的物理可行性。"

### 8.2 与 SayCan 的关系

SayCan 的核心公式：`π = argmax p(cπ|s,ℓπ) × p(ℓπ|i)`

场景图增强了这个公式的两端：
- **p(ℓπ|i)**（LLM 语义理解）：场景图为 LLM 提供结构化的环境信息，提升语义理解质量
- **p(cπ|s,ℓπ)**（可供性评估）：场景图的前置条件验证是一种更精确的可供性评估

```
SayCan 原始:  LLM 语义 × 价值函数可供性
MOSAIC 增强:  LLM(场景图增强) × 场景图前置条件验证 × 价值函数可供性
```

### 8.3 参考文献

| 工作 | 年份 | 核心贡献 | MOSAIC 借鉴点 |
|------|------|---------|-------------|
| VeriGraph | 2024 | 场景图上的计划验证 | PlanVerifier 设计 |
| MoMa-LLM | 2024 | 动态场景图 + 物体中心动作空间 | 动态更新机制 |
| EmbodiedRAG | 2024 | 3D 场景图子图检索 | 子图提取 + token 优化 |
| MomaGraph | 2025 | 统一空间-功能场景图 | affordance 编码到边 |
| GraphPlan | 2025 | 事件驱动重规划 | EventBus 集成 |
| RoboEXP | 2024 | 动作条件场景图 | 因果关系边 |
| Domain-Conditioned SG | 2024 | 场景图 → PDDL 映射 | 前置条件/效果规则 |
| SayCan | 2022 | LLM × 可供性 | 基础框架 |
| Inner Monologue | 2022 | 闭环反馈 | 验证反馈注入 |

---

## 九、结论

场景图表征是 MOSAIC 从"文本化世界理解"到"结构化世界理解"的关键演进。

核心价值：
1. **关系显式化**：空间、功能、状态关系成为一等公民，LLM 不再需要从文本推断
2. **计划可验证**：执行前在场景图上模拟验证，避免物理执行失败
3. **增量可更新**：每次执行后只更新受影响的节点和边，不重建整个描述
4. **token 可控**：子图检索确保 LLM 只看到任务相关信息

这个设计将 VeriGraph 的验证思想、MoMa-LLM 的动态更新、EmbodiedRAG 的子图检索、
MomaGraph 的功能可供性统一到 MOSAIC 的插件化架构中，
形成一个完整的"感知-表征-验证-执行-更新"闭环。
