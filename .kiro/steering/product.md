---
inclusion: always
---

# MOSAIC 产品概述

MOSAIC（Modular Open-Source Agent for Intelligent Control）是一个模块化机器人智能体框架，通过 LLM 驱动自然语言任务调度。

## 核心能力
- 用户通过自然语言下达指令（如"导航到厨房"、"帮我做杯咖啡送过来"）
- 系统自动完成：意图解析 → 任务规划 → 执行调度
- 支持复合指令自动分解为多步骤物理动作序列

## 两个版本并存
- `mosaic_demo/`：初期验证 Demo，单体架构，直接串联 Parser → Planner → Executor
- `mosaic/`：v2 重写，事件驱动 + 插件优先架构，通过 EventBus 解耦所有组件

## 支持的能力模块
导航（navigate_to, patrol）、运动（rotate, stop）、物品操作（pick_up, hand_over）、家电控制（operate_appliance, wait_appliance）

## LLM Provider
支持 MiniMax、OpenAI、Ollama 等多 Provider 共存，通过配置切换默认 Provider。API 密钥通过环境变量注入，禁止硬编码。
