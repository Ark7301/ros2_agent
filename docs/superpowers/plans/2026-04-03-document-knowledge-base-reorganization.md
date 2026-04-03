# Document Knowledge-Base Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the repository documentation into a durable dual-track knowledge base with clear developer and research paths, consistent naming, explicit indexes, and no parallel doc entry points.

**Architecture:** Build the new `docs/dev`, `docs/research`, and `docs/archive` structure first, then migrate existing documents into their target locations, normalize metadata, and finally clean up obsolete paths and update top-level navigation. Treat `.kiro/specs/` and `docs/superpowers/` as process assets referenced from the knowledge base, not as part of the main documentation tree.

**Tech Stack:** Git, Markdown, shell filesystem commands, ripgrep

---

## File Structure

### Create

- `docs/README.md`
- `docs/dev/README.md`
- `docs/research/README.md`
- `docs/archive/README.md`

### Modify

- `.gitignore`
- `README.md`
- All migrated Markdown documents under `docs/dev/`, `docs/research/`, and `docs/archive/` to add normalized metadata headers

### Move Into `docs/dev/`

- `docs/MOSAIC仿真环境搭建指南.md` -> `docs/dev/onboarding/sim-environment-setup.md`
- `docs/SLAM仿真建图操作指南.md` -> `docs/dev/runbooks/slam-sim-mapping.md`
- `docs/场景图集成-体验测试指南.md` -> `docs/dev/runbooks/scene-graph-integration-testing.md`
- `docs/API 文档/API-KEY.md` -> `docs/dev/reference/api-keys.md`
- `docs/MOSAIC-v2-冒烟测试报告.md` -> `docs/dev/reports/2026-04-03-mosaic-v2-smoke-test.md`
- `scripts/docs/SLAM建图问题修复报告.md` -> `docs/dev/reports/2026-04-03-slam-mapping-fix-report.md`
- `scripts/docs/自动建图方案改进计划.md` -> `docs/dev/architecture/2026-03-11-auto-mapping-improvement-plan.md`

### Move Into `docs/research/`

- `docs/MOSAIC核心议题-如何使LLM理解物理世界.md` -> `docs/research/directions/llm-physical-world-understanding.md`
- `docs/MOSAIC超越MCP-具身智能体与工具调用的本质差异评估.md` -> `docs/research/directions/embodied-agent-vs-mcp.md`
- `docs/MOSAIC借鉴OpenClaw深度分析报告.md` -> `docs/research/surveys/openclaw-analysis.md`
- `docs/openclaw技术调研-mosaic架构优化方案.md` -> `docs/research/surveys/openclaw-to-mosaic-architecture.md`
- `docs/VLM场景图前沿方案调研.md` -> `docs/research/surveys/vlm-scene-graph-survey.md`
- `docs/自动场景建图开源方案调研.md` -> `docs/research/surveys/auto-mapping-open-source-survey.md`
- `docs/MOSAIC场景图实现示例调研-开源项目代码分析.md` -> `docs/research/surveys/scene-graph-implementation-examples.md`
- `docs/MOSAIC场景图表征架构规划-从文本到结构化世界理解.md` -> `docs/research/surveys/scene-graph-representation-architecture.md`
- `docs/MOSAIC混合架构方案分析-Python核心+TS调度层.md` -> `docs/research/surveys/python-core-ts-orchestration.md`
- `docs/MOSAIC-v2-前沿架构方案.md` -> `docs/research/surveys/mosaic-v2-frontier-architecture.md`
- `docs/MOSAIC-MCP-Server方案深度分析-回溯SayCan设计哲学.md` -> `docs/research/papers/mcp-server-and-saycan-analysis.md`
- `docs/外文翻译-SayCan.md` -> `docs/research/papers/saycan-translation.md`
- `docs/论文素材-参考文献调研清单.md` -> `docs/research/references/bibliography-survey-index.md`

### Move Thesis And Reference Assets

