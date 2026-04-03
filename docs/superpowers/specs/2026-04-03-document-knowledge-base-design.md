# 仓库文档知识库化重构设计

## 文档元信息

- title: 仓库文档知识库化重构设计
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, knowledge-base, repository-structure, research, developer-docs

## 1. 背景

当前仓库中的文档体系已经失去清晰边界，主要问题如下：

- `docs/` 根目录直接堆放开发指南、架构方案、研究调研、论文资料和阶段性报告，缺少统一分层。
- `scripts/docs/` 形成了第二套文档入口，正式知识库和脚本附属文档并存。
- `.kiro/specs/` 保存了大量过程规格，但仓库内没有明确说明其定位，容易与正式文档混淆。
- 现有 `README.md` 仍主要描述早期 demo 形态，与当前仓库内容不完全一致。
- 文档命名方式不统一，存在中文长标题、主题命名和阶段性文档混用的情况，不利于长期维护和检索。

本次设计聚焦于“文档与知识资产重构”，不直接修改运行时代码结构，也不处理测试、依赖和模块拆分问题。

## 2. 目标

本次重构需要达成以下目标：

- 建立双轨文档体系，明确区分开发协作文档与研究沉淀文档。
- 让研究资料继续保留在当前仓库内，但不再与开发文档混放。
- 将当前松散的文档集合整理为可持续维护的知识库，而不是一次性归档。
- 统一正式文档入口，消除旁路目录和孤立文档。
- 为后续新增文档提供稳定的落点、命名规范和维护规则。

## 3. 非目标

以下内容不属于本次文档重构范围：

- 不迁出研究资料到外部知识库或新仓库。
- 不在本阶段重构 `mosaic`、`mosaic_demo` 或 `plugins` 的代码边界。
- 不在本阶段统一 Python 依赖、启动命令或测试脚本。
- 不将 `.kiro/specs/` 过程规格目录并入正式知识库正文树。

## 4. 关键决策

本设计基于以下已确认约束：

- 采用“双轨文档体系”，同时服务开发协作与研究沉淀。
- 研究资料保留在本仓库中，不外迁。
- 目标是构建“知识库型”文档体系，而不是仅做搬运归档。
- 允许大规模重命名和目录重组，以长期结构最优为优先。

## 5. 目标信息架构

重构后的正式知识库结构如下：

```text
docs/
  README.md

  dev/
    README.md
    onboarding/
    architecture/
    runbooks/
    reference/
    reports/

  research/
    README.md
    directions/
    surveys/
    papers/
    thesis/
    references/

  archive/
    README.md
```

各层职责定义如下：

- `docs/README.md`
  - 作为全仓库文档总入口。
  - 负责说明双轨结构、导航方式和文档维护规则。
- `docs/dev/`
  - 面向开发协作。
  - 仅存放会直接指导开发、运行、调试、测试、集成的文档。
- `docs/research/`
  - 面向研究沉淀。
  - 仅存放方向分析、前沿调研、论文解读、论文产出和参考资料。
- `docs/archive/`
  - 存放历史有效但当前不再作为主文档维护的文档。
  - 不承担常规导航职责，只负责保留追溯价值。

## 6. 文档分流规则

所有文档迁移和后续新增都必须遵守以下规则：

- 如果文档用于指导开发者如何搭建环境、启动系统、配置参数、调试流程或执行测试，则归入 `docs/dev/`。
- 如果文档用于沉淀研究方向、技术调研、论文翻译、论文写作或参考文献材料，则归入 `docs/research/`。
- 如果文档已经失去当前指导作用，但仍有历史追溯价值，则归入 `docs/archive/`。
- `docs/` 根目录不再直接存放主题文档，只保留总入口和必要结构性文件。
- `scripts/docs/` 不再作为正式文档入口，现有文档需要迁移到知识库主目录。
- `.kiro/specs/` 保持原地，视为过程资产，不纳入正式知识库正文树。

## 7. 命名规范

### 7.1 稳定文档

长期有效、会被持续引用的文档使用语义化英文短名：

- `system-architecture.md`
- `slam-sim-runbook.md`
- `api-keys.md`

适用对象：

- 架构说明
- 开发指南
- 操作手册
- 配置与接口说明
- 长期有效的研究总览文档

### 7.2 时效文档

阶段性结论、报告、调研纪要优先使用日期前缀：

- `2026-04-03-mosaic-v2-smoke-test.md`
- `2026-03-11-auto-mapping-improvement-plan.md`

适用对象：

- 测试报告
- 阶段调研
- 修复报告
- 阶段计划

