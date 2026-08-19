"""verify_observability.py —— FR-4 Langfuse 观测验证（离线优先）。

跑法（在 agent-lab 目录下）：
    .venv/Scripts/python.exe evals/verify_observability.py

覆盖：
  1. 降级：无 LANGFUSE key → NullTracer（不崩、静默）
  2. trace 命名契约：start_session_trace 返回可用 span
  3. span 方法：LLM / 工具调用 observation 可调用（NullSpan 静默）
  4. 有 key 时（可选）：真实 Langfuse 初始化成功
"""

import os
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")
    if not cond:
        fails.append(name)


def main():
    print("[1] 降级（无 key → NullTracer）")
    from observability import Tracer, NullTracer

    t = Tracer()
    check("无 key 时降级（enabled=False）", t.enabled is False)
    check("实现是 NullTracer", isinstance(t._impl, NullTracer))

    print("[2] trace 命名契约")
    span = t.start_session_trace("test-session-001", name="agent-run")
    check("会话 trace 可用", span is not None)

    print("[3] observation 方法可调用（静默）")
    s1 = t.span_llm_call(span, "llm-call", "deepseek-v4-flash", "q", "a")
    check("LLM observation 可调用", s1 is not None)
    s2 = t.span_tool_call(span, "tool-call", "calculator", {"expression": "1+1"}, {"result": 2})
    check("工具 observation 可调用", s2 is not None)

    print("[4] 有 key 时真实初始化（可选验证）")
    if os.getenv("LANGFUSE_PUBLIC_KEY"):
        t2 = Tracer()
        check("有 key → enabled=True", t2.enabled is True)
        print("  (检测到 LANGFUSE key，真实初始化验证)")
    else:
        print("  (无 LANGFUSE key，跳过真实初始化——降级已验证)")

    print("\n结果: 全部通过" if not fails else f"\n结果: {len(fails)} 失败 -> {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