- `docs/论文文档/产品需求设计.md` -> `docs/research/thesis/product-requirements.md`
- `docs/论文文档/外文翻译.md` -> `docs/research/thesis/translation.md`
- `docs/论文文档/外文翻译.pdf` -> `docs/research/thesis/translation.pdf`
- `docs/论文文档/开题报告.md` -> `docs/research/thesis/proposal.md`
- `docs/论文文档/开题报告.pdf` -> `docs/research/thesis/proposal.pdf`
- `docs/论文文档/文献综述.md` -> `docs/research/thesis/literature-review.md`
- `docs/论文文档/文献综述.pdf` -> `docs/research/thesis/literature-review.pdf`
- `docs/论文文档/系统技术设计方案.md` -> `docs/research/thesis/system-technical-design.md`
- `docs/论文文档/系统技术设计方案.pdf` -> `docs/research/thesis/system-technical-design.pdf`
- `docs/论文素材/论文素材-Agent Loop技术演进研究.md` -> `docs/research/references/agent-loop-evolution.md`
- `docs/论文素材/论文素材-Co-NavGPT多机器人协作视觉导航.md` -> `docs/research/references/co-navgpt-multi-robot-visual-navigation.md`
- `docs/论文素材/论文素材-EmbodiedAgent技术方案深度分析与对比.md` -> `docs/research/references/embodied-agent-systems-comparison.md`
- `docs/论文素材/论文素材-SubAgent技术深度调研与系统评估.md` -> `docs/research/references/subagent-systems-evaluation.md`
- `docs/论文素材/论文素材-VLA技术研究现状深度调研.md` -> `docs/research/references/vla-state-of-the-art.md`
- `docs/论文素材/论文素材-世界模型与VLA_VLN技术调研.md` -> `docs/research/references/world-models-vla-vln-survey.md`
- `docs/论文素材/论文素材-人形机器人最后一步实现技术调研.md` -> `docs/research/references/humanoid-last-mile-survey.md`
- `docs/论文素材/论文素材-全局状态上下文管理方案调研.md` -> `docs/research/references/global-state-context-management.md`
- `docs/论文素材/论文素材-全局状态上下文管理方案调研.pdf` -> `docs/research/references/global-state-context-management.pdf`
- `docs/论文素材/论文素材-机器人自主探索与环境理解前沿方案.md` -> `docs/research/references/robot-autonomous-exploration-survey.md`
- `docs/论文素材/论文素材-机器人自主探索与环境理解前沿方案.pdf` -> `docs/research/references/robot-autonomous-exploration-survey.pdf`
- `docs/论文素材/论文素材-项目价值与场景分析.md` -> `docs/research/references/project-value-and-scenarios.md`

### Move Into `docs/archive/`

- `docs/Do as I can.md` -> `docs/archive/do-as-i-can.md`
- `docs/开发记录/progress.md` -> `docs/archive/development-progress-log.md`

### Remove After Migration

- `docs/.DS_Store`
- Empty directories `docs/API 文档`, `docs/开发记录`, `docs/论文文档`, `docs/论文素材`
- Empty directory `scripts/docs`

## Task 1: Scaffold The Knowledge Base Structure

**Files:**
- Create: `docs/README.md`
- Create: `docs/dev/README.md`
- Create: `docs/research/README.md`
- Create: `docs/archive/README.md`
- Modify: `.gitignore`

- [ ] **Step 1: Snapshot the pre-migration docs tree**

Run:

```bash
find docs -maxdepth 2 -type f | sort
```

Expected: A flat `docs/` root with Chinese-titled files and no `docs/dev/README.md`, `docs/research/README.md`, or `docs/archive/README.md`.

- [ ] **Step 2: Create the target directory structure**

Run:

```bash
mkdir -p docs/dev/onboarding docs/dev/architecture docs/dev/runbooks docs/dev/reference docs/dev/reports
mkdir -p docs/research/directions docs/research/surveys docs/research/papers docs/research/thesis docs/research/references
mkdir -p docs/archive
```

Expected: `find docs -maxdepth 2 -type d | sort` shows `docs/dev`, `docs/research`, and `docs/archive`.

- [ ] **Step 3: Write `docs/README.md`**

Use this exact content:

