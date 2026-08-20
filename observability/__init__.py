"""observability.py —— Langfuse 观测（FR-4，零侵入 + 无 key 降级）。

设计（PRD FR-4）：
- trace 命名契约：trace = 会话（session_id），observation = LLM 调用 / 工具调用
- 零侵入：包装 client，不改 AgentLoop 核心逻辑
- 可选依赖降级：无 LANGFUSE_PUBLIC_KEY / 未装 langfuse → NullTracer（静默）
- 降级覆盖两种情况：key 不存在 + key 存在但无效（后者 Langfuse 可能打警告不崩）

真实 API 适配（2026-08-19 实测 langfuse 4.14.4）：
- 老 API（trace()/generation()/span()）已不存在
- 新 API：Langfuse.start_observation(name, type, ...) → 返回 observation，.end()
- 通过 start_as_current_observation 的上下文管理，子 observation 自动挂到当前父级

两版观测路径：
- 手写版：本模块（start_observation）
- LangChain 版：langfuse.callback_handler.CallbackHandler（M4 文档记录，可选接入）
"""

import os
import logging

logger = logging.getLogger(__name__)

try:  # 可选依赖：未安装 langfuse 时降级
    from langfuse import Langfuse
    _LANGFUSE_AVAILABLE = True
except ImportError:
    _LANGFUSE_AVAILABLE = False


def langfuse_enabled() -> bool:
    """降级检测：key 不存在 → False。"""
    return _LANGFUSE_AVAILABLE and bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


class NullSpan:
    """静默降级 span（接口与真实 observation 对齐）。"""

    def end(self, **kwargs):
        pass

    def update(self, **kwargs):
        pass


class NullTracer:
    """无 key / 未安装时的静默降级。"""

    def __init__(self):
        self.enabled = False

    def start_session_trace(self, name, session_id=None):
        return NullSpan()

    def span_llm_call(self, trace, name, model, input, output, usage=None):
        return NullSpan()

    def span_tool_call(self, trace, name, tool_name, input, output, duration_ms=None):
        return NullSpan()


class Tracer:
    """统一观测入口：真实 Langfuse 或 NullTracer（降级）。"""

    def __init__(self):
        self._impl = None
        self.enabled = False
        self._init()

    def _init(self):
        if not langfuse_enabled():
            self._impl = NullTracer()
            return
        try:
            self._impl = Langfuse(
                public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
            )
            self.enabled = True
        except Exception as e:
            logger.warning("[obs] Langfuse 初始化失败，降级 NullTracer: %s", e)
            self._impl = NullTracer()

    # -- trace 命名契约（PRD FR-4）：trace = 会话 -------------------------

    def start_session_trace(self, session_id, name="agent-run"):
        """会话级 trace 根节点（FR-3/4 共用）。

        langfuse 4.x 规范：start_as_current_observation 上下文管理器 + trace_context
        显式 trace_id；子 observation 在 with 块内自动挂到当前 trace。
        返回一个包装对象：进入 with 启动 trace，.end() 退出。
        """
        if not self.enabled:
            return NullSpan()
        try:
            import uuid
            from langfuse import Langfuse

            trace_id = uuid.uuid4().hex  # 32 hex chars（langfuse 要求）
            cm = self._impl.start_as_current_observation(
                name=f"{name}:{session_id}",
                as_type="agent",
                trace_context={"trace_id": trace_id},
            )
            root = cm.__enter__()
            return _TraceHandle(root, cm, session_id)
        except Exception as e:
            logger.warning("[obs] start_session_trace 失败: %s", e)
            return NullSpan()

    def span_llm_call(self, trace, name, model, input, output, usage=None):
        """LLM 调用 observation（挂到当前 trace）。"""
        if not self.enabled:
            return NullSpan()
        try:
            return trace.start_observation(
                name=name,
                as_type="generation",
                model=model,
                input=input,
                output=output,
                metadata={"usage": usage} if usage else None,
            )
        except Exception:
            return NullSpan()

    def span_tool_call(self, trace, name, tool_name, input, output, duration_ms=None):
        """工具调用 observation（挂到当前 trace）。"""
        if not self.enabled:
            return NullSpan()
        try:
            return trace.start_observation(
                name=f"tool:{tool_name}",
                as_type="tool",
                input=input,
                output=output,
                metadata={"duration_ms": duration_ms} if duration_ms else None,
            )
        except Exception:
            return NullSpan()


class _TraceHandle:
    """trace 根节点的包装：.end() 退出上下文管理器，并设置 session_id。"""

    def __init__(self, root, cm, session_id):
        self._root = root
        self._cm = cm
        self._session_id = session_id

    def start_observation(self, *args, **kwargs):
        # 子 observation 挂到根节点（同一 trace）
        return self._root.start_observation(*args, **kwargs)

    def end(self, **kwargs):
        try:
            self._root.update(**kwargs)
        except Exception:
            pass
        try:
            self._cm.__exit__(None, None, None)
        except Exception:
            pass


# 全局单例
tracer = Tracer()


def get_tracer() -> Tracer:
    """返回全局 tracer（真实 Langfuse 或 NullTracer 降级）。"""
    return tracer
