"""生命周期钩子管理器 — 优先级排序 + 拦截链 + 超时保护

覆盖 Gateway、Session、Turn、LLM、Tool、Node、Context 全链路的钩子系统。
"""

import asyncio
from typing import Callable, Awaitable, Any

# 钩子处理函数类型：接收上下文字典，返回任意值
HookHandler = Callable[[dict[str, Any]], Awaitable[Any]]

# 预定义钩子点 — 覆盖系统全生命周期
HOOK_POINTS = [
    # Gateway 生命周期
    "gateway.start",
    "gateway.stop",
    # 配置变更
    "config.reload",
    # Session 生命周期
    "session.create",
    "session.close",
    "session.idle",
    # Turn 生命周期
    "turn.start",
    "turn.end",
    "turn.error",
    # LLM 调用前后
    "llm.before_call",
    "llm.after_call",
    # 工具执行前后 + 权限审批
    "tool.before_exec",
    "tool.after_exec",
    "tool.permission",
    # 节点状态变更
    "node.connect",
    "node.disconnect",
    "node.health_change",
    # 上下文管理
    "context.compact",
    "context.overflow",
]


class HookManager:
    """生命周期钩子 — 优先级排序 + 拦截链 + 超时保护

    - on(): 注册钩子，按 priority 升序排列（数值越小越先执行）
    - emit(): 触发钩子链，handler 返回 False 可拦截后续执行
    - 单个 handler 超时（5秒）或异常不影响链的继续执行
    """

    def __init__(self):
        # 钩子点 → [(priority, handler), ...] 按 priority 升序排列
        self._hooks: dict[str, list[tuple[int, HookHandler]]] = {}

    def on(self, point: str, handler: HookHandler, priority: int = 100):
        """注册钩子（priority 越小越先执行）"""
        self._hooks.setdefault(point, []).append((priority, handler))
        self._hooks[point].sort(key=lambda x: x[0])

    async def emit(self, point: str, context: dict[str, Any]) -> bool:
        """触发钩子链，返回 False 表示被拦截

        按优先级顺序依次执行 handler：
        - handler 返回 False → 停止链，返回 False
        - handler 超时（5秒）→ 跳过，继续下一个
        - handler 抛异常 → 跳过，继续下一个
        """
        for _, handler in self._hooks.get(point, []):
            try:
                result = await asyncio.wait_for(handler(context), timeout=5.0)
                if result is False:
                    return False
            except (asyncio.TimeoutError, Exception):
                pass  # 单个 hook 失败不影响链
        return True