```md
# Documentation Hub

## Structure

- [Developer docs](dev/README.md)
- [Research docs](research/README.md)
- [Archive](archive/README.md)

## Developer docs

- [Onboarding](dev/onboarding/)
- [Architecture](dev/architecture/)
- [Runbooks](dev/runbooks/)
- [Reference](dev/reference/)
- [Reports](dev/reports/)

## Research docs

- [Directions](research/directions/)
- [Surveys](research/surveys/)
- [Papers](research/papers/)
- [Thesis](research/thesis/)
- [References](research/references/)

## Process Assets

- [Design specs](superpowers/specs/)
- [Implementation plans](superpowers/plans/)
- Historical Kiro specs live in `.kiro/specs/`

## Maintenance Rules

- Do not add topic documents directly under `docs/`.
- Update the nearest `README.md` when adding or moving a document.
- Keep developer-facing and research-facing materials in separate trees.
- Move obsolete documents into `docs/archive/` instead of leaving them in place.
```

- [ ] **Step 4: Write the section index files**

Use this exact content for `docs/dev/README.md`:

```md
# Developer Documentation

## Purpose

This section contains material that directly helps contributors set up, run, configure, debug, and verify the repository.

## Sections

- `onboarding/`: environment setup and first-run guidance
- `architecture/`: active implementation architecture and design notes
- `runbooks/`: task-oriented operational guides
- `reference/`: stable configuration and API reference
- `reports/`: smoke tests, fix reports, and verification records

## Key Documents

- `onboarding/sim-environment-setup.md`
- `architecture/2026-03-11-auto-mapping-improvement-plan.md`
- `runbooks/slam-sim-mapping.md`
- `runbooks/scene-graph-integration-testing.md`
- `reference/api-keys.md`
- `reports/2026-04-03-mosaic-v2-smoke-test.md`
- `reports/2026-04-03-slam-mapping-fix-report.md`

## Related Process Assets

- `docs/superpowers/specs/2026-04-03-document-knowledge-base-design.md`
- `.kiro/specs/`
```

Use this exact content for `docs/research/README.md`:

```md
# Research Documentation

## Purpose

This section contains research directions, surveys, translations, thesis artifacts, and supporting reference material that inform the repository roadmap.

## Sections

- `directions/`: foundational ideas and positioning
- `surveys/`: topic investigations and architecture comparisons
- `papers/`: paper translations and paper-driven analysis
- `thesis/`: thesis deliverables and manuscript assets
- `references/`: source inventories and supporting notes

## Key Documents

- `directions/llm-physical-world-understanding.md`
- `directions/embodied-agent-vs-mcp.md`
- `surveys/openclaw-analysis.md`
- `surveys/mosaic-v2-frontier-architecture.md`
- `papers/saycan-translation.md`
- `thesis/system-technical-design.md`
- `references/bibliography-survey-index.md`
```

Use this exact content for `docs/archive/README.md`:

```md
# Archive

## Purpose

This section keeps historical documents that are worth preserving but should no longer appear as active guidance.

## Archive Rules

- Archive material that has been superseded by a clearer active document.
- Archive material that only reflects a past project phase.
- Keep archived documents readable, but do not use this directory as the primary navigation path.
```

- [ ] **Step 5: Add workspace-noise ignores**

Update `.gitignore` to this exact content:

```gitignore
third_party/
.hypothesis/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
```

- [ ] **Step 6: Verify the new skeleton exists**

Run:

```bash
find docs -maxdepth 2 -type d | sort
```

Expected: `docs/archive`, `docs/dev`, `docs/research`, `docs/superpowers`, and their immediate subdirectories all appear.

- [ ] **Step 7: Commit the scaffold**

Run:

```bash
git add .gitignore docs/README.md docs/dev/README.md docs/research/README.md docs/archive/README.md
git commit -m "docs: scaffold knowledge base structure"
```

Expected: A commit containing only the new index files and `.gitignore` update.

## Task 2: Migrate Developer-Facing Documentation

**Files:**
- Modify: `docs/dev/README.md`
- Move: `docs/MOSAIC仿真环境搭建指南.md`
- Move: `docs/SLAM仿真建图操作指南.md`
- Move: `docs/场景图集成-体验测试指南.md`
- Move: `docs/API 文档/API-KEY.md`
- Move: `docs/MOSAIC-v2-冒烟测试报告.md`
- Move: `scripts/docs/SLAM建图问题修复报告.md`
- Move: `scripts/docs/自动建图方案改进计划.md`

