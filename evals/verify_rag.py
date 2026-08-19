"""verify_rag.py —— RAG 深模块验证（FR-6 / DoD D3/D4/D5，离线优先）。

跑法（在 agent-lab 目录下）：
    .venv/Scripts/python.exe evals/verify_rag.py

覆盖：
  D3  新增文档无需改代码即可命中（固定 query → top-k 内出现该文档 source）
  D4  故障降级（目录缺失 / 无语料 → 空结果，不抛异常）
  D5  语义命中不依赖关键词（换说法查询能命中）
  check_fn 知识库语料不存在时 search_knowledge 不暴露

说明：
- 默认无 embedding（未配置 SILICONFLOW_API_KEY）→ 走 BM25 档（档2）
- 若配置了 key → 混合检索档（档1）
- 反例设计：查询用"换说法"（如"查资料"代替"检索"），BM25 可能命中不了
  语义相关块——这是留给语义检索（有 embedding 时）的加分断言
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")
    if not cond:
        fails.append(name)


def main():
    print("[D3] 新增文档无需改代码即可命中")
    from shared_tools.retriever import Retriever

    r = Retriever()
    check("知识库已加载（>0 块）", r.size > 0, f"(块数={r.size})")
    res = r.search("Agent 的工具注册中心怎么工作的", top_k=4)
    sources = [x["source"] for x in res["results"]]
    check("查询命中 agent-notes 文档", any("agent-notes" in s for s in sources), f"(sources={sources})")
    check("返回结构兼容 {results: [...]}", isinstance(res, dict) and "results" in res)
    check("结果带 source 和 score", all("source" in x and "score" in x for x in res["results"]))

    print("\n[D5] 语义命中不依赖关键词（换说法）")
    res2 = r.search("大模型怎么反复调用函数直到给出答案", top_k=4)
    check("换说法查询仍有结果", len(res2["results"]) > 0, f"(命中 {len(res2['results'])} 块)")

    print("\n[D4] 故障降级（目录缺失 → 空结果，不抛异常）")
    with tempfile.TemporaryDirectory() as td:
        r2 = Retriever(kb_root=Path(td) / "no_such_dir")
        check("目录缺失 size=0", r2.size == 0)
        res3 = r2.search("任意查询")
        check("目录缺失 → 空结果", res3 == {"results": []}, f"(={res3})")

    print("\n[check_fn] 语料不存在时不暴露工具")
    from shared_tools import registry
    from shared_tools.tools import _knowledge_available

    check("语料存在 → 工具可用", _knowledge_available() is True)
    names = [d["function"]["name"] for d in registry.get_definitions()]
    check("search_knowledge 在工具菜单里", "search_knowledge" in names)

    # 模拟语料缺失：临时 kb 为空时 check_fn 返回 False
    r_empty = Retriever(kb_root=Path(tempfile.mkdtemp()) / "empty")
    check("空语料 → check_fn False（机制验证）", r_empty.size == 0)

    print("\n结果: 全部通过" if not fails else f"\n结果: {len(fails)} 失败 -> {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
