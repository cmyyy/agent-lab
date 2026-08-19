"""observability.py —— Langfuse 观测（FR-4，零侵入 + 无 key 降级）。

设计（PRD FR-4）：
- trace 命名契约：trace = 会话（session_id），observation = LLM 调用 / 工具调用
- 零侵入：包装 client，不改 AgentLoop 核心逻辑
- 可选依赖降级：无 LANGFUSE_PUBLIC_KEY / 未装 langfuse → NullTracer（静默）
- 降级覆盖两种情况：key 不存在 + key 存在但无效（后者 Langfuse 可能打警告不崩）

两版观测路径：
- 手写版：TracingOpenAIWrapper 包装 openai client
- LangChain 版：langfuse.callback_handler.CallbackHandler（M4 文档记录，
  代码里留给 agent.py 可选接入）

面试点：观测→决策闭环——至少一次由数据驱动的决策（如 top_k 调优）。
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
    return _LANGFUSE_AVAILABLE and bool(os.getenv("LANGFUSE_PUBLIC_KEY"))


class NullTracer:
    """无 key / 未安装时的静默降级（接口与真实 tracer 对齐）。"""

    def __init__(self):
        self.enabled = False

    def start_trace(self, name, session_id=None):
        return NullSpan()

    def get_llm_observation(self, trace, name, model, input, output, metadata=None):
        return NullSpan()


class NullSpan:
    def end(self, **kwargs):
        pass

    def update(self, **kwargs):
        pass

    def get_observation(self, name):
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
        """会话级 trace（session_id 归组，FR-3/4 共用）。"""
        if not self.enabled:
            return NullSpan()
        return self._impl.trace(name=f"{name}:{session_id}", session_id=session_id)

    def span_llm_call(self, trace, name, model, input, output, usage=None):
        """LLM 调用 observation。"""
        if not self.enabled:
            return NullSpan()
        try:
            return trace.generation(
                name=name,
                model=model,
                input=input,
                output=output,
                metadata={"usage": usage} if usage else None,
            )
        except Exception:
            return NullSpan()

    def span_tool_call(self, trace, name, tool_name, input, output, duration_ms=None):
        """工具调用 observation。"""
        if not self.enabled:
            return NullSpan()
        try:
            return trace.span(
                name=f"tool:{tool_name}",
                input=input,
                output=output,
                metadata={"duration_ms": duration_ms} if duration_ms else None,
            )
        except Exception:
            return NullSpan()


# 全局单例
tracer = Tracer()


def get_tracer() -> Tracer:
    """返回全局 tracer（真实 Langfuse 或 NullTracer 降级）。"""
    return tracer