- [ ] **Step 1: Verify all developer-doc sources exist before moving**

Run:

```bash
test -f "docs/MOSAIC仿真环境搭建指南.md" && test -f "docs/SLAM仿真建图操作指南.md" && test -f "docs/场景图集成-体验测试指南.md" && test -f "docs/API 文档/API-KEY.md" && test -f "docs/MOSAIC-v2-冒烟测试报告.md" && test -f "scripts/docs/SLAM建图问题修复报告.md" && test -f "scripts/docs/自动建图方案改进计划.md" && echo "sources-ready"
```

Expected: `sources-ready`

- [ ] **Step 2: Move the developer documents into the new tree**

Run:

```bash
git mv "docs/MOSAIC仿真环境搭建指南.md" "docs/dev/onboarding/sim-environment-setup.md"
git mv "docs/SLAM仿真建图操作指南.md" "docs/dev/runbooks/slam-sim-mapping.md"
git mv "docs/场景图集成-体验测试指南.md" "docs/dev/runbooks/scene-graph-integration-testing.md"
git mv "docs/API 文档/API-KEY.md" "docs/dev/reference/api-keys.md"
git mv "docs/MOSAIC-v2-冒烟测试报告.md" "docs/dev/reports/2026-04-03-mosaic-v2-smoke-test.md"
git mv "scripts/docs/SLAM建图问题修复报告.md" "docs/dev/reports/2026-04-03-slam-mapping-fix-report.md"
git mv "scripts/docs/自动建图方案改进计划.md" "docs/dev/architecture/2026-03-11-auto-mapping-improvement-plan.md"
```

Expected: `git status --short` shows only rename entries for these files.

- [ ] **Step 3: Add metadata headers to the moved Markdown files**

Add a top-of-file metadata block matching the spec format to each file in this table:

| File | title | status | owner | updated | tags |
|---|---|---|---|---|---|
| `docs/dev/onboarding/sim-environment-setup.md` | MOSAIC Simulation Environment Setup | active | repository-maintainers | 2026-04-03 | docs, dev, onboarding, simulation |
| `docs/dev/runbooks/slam-sim-mapping.md` | SLAM Simulation Mapping Runbook | active | repository-maintainers | 2026-04-03 | docs, dev, runbook, slam |
| `docs/dev/runbooks/scene-graph-integration-testing.md` | Scene Graph Integration Testing Guide | active | repository-maintainers | 2026-04-03 | docs, dev, runbook, scene-graph |
| `docs/dev/reference/api-keys.md` | API Keys Reference | active | repository-maintainers | 2026-04-03 | docs, dev, reference, api |
| `docs/dev/reports/2026-04-03-mosaic-v2-smoke-test.md` | MOSAIC v2 Smoke Test Report | active | repository-maintainers | 2026-04-03 | docs, dev, report, smoke-test |
| `docs/dev/reports/2026-04-03-slam-mapping-fix-report.md` | SLAM Mapping Fix Report | active | repository-maintainers | 2026-04-03 | docs, dev, report, slam |
| `docs/dev/architecture/2026-03-11-auto-mapping-improvement-plan.md` | Auto Mapping Improvement Plan | active | repository-maintainers | 2026-04-03 | docs, dev, architecture, mapping |

- [ ] **Step 4: Verify the developer doc tree is complete**

Run:

```bash
find docs/dev -maxdepth 3 -type f | sort
```

Expected: The list includes `docs/dev/README.md` plus the seven moved files under `onboarding`, `architecture`, `runbooks`, `reference`, and `reports`.

- [ ] **Step 5: Commit the developer-doc migration**

Run:

```bash
git add docs/dev
git commit -m "docs: migrate developer documentation"
```

Expected: A commit containing only the `docs/dev/` moves and metadata updates.

## Task 3: Migrate Research Directions, Surveys, And Paper Notes

