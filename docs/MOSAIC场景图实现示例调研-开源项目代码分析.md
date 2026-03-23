# MOSAIC 场景图实现示例调研：开源项目代码级分析

> 本文调研 10+ 个开源项目的场景图实现，提取可直接复用的数据结构、序列化格式、
> 集成模式和代码模板，为 MOSAIC 场景图落地提供实战参考。

---

## 一、调研项目总览与 MOSAIC 适用性评级

| 项目 | 年份/会议 | 语言 | 代码可用性 | MOSAIC 适用性 | 核心价值 |
|------|----------|------|-----------|-------------|---------|
| **SG-Nav** | 2024/NeurIPS | Python | ★★★★★ | ★★★★★ | 层次化场景图 + LLM 提示词序列化 |
| **Taskography** | 2021/CoRL | Python | ★★★★★ | ★★★★☆ | PDDL 符号规划 + 场景图任务采样 |
| **ConceptGraphs** | 2023/ICRA | Python | ★★★★★ | ★★★☆☆ | 开放词汇 3D 场景图构建 |
| **OVSG** | 2023/CoRL | Python | ★★★★☆ | ★★★★☆ | 上下文感知实体定位 + LLM 查询 |
| **Spark-DSG** | MIT-SPARK | C++/Python | ★★★★☆ | ★★★☆☆ | 工业级场景图 API（Hydra 后端） |
| **GNN4TaskPlan** | 2024/NeurIPS | Python | ★★★★★ | ★★★★☆ | GNN 增强 LLM 任务规划 |
| **LLM-DP** | 2024 | Python | ★★★★☆ | ★★★★★ | LLM + PDDL 规划器混合架构 |
| **DovSG** | 2024 | Python | ★★★☆☆ | ★★★★☆ | 动态场景图 + 长期移动操作 |
| **HOV-SG** | 2024/RSS | Python | ★★★★☆ | ★★★☆☆ | 层次化开放词汇场景图 |
| **VeriGraph** | 2024 | 概念验证 | ★★☆☆☆ | ★★★★★ | 场景图上的计划验证（核心思想） |

---

## 二、关键项目深度代码分析

### 2.1 SG-Nav：层次化场景图 + LLM 提示词（最直接相关）

