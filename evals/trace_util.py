"""trace_util —— 统一工具调用记录器（FR-1.4 对比采集 + FR-4 观测雏形）。

两版统一的工具调用采集点（2026-08-19 设计决策）：
- 手写版：工具调用发生在 registry.dispatch（monkeypatch 拦截）
- LangChain 版：工具调用发生在 tool_adapter._safe_handler（StructuredTool 包装层）

两条路径不同，必须各挂一个采集点——这就是"两版统一观测"的接口设计
（PRD FR-4：trace=会话 / observation=工具调用，两版命名一致才有对比意义）。

实现：本文件定义 recorder（上下文管理器），
- 手写版自动挂到 registry.dispatch
- LangChain 版通过 tool_adapter 的 _CURRENT_RECORDER 全局钩子挂接
（tool_adapter._safe_handler 里每次调用检查钩子并记录）
"""

import contextlib

# LangChain 版工具调用的采集钩子（tool_adapter._safe_handler 会检查并记录）
_CURRENT_RECORDER = None


@contextlib.contextmanager
def ToolCallRecorder():
    """记录两版工具调用序列（手写版 registry.dispatch + LangChain 版 adapter 钩子）。"""
    global _CURRENT_RECORDER

    from shared_tools import registry

    calls = []
    _CURRENT_RECORDER = calls

    original = registry.dispatch

    def recording_dispatch(name, args):
        calls.append(name)
        return original(name, args)

    registry.dispatch = recording_dispatch
    try:
        yield type("Rec", (), {"tool_calls": calls})()
    finally:
        registry.dispatch = original
        _CURRENT_RECORDER = None


def record_tool_call(name: str) -> None:
    """工具调用钩子（tool_adapter 用）：有活跃 recorder 时记录工具名。"""
    if _CURRENT_RECORDER is not None:
        _CURRENT_RECORDER.append(name)