**Files:**
- Modify: `docs/research/README.md`
- Move: `docs/MOSAIC核心议题-如何使LLM理解物理世界.md`
- Move: `docs/MOSAIC超越MCP-具身智能体与工具调用的本质差异评估.md`
- Move: `docs/MOSAIC借鉴OpenClaw深度分析报告.md`
- Move: `docs/openclaw技术调研-mosaic架构优化方案.md`
- Move: `docs/VLM场景图前沿方案调研.md`
- Move: `docs/自动场景建图开源方案调研.md`
- Move: `docs/MOSAIC场景图实现示例调研-开源项目代码分析.md`
- Move: `docs/MOSAIC场景图表征架构规划-从文本到结构化世界理解.md`
- Move: `docs/MOSAIC混合架构方案分析-Python核心+TS调度层.md`
- Move: `docs/MOSAIC-v2-前沿架构方案.md`
- Move: `docs/MOSAIC-MCP-Server方案深度分析-回溯SayCan设计哲学.md`
- Move: `docs/外文翻译-SayCan.md`

- [ ] **Step 1: Move the research direction and survey documents**

Run:

```bash
git mv "docs/MOSAIC核心议题-如何使LLM理解物理世界.md" "docs/research/directions/llm-physical-world-understanding.md"
git mv "docs/MOSAIC超越MCP-具身智能体与工具调用的本质差异评估.md" "docs/research/directions/embodied-agent-vs-mcp.md"
git mv "docs/MOSAIC借鉴OpenClaw深度分析报告.md" "docs/research/surveys/openclaw-analysis.md"
git mv "docs/openclaw技术调研-mosaic架构优化方案.md" "docs/research/surveys/openclaw-to-mosaic-architecture.md"
git mv "docs/VLM场景图前沿方案调研.md" "docs/research/surveys/vlm-scene-graph-survey.md"
git mv "docs/自动场景建图开源方案调研.md" "docs/research/surveys/auto-mapping-open-source-survey.md"
git mv "docs/MOSAIC场景图实现示例调研-开源项目代码分析.md" "docs/research/surveys/scene-graph-implementation-examples.md"
git mv "docs/MOSAIC场景图表征架构规划-从文本到结构化世界理解.md" "docs/research/surveys/scene-graph-representation-architecture.md"
git mv "docs/MOSAIC混合架构方案分析-Python核心+TS调度层.md" "docs/research/surveys/python-core-ts-orchestration.md"
git mv "docs/MOSAIC-v2-前沿架构方案.md" "docs/research/surveys/mosaic-v2-frontier-architecture.md"
git mv "docs/MOSAIC-MCP-Server方案深度分析-回溯SayCan设计哲学.md" "docs/research/papers/mcp-server-and-saycan-analysis.md"
git mv "docs/外文翻译-SayCan.md" "docs/research/papers/saycan-translation.md"
```

Expected: `find docs/research -maxdepth 2 -type f | sort` shows files under `directions`, `surveys`, and `papers`.

- [ ] **Step 2: Add metadata headers to the moved research Markdown files**

Use `status: active`, `owner: repository-maintainers`, and `updated: 2026-04-03` for every file in this table:

| File | title | tags | source_type |
|---|---|---|---|
| `docs/research/directions/llm-physical-world-understanding.md` | How LLMs Understand The Physical World | docs, research, directions, llm | note |
| `docs/research/directions/embodied-agent-vs-mcp.md` | Embodied Agent vs MCP | docs, research, directions, mcp | note |
| `docs/research/surveys/openclaw-analysis.md` | OpenClaw Analysis | docs, research, survey, openclaw | survey |
| `docs/research/surveys/openclaw-to-mosaic-architecture.md` | OpenClaw To MOSAIC Architecture Survey | docs, research, survey, architecture | survey |
| `docs/research/surveys/vlm-scene-graph-survey.md` | VLM Scene Graph Survey | docs, research, survey, vlm | survey |
| `docs/research/surveys/auto-mapping-open-source-survey.md` | Auto Mapping Open Source Survey | docs, research, survey, mapping | survey |
| `docs/research/surveys/scene-graph-implementation-examples.md` | Scene Graph Implementation Examples | docs, research, survey, scene-graph | survey |
| `docs/research/surveys/scene-graph-representation-architecture.md` | Scene Graph Representation Architecture | docs, research, survey, scene-graph | survey |
| `docs/research/surveys/python-core-ts-orchestration.md` | Python Core And TypeScript Orchestration | docs, research, survey, architecture | survey |
| `docs/research/surveys/mosaic-v2-frontier-architecture.md` | MOSAIC v2 Frontier Architecture | docs, research, survey, architecture | survey |
| `docs/research/papers/mcp-server-and-saycan-analysis.md` | MCP Server And SayCan Analysis | docs, research, paper, saycan | paper |
| `docs/research/papers/saycan-translation.md` | SayCan Translation | docs, research, paper, translation | paper |

