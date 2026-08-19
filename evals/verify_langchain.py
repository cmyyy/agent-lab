"""verify_langchain.py —— LangChain 版结构验证（离线，不碰网络）。

跑法（在 agent-lab 目录下）：
    .venv/Scripts/python.exe evals/verify_langchain.py

覆盖（FR-1 双实现）：
  1. 工具适配层：registry 6 工具全部转成 StructuredTool（schema 完整）
  2. 工具名一致：LangChain 工具名 == 手写版 schema 名（同一套工具）
  3. 适配层工具调用：直接调工具，返回 JSON 字符串，错误契约不变（永不抛异常）
  4. Agent 构建：LangChainAgent 能构建成功（ChatOpenAI + create_agent 1.0 API）
  5. 对比公平性：默认 temperature=0（与手写版一致）

不碰网络：只构建 agent（不 invoke），工具直接用适配层调用（不走 LLM）。
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
    print("[1] 工具适配层（registry → StructuredTool）")
    from langchain.tool_adapter import get_langchain_tools

    tools = get_langchain_tools()
    check("6 个工具全部转换", len(tools) == 6, f"(={len(tools)})")
    names = {t.name for t in tools}
    check("工具名集合正确", names == {"get_weather", "get_time", "calculator", "search_knowledge", "save_note", "read_note"},
          f"={sorted(names)}")
    check("工具带 description", all(t.description for t in tools))

    print("[2] 适配层工具调用（错误契约）")
    calc = next(t for t in tools if t.name == "calculator")
    r = json.loads(calc.invoke({"expression": "(25 * 1.8) + 32"}))
    check("calculator 正常返回 77.0", r.get("result") == 77.0, f"(={r})")
    r2 = json.loads(calc.invoke({"expression": "__import__('os').system('x')"}))
    check("注入被拒（错误契约）", "error" in r2, f"(={r2})")
    unknown = next(t for t in tools if t.name == "read_note")
    r3 = json.loads(unknown.invoke({"title": "不存在"}))
    check("读不存在笔记返回结构化错误", "error" in r3, f"(={r3})")

    print("[3] Agent 构建（LangChain 1.0 create_agent + ChatOpenAI）")
    from langchain.agent import LangChainAgent

    agent = LangChainAgent()
    check("agent 构建成功", agent.agent is not None)
    check("对比公平性: temperature=0", agent.temperature == 0)

    print("\n结果: 全部通过" if not fails else f"\n结果: {len(fails)} 失败 -> {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
