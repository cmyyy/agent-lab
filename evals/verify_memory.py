"""verify_memory.py —— FR-3 记忆 + FR-7 自进化最小闭环验证（离线，临时 DB）。

跑法（在 agent-lab 目录下）：
    .venv/Scripts/python.exe evals/verify_memory.py

覆盖：
  FR-3：笔记读写（SQLite 落点）/ 会话 upsert / 消息持久化 + 读回
  FR-7：经验表 status 流转（pending → approved）/ 最小闭环（失败入库 → 审批 → 复用）
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import shared_tools.memory as mem

fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")
    if not cond:
        fails.append(name)


def main():
    # 用临时 DB（不污染项目 agent.db）
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    mem.init_db(db_path=tmp)

    print("[FR-3] 笔记读写（SQLite 落点）")
    r = mem.save_note("测试笔记", "这是内容")
    check("保存成功", r.get("status") == "ok", f"(={r})")
    r2 = mem.read_note("测试笔记")
    check("读回内容一致", r2.get("content") == "这是内容")
    r3 = mem.read_note("不存在")
    check("读不存在 → 结构化错误", "error" in r3)

    print("[FR-3] 会话 + 消息持久化")
    mem.upsert_session("sess-test-1")
    mem.append_message("sess-test-1", "user", "你好")
    mem.append_message("sess-test-1", "assistant", "你好！")
    hist = mem.load_history("sess-test-1")
    check("消息读回 2 条", len(hist) == 2, f"(={len(hist)})")
    check("顺序正确", hist[0]["role"] == "user" and hist[1]["role"] == "assistant")
    hist2 = mem.load_history("sess-other")
    check("其他会话历史为空", hist2 == [])

    print("[FR-7] 经验表 + 最小闭环")
    eid = mem.add_experience("calculator 注入被拦截", "白名单校验失败时返回结构化错误", "verify_core 用例5")
    check("经验入库（默认 pending）", eid > 0)
    mem.approve_experience(eid)
    exps = mem.get_approved_experiences()
    check("审批后经验可读", len(exps) == 1 and exps[0]["pattern"].startswith("calculator"))
    check("未审批的经验不返回", all("未审批" not in e["pattern"] for e in exps))

    # 最小闭环：失败 → 入库 → 审批 → 可复用（模拟 FR-7 链路）
    mem.add_experience("未审批样例", "不应出现在 approved", "demo")
    exps2 = mem.get_approved_experiences()
    check("闭环：只返回 approved", len(exps2) == 1)

    # 清理
    tmp.unlink(missing_ok=True)
    print("\n结果: 全部通过" if not fails else f"\n结果: {len(fails)} 失败 -> {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