- [ ] **Step 3: Verify the research survey tree**

Run:

```bash
find docs/research -maxdepth 2 -type f | sort
```

Expected: The output includes `docs/research/README.md` and files in `directions`, `surveys`, and `papers`.

- [ ] **Step 4: Commit the research survey migration**

Run:

```bash
git add docs/research
git commit -m "docs: migrate research directions and surveys"
```

Expected: A commit containing only the `docs/research/` research-tree moves and metadata updates.

## Task 4: Migrate Thesis Artifacts And Reference Material

**Files:**
- Move: `docs/论文文档/*`
- Move: `docs/论文素材-参考文献调研清单.md`
- Move: `docs/论文素材/*`

- [ ] **Step 1: Move thesis and reference files into the research tree**

Run:

```bash
git mv "docs/论文文档/产品需求设计.md" "docs/research/thesis/product-requirements.md"
git mv "docs/论文文档/外文翻译.md" "docs/research/thesis/translation.md"
git mv "docs/论文文档/外文翻译.pdf" "docs/research/thesis/translation.pdf"
git mv "docs/论文文档/开题报告.md" "docs/research/thesis/proposal.md"
git mv "docs/论文文档/开题报告.pdf" "docs/research/thesis/proposal.pdf"
git mv "docs/论文文档/文献综述.md" "docs/research/thesis/literature-review.md"
git mv "docs/论文文档/文献综述.pdf" "docs/research/thesis/literature-review.pdf"
git mv "docs/论文文档/系统技术设计方案.md" "docs/research/thesis/system-technical-design.md"
git mv "docs/论文文档/系统技术设计方案.pdf" "docs/research/thesis/system-technical-design.pdf"
git mv "docs/论文素材-参考文献调研清单.md" "docs/research/references/bibliography-survey-index.md"
git mv "docs/论文素材/论文素材-Agent Loop技术演进研究.md" "docs/research/references/agent-loop-evolution.md"
git mv "docs/论文素材/论文素材-Co-NavGPT多机器人协作视觉导航.md" "docs/research/references/co-navgpt-multi-robot-visual-navigation.md"
git mv "docs/论文素材/论文素材-EmbodiedAgent技术方案深度分析与对比.md" "docs/research/references/embodied-agent-systems-comparison.md"
git mv "docs/论文素材/论文素材-SubAgent技术深度调研与系统评估.md" "docs/research/references/subagent-systems-evaluation.md"
git mv "docs/论文素材/论文素材-VLA技术研究现状深度调研.md" "docs/research/references/vla-state-of-the-art.md"
git mv "docs/论文素材/论文素材-世界模型与VLA_VLN技术调研.md" "docs/research/references/world-models-vla-vln-survey.md"
git mv "docs/论文素材/论文素材-人形机器人最后一步实现技术调研.md" "docs/research/references/humanoid-last-mile-survey.md"
git mv "docs/论文素材/论文素材-全局状态上下文管理方案调研.md" "docs/research/references/global-state-context-management.md"
git mv "docs/论文素材/论文素材-全局状态上下文管理方案调研.pdf" "docs/research/references/global-state-context-management.pdf"
git mv "docs/论文素材/论文素材-机器人自主探索与环境理解前沿方案.md" "docs/research/references/robot-autonomous-exploration-survey.md"
git mv "docs/论文素材/论文素材-机器人自主探索与环境理解前沿方案.pdf" "docs/research/references/robot-autonomous-exploration-survey.pdf"
git mv "docs/论文素材/论文素材-项目价值与场景分析.md" "docs/research/references/project-value-and-scenarios.md"
```

