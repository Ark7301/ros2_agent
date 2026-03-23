"""协议层 — 错误码枚举定义"""
from enum import Enum


class ErrorCode(Enum):
    """系统错误码"""
    # 插件相关
    PLUGIN_NOT_FOUND = "plugin_not_found"
    PLUGIN_LOAD_FAILED = "plugin_load_failed"

    # 会话相关
    SESSION_NOT_FOUND = "session_not_found"
    SESSION_CLOSED = "session_closed"
    SESSION_LIMIT_REACHED = "session_limit_reached"

    # Turn 执行相关
    TURN_TIMEOUT = "turn_timeout"
    TURN_MAX_ITERATIONS = "turn_max_iterations"

    # Provider 相关
    PROVIDER_ERROR = "provider_error"
    PROVIDER_AUTH_FAILED = "provider_auth_failed"

    # 配置相关
    CONFIG_ERROR = "config_error"
    CONFIG_FILE_NOT_FOUND = "config_file_not_found"

    # 节点相关
    NODE_HEARTBEAT_TIMEOUT = "node_heartbeat_timeout"
    NODE_NOT_FOUND = "node_not_found"

    # 工具执行相关
    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
