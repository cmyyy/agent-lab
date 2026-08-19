"""verify_dual.py —— 双版本真实 API 同测（FR-1.4 / DoD D6）。

跑法（在 agent-lab 目录下，需要 .env 有 DEEPSEEK_API_KEY）：
    .venv/Scripts/python.exe evals/verify_dual.py [--quick]

输出：每个 golden 用例两版的 工具调用序列 + 回答字段命中，最后给一致率。

注意：
- 真实 API 调用，8 用例 × 2 版 ≈ 16 次 agent 运行（分钟级）
- 成本约几分钱（deepseek-v4-flash）
- --quick 只跑前 4 个用例（快速冒烟）
"""

import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from evals.golden_cases import GOLDEN_CASES
from evals.trace_util import ToolCallRecorder


def run_case(agent_cls, query):
    """跑单个用例，返回 (工具调用序列, 最终回答)。"""
    agent = agent_cls()
    with ToolCallRecorder() as rec:
        answer = agent.run(query)
    return rec.tool_calls, answer


def check_case(tools_actual, answer, case):
    """断言：工具序列包含期望工具 + 回答包含期望字段。返回 (工具命中, 字段命中)。"""
    expected_tools = case["expected_tools"]
    tools_hit = all(t in tools_actual for t in expected_tools)
    fields = case["expected_fields"]
    if not fields:
        fields_hit = True
    else:
        fields_hit = any(f in (answer or "") for f in fields)
    return tools_hit, fields_hit


def main():
    quick = "--quick" in sys.argv
    cases = GOLDEN_CASES[:4] if quick else GOLDEN_CASES

    from handcrafted.agent import AgentLoop
    from lc_agent.agent import LangChainAgent
    from openai import OpenAI
    import os
    from dotenv import load_dotenv

    load_dotenv()
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
    )

    def make_handcrafted():
        return AgentLoop(client)

    print(f"双版本真实 API 同测（{len(cases)} 用例 × 2 版）\n")
    results = {"手写版": {"tools": 0, "fields": 0, "total": 0},
               "LangChain": {"tools": 0, "fields": 0, "total": 0}}
    mismatches = []

    for i, case in enumerate(cases, 1):
        q = case["query"][:30] + ("..." if len(case["query"]) > 30 else "")
        print(f"--- 用例 {i}: {q} ---")

        for label, cls in (("手写版", make_handcrafted), ("LangChain", LangChainAgent)):
            try:
                tools, answer = run_case(cls, case["query"])
                th, fh = check_case(tools, answer, case)
                results[label]["total"] += 1
                results[label]["tools"] += 1 if th else 0
                results[label]["fields"] += 1 if fh else 0
                status = "✅" if (th and fh) else "❌"
                print(f"  {label}: {status} 工具序列={tools} 期望={case['expected_tools']} "
                      f"字段命中={fh} 期望字段={case['expected_fields']}")
                if not (th and fh):
                    mismatches.append((label, case["query"][:40], tools, (answer or "")[:60]))
            except Exception as e:
                print(f"  {label}: 💥 异常 {e}")
                mismatches.append((label, case["query"][:40], "EXC", str(e)[:60]))

    print("\n" + "=" * 50)
    print("一致率汇总：")
    for label in ("手写版", "LangChain"):
        r = results[label]
        tt = r["tools"] / r["total"] * 100 if r["total"] else 0
        tf = r["fields"] / r["total"] * 100 if r["total"] else 0
        print(f"  {label}: 工具命中 {r['tools']}/{r['total']} ({tt:.0f}%)  字段命中 {r['fields']}/{r['total']} ({tf:.0f}%)")

    # D6 验收：两版差异 ≤ 1 场景（用字段命中率近似行为一致）
    diff = abs(results["手写版"]["fields"] - results["LangChain"]["fields"])
    print(f"\n两版字段命中差异: {diff} 个场景（D6 验收线：≤1）")
    if mismatches:
        print("\n未通过用例：")
        for m in mismatches:
            print(f"  {m[0]} | {m[1]} | 工具={m[2]} | 回答={m[3]}")
    ok = diff <= 1 and not mismatches
    print("\n结果: 双版本一致 ✅" if ok else "\n结果: 有差异 ❌")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
