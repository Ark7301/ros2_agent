- title: Bibliography Survey Index
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, research, references, bibliography
- source_type: survey

# 参考文献调研清单

> 课题：面向 ROS 2 架构的 AI Agent 机器人任务调度系统设计与实现
> 用途：论文参考文献 + 外文翻译选材，所有条目均经联网验证可查

---

## 一、ROS 2 架构与导航

| # | 论文标题 | 作者 | 发表/来源 | 检索词 |
|---|---------|------|----------|--------|
| 1 | ROS: an open-source Robot Operating System | Quigley M, Gerkey B, Conley K, et al. | ICRA Workshop, 2009 | `Quigley ROS open-source Robot Operating System ICRA 2009` |
| 2 | Robot Operating System 2: Design, Architecture, and Uses in the Wild | Macenski S, Foote T, Gerkey B, Lalancette C, Woodall W. | Science Robotics, 7(66), eabm6074, 2022 | `Macenski Robot Operating System 2 Science Robotics 2022` |
| 3 | The Marathon 2: A Navigation System | Macenski S, Martín F, White R, Clavero JG. | IEEE/RSJ IROS, 2020 | `Macenski Marathon 2 Navigation System IROS 2020` |
| 4 | SLAM Toolbox: SLAM for the dynamic world | Macenski S, Jambrecic I. | Journal of Open Source Software (JOSS), 6(61), 2783, 2021 | DOI: `10.21105/joss.02783` |

---

## 二、LLM + 机器人任务规划（核心方向）

| # | 论文标题 | 作者 | 发表/来源 | 检索词 |
|---|---------|------|----------|--------|
| 5 | Do As I Can, Not As I Say: Grounding Language in Robotic Affordances | Ahn M, Brohan A, Brown N, et al. (Google) | CoRL, 2022 | arXiv: `2204.01691` |
| 6 | Inner Monologue: Embodied Reasoning through Planning with Language Models | Huang W, Xia F, Xiao T, et al. (Google) | CoRL, 2022 | arXiv: `2207.05608` |
| 7 | PaLM-E: An Embodied Multimodal Language Model | Driess D, Xia F, Sajjadi MSM, et al. (Google) | ICML, 2023 | arXiv: `2303.03378` |
| 8 | Grounding LLMs For Robot Task Planning Using Closed-loop State Feedback | Dalal M, et al. (NYU) | Advanced Robotics Research, 2024 | arXiv: `2402.08546` |

---

## 三、Agent 推理框架（ReAct / Agent Loop）

| # | 论文标题 | 作者 | 发表/来源 | 检索词 |
|---|---------|------|----------|--------|
| 9 | ReAct: Synergizing Reasoning and Acting in Language Models | Yao S, Zhao J, Yu D, et al. | ICLR, 2023 | arXiv: `2210.03629` |

---

## 四、端到端视觉语言导航（VLN，演进方向）

| # | 论文标题 | 作者 | 发表/来源 | 检索词 |
|---|---------|------|----------|--------|
| 10 | NaVid: Video-based VLM Plans the Next Step for Vision-and-Language Navigation | Zhang J, Wang K, Xu R, Zhou G, Hong Y, Fang X, Wu Q, Zhang Z, Wang H. | RSS, 2024 | arXiv: `2402.15852` |
| 11 | Uni-NaVid: A Video-based Vision-Language-Action Model for Unifying Embodied Navigation Tasks | PKU-EPIC 团队（NaVid 后续工作） | arXiv, 2024 | arXiv: `2412.06224` |

---

## 五、OpenAI Function Calling / Agent 工具（工程参考，非论文）

| # | 资料标题 | 来源 | 链接 |
|---|---------|------|------|
| 12 | Function Calling and Other API Updates | OpenAI Blog, 2023.06.13 | https://openai.com/index/function-calling-and-other-api-updates |
| 13 | New Tools for Building Agents (Responses API + Agents SDK) | OpenAI Blog, 2025.03.11 | https://openai.com/index/new-tools-for-building-agents |
| 14 | Introducing the Model Context Protocol (MCP) | Anthropic Blog, 2024.11 | https://www.anthropic.com/news/model-context-protocol |

---

## 外文翻译选材建议

- 若外文翻译已选 #2（ROS 2 Science Robotics），推荐 #5（SayCan）或 #9（ReAct）作为补充
- #5 SayCan 是 LLM+机器人任务调度的开山之作，与课题最直接相关
- #9 ReAct 是 Agent Loop 的奠基论文，与系统 V2 演进方向相关