Expected: `find docs/research -maxdepth 2 -type f | sort` now shows files under `thesis` and `references`.

- [ ] **Step 2: Add metadata headers to moved Markdown thesis and reference documents**

Use `status: active`, `owner: repository-maintainers`, and `updated: 2026-04-03` for every Markdown file in this table:

| File | title | tags | source_type |
|---|---|---|---|
| `docs/research/thesis/product-requirements.md` | Product Requirements | docs, research, thesis, requirements | thesis |
| `docs/research/thesis/translation.md` | Thesis Translation | docs, research, thesis, translation | thesis |
| `docs/research/thesis/proposal.md` | Thesis Proposal | docs, research, thesis, proposal | thesis |
| `docs/research/thesis/literature-review.md` | Literature Review | docs, research, thesis, literature-review | thesis |
| `docs/research/thesis/system-technical-design.md` | System Technical Design | docs, research, thesis, system-design | thesis |
| `docs/research/references/bibliography-survey-index.md` | Bibliography Survey Index | docs, research, references, bibliography | survey |
| `docs/research/references/agent-loop-evolution.md` | Agent Loop Evolution | docs, research, references, agent-loop | note |
| `docs/research/references/co-navgpt-multi-robot-visual-navigation.md` | Co-NavGPT Multi Robot Visual Navigation | docs, research, references, navigation | note |
| `docs/research/references/embodied-agent-systems-comparison.md` | Embodied Agent Systems Comparison | docs, research, references, embodied-agent | note |
| `docs/research/references/subagent-systems-evaluation.md` | Subagent Systems Evaluation | docs, research, references, subagent | note |
| `docs/research/references/vla-state-of-the-art.md` | VLA State Of The Art | docs, research, references, vla | note |
| `docs/research/references/world-models-vla-vln-survey.md` | World Models VLA VLN Survey | docs, research, references, world-models | note |
| `docs/research/references/humanoid-last-mile-survey.md` | Humanoid Last Mile Survey | docs, research, references, humanoid | note |
| `docs/research/references/global-state-context-management.md` | Global State Context Management | docs, research, references, context | note |
| `docs/research/references/robot-autonomous-exploration-survey.md` | Robot Autonomous Exploration Survey | docs, research, references, exploration | note |
| `docs/research/references/project-value-and-scenarios.md` | Project Value And Scenarios | docs, research, references, strategy | note |

- [ ] **Step 3: Verify thesis and reference assets**

Run:

```bash
find docs/research/thesis docs/research/references -maxdepth 1 -type f | sort
```

Expected: Five Markdown plus four PDF files in `thesis`, and the renamed bibliography and reference materials in `references`.

- [ ] **Step 4: Commit the thesis and references migration**

Run:

```bash
git add docs/research
git commit -m "docs: migrate thesis and reference materials"
```

Expected: A commit containing only thesis and reference moves plus metadata updates.

## Task 5: Archive Historical Notes And Remove Obsolete Paths

**Files:**
- Move: `docs/Do as I can.md`
- Move: `docs/开发记录/progress.md`
- Delete: `docs/.DS_Store`
- Delete: empty legacy directories under `docs/`
- Delete: empty `scripts/docs`

- [ ] **Step 1: Move historical notes into the archive**

Run:

```bash
git mv "docs/Do as I can.md" "docs/archive/do-as-i-can.md"
git mv "docs/开发记录/progress.md" "docs/archive/development-progress-log.md"
```

Expected: `find docs/archive -maxdepth 1 -type f | sort` lists `README.md`, `do-as-i-can.md`, and `development-progress-log.md`.

- [ ] **Step 2: Add archive metadata to the moved Markdown files**

Add a top-of-file metadata block with these exact values:

| File | title | status | owner | updated | tags |
|---|---|---|---|---|---|
| `docs/archive/do-as-i-can.md` | Do As I Can | archived | repository-maintainers | 2026-04-03 | docs, archive, history |
| `docs/archive/development-progress-log.md` | Development Progress Log | archived | repository-maintainers | 2026-04-03 | docs, archive, progress |