如果历史文档缺少可靠日期信息，但当前仍需要作为唯一主入口保留，则可以先使用语义化名称，并在文档元信息中明确 `updated` 字段；后续一旦补齐时间信息，再评估是否改为日期前缀命名。

### 7.3 命名约束

- 正式知识库优先使用 ASCII 文件名，避免中文长标题路径持续扩散。
- 文件名应体现主题，不包含无信息量修饰词。
- 同主题文档如果存在主从关系，主文档使用稳定名称，阶段补充文档使用日期前缀。

## 8. 索引与元信息规范

### 8.1 索引规范

以下目录必须存在 `README.md` 作为导航页：

- `docs/`
- `docs/dev/`
- `docs/research/`
- `docs/archive/`

索引页至少包含以下内容：

- 目录用途说明
- 子目录导航
- 推荐阅读顺序
- 文档状态说明
- 与其他文档区域的关系说明

### 8.2 最小元信息规范

正式知识库中的 Markdown 文档应包含最小元信息区块，至少包括：

- `title`
- `status`
- `owner`
- `updated`
- `tags`

研究类文档额外包含：

- `source_type`

推荐状态值：

- `draft`
- `active`
- `superseded`
- `archived`

## 9. 现有文档迁移映射

### 9.1 迁入 `docs/dev/`

下列文档迁入开发协作主线：

| 当前路径 | 目标路径 |
|---|---|
| `docs/MOSAIC仿真环境搭建指南.md` | `docs/dev/onboarding/sim-environment-setup.md` |
| `docs/SLAM仿真建图操作指南.md` | `docs/dev/runbooks/slam-sim-mapping.md` |
| `docs/场景图集成-体验测试指南.md` | `docs/dev/runbooks/scene-graph-integration-testing.md` |
| `docs/API 文档/API-KEY.md` | `docs/dev/reference/api-keys.md` |
| `docs/MOSAIC-v2-冒烟测试报告.md` | `docs/dev/reports/2026-04-03-mosaic-v2-smoke-test.md` |
| `scripts/docs/SLAM建图问题修复报告.md` | `docs/dev/reports/2026-04-03-slam-mapping-fix-report.md` |
| `scripts/docs/自动建图方案改进计划.md` | `docs/dev/architecture/2026-03-11-auto-mapping-improvement-plan.md` |

### 9.2 迁入 `docs/research/`

下列文档迁入研究沉淀主线：

| 当前路径 | 目标路径 |
|---|---|
| `docs/MOSAIC核心议题-如何使LLM理解物理世界.md` | `docs/research/directions/llm-physical-world-understanding.md` |
| `docs/MOSAIC超越MCP-具身智能体与工具调用的本质差异评估.md` | `docs/research/directions/embodied-agent-vs-mcp.md` |
| `docs/MOSAIC借鉴OpenClaw深度分析报告.md` | `docs/research/surveys/openclaw-analysis.md` |
| `docs/openclaw技术调研-mosaic架构优化方案.md` | `docs/research/surveys/openclaw-to-mosaic-architecture.md` |
| `docs/VLM场景图前沿方案调研.md` | `docs/research/surveys/vlm-scene-graph-survey.md` |
| `docs/自动场景建图开源方案调研.md` | `docs/research/surveys/auto-mapping-open-source-survey.md` |
| `docs/MOSAIC场景图实现示例调研-开源项目代码分析.md` | `docs/research/surveys/scene-graph-implementation-examples.md` |
| `docs/MOSAIC场景图表征架构规划-从文本到结构化世界理解.md` | `docs/research/surveys/scene-graph-representation-architecture.md` |
| `docs/MOSAIC混合架构方案分析-Python核心+TS调度层.md` | `docs/research/surveys/python-core-ts-orchestration.md` |
| `docs/MOSAIC-MCP-Server方案深度分析-回溯SayCan设计哲学.md` | `docs/research/papers/mcp-server-and-saycan-analysis.md` |
| `docs/外文翻译-SayCan.md` | `docs/research/papers/saycan-translation.md` |
| `docs/论文素材-参考文献调研清单.md` | `docs/research/references/bibliography-survey-index.md` |

### 9.3 `docs/论文文档/` 的迁移策略

`docs/论文文档/` 统一迁入 `docs/research/thesis/`：

