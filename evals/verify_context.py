"""verify_context.py —— FR-2 上下文管理验证（离线）。

跑法（在 agent-lab 目录下）：
    .venv/Scripts/python.exe evals/verify_context.py

覆盖：
  1. 滑动窗口：超窗消息被裁剪，system 始终保留
  2. 工具结果截断：超限截断 + 标注"结果已截断"
  3. 单条消息截断
  4. token 估算：中文/英文不同系数
  5. 集成：AgentLoop 使用窗口（fake client 验证不崩）
"""

import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")
    if not cond:
        fails.append(name)


def main():
    print("[1] 滑动窗口")
    from shared_tools.context import apply_sliding_window

    msgs = [{"role": "user", "content": f"旧消息{i}"} for i in range(30)]
    w = apply_sliding_window(msgs, "SYS", max_messages=10)
    check("窗口后消息数 = 1 + 10", len(w) == 11, f"(={len(w)})")
    check("system 在最前", w[0]["role"] == "system" and w[0]["content"] == "SYS")
    check("保留最近消息", w[-1]["content"] == "旧消息29")
    check("旧消息被丢弃", all("旧消息0" not in m["content"] for m in w))

    print("\n[2] 工具结果截断")
    from shared_tools.context import truncate_tool_result

    t = truncate_tool_result("x" * 5000, max_chars=100)
    check("超限截断", len(t) < 5000)
    check("标注'结果已截断'", "结果已截断" in t)
    t2 = truncate_tool_result("短内容", max_chars=100)
    check("短内容不截断", t2 == "短内容")

    print("\n[3] 消息列表截断")
    from shared_tools.context import apply_message_truncation

    msgs2 = [
        {"role": "tool", "content": "t" * 5000},
        {"role": "user", "content": "u" * 5000},
        {"role": "user", "content": "正常"},
    ]
    out = apply_message_truncation(msgs2)
    check("tool 消息被截断", "结果已截断" in out[0]["content"])
    check("user 消息被截断", out[1]["content"].endswith("[截断]"))
    check("正常消息不动", out[2]["content"] == "正常")

    print("\n[4] token 估算")
    from shared_tools.context import estimate_tokens

    check("中文按字符", estimate_tokens("你好世界") >= 4)
    check("英文按 4 字符", estimate_tokens("hello") >= 1)

    print("\n[5] 集成：AgentLoop 使用窗口（fake client）")
    from evals.trace_util import ToolCallRecorder
    from handcrafted.agent import AgentLoop

    class _FakeMsg:
        def __init__(self, tool_calls=None, content=None):
            self.tool_calls = tool_calls
            self.content = content

    class _FakeToolCall:
        def __init__(self, id, name, args):
            self.id = id
            self.function = type("F", (), {"name": name, "arguments": args})()

    class _FakeClient:
        def __init__(self):
            self.calls = 0

        @property
        def chat(self):
            return self

        @property
        def completions(self):
            return self

        def create(self, **kw):
            self.calls += 1
            if self.calls == 1:
                tc = _FakeToolCall("c1", "calculator", json.dumps({"expression": "6 * 7"}))
                return type("R", (), {"choices": [type("C", (), {"message": _FakeMsg(tool_calls=[tc])})]})()
            return type("R", (), {"choices": [type("C", (), {"message": _FakeMsg(content="42")})]})()

    agent = AgentLoop(_FakeClient(), max_context_messages=5)
    with ToolCallRecorder() as rec:
        out = agent.run("算 6*7")
    check("集成：循环正常跳出", out == "42")
    check("集成：工具被调用", rec.tool_calls == ["calculator"])

    print("\n结果: 全部通过" if not fails else f"\n结果: {len(fails)} 失败 -> {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
