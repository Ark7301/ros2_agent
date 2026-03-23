# mosaic/runtime/turn_runner.py
"""Turn 级原子执行器 — ReAct 循环 + 并行工具调用 + 指数退避重试

一个 Turn = 用户输入 → [LLM 推理 → 工具调用]* → 最终响应。
Planner 是内部策略（非插件 Slot），通过 ReAct 循环实现：
1. 组装上下文 → 2. LLM 推理 → 3. 工具调用（可选）→ 4. 循环或返回

Requirements: 5.1-5.12, 10.1-10.3
"""

import asyncio
import json
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from mosaic.plugin_sdk.types import ProviderConfig, ExecutionContext, ExecutionResult
from mosaic.runtime.scene_graph_manager import SceneGraphManager


@dataclass
class TurnResult:
    """Turn 执行结果

    包含最终响应、工具调用记录、执行结果、token 用量和耗时等信息。
    """
    success: bool
    response: str
    tool_calls: list[dict] = field(default_factory=list)
    execution_results: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    duration_ms: float = 0.0
    turn_id: str = ""


class TurnRunner:
    """Turn 级原子执行器 — ReAct 循环 + 并行工具调用

    核心流程：
    1. 通过 ContextEnginePlugin 组装上下文消息
    2. 从所有 CapabilityPlugin 收集工具定义
    3. 进入 ReAct 循环：LLM 推理 → 工具调用 → 追加结果 → 继续
    4. Provider 返回无工具调用时终止循环，返回最终响应
    5. 超过 max_iterations 或 turn_timeout_s 时强制终止

    钩子触发点：turn.start / turn.end / turn.error / llm.before_call / llm.after_call
    """

    def __init__(
        self,
        registry,
        event_bus,
        hooks,
        max_iterations: int = 10,
        turn_timeout_s: float = 120,
        system_prompt: str = "",
        scene_graph_mgr: SceneGraphManager | None = None,
    ):
        self._registry = registry       # PluginRegistry 实例
        self._event_bus = event_bus      # EventBus 实例
        self._hooks = hooks              # HookManager 实例
        self._max_iterations = max_iterations    # ReAct 最大迭代次数
        self._turn_timeout_s = turn_timeout_s    # Turn 超时时间（秒）
        self._system_prompt = system_prompt      # 系统提示词
        self._scene_graph_mgr = scene_graph_mgr  # 场景图管理器（可选）

    async def run(self, session, user_input: str) -> TurnResult:
        """执行完整 Turn — 入口方法，含超时保护

        通过 asyncio.wait_for 实现 turn_timeout_s 超时终止。
        触发 turn.start / turn.end / turn.error 钩子。
        """
        start = time.monotonic()
        turn_id = f"turn-{session.session_id[:8]}-{session.turn_count}"

        # 触发 turn.start 钩子
        await self._hooks.emit("turn.start", {
            "session_id": session.session_id,
            "turn_id": turn_id,
        })

        try:
            # 超时保护：asyncio.wait_for 在超时时抛出 asyncio.TimeoutError
            result = await asyncio.wait_for(
                self._run_react_loop(session, user_input, turn_id, start),
                timeout=self._turn_timeout_s,
            )
            # 触发 turn.end 钩子
            await self._hooks.emit("turn.end", {
                "session_id": session.session_id,
                "turn_id": turn_id,
                "success": result.success,
            })
            return result
        except Exception as e:
            # 触发 turn.error 钩子（超时、迭代超限等异常）
            await self._hooks.emit("turn.error", {
                "session_id": session.session_id,
                "error": str(e),
            })
            raise

    async def _run_react_loop(
        self,
        session,
        user_input: str,
        turn_id: str,
        start: float,
    ) -> TurnResult:
        """ReAct 循环核心

        循环不变量：
        - iteration < max_iterations
        - messages 列表单调递增（每次迭代追加工具结果）
        - all_tool_calls 和 all_results 长度一致
        """
        # 1. 通过 context-engine Slot 组装上下文
        context_engine = self._registry.resolve_slot("context-engine")
        context = await context_engine.assemble(session.session_id, 4096)

        # 构建消息列表：system prompt → 历史上下文 → 当前用户输入
        messages: list[dict] = []
        if self._system_prompt:
            # ★ 集成点 1：组装上下文时注入场景图子图
            system_content = self._system_prompt
            if self._scene_graph_mgr:
                scene_text = self._scene_graph_mgr.get_scene_prompt(user_input)
                system_content = f"{self._system_prompt}\n\n{scene_text}"
            messages.append({"role": "system", "content": system_content})
        messages.extend(context.messages)
        messages.append({"role": "user", "content": user_input})

        # 2. 从所有 CapabilityPlugin 收集工具定义
        tools = self._collect_tool_definitions()

        # 3. 获取默认 Provider
        provider = self._registry.resolve_provider()

        all_tool_calls: list[dict] = []
        all_results: list[Any] = []

        # 过程输出：Turn 开始
        self._log(f"🔄 Turn 开始 [{turn_id}]")
        self._log(f"📨 用户输入: {user_input}")

        for iteration in range(self._max_iterations):
            # 触发 llm.before_call 钩子
            await self._hooks.emit("llm.before_call", {
                "session_id": session.session_id,
                "iteration": iteration,
            })

            # 过程输出：LLM 推理
            self._log(f"🤖 LLM 推理中... (第 {iteration + 1} 轮)")

            # Provider 调用带指数退避重试（最多 3 次）
            response = await self._call_provider_with_retry(
                provider, messages, tools,
            )

            # 触发 llm.after_call 钩子
            await self._hooks.emit("llm.after_call", {
                "session_id": session.session_id,
                "has_tool_calls": bool(response.tool_calls),
            })

            # 无工具调用 → 尝试从文本中回退解析工具调用
            if not response.tool_calls:
                fallback_calls = self._extract_tool_calls_from_text(
                    response.content or "", tools,
                )
                if fallback_calls:
                    # 回退解析成功，将提取的工具调用注入 response
                    self._log("⚠️ LLM 未使用 function calling，从文本中回退解析工具调用")
                    response.tool_calls = fallback_calls
                else:
                    # 确实没有工具调用 → 终止循环，返回最终响应
                    elapsed = (time.monotonic() - start) * 1000
                    tokens = (response.usage or {}).get("total_tokens", 0)
                    self._log(f"✅ Turn 完成 [{elapsed:.0f}ms, {tokens} tokens]")

                    # 通过 ContextEnginePlugin.ingest() 持久化消息
                    await context_engine.ingest(
                        session.session_id,
                        {"role": "user", "content": user_input},
                    )
                    await context_engine.ingest(
                        session.session_id,
                        {"role": "assistant", "content": response.content},
                    )
                    return TurnResult(
                        success=True,
                        response=response.content,
                        tool_calls=all_tool_calls,
                        execution_results=all_results,
                        tokens_used=tokens,
                        duration_ms=elapsed,
                        turn_id=turn_id,
                    )

            # 过程输出：LLM 决定调用工具
            for tc in response.tool_calls:
                args = tc.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        args = {}
                self._log(f"🔧 调用工具: {tc['name']}({args})")

            # 有工具调用 → 并行执行所有工具

            # ★ 集成点 2：执行前验证计划（VeriGraph 思路）
            if self._scene_graph_mgr:
                plan_steps = [
                    {
                        "action": tc["name"],
                        "params": (
                            json.loads(tc["arguments"])
                            if isinstance(tc.get("arguments"), str)
                            else tc.get("arguments", {})
                        ),
                    }
                    for tc in response.tool_calls
                ]
                verification = self._scene_graph_mgr.verify_plan(plan_steps)
                if not verification.feasible:
                    # 计划不可行 → 将验证反馈注入消息，让 LLM 修正
                    feedback = verification.to_llm_feedback()
                    self._log(f"⚠️ 计划验证失败: {verification.failure_reason}")
                    messages.append({
                        "role": "system",
                        "content": f"[计划验证失败]\n{feedback}",
                    })
                    continue  # 跳过执行，让 LLM 重新规划

            tool_results = await self._execute_tools(
                response.tool_calls, session,
            )
            all_tool_calls.extend(response.tool_calls)
            all_results.extend(tool_results)

            # ★ 集成点 3：执行后更新场景图
            if self._scene_graph_mgr:
                for tc, tr in zip(response.tool_calls, tool_results):
                    if isinstance(tr, ExecutionResult):
                        args = tc.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except (json.JSONDecodeError, TypeError):
                                args = {}
                        self._scene_graph_mgr.update_from_execution(
                            tc["name"], args, tr.success,
                        )
                # 刷新场景图（环境已变化）
                scene_text = self._scene_graph_mgr.get_scene_prompt(user_input)
                if messages and messages[0].get("role") == "system":
                    messages[0]["content"] = (
                        f"{self._system_prompt}\n\n{scene_text}"
                    )

            # 过程输出：工具执行结果
            for tc, tr in zip(response.tool_calls, tool_results):
                if isinstance(tr, ExecutionResult):
                    if tr.success:
                        self._log(f"  ✓ {tc['name']}: {tr.message}")
                    else:
                        self._log(f"  ✗ {tc['name']}: {tr.error}")
                else:
                    self._log(f"  → {tc['name']}: {tr}")

            # 追加工具调用和结果到消息历史
            # 将扁平化的 tool_calls 转回 OpenAI function calling 格式
            formatted_tool_calls = []
            for tc in response.tool_calls:
                formatted_tool_calls.append({
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc.get("arguments", "{}") if isinstance(tc.get("arguments"), str) else json.dumps(tc.get("arguments", {})),
                    },
                })
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": formatted_tool_calls,
            })
            for tc, tr in zip(response.tool_calls, tool_results):
                # 工具结果内容需要是字符串
                if isinstance(tr, ExecutionResult):
                    tool_content = tr.message if tr.success else f"错误: {tr.error}"
                else:
                    tool_content = str(tr)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": tool_content,
                })

        # 迭代次数耗尽，抛出 RuntimeError
        raise RuntimeError(f"Turn 超过最大迭代次数: {self._max_iterations}")

    @staticmethod
    def _log(msg: str) -> None:
        """输出过程日志到 stdout，让用户看到后台操作"""
        print(f"  {msg}", flush=True)

    async def _call_provider_with_retry(
        self,
        provider,
        messages: list[dict],
        tools: list[dict],
        max_retries: int = 3,
    ):
        """Provider 调用指数退避重试

        重试策略：最多 max_retries 次，每次等待 0.1 * 2^attempt 秒。
        重试耗尽后抛出最后一次异常。
        """
        for attempt in range(max_retries):
            try:
                return await provider.chat(messages, tools, config=ProviderConfig())
            except Exception:
                if attempt == max_retries - 1:
                    raise
                # 指数退避：0.1s → 0.2s → 0.4s
                await asyncio.sleep(0.1 * (2 ** attempt))

    async def _execute_tools(
        self,
        tool_calls: list[dict],
        session,
    ) -> list[Any]:
        """并行执行工具调用

        使用 asyncio.gather 并行执行所有工具调用。
        arguments 可能是 JSON 字符串（LLM API 返回格式），需要解析为 dict。
        异常被封装为 ExecutionResult(success=False)，保证返回数量与输入一致。
        """
        tasks = []
        for tc in tool_calls:
            # 根据工具名查找对应的 CapabilityPlugin
            cap = self._resolve_capability_for_tool(tc["name"])
            ctx = ExecutionContext(session_id=session.session_id)
            # arguments 可能是 JSON 字符串，需要解析
            args = tc.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            tasks.append(
                cap.execute(tc["name"], args, ctx),
            )
        # 并行执行，异常不中断其他任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # 异常封装为 ExecutionResult(success=False)
        return [
            r if not isinstance(r, Exception)
            else ExecutionResult(success=False, error=str(r))
            for r in results
        ]

    def _collect_tool_definitions(self) -> list[dict]:
        """从所有已注册 CapabilityPlugin 收集工具定义

        将裸工具定义包裹为 OpenAI function calling 格式：
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        tools: list[dict] = []
        for pid in self._registry.list_by_kind("capability"):
            plugin = self._registry.resolve(pid)
            for tool_def in plugin.get_tool_definitions():
                # 如果已经是 function calling 格式则直接使用
                if "type" in tool_def and "function" in tool_def:
                    tools.append(tool_def)
                else:
                    # 包裹为 OpenAI function calling 格式
                    tools.append({
                        "type": "function",
                        "function": tool_def,
                    })
        return tools

    def _resolve_capability_for_tool(self, tool_name: str):
        """根据工具名查找对应的 CapabilityPlugin

        遍历所有 capability 类型插件，匹配工具名。
        未找到时抛出 KeyError。
        """
        for pid in self._registry.list_by_kind("capability"):
            plugin = self._registry.resolve(pid)
            if tool_name in [t["name"] for t in plugin.get_tool_definitions()]:
                return plugin
        raise KeyError(f"未找到工具: {tool_name}")
    def _extract_tool_calls_from_text(
        self, content: str, tools: list[dict],
    ) -> list[dict]:
        """从 LLM 文本输出中回退解析工具调用

        当 LLM 未通过 function calling 格式返回工具调用，
        而是在文本中输出了类似 `函数名({"参数": "值"})` 的内容时，
        尝试从文本中提取并构造标准 tool_call 结构。

        支持的文本模式：
        - tool_name({"key": "value"})
        - tool_name({"key": "value", ...})
        - functions.tool_name({"key": "value"})
        """
        # 收集所有已知工具名
        known_tools: set[str] = set()
        for tool_def in tools:
            func = tool_def.get("function", tool_def)
            name = func.get("name", "")
            if name:
                known_tools.add(name)

        extracted: list[dict] = []
        # 匹配 可选前缀.工具名({...JSON...})
        pattern = re.compile(
            r'(?:functions?\.)?' +
            r'(' + '|'.join(re.escape(t) for t in known_tools) + r')' +
            r'\s*\(\s*(\{.*?\})\s*\)',
            re.DOTALL,
        )
        for match in pattern.finditer(content):
            name = match.group(1)
            args_str = match.group(2)
            try:
                json.loads(args_str)  # 验证 JSON 合法性
            except (json.JSONDecodeError, TypeError):
                continue
            extracted.append({
                "id": f"fallback-{uuid.uuid4().hex[:8]}",
                "name": name,
                "arguments": args_str,
            })
        return extracted