| 当前路径 | 目标路径 |
|---|---|
| `docs/论文文档/产品需求设计.md` | `docs/research/thesis/product-requirements.md` |
| `docs/论文文档/外文翻译.md` | `docs/research/thesis/translation.md` |
| `docs/论文文档/外文翻译.pdf` | `docs/research/thesis/translation.pdf` |
| `docs/论文文档/开题报告.md` | `docs/research/thesis/proposal.md` |
| `docs/论文文档/开题报告.pdf` | `docs/research/thesis/proposal.pdf` |
| `docs/论文文档/文献综述.md` | `docs/research/thesis/literature-review.md` |
| `docs/论文文档/文献综述.pdf` | `docs/research/thesis/literature-review.pdf` |
| `docs/论文文档/系统技术设计方案.md` | `docs/research/thesis/system-technical-design.md` |
| `docs/论文文档/系统技术设计方案.pdf` | `docs/research/thesis/system-technical-design.pdf` |

### 9.4 `docs/论文素材/` 的迁移策略

`docs/论文素材/` 中的 Markdown 和 PDF 迁入 `docs/research/references/`，作为资料库和索引层存在，不承担主叙事职责。

### 9.5 归档候选规则

只有满足以下任一条件的文档才进入 `docs/archive/`：

- 同主题已有更新且明确的主文档。
- 仅保留阶段性历史价值，不再用于当前开发或研究。
- 内容零散且无法作为当前知识库导航入口使用。

根据当前仓库状态，`docs/Do as I can.md` 为优先复核对象。若确认其不再承担当前方向说明职责，则迁入 `docs/archive/`。

## 10. `.kiro/specs/` 的定位

`.kiro/specs/` 继续保留为过程规格与历史设计资产，原因如下：

- 其内容服务于过程追溯和历史设计决策，不等同于当前正式知识库正文。
- 直接并入 `docs/` 会重新混淆“正式文档”和“过程资产”的边界。
- 保留原路径有利于延续既有工具链与工作流。

正式知识库中应通过 `docs/dev/README.md` 增加说明性入口，例如：

- 过程规格与历史方案请参见 `.kiro/specs/`

## 11. 维护规则

为避免仓库再次回到无序状态，后续维护必须遵循以下规则：

- 新增文档时必须先判断其归属，不允许直接新建到 `docs/` 根目录。
- 新增正式文档后，必须同步更新对应层级的 `README.md` 索引。
- 每个主题只保留一个主入口文档，补充材料通过链接挂靠到主文档。
- 阶段性文档必须带状态字段，过时后标记为 `superseded` 或迁入 `archive/`。
- 不再新增 `scripts/docs/` 之类的旁路正式文档目录。
- 非文档噪音文件不得进入知识库目录，例如 `.DS_Store`。

## 12. 迁移执行顺序

建议按以下顺序执行重构：

1. 创建 `docs/` 新目录骨架和各级 `README.md`。
2. 迁移 `docs/dev/` 相关文档，优先改善开发协作体验。
3. 迁移 `docs/research/` 相关文档，包括调研、论文和论文产出。
4. 合并 `scripts/docs/` 内容，并补充 `.kiro/specs/` 的入口说明。
5. 更新仓库根 `README.md` 中的文档导航。
6. 清理 `.DS_Store` 等非文档噪音文件，并补充忽略规则。
7. 校验关键链接和索引页，确保新知识库可导航。

## 13. 验收标准

重构完成后，应满足以下验收标准：

- `docs/` 根目录不再堆放主题文档，仅保留总入口和结构性文件。
- 开发者可以从 `docs/README.md` 在三次点击内定位环境搭建、运行方式、架构说明和配置参考。
- 研究资料已经按方向、调研、论文、论文产出、参考资料清晰分层。
- 仓库中不存在第二套正式文档入口，例如长期保留的 `scripts/docs/`。
- 关键索引页和关键迁移链接有效，不存在大面积断链。
- 新增文档具备明确落点、命名规范和状态约束。

## 14. 风险与缓解

本次重构存在以下主要风险：

- 大规模重命名会导致旧链接失效。
  - 缓解方式：先建立索引页和迁移清单，再分批迁移并更新关键入口。
- 文档边界判断可能出现争议。
  - 缓解方式：以“直接指导开发”与“研究沉淀”为唯一一级判断标准，减少灰区。
- 过程规格和正式知识库再次混淆。
  - 缓解方式：明确 `.kiro/specs/` 为过程资产，仅通过索引引用，不纳入正文树。

## 15. 后续规划边界

在本设计完成并实施后，可另起后续规划处理以下问题：

- 仓库根 `README.md` 与当前产品形态对齐。
- 代码目录与模块边界重构。
- 启动、依赖、测试入口统一。
- 仓库卫生治理与实验痕迹清理。