- [ ] **Step 3: Remove obsolete filesystem leftovers**

Run:

```bash
rm -f docs/.DS_Store
rmdir "docs/API 文档" "docs/开发记录" "docs/论文文档" "docs/论文素材" "scripts/docs"
```

Expected: The command succeeds without leaving any of those directories behind.

- [ ] **Step 4: Verify there is no parallel doc entry point left**

Run:

```bash
find docs -maxdepth 2 -type d | sort
test ! -d "scripts/docs" && test ! -d "docs/API 文档" && test ! -d "docs/论文文档" && test ! -d "docs/论文素材" && echo "legacy-clean"
```

Expected: `legacy-clean`

- [ ] **Step 5: Commit the archive and cleanup work**

Run:

```bash
git add docs/archive docs
git commit -m "docs: archive historical notes and clean legacy paths"
```

Expected: A commit covering only the archive moves, `.DS_Store` deletion, and empty-directory cleanup.

## Task 6: Align Top-Level Navigation And Final Verification

**Files:**
- Modify: `README.md`
- Verify: `docs/README.md`, `docs/dev/README.md`, `docs/research/README.md`, `docs/archive/README.md`

- [ ] **Step 1: Add a documentation navigation section to `README.md`**

Insert this exact section after the introductory paragraphs near the top of `README.md`:

```md
## Documentation

- [Documentation Hub](docs/README.md)
- [Developer Documentation](docs/dev/README.md)
- [Research Documentation](docs/research/README.md)
- [Archive](docs/archive/README.md)
- [Knowledge Base Design Spec](docs/superpowers/specs/2026-04-03-document-knowledge-base-design.md)
- [Knowledge Base Implementation Plan](docs/superpowers/plans/2026-04-03-document-knowledge-base-reorganization.md)
```

- [ ] **Step 2: Verify the new navigation targets resolve**

Run:

```bash
test -f docs/README.md && test -f docs/dev/README.md && test -f docs/research/README.md && test -f docs/archive/README.md && test -f docs/superpowers/specs/2026-04-03-document-knowledge-base-design.md && test -f docs/superpowers/plans/2026-04-03-document-knowledge-base-reorganization.md && echo "nav-ready"
```

Expected: `nav-ready`

- [ ] **Step 3: Run final structural verification**

Run:

```bash
find docs -maxdepth 2 -type f | sort
rg -n "scripts/docs|docs/API 文档|docs/论文文档|docs/论文素材" README.md docs
git diff --check
```

Expected:

- The `find` output shows only `docs/README.md`, the `docs/dev|research|archive` trees, and `docs/superpowers/...`.
- `rg` returns no matches.
- `git diff --check` returns no whitespace or conflict-marker errors.

- [ ] **Step 4: Commit the top-level navigation update**

Run:

```bash
git add README.md docs/README.md docs/dev/README.md docs/research/README.md docs/archive/README.md
git commit -m "docs: align repository navigation with knowledge base"
```

Expected: A final commit that updates only navigation and index pages.

## Self-Review

### Spec Coverage

- Dual-track `docs/dev` and `docs/research` structure: covered by Task 1.
- Naming rules and index pages: covered by Tasks 1, 2, 3, and 4.
- Developer/research migration mapping: covered by Tasks 2, 3, and 4.
- Archive policy and historical-note handling: covered by Task 5.
- Removal of parallel doc entry points and `.DS_Store`: covered by Task 5.
- Root `README.md` navigation refresh: covered by Task 6.
- `.kiro/specs/` as process assets, not core knowledge-base content: covered by Task 1 index content and Task 6 verification.

### Placeholder Scan

- No `TODO`, `TBD`, or “fill in later” instructions remain.
- Every move uses an exact source and target path.
- Every verification step includes an explicit command and expected result.

### Type Consistency

- The plan consistently uses `docs/dev`, `docs/research`, `docs/archive`, and `docs/superpowers`.
- Date-prefixed report and plan names match the naming rules defined in the approved spec.
- `README.md` links point to the same paths created or moved in earlier tasks.