**项目地址**: [github.com/bagh2178/SG-Nav](https://github.com/bagh2178/SG-Nav)

SG-Nav 是目前最接近 MOSAIC 场景图需求的开源实现。它的核心创新是：
用三层层次化场景图（Object → Group → Room）来提示 LLM 做导航决策。

#### 场景图数据模型

SG-Nav 定义了三种节点类型和两种边类型：

```python
# SG-Nav 的场景图节点（从论文和代码提取的核心模式）
# 三层层次结构：Object < Group < Room

class SceneGraphNode:
    """SG-Nav 节点"""
    node_id: int              # 唯一 ID
    level: str                # "object" | "group" | "room"
    category: str             # 语义类别（"chair", "dining_area", "kitchen"）
    confidence: float         # 检测置信度
    position_3d: np.ndarray   # 3D 点云质心
    instance_mask: np.ndarray # 点云实例掩码

class SceneGraphEdge:
    """SG-Nav 边"""
    source_id: int
    target_id: int
    edge_type: str            # "affiliation" (跨层) | "relationship" (同层)
    relation: str             # "on_top_of", "next_to", "belongs_to", ...
```

#### 关键实现模式：增量式场景图构建

SG-Nav 的场景图不是一次性构建的，而是随机器人探索增量更新：

```python
# SG-Nav 增量更新伪代码（从论文 Section 3.2 提取）
def update_scene_graph(self, new_observation, timestamp):
    # 1. 从 RGB-D 检测新物体节点
    new_object_nodes = self.detect_objects(new_observation)
    
    # 2. 与已有节点匹配（避免重复）
    for node in new_object_nodes:
        matched = self.match_with_existing(node)
        if matched:
            self.merge_node(matched, node)  # 更新已有节点
        else:
            self.register_node(node)         # 注册新节点
    
    # 3. 密集连接新节点到所有已有节点（LLM 批量推理边关系）
    # 关键优化：一次 LLM 调用推理所有 m*(m+n) 条边
    edge_prompt = self.build_batch_edge_prompt(new_nodes, existing_nodes)
    edges = self.llm_infer_edges(edge_prompt)
    
    # 4. 剪枝不重要的边
    self.prune_edges(edges)
    
    # 5. 更新 Group 节点（基于物体关联性）
    self.update_groups()
    
    # 6. 更新 Room 节点（基于空间分割）
    self.update_rooms()
```

#### 关键实现模式：场景图序列化为 LLM 提示词

这是 MOSAIC 最需要借鉴的部分——如何把场景图转化为 LLM 能理解的文本：

```python
# SG-Nav 的层次化 Chain-of-Thought 提示词格式（从论文提取）
# 将场景图分割为子图，每个子图独立提示 LLM

SUBGRAPH_PROMPT_TEMPLATE = """
Given the following scene subgraph:
Room: {room_name}
Groups in this room:
{group_descriptions}
Objects:
{object_descriptions}
Relationships:
{edge_descriptions}

Question: How likely is the target object "{target}" 
located in this subgraph? 

Think step by step:
1. What room is this? What objects are typically found here?
2. Are there any groups related to the target?
3. Based on spatial relationships, where might the target be?

Score (0-1):
"""

# 子图提取策略：以 Room 节点为中心，包含其下属所有 Group 和 Object
def extract_subgraphs(scene_graph):
    subgraphs = []
    for room in scene_graph.get_nodes_by_level("room"):
        sg = SubGraph(root=room)
        sg.groups = scene_graph.get_children(room.id, "affiliation")
        for group in sg.groups:
            sg.objects.extend(
                scene_graph.get_children(group.id, "affiliation")
            )
        sg.edges = scene_graph.get_intra_edges(sg.all_node_ids)
        subgraphs.append(sg)
    return subgraphs
```

#### MOSAIC 可直接复用的模式

1. **三层层次结构** → MOSAIC 的 Room > Furniture > Object 层次
2. **增量更新** → MOSAIC 的 `update_from_execution()` 模式
3. **子图提取 + 独立提示** → MOSAIC 的 `extract_task_subgraph()` 方法
4. **批量边推理** → MOSAIC 可用于初始化时从配置推断缺失的边关系



### 2.2 Taskography：PDDL 符号规划 + 场景图（计划验证的最佳参考）

**项目地址**: [github.com/taskography/taskography](https://github.com/taskography/taskography)

Taskography 是第一个大规模机器人任务规划基准，基于 3D 场景图。
它的核心价值在于：展示了如何将场景图转化为 PDDL 规划域，实现符号级任务规划。

#### PDDL 域定义（直接对应 MOSAIC 的 ActionRule）

Taskography 定义了多个 PDDL 域文件，其中 `taskographyv2.pddl`（Rearrangement 任务）
最接近 MOSAIC 的家庭服务场景：

```pddl
;; Taskography Rearrangement 域（简化版，从 scenegraph/domain/taskographyv2.pddl 提取）
(define (domain taskography-rearrangement)
  (:requirements :strips :typing)
  
  ;; 类型定义 — 对应 MOSAIC 的 SceneNodeType
  (:types
    room - location        ;; 房间
    receptacle - object    ;; 容器（桌子、柜子）
    item - object          ;; 可操作物品
    robot - agent          ;; 机器人
  )
  
  ;; 谓词定义 — 对应 MOSAIC 的场景图边类型
  (:predicates
    (robot-at ?r - robot ?l - location)        ;; AT 边
    (item-at ?i - item ?l - location)          ;; 物品位置
    (on ?i - item ?rec - receptacle)           ;; ON_TOP 边
    (holding ?r - robot ?i - item)             ;; HOLDING 边
    (hand-empty ?r - robot)                    ;; 手空
    (connected ?l1 - location ?l2 - location)  ;; REACHABLE 边
    (item-graspable ?i - item)                 ;; affordance
  )
  
  ;; 动作定义 — 对应 MOSAIC 的 ActionRule
  (:action navigate
    :parameters (?r - robot ?from - location ?to - location)
    :precondition (and 
      (robot-at ?r ?from)
      (connected ?from ?to)
    )
    :effect (and 
      (robot-at ?r ?to)
      (not (robot-at ?r ?from))
    )
  )
  
  (:action pick-up
    :parameters (?r - robot ?i - item ?rec - receptacle ?l - location)
    :precondition (and
      (robot-at ?r ?l)
      (item-at ?i ?l)
      (on ?i ?rec)
      (hand-empty ?r)
      (item-graspable ?i)
    )
    :effect (and
      (holding ?r ?i)
      (not (on ?i ?rec))
      (not (hand-empty ?r))
    )
  )
  
  (:action place
    :parameters (?r - robot ?i - item ?rec - receptacle ?l - location)
    :precondition (and
      (robot-at ?r ?l)
      (holding ?r ?i)
    )
    :effect (and
      (on ?i ?rec)
      (hand-empty ?r)
      (not (holding ?r ?i))
    )
  )
)
```

#### 场景图到 PDDL 问题的转换

Taskography 的核心代码展示了如何将 3D 场景图转化为 PDDL 问题实例：

```python
# 从 Taskography 的任务采样器提取的核心模式
# scenegraph/task_sampler.py 的简化版

def scene_graph_to_pddl_problem(scene_graph, task_spec):
    """将场景图转化为 PDDL 问题文件
    
    这个转换过程正是 MOSAIC 的 PlanVerifier 需要做的事情：
    将场景图的节点和边映射为 PDDL 的对象和初始状态谓词。
    """
    objects = []    # PDDL 对象声明
    init_state = [] # PDDL 初始状态
    
    # 1. 从场景图节点生成 PDDL 对象
    for node in scene_graph.nodes:
        if node.type == "room":
            objects.append(f"{node.id} - location")
        elif node.type == "receptacle":
            objects.append(f"{node.id} - receptacle")
        elif node.type == "item":
            objects.append(f"{node.id} - item")
    objects.append("robot0 - robot")
    
    # 2. 从场景图边生成 PDDL 初始状态
    for edge in scene_graph.edges:
        if edge.type == "contains" and edge.source.type == "room":
            # 房间包含物品 → item-at
            init_state.append(f"(item-at {edge.target.id} {edge.source.id})")
        elif edge.type == "on_top":
            init_state.append(f"(on {edge.source.id} {edge.target.id})")
        elif edge.type == "connected":
            init_state.append(f"(connected {edge.source.id} {edge.target.id})")
            init_state.append(f"(connected {edge.target.id} {edge.source.id})")
    
    # 3. 机器人初始状态
    robot_location = scene_graph.get_agent_location()
    init_state.append(f"(robot-at robot0 {robot_location})")
    init_state.append("(hand-empty robot0)")
    
    # 4. 物品可抓取性
    for node in scene_graph.get_nodes_by_type("item"):
        if "graspable" in node.affordances:
            init_state.append(f"(item-graspable {node.id})")
    
    # 5. 目标状态（从任务规格生成）
    goal = task_spec.to_pddl_goal()
    
    return PDDLProblem(objects=objects, init=init_state, goal=goal)
```

#### MOSAIC 可直接复用的模式

1. **PDDL 前置条件/效果** → 直接映射为 MOSAIC 的 `Precondition` 和 `Effect` 数据类
2. **场景图→PDDL 转换** → MOSAIC 的 `verify_preconditions()` 本质上就是在做 PDDL 前置条件检查
3. **任务采样** → MOSAIC 可以用类似方式从场景图自动生成测试用例
4. **PDDLGym 接口** → 如果 MOSAIC 未来需要强化学习训练，可以直接对接

### 2.3 OVSG：上下文感知实体定位（LLM 查询场景图的最佳参考）

**项目地址**: [github.com/changhaonan/OVSG](https://github.com/changhaonan/OVSG)

OVSG 的核心创新是：不只按物体类别查找，而是按上下文查找。
"拿起厨房桌子上的杯子" vs "拿起杯子" — 前者需要理解空间上下文。

#### 场景图数据结构

```python
# OVSG 的场景图核心数据结构（从代码提取）
# ovsg/scene_graph.py

class OVSGNode:
    """OVSG 节点 — 支持三种实体类型"""
    entity_type: str          # "object" | "agent" | "region"
    instance_id: int          # 实例 ID
    category: str             # 语义类别
    clip_embedding: np.ndarray  # CLIP 特征向量（用于开放词汇匹配）
    position_3d: np.ndarray   # 3D 位置
    bbox_3d: np.ndarray       # 3D 包围盒

class OVSGEdge:
    """OVSG 边 — 空间关系"""
    source_id: int
    target_id: int
    relation: str             # "on", "in", "next_to", "near", ...
    confidence: float

class OVSG:
    """开放词汇场景图"""
    nodes: list[OVSGNode]
    edges: list[OVSGEdge]
    
    def query(self, text_query: str) -> list[OVSGNode]:
        """用自然语言查询场景图
        
        核心流程：
        1. LLM 解析查询 → 提取目标实体 + 上下文约束
        2. CLIP 匹配 → 找到候选节点
        3. 上下文过滤 → 用场景图边验证上下文约束
        """
        # LLM 解析："pick up a cup on the kitchen table"
        # → target: "cup", context: [("on", "kitchen table")]
        parsed = self.llm_parse_query(text_query)
        
        # CLIP 匹配候选
        candidates = self.clip_match(parsed.target)
        
        # 上下文过滤
        for constraint in parsed.context:
            candidates = [c for c in candidates 
                         if self.check_edge(c.id, constraint.relation, 
                                           constraint.anchor)]
        
        return candidates
```

#### LLM 查询解析的 Prompt 设计

```python
# OVSG 的 LLM 查询解析 Prompt（从 example/exp_ovsg_llm.py 提取模式）
QUERY_PARSE_PROMPT = """
Parse the following query into structured format:
Query: "{query}"

Extract:
1. Target entity (what to find)
2. Context constraints (spatial relationships with other entities)

Output JSON:
{{
  "target": "entity name",
  "context": [
    {{"relation": "on/in/next_to/near", "anchor": "reference entity"}}
  ]
}}

Examples:
Query: "pick up a cup on the kitchen table"
Output: {{"target": "cup", "context": [{{"relation": "on", "anchor": "kitchen table"}}]}}

Query: "navigate to the sofa where someone is sitting"
Output: {{"target": "sofa", "context": [{{"relation": "near", "anchor": "person"}}]}}
"""
```

#### MOSAIC 可直接复用的模式

1. **上下文感知查询** → MOSAIC 的 `find_by_label()` 可以增强为上下文感知版本
2. **LLM 查询解析** → 当用户说"帮我拿茶几上的杯子"时，解析出空间约束
3. **CLIP 嵌入** → 未来 MOSAIC 接入视觉感知时，可以用 CLIP 做开放词汇匹配

### 2.4 LLM-DP：LLM + PDDL 混合规划（VeriGraph 思路的最佳实现参考）

**项目地址**: [github.com/itl-ed/llm-dp](https://github.com/itl-ed/llm-dp)

LLM-DP 是 VeriGraph 计划验证思路的最完整开源实现。
它在 ALFWorld 环境中将 LLM 的常识推理与 PDDL 的形式化验证结合。

#### 核心架构

```python
# LLM-DP 的核心架构（从代码提取的模式）

class LLMDynamicPlanner:
    """LLM + PDDL 混合规划器
    
    核心流程：
    1. LLM 观察环境 → 生成信念状态（场景图的文本版本）
    2. 信念状态 → 转化为 PDDL 问题
    3. PDDL 规划器 → 生成形式化计划
    4. 计划执行 → 观察结果 → 更新信念状态
    5. 如果计划失败 → LLM 重新评估 → 重新规划
    """
    
    def __init__(self, llm, pddl_planner, domain_file):
        self.llm = llm                    # GPT-3.5/4
        self.planner = pddl_planner       # LAPKT (BFS-f 或 FF)
        self.domain = load_pddl(domain_file)
        self.belief_state = {}            # 当前信念状态
    
    def plan_and_execute(self, task_description, environment):
        """规划并执行任务"""
        # 1. LLM 初始化信念状态
        observation = environment.observe()
        self.belief_state = self.llm_init_belief(observation, task_description)
        
        while not task_complete:
            # 2. 信念状态 → PDDL 问题
            pddl_problem = self.belief_to_pddl(self.belief_state)
            
            # 3. PDDL 规划器求解
            plan = self.planner.solve(self.domain, pddl_problem)
            
            if plan is None:
                # 规划失败 → LLM 重新评估信念状态
                self.belief_state = self.llm_revise_belief(
                    observation, self.belief_state
                )
                continue
            
            # 4. 逐步执行计划
            for action in plan:
                result = environment.execute(action)
                observation = environment.observe()
                
                # 5. 更新信念状态
                self.update_belief(action, result, observation)
                
                if result.failed:
                    break  # 执行失败 → 重新规划
    
    def belief_to_pddl(self, belief):
        """将信念状态转化为 PDDL 问题
        
        这个函数本质上就是 MOSAIC 的 scene_graph → precondition_check 的过程。
        """
        objects = []
        init_facts = []
        
        for entity in belief["entities"]:
            objects.append(f"{entity['id']} - {entity['type']}")
            for prop in entity["properties"]:
                init_facts.append(f"({prop} {entity['id']})")
        
        for relation in belief["relations"]:
            init_facts.append(
                f"({relation['type']} {relation['subject']} {relation['object']})"
            )
        
        return PDDLProblem(
            objects=objects,
            init=init_facts,
            goal=belief["goal"],
        )
```

#### MOSAIC 可直接复用的模式

1. **信念状态 ↔ 场景图** → LLM-DP 的 belief_state 就是 MOSAIC 场景图的简化版
2. **PDDL 规划器集成** → MOSAIC 可以选择性地用 PDDL 规划器做计划验证
3. **LLM 信念修正** → 当执行失败时，让 LLM 重新评估场景图状态
4. **混合架构** → LLM 做高层推理，PDDL 做形式化验证，完美匹配 MOSAIC 的设计



### 2.5 Spark-DSG：工业级场景图 API（数据结构的最佳参考）

**项目地址**: [github.com/MIT-SPARK/Spark-DSG](https://github.com/MIT-SPARK/Spark-DSG)

MIT-SPARK 实验室的 Spark-DSG 是 Hydra 系统的核心数据结构库，
提供了 C++ 和 Python 绑定的工业级场景图 API。

#### 层次化场景图结构

Spark-DSG 定义了 5 层层次结构（从底到顶）：

```
Layer 1: Places (导航可达点)
Layer 2: Objects (物体实例)  
Layer 3: Rooms (房间)
Layer 4: Buildings (建筑/楼层)
Layer 5: (预留)
```

```python
# Spark-DSG Python API 使用示例（从官方 notebook 提取）
import spark_dsg as dsg

# 创建场景图
G = dsg.DynamicSceneGraph()

# 添加节点（指定层级）
G.add_node(dsg.LayerId.OBJECTS, "cup_1", 
           attrs=dsg.ObjectNodeAttributes(
               position=[1.0, 2.0, 0.8],
               name="cup",
               bounding_box=dsg.BoundingBox(...)
           ))

G.add_node(dsg.LayerId.ROOMS, "kitchen",
           attrs=dsg.RoomNodeAttributes(
               position=[3.0, 2.0, 0.0],
               name="kitchen"
           ))

# 添加边（跨层或同层）
G.insert_edge("cup_1", "kitchen")  # 物体属于房间

# 查询
kitchen_objects = G.get_children("kitchen")  # 获取厨房内所有物体
rooms = G.get_layer(dsg.LayerId.ROOMS)       # 获取所有房间
```

#### MOSAIC 可借鉴的设计

1. **分层 ID 系统** → 每个节点 ID 编码了层级信息，查询效率高
2. **属性类型化** → 不同层级的节点有不同的属性类（ObjectNodeAttributes vs RoomNodeAttributes）
3. **动态场景图** → 支持时间维度的节点/边增删
4. **序列化** → 支持 JSON/MessagePack 序列化，可持久化和网络传输

### 2.6 GNN4TaskPlan：GNN 增强 LLM 任务规划

**项目地址**: [github.com/WxxShirley/GNN4TaskPlan](https://github.com/WxxShirley/GNN4TaskPlan)

GNN4TaskPlan 的核心发现：LLM 在图结构上的决策能力有理论缺陷，
GNN 可以弥补这个缺陷。

#### 任务图数据结构

```python
# GNN4TaskPlan 的任务图表示（从代码提取的核心模式）
# 任务被表示为有向无环图（DAG），节点是子任务，边是依赖关系

class TaskGraph:
    """任务图 — 子任务 + 依赖关系"""
    nodes: list[TaskNode]     # 子任务节点
    edges: list[TaskEdge]     # 依赖边
    
class TaskNode:
    node_id: str
    tool_name: str            # 对应的工具/API
    description: str          # 子任务描述
    parameters: dict          # 参数
    embedding: np.ndarray     # GNN 编码的节点嵌入

class TaskEdge:
    source_id: str            # 前置子任务
    target_id: str            # 后续子任务
    dependency_type: str      # "data" | "control" | "resource"
```

#### GNN 检索增强的规划流程

```python
# GNN4TaskPlan 的核心流程
def gnn_enhanced_planning(user_request, tool_graph):
    """GNN 增强的任务规划
    
    1. 构建工具依赖图
    2. GNN 编码图结构
    3. 基于 GNN 嵌入检索相关子图
    4. 将子图信息注入 LLM 提示词
    """
    # 1. GNN 编码工具图
    node_embeddings = gnn_encoder(tool_graph)
    
    # 2. 用户请求 → 查询嵌入
    query_embedding = text_encoder(user_request)
    
    # 3. 检索最相关的工具子图
    relevant_tools = retrieve_by_similarity(
        query_embedding, node_embeddings, top_k=10
    )
    
    # 4. 构建增强提示词
    prompt = f"""
    User request: {user_request}
    
    Available tools (ranked by relevance):
    {format_tools(relevant_tools)}
    
    Tool dependencies:
    {format_dependencies(relevant_tools, tool_graph)}
    
    Generate a plan as a sequence of tool calls:
    """
    
    # 5. LLM 生成计划
    plan = llm.generate(prompt)
    return plan
```

#### MOSAIC 可借鉴的设计

1. **GNN 编码场景图** → 未来 MOSAIC 可以用 GNN 编码场景图，增强子图检索
2. **工具依赖图** → MOSAIC 的 Capability 之间的依赖关系可以建模为图
3. **检索增强** → 大型环境中，GNN 嵌入比关键词匹配更精确



### 2.7 VeriGraph：场景图上的计划验证（核心思想提取）

**论文地址**: [arxiv.org/html/2411.10446v1](https://arxiv.org/html/2411.10446v1)

VeriGraph 没有完整的开源代码，但论文提供了足够的实现细节。
它的核心贡献是 MOSAIC PlanVerifier 的直接灵感来源。

#### 迭代式计划验证算法

```python
# VeriGraph 的迭代式计划验证（从论文 Section III 提取的算法）

class VeriGraphPlanner:
    """VeriGraph 迭代式规划器
    
    核心参数：
    - error_threshold τ = 5（最佳平衡点）
    - actions_per_iteration = 3（每次验证 3 步）
    - max_iterations = 10
    """
    
    def __init__(self, scene_graph_generator, task_planner, verifier):
        self.sgg = scene_graph_generator   # VLM (GPT-4V)
        self.planner = task_planner        # LLM (GPT-4)
        self.verifier = verifier           # 场景图验证器
    
    def plan(self, image, instruction):
        """迭代式规划"""
        # 1. 从图像生成场景图
        scene_graph = self.sgg.generate(image)
        
        # 2. 初始规划
        plan = self.planner.generate_plan(scene_graph, instruction)
        
        # 3. 迭代验证 + 修正
        for iteration in range(self.max_iterations):
            # 每次取 3 步验证
            chunk = plan[:self.actions_per_iter]
            
            # 在场景图上模拟执行
            sim_graph = scene_graph.copy()
            errors = []
            
            for action in chunk:
                # 检查前置条件
                ok, reason = self.verifier.check_preconditions(
                    sim_graph, action
                )
                if not ok:
                    errors.append(f"Step {action}: {reason}")
                    break
                
                # 应用效果
                sim_graph = self.verifier.apply_effects(sim_graph, action)
            
            if not errors:
                # 验证通过 → 执行这批动作
                self.execute(chunk)
                plan = plan[self.actions_per_iter:]
                # 重新观察 → 更新场景图
                scene_graph = self.sgg.generate(self.observe())
                if not plan:
                    return SUCCESS
            else:
                # 验证失败 → 反馈给 LLM 修正
                feedback = "\n".join(errors)
                plan = self.planner.replan(scene_graph, instruction, feedback)
        
        return FAILURE
```

#### 关键实验数据（对 MOSAIC 的指导意义）

| 配置 | 成功率 | 说明 |
|------|--------|------|
| SayCan（纯文本列表） | 0.00-0.17 | 没有场景图，纯靠 LLM 猜测 |
| ViLa（直接看图像） | 0.05-0.62 | VLM 直接从图像规划 |
| VeriGraph（直接规划） | 0.35-0.73 | 有场景图但不迭代验证 |
| VeriGraph（迭代验证） | 0.55-0.86 | 场景图 + 迭代验证 |
| VeriGraph（真实场景图） | ~100% | 场景图完全准确时 |

**核心结论**：场景图质量决定一切。当场景图准确时，迭代验证几乎 100% 成功。
这对 MOSAIC 的启示是：MOSAIC 的场景图来自配置文件 + ROS2 传感器，
比 VLM 生成的场景图更准确，因此 PlanVerifier 的效果应该更好。

### 2.8 ConceptGraphs：开放词汇 3D 场景图构建

**项目地址**: [github.com/concept-graphs/concept-graphs](https://github.com/concept-graphs/concept-graphs)

ConceptGraphs 展示了如何从 RGB-D 视频流构建开放词汇场景图。
虽然 MOSAIC 当前阶段不需要视觉构建，但其数据结构设计值得参考。

#### 场景图节点表示

```python
# ConceptGraphs 的节点表示（从代码提取的核心模式）
# 每个节点是一个 3D 物体实例

class ConceptNode:
    """ConceptGraphs 节点"""
    instance_id: int
    # 语义特征（多视角融合）
    clip_features: np.ndarray      # CLIP 视觉特征（768维）
    text_features: np.ndarray      # 文本描述特征
    caption: str                   # LLM 生成的物体描述
    category: str                  # 物体类别
    
    # 几何特征
    point_cloud: np.ndarray        # 3D 点云 (N, 3)
    centroid: np.ndarray           # 质心 (3,)
    bbox_3d: np.ndarray            # 3D 包围盒
    
    # 多视角观测
    observations: list[Observation]  # 从不同视角的观测
    
class Observation:
    """单次观测"""
    frame_id: int
    camera_pose: np.ndarray        # 4x4 变换矩阵
    mask_2d: np.ndarray            # 2D 分割掩码
    clip_feature: np.ndarray       # 该视角的 CLIP 特征
    confidence: float

# 边通过空间关系推断
class ConceptEdge:
    source_id: int
    target_id: int
    relation: str                  # LLM 推断的空间关系
    spatial_distance: float        # 3D 距离
```

#### 多视角融合算法

```python
# ConceptGraphs 的核心：多视角特征融合
def fuse_observations(existing_node, new_observation):
    """将新观测融合到已有节点
    
    关键：不是简单平均，而是加权融合，
    高置信度的观测权重更大。
    """
    # 1. 检查是否匹配（CLIP 特征相似度 + 3D 重叠度）
    similarity = cosine_similarity(
        existing_node.clip_features, 
        new_observation.clip_feature
    )
    overlap = compute_3d_iou(
        existing_node.point_cloud, 
        new_observation.point_cloud
    )
    
    if similarity > 0.7 and overlap > 0.3:
        # 2. 融合特征（加权平均）
        w = new_observation.confidence
        existing_node.clip_features = (
            existing_node.clip_features * (1 - w) + 
            new_observation.clip_feature * w
        )
        # 3. 扩展点云
        existing_node.point_cloud = np.vstack([
            existing_node.point_cloud, 
            new_observation.point_cloud
        ])
        # 4. 更新包围盒
        existing_node.bbox_3d = compute_bbox(existing_node.point_cloud)
        
        existing_node.observations.append(new_observation)
        return True
    
    return False  # 不匹配，创建新节点
```

#### MOSAIC 可借鉴的设计

1. **多源融合** → MOSAIC 的场景图节点可以融合多个传感器的数据
2. **置信度加权** → 不同数据源的可靠性不同，需要加权
3. **增量更新** → 新观测与已有节点匹配 → 融合或创建新节点



---

## 三、跨项目模式提取：MOSAIC 可直接复用的 8 个代码模板

### 模板 1：场景图核心数据结构（综合 SG-Nav + Spark-DSG + OVSG）

```python
"""MOSAIC 场景图核心数据结构 — 综合最佳实践"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import copy

class NodeType(Enum):
    ROOM = "room"
    FURNITURE = "furniture"
    APPLIANCE = "appliance"
    OBJECT = "object"
    AGENT = "agent"
    PERSON = "person"
    WAYPOINT = "waypoint"
    PART = "part"

class EdgeType(Enum):
    # 层次关系（SG-Nav 的 affiliation）
    CONTAINS = "contains"
    PART_OF = "part_of"
    # 空间关系（OVSG 的 spatial relations）
    ON_TOP = "on_top"
    INSIDE = "inside"
    NEXT_TO = "next_to"
    REACHABLE = "reachable"
    # 智能体关系
    AT = "at"
    HOLDING = "holding"
    NEAR = "near"
    # 功能关系（ConceptGraphs 启发）
    SUPPORTS = "supports"
    # 因果关系（RoboEXP 启发）
    REVEALS = "reveals"
    PRODUCES = "produces"

@dataclass
class SceneNode:
    node_id: str
    node_type: NodeType
    label: str
    # 空间（Spark-DSG 风格）
    position: tuple[float, float] | None = None
    # 状态（MomaGraph 启发）
    state: dict[str, str] = field(default_factory=dict)
    # 可供性（直接编码，不单独建边）
    affordances: list[str] = field(default_factory=list)
    # 属性
    properties: dict[str, Any] = field(default_factory=dict)
    # 元数据（ConceptGraphs 启发）
    confidence: float = 1.0
    last_observed: float = 0.0
    source: str = "config"  # "config" | "sensor" | "inferred"

@dataclass
class SceneEdge:
    source_id: str
    target_id: str
    edge_type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
```

### 模板 2：场景图序列化为 LLM 提示词（SG-Nav 风格）

```python
def to_prompt_text(graph, max_nodes: int = 30) -> str:
    """将场景图序列化为 LLM 可理解的层次化文本
    
    格式设计原则（综合 SG-Nav + EmbodiedRAG）：
    1. 层次化展示：位置层 → 物体层 → 智能体层
    2. 关系内联：用箭头表示关系，减少 token
    3. 状态标注：用括号标注关键状态
    4. 可达性单独列出：方便 LLM 做路径规划
    """
    lines = ["[场景图]"]
    
    # 位置层
    rooms = graph.find_by_type(NodeType.ROOM)
    if rooms:
        lines.append("位置层:")
        for room in rooms:
            children = graph.get_children(room.node_id, EdgeType.CONTAINS)
            child_labels = [c.label for c in children]
            lines.append(f"  {room.label} ──contains──→ [{', '.join(child_labels)}]")
    
    # 物体层（只展示有物品的家具）
    furniture = graph.find_by_type(NodeType.FURNITURE)
    object_lines = []
    for f in furniture:
        objects_on = graph.get_children(f.node_id, EdgeType.ON_TOP)
        objects_in = graph.get_children(f.node_id, EdgeType.INSIDE)
        if objects_on or objects_in:
            items = []
            for obj in objects_on + objects_in:
                state_str = f"({','.join(f'{k}={v}' for k,v in obj.state.items())})" if obj.state else ""
                aff_str = f"[{'|'.join(obj.affordances)}]" if obj.affordances else ""
                items.append(f"{obj.label}{state_str}{aff_str}")
            object_lines.append(f"  {f.label} ──on/in──→ [{', '.join(items)}]")
    if object_lines:
        lines.append("物体层:")
        lines.extend(object_lines)
    
    # 智能体层
    agent = graph.find_by_type(NodeType.AGENT)
    if agent:
        a = agent[0]
        at_nodes = graph.get_children(a.node_id, EdgeType.AT)
        holding = graph.get_children(a.node_id, EdgeType.HOLDING)
        at_label = at_nodes[0].label if at_nodes else "未知"
        hold_label = holding[0].label if holding else "无"
        lines.append(f"智能体: 机器人 ──at──→ {at_label}, holding: {hold_label}")
    
    persons = graph.find_by_type(NodeType.PERSON)
    for p in persons:
        at_nodes = graph.get_children(p.node_id, EdgeType.AT)
        at_label = at_nodes[0].label if at_nodes else "未知"
        lines.append(f"  {p.label} ──at──→ {at_label}")
    
    # 可达性
    reachable_edges = [e for e in graph._edges if e.edge_type == EdgeType.REACHABLE]
    if reachable_edges:
        pairs = set()
        for e in reachable_edges:
            src = graph.get_node(e.source_id)
            tgt = graph.get_node(e.target_id)
            if src and tgt:
                pair = tuple(sorted([src.label, tgt.label]))
                pairs.add(pair)
        lines.append("可达性:")
        for a, b in sorted(pairs):
            lines.append(f"  {a} ←→ {b}")
    
    return "\n".join(lines)
```

### 模板 3：前置条件检查（Taskography PDDL 风格）

```python
def check_precondition(graph, precondition, params) -> tuple[bool, str]:
    """检查单个前置条件（Taskography PDDL 映射到 Python）
    
    将 PDDL 的 (:precondition ...) 转化为场景图查询。
    """
    ctype = precondition.condition_type
    
    # 解析参数模板
    resolved = {k: params.get(v.strip("{}"), v) 
                for k, v in precondition.params.items()}
    
    if ctype == "node_exists":
        label = resolved["label"]
        nodes = graph.find_by_label(label)
        if nodes:
            return True, f"节点 '{label}' 存在"
        return False, f"场景图中不存在 '{label}'"
    
    elif ctype == "agent_at_same_location":
        obj_label = resolved["object"]
        agent = graph.get_agent_node()
        obj_nodes = graph.find_by_label(obj_label)
        if not agent or not obj_nodes:
            return False, f"找不到机器人或 '{obj_label}'"
        agent_loc = graph.get_location_of(agent.node_id)
        obj_loc = graph.get_location_of(obj_nodes[0].node_id)
        if agent_loc and obj_loc and agent_loc.node_id == obj_loc.node_id:
            return True, "机器人与目标在同一位置"
        agent_name = agent_loc.label if agent_loc else "未知"
        obj_name = obj_loc.label if obj_loc else "未知"
        return False, f"机器人在{agent_name}，{obj_label}在{obj_name}"
    
    elif ctype == "agent_not_holding":
        agent = graph.get_agent_node()
        if not agent:
            return False, "找不到机器人节点"
        holding = graph.get_children(agent.node_id, EdgeType.HOLDING)
        if not holding:
            return True, "机器人手中无物品"
        return False, f"机器人正持有 {holding[0].label}"
    
    elif ctype == "node_has_affordance":
        node_label = resolved["node"]
        affordance = resolved["affordance"]
        nodes = graph.find_by_label(node_label)
        if not nodes:
            return False, f"找不到 '{node_label}'"
        if affordance in nodes[0].affordances:
            return True, f"'{node_label}' 具有 {affordance} 能力"
        return False, f"'{node_label}' 不具有 {affordance} 能力"
    
    elif ctype == "path_reachable":
        # BFS 检查可达性
        agent = graph.get_agent_node()
        target_label = resolved.get("to", "")
        target_nodes = graph.find_by_label(target_label)
        if not agent or not target_nodes:
            return False, "找不到起点或终点"
        agent_loc = graph.get_location_of(agent.node_id)
        if not agent_loc:
            return False, "无法确定机器人位置"
        # BFS
        path = bfs_find_path(graph, agent_loc.node_id, 
                            target_nodes[0].node_id, EdgeType.REACHABLE)
        if path:
            path_labels = [graph.get_node(n).label for n in path]
            return True, f"路径: {' → '.join(path_labels)}"
        return False, f"从 {agent_loc.label} 到 {target_label} 无可达路径"
    
    return False, f"未知条件类型: {ctype}"


def bfs_find_path(graph, start_id, end_id, edge_type):
    """BFS 查找路径"""
    from collections import deque
    visited = {start_id}
    queue = deque([(start_id, [start_id])])
    while queue:
        current, path = queue.popleft()
        if current == end_id:
            return path
        # 获取所有 REACHABLE 邻居（双向）
        for edge in graph._edges:
            if edge.edge_type != edge_type:
                continue
            neighbor = None
            if edge.source_id == current and edge.target_id not in visited:
                neighbor = edge.target_id
            elif edge.target_id == current and edge.source_id not in visited:
                neighbor = edge.source_id
            if neighbor:
                visited.add(neighbor)
                queue.append((neighbor, path + [neighbor]))
    return None
```

### 模板 4：动作效果模拟（VeriGraph 风格）

```python
def apply_effect(graph, effect, params) -> None:
    """在场景图上应用动作效果（原地修改）
    
    对应 Taskography PDDL 的 (:effect ...) 部分。
    """
    etype = effect.effect_type
    resolved = {k: params.get(v.strip("{}"), v) 
                for k, v in effect.params.items()}
    
    if etype == "move_agent":
        # 移动机器人到新位置
        agent = graph.get_agent_node()
        target_label = resolved["to"]
        target = graph.find_by_label(target_label)
        if agent and target:
            # 移除旧 AT 边
            graph.remove_edges(agent.node_id, None, EdgeType.AT)
            # 添加新 AT 边
            graph.add_edge(SceneEdge(
                source_id=agent.node_id,
                target_id=target[0].node_id,
                edge_type=EdgeType.AT,
            ))
    
    elif etype == "transfer_holding":
        # 拿起物品：移除物品的空间边，添加 HOLDING 边
        agent = graph.get_agent_node()
        obj_label = resolved["object"]
        obj = graph.find_by_label(obj_label)
        if agent and obj:
            obj_node = obj[0]
            # 移除物品的 ON_TOP/INSIDE 边
            graph.remove_edges(obj_node.node_id, None, EdgeType.ON_TOP)
            graph.remove_edges(None, obj_node.node_id, EdgeType.ON_TOP)
            graph.remove_edges(obj_node.node_id, None, EdgeType.INSIDE)
            graph.remove_edges(None, obj_node.node_id, EdgeType.INSIDE)
            # 添加 HOLDING 边
            graph.add_edge(SceneEdge(
                source_id=agent.node_id,
                target_id=obj_node.node_id,
                edge_type=EdgeType.HOLDING,
            ))
    
    elif etype == "remove_holding":
        # 放下/递交物品
        agent = graph.get_agent_node()
        obj_label = resolved["object"]
        obj = graph.find_by_label(obj_label)
        if agent and obj:
            graph.remove_edges(agent.node_id, obj[0].node_id, EdgeType.HOLDING)
    
    elif etype == "update_state":
        # 更新节点状态
        node_label = resolved["node"]
        new_state = resolved.get("state", {})
        nodes = graph.find_by_label(node_label)
        if nodes:
            nodes[0].state.update(new_state)
```

### 模板 5：子图提取（EmbodiedRAG 风格）

```python
def extract_task_subgraph(graph, task_keywords, max_hops=2):
    """基于任务关键词提取相关子图
    
    算法（EmbodiedRAG 启发）：
    1. 关键词匹配 → 种子节点
    2. BFS 扩展 N 跳 → 相关节点
    3. 始终包含 agent + person 节点
    4. 收集所有相关边
    """
    seed_ids = set()
    
    # 1. 关键词匹配种子节点
    for keyword in task_keywords:
        for node in graph._nodes.values():
            if keyword in node.label:
                seed_ids.add(node.node_id)
    
    # 2. BFS 扩展
    expanded = set(seed_ids)
    frontier = set(seed_ids)
    for hop in range(max_hops):
        next_frontier = set()
        for nid in frontier:
            for edge in graph._edges:
                neighbor = None
                if edge.source_id == nid:
                    neighbor = edge.target_id
                elif edge.target_id == nid:
                    neighbor = edge.source_id
                if neighbor and neighbor not in expanded:
                    next_frontier.add(neighbor)
                    expanded.add(neighbor)
        frontier = next_frontier
    
    # 3. 始终包含 agent 和 person
    for node in graph._nodes.values():
        if node.node_type in (NodeType.AGENT, NodeType.PERSON):
            expanded.add(node.node_id)
            # 也包含它们的位置节点
            loc = graph.get_location_of(node.node_id)
            if loc:
                expanded.add(loc.node_id)
    
    # 4. 构建子图
    subgraph = SceneGraph()
    for nid in expanded:
        node = graph.get_node(nid)
        if node:
            subgraph.add_node(copy.deepcopy(node))
    for edge in graph._edges:
        if edge.source_id in expanded and edge.target_id in expanded:
            subgraph.add_edge(copy.deepcopy(edge))
    
    return subgraph
```

### 模板 6：从 YAML 配置初始化场景图

```python
import yaml

def initialize_from_config(config_path: str) -> SceneGraph:
    """从 YAML 配置文件初始化场景图
    
    配置格式见 MOSAIC 场景图规划文档 Section 4.1
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)
    
    env = config.get("environment", {})
    graph = SceneGraph()
    
    # 1. 创建房间节点
    for room_cfg in env.get("rooms", []):
        room_node = SceneNode(
            node_id=room_cfg["id"],
            node_type=NodeType.ROOM,
            label=room_cfg["label"],
            position=tuple(room_cfg.get("position", [0, 0])),
        )
        graph.add_node(room_node)
        
        # 2. 创建家具节点 + contains 边
        for furn_cfg in room_cfg.get("furniture", []):
            furn_node = SceneNode(
                node_id=furn_cfg["id"],
                node_type=NodeType.FURNITURE,
                label=furn_cfg["label"],
                position=tuple(furn_cfg.get("position", [0, 0])),
            )
            graph.add_node(furn_node)
            graph.add_edge(SceneEdge(
                source_id=room_cfg["id"],
                target_id=furn_cfg["id"],
                edge_type=EdgeType.CONTAINS,
            ))
            
            # 3. 创建物品节点 + on_top 边
            for obj_cfg in furn_cfg.get("objects", []):
                obj_type = NodeType[obj_cfg.get("type", "object").upper()]
                obj_node = SceneNode(
                    node_id=obj_cfg["id"],
                    node_type=obj_type,
                    label=obj_cfg["label"],
                    state=obj_cfg.get("state", {}),
                    affordances=obj_cfg.get("affordances", []),
                    properties=obj_cfg.get("properties", {}),
                )
                graph.add_node(obj_node)
                graph.add_edge(SceneEdge(
                    source_id=furn_cfg["id"],
                    target_id=obj_cfg["id"],
                    edge_type=EdgeType.ON_TOP,
                ))
    
    # 4. 创建连通性边
    for conn in env.get("connections", []):
        graph.add_edge(SceneEdge(
            source_id=conn[0], target_id=conn[1],
            edge_type=EdgeType.REACHABLE,
        ))
        graph.add_edge(SceneEdge(
            source_id=conn[1], target_id=conn[0],
            edge_type=EdgeType.REACHABLE,
        ))
    
    # 5. 创建智能体节点
    for agent_cfg in env.get("agents", []):
        agent_node = SceneNode(
            node_id=agent_cfg["id"],
            node_type=NodeType.AGENT,
            label=agent_cfg["label"],
            state={"battery": str(agent_cfg.get("battery", 100))},
        )
        graph.add_node(agent_node)
        if agent_cfg.get("at"):
            graph.add_edge(SceneEdge(
                source_id=agent_cfg["id"],
                target_id=agent_cfg["at"],
                edge_type=EdgeType.AT,
            ))
    
    # 6. 创建人员节点
    for person_cfg in env.get("people", []):
        person_node = SceneNode(
            node_id=person_cfg["id"],
            node_type=NodeType.PERSON,
            label=person_cfg["label"],
        )
        graph.add_node(person_node)
        if person_cfg.get("at"):
            graph.add_edge(SceneEdge(
                source_id=person_cfg["id"],
                target_id=person_cfg["at"],
                edge_type=EdgeType.AT,
            ))
    
    return graph
```

### 模板 7：计划验证反馈生成（VeriGraph 风格）

```python
def generate_verification_feedback(result) -> str:
    """将验证结果转化为 LLM 可理解的反馈
    
    VeriGraph 的实验表明，结构化的反馈能让 LLM 更有效地修正计划。
    """
    if result.feasible:
        return "✓ 计划验证通过，所有步骤的前置条件均满足。"
    
    lines = [
        f"✗ 计划在第 {result.failure_step + 1} 步失败",
        f"失败动作: {result.step_results[result.failure_step].action}",
        f"原因: {result.failure_reason}",
        "",
        "执行轨迹:",
    ]
    
    for sr in result.step_results:
        if sr.passed:
            lines.append(f"  ✓ 第 {sr.step_index + 1} 步: {sr.action}")
        else:
            lines.append(f"  ✗ 第 {sr.step_index + 1} 步: {sr.action} — {sr.reason}")
            break
    
    # 提供修正建议（基于失败原因推断）
    lines.append("")
    if "不在同一位置" in result.failure_reason:
        lines.append("建议: 在执行此动作前，先导航到目标所在位置。")
    elif "正持有" in result.failure_reason:
        lines.append("建议: 先放下或递交当前持有的物品。")
    elif "无可达路径" in result.failure_reason:
        lines.append("建议: 检查是否有替代路径，或目标位置是否正确。")
    
    lines.append("请修正计划后重试。")
    return "\n".join(lines)
```

### 模板 8：场景图事件驱动更新（GraphPlan 风格）

```python
async def on_tool_executed(event_bus, graph, event):
    """工具执行完成后更新场景图（事件驱动）
    
    GraphPlan 的核心思想：场景图变化触发重规划。
    """
    action = event.payload.get("action", "")
    params = event.payload.get("params", {})
    result = event.payload.get("result", {})
    
    if not result.get("success"):
        return  # 执行失败不更新场景图
    
    # 根据动作类型更新场景图
    if action == "navigate_to":
        target = params.get("target", "")
        agent = graph.get_agent_node()
        target_nodes = graph.find_by_label(target)
        if agent and target_nodes:
            graph.remove_edges(agent.node_id, None, EdgeType.AT)
            graph.add_edge(SceneEdge(
                source_id=agent.node_id,
                target_id=target_nodes[0].node_id,
                edge_type=EdgeType.AT,
            ))
    
    elif action == "pick_up":
        obj_name = params.get("object_name", "")
        agent = graph.get_agent_node()
        obj_nodes = graph.find_by_label(obj_name)
        if agent and obj_nodes:
            obj = obj_nodes[0]
            # 移除物品的空间关系边
            for et in [EdgeType.ON_TOP, EdgeType.INSIDE]:
                graph.remove_edges(obj.node_id, None, et)
                graph.remove_edges(None, obj.node_id, et)
            # 添加 HOLDING 边
            graph.add_edge(SceneEdge(
                source_id=agent.node_id,
                target_id=obj.node_id,
                edge_type=EdgeType.HOLDING,
            ))
    
    elif action == "hand_over":
        obj_name = params.get("object_name", "")
        agent = graph.get_agent_node()
        obj_nodes = graph.find_by_label(obj_name)
        if agent and obj_nodes:
            graph.remove_edges(agent.node_id, obj_nodes[0].node_id, 
                             EdgeType.HOLDING)
    
    elif action == "operate_appliance":
        appliance_name = params.get("appliance_name", "")
        action_type = params.get("action", "")
        nodes = graph.find_by_label(appliance_name)
        if nodes:
            if action_type in ("启动", "开"):
                nodes[0].state["power"] = "on"
            elif action_type in ("停止", "关"):
                nodes[0].state["power"] = "off"
    
    # 发布场景图更新事件（触发重规划）
    await event_bus.emit(Event(
        type="scene_graph.updated",
        payload={"action": action, "graph_version": graph.version},
        source="scene_graph_manager",
    ))
```



---

## 四、场景图序列化格式对比（LLM 提示词设计）

不同项目采用了不同的场景图序列化格式来提示 LLM。以下是对比：

### 4.1 SG-Nav 格式（层次化子图）

```
Subgraph 1 (Kitchen):
  Room: Kitchen
  Groups: [Cooking Area, Dining Area]
  Objects: [stove, pot, cutting_board, dining_table, chair_1, chair_2]
  Relationships:
    - stove next_to cutting_board
    - pot on_top_of stove
    - chair_1 belongs_to Dining Area
    - Cooking Area belongs_to Kitchen
```

优点：结构清晰，层次分明
缺点：token 较多，大环境下子图数量多

### 4.2 SayPlan 格式（语义子图搜索）

```
Scene Graph (relevant subgraph):
Nodes: kitchen, counter, coffee_machine, fridge, living_room, sofa
Edges: 
  kitchen CONTAINS counter
  counter HAS coffee_machine  
  kitchen CONNECTED_TO living_room
  living_room CONTAINS sofa
Robot: AT living_room
```

优点：紧凑，只包含相关信息
缺点：缺少状态和可供性信息

### 4.3 MOSAIC 推荐格式（综合最佳实践）

```
[场景图]
位置层:
  厨房 ──contains──→ [料理台, 冰箱, 水槽]
  客厅 ──contains──→ [沙发, 茶几, 电视柜]
  卫生间 ──contains──→ [毛巾架]

物体层:
  料理台 ──on/in──→ [咖啡机(power=off)[operable], 面包机(power=off)]
  茶几 ──on/in──→ [水杯[graspable], 遥控器[graspable]]
  毛巾架 ──on/in──→ [黄色毛巾[graspable]]

智能体: 机器人 ──at──→ 客厅, holding: 无
  用户 ──at──→ 客厅

可达性:
  客厅 ←→ 厨房
  客厅 ←→ 卧室
  客厅 ←→ 充电站
  厨房 ←→ 卫生间
```

设计理由：
1. **中文标签** → MOSAIC 面向中文用户和中文 LLM
2. **状态内联** → `(power=off)` 直接跟在物体名后，减少 token
3. **可供性标注** → `[graspable]` 方括号标注，LLM 一眼可见
4. **双向可达** → `←→` 表示双向，比两条单向边更紧凑
5. **层次化** → 位置→物体→智能体，从宏观到微观

---

## 五、实施建议与优先级

### 5.1 第一阶段：最小可行场景图（~500 行，1-2 天）

基于模板 1 + 6 + 2，实现：
- `SceneNode` / `SceneEdge` 数据类
- `SceneGraph` 核心类（增删改查 + 索引）
- `initialize_from_config()` 从 YAML 初始化
- `to_prompt_text()` 序列化为 LLM 提示词
- 修改 `TurnRunner` 注入场景图文本

**验证方式**：用现有的 "帮我去卫生间拿个毛巾过来" 测试用例，
对比注入场景图前后 LLM 的规划质量。

### 5.2 第二阶段：计划验证（~400 行，1-2 天）

基于模板 3 + 4 + 7，实现：
- `ActionRule` / `Precondition` / `Effect` 数据类
- `PlanVerifier.verify_plan()` 逐步验证
- `generate_verification_feedback()` 反馈生成
- 修改 `TurnRunner` 在执行前验证计划

**验证方式**：构造一个 LLM 会犯错的场景（如直接 pick_up 而不先 navigate_to），
验证 PlanVerifier 能否拦截并反馈。

### 5.3 第三阶段：动态更新（~300 行，1 天）

基于模板 8，实现：
- `SceneGraphManager` 生命周期管理
- `on_tool_executed()` 事件驱动更新
- 与 EventBus 集成

### 5.4 第四阶段：子图提取（~200 行，0.5 天）

基于模板 5，实现：
- `extract_task_subgraph()` 关键词匹配 + BFS 扩展
- 大环境下的 token 优化

---

## 六、参考文献

1. SG-Nav: [github.com/bagh2178/SG-Nav](https://github.com/bagh2178/SG-Nav) — NeurIPS 2024
2. Taskography: [github.com/taskography/taskography](https://github.com/taskography/taskography) — CoRL 2021
3. ConceptGraphs: [github.com/concept-graphs/concept-graphs](https://github.com/concept-graphs/concept-graphs) — ICRA 2024
4. OVSG: [github.com/changhaonan/OVSG](https://github.com/changhaonan/OVSG) — CoRL 2023
5. Spark-DSG: [github.com/MIT-SPARK/Spark-DSG](https://github.com/MIT-SPARK/Spark-DSG) — MIT SPARK Lab
6. GNN4TaskPlan: [github.com/WxxShirley/GNN4TaskPlan](https://github.com/WxxShirley/GNN4TaskPlan) — NeurIPS 2024
7. LLM-DP: [github.com/itl-ed/llm-dp](https://github.com/itl-ed/llm-dp) — LLM + PDDL 混合规划
8. VeriGraph: [arxiv.org/abs/2411.10446](https://arxiv.org/abs/2411.10446) — 2024
9. HOV-SG: [hovsg.github.io](https://hovsg.github.io/) — RSS 2024
10. DovSG: [bjhyzj.github.io/dovsg-web](https://bjhyzj.github.io/dovsg-web) — 2024
11. SayPlan: [sayplan.github.io](https://sayplan.github.io/) — CoRL 2023
12. GraphPlan: [openreview.net/forum?id=UMN77tJZdK](https://openreview.net/forum?id=UMN77tJZdK) — 2025
