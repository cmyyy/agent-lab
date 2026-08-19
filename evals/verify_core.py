"""verify_core.py —— agent-lab 核心行为验证（eval 雏形第一块）。

不依赖真实 API（mock 掉 LLM 客户端），秒出结果，任何改动后跑一次防回归。
这是 golden 回归套件的前身：先用结构性断言锁住核心循环行为，
后续把真实 API 的 golden queries（{query, expected_tools, expected_fields}）加进来。

运行：
    python evals/verify_core.py

当前覆盖：
  1. registry 暴露 6 个 schema 且与 TOOLS_SCHEMA 一致（菜单不漂移）
  2. dispatch 三路径：正常分发 / 未知工具 / 注入（永不抛异常）
  3. check_fn 过滤：不可用的工具不暴露（模型看不到=不会幻觉调用）
  4. AgentLoop 循环：tool_call -> 分发 -> 回填 -> 纯文本跳出，恰好 2 轮
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared_tools import TOOLS_SCHEMA, registry
from handcrafted.agent import AgentLoop

fails = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        fails.append(name)


def test_registry_consistency():
    defs = registry.get_definitions()
    check("registry 暴露 6 个 schema", len(defs) == 6)
    check(
        "与 TOOLS_SCHEMA 一致",
        [d["function"]["name"] for d in defs]
        == [t["function"]["name"] for t in TOOLS_SCHEMA],
    )


def test_dispatch_paths():
    r = registry.dispatch("calculator", {"expression": "(25 * 1.8) + 32"})
    check("正常分发", r.get("result") == 77.0)
    r = registry.dispatch("not_exist", {})
    check("未知工具 -> error", "error" in r)
    r = registry.dispatch("calculator", {"expression": "__import__('os').system('x')"})
    check("注入 -> error", "error" in r)


def test_check_fn_filter():
    registry.register(
        "secret_tool",
        {"type": "function", "function": {"name": "secret_tool", "parameters": {"type": "object", "properties": {}}}},
        lambda: "secret",
        check_fn=lambda: False,
    )
    check(
        "check_fn=False 不暴露",
        all(d["function"]["name"] != "secret_tool" for d in registry.get_definitions()),
    )
    registry._tools.pop("secret_tool", None)


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


def test_agent_loop():
    client = _FakeClient()
    agent = AgentLoop(client)
    out = agent.run("算 6*7")
    check("分发+跳出", out == "42")
    check("恰好 2 轮", client.calls == 2)


if __name__ == "__main__":
    print("[1] registry 一致性")
    test_registry_consistency()
    print("[2] dispatch 三路径")
    test_dispatch_paths()
    print("[3] check_fn 过滤")
    test_check_fn_filter()
    print("[4] AgentLoop 循环")
    test_agent_loop()
    print("结果: 全部通过" if not fails else f"结果: {len(fails)} 失败")
    sys.exit(1 if fails else 0)
