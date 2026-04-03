- title: MOSAIC v2 Smoke Test Report
- status: active
- owner: repository-maintainers
- updated: 2026-04-03
- tags: docs, dev, report, smoke-test

# MOSAIC v2 冒烟测试报告

| 项目 | 值 |
|------|-----|
| 测试日期 | 2026-03-20 |
| Python 版本 | 3.10.12 |
| 测试框架 | pytest 9.0.2 + pytest-asyncio 1.3.0 + hypothesis 6.151.9 |
| 总测试数 | 203（原有属性测试 124 + 冒烟测试 79） |
| 通过 | 203 |
| 失败 | 0 |
| 耗时 | 47.11s |

## 测试覆盖范围

| 编号 | 测试组 | 用例数 | 覆盖模块 |
|------|--------|--------|----------|
| SM-01 | 公共 API 导入完整性 | 4 | `mosaic/__init__.py`、协议层、插件 SDK Protocol |
| SM-02 | EventBus 完整生命周期 | 5 | 事件分发、通配符匹配、中间件拦截、优先级排序、stop 终止 |
| SM-03 | HookManager 完整功能 | 4 | 优先级排序、拦截链、异常跳过、预定义钩子点 |
| SM-04 | ConfigManager 完整功能 | 6 | YAML 加载、点分路径、默认值、环境变量替换、热重载 |
| SM-05 | PluginRegistry（含修复验证） | 7 | discover kind 映射、plugin_id 连字符、Slot/Provider 解析、工具收集 |
| SM-06 | SessionManager 生命周期 | 6 | 创建→执行→关闭、并发限制、空闲回收、find_active_session |
| SM-07 | AgentRouter 路由功能 | 6 | channel/intent/scene 绑定、优先级、默认回退、确定性 |
| SM-08 | TurnRunner ReAct 循环 | 5 | 无工具响应、工具调用、迭代超限、异常封装、钩子触发 |
| SM-09 | NodeRegistry 节点管理 | 5 | 注册/注销、心跳恢复、能力查找、健康检查 |
| SM-10 | 能力插件（Navigation/Motion） | 8 | navigate_to/patrol/rotate/stop 执行、健康检查、取消、工具定义 |
| SM-11 | 记忆和上下文引擎插件 | 6 | FileMemory CRUD/搜索、SlidingWindow 摄入/组装/裁剪/隔离/压缩 |
| SM-12 | CLI Channel 插件 | 3 | Protocol 合规、send 输出、handler 注册 |
| SM-13 | MiniMax Provider 插件 | 4 | 元数据、auth 验证、请求体构建、响应解析 |
| SM-14 | GatewayServer 组件编排 | 6 | 初始化、插件发现、Slot/Provider 配置、路由绑定、启动/停止 |
| SM-15 | 端到端集成 | 4 | 完整文本管道、工具调用管道、多 Session 隔离、错误恢复 |

## 发现并修复的 Bug

### BUG-1: PluginRegistry.discover() kind 映射错误（严重）

- 位置: `mosaic/plugin_sdk/registry.py` — `discover()` 方法
- 原因: 使用 `category.rstrip("s")` 将目录名转为 kind，导致：
  - `capabilities` → `"capabilitie"`（应为 `"capability"`）
  - `context_engines` → `"context_engine"`（应为 `"context-engine"`）
- 影响: `list_by_kind("capability")` 返回空列表，TurnRunner 无法收集任何工具定义；`resolve_slot("context-engine")` 无法匹配
- 修复: 改为显式字典映射 `_CATEGORY_TO_KIND`，同时将 plugin_id 中的下划线转为连字符

### BUG-2: PluginRegistry.discover() plugin_id 命名不一致（严重）

- 位置: `mosaic/plugin_sdk/registry.py` — `discover()` 方法
- 原因: discover 注册的 plugin_id 使用 Python 目录名（下划线，如 `sliding_window`），但配置文件和 Slot 配置使用连字符（如 `sliding-window`）
- 影响: `set_slot("context-engine", "sliding-window")` 后 `resolve_slot` 找不到插件
- 修复: discover 时将 `name.replace("_", "-")` 统一为连字符命名

### BUG-3: EventBus.stop() 无法终止事件循环（中等）

- 位置: `mosaic/core/event_bus.py` — `start()` / `stop()` 方法
- 原因: `start()` 中 `await self._queue.get()` 在队列为空时永远阻塞，`stop()` 仅设置 `_running = False` 无法唤醒
- 影响: Gateway 停止时 EventBus 后台任务无法正常退出，只能靠 `task.cancel()` 强制取消
- 修复: 改为 `asyncio.wait_for(self._queue.get(), timeout=0.5)` 轮询，超时后检查 `_running` 标志

### BUG-4: GatewayServer 直接访问 SessionManager 私有属性（低）

- 位置: `mosaic/gateway/server.py` — `_get_or_create_session()` 方法
- 原因: 直接遍历 `self._session_manager._sessions.values()` 并用 `state.value` 字符串比较
- 影响: 违反封装原则，且字符串比较不如枚举比较安全
- 修复: 给 SessionManager 新增 `find_active_session()` 公共方法，使用枚举比较

### BUG-5: TurnRunner 使用命名关键字参数调用 assemble（低）

- 位置: `mosaic/runtime/turn_runner.py` — `_run_react_loop()` 方法
- 原因: `context_engine.assemble(session.session_id, token_budget=4096)` 使用命名参数，要求所有 ContextEnginePlugin 实现必须使用完全相同的参数名
- 影响: 参数名不匹配的插件实现会抛出 TypeError
- 修复: 改为位置参数调用 `context_engine.assemble(session.session_id, 4096)`

## 结论

MOSAIC v2 全部 15 个测试组、203 个测试用例通过。5 个 Bug 已全部修复，其中 BUG-1 和 BUG-2 为严重级别（会导致系统核心功能完全不可用），BUG-3 为中等级别，BUG-4 和 BUG-5 为低级别。系统端到端数据流验证通过，各组件集成正常。
