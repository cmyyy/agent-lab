"""verify_semantic.py —— FR-5 DeepEval 语义评估（真实 LLM judge）。

跑法（在 agent-lab 目录下，需要 DEEPSEEK_API_KEY）：
    .venv/Scripts/python.exe evals/verify_semantic.py [--quick]

覆盖：
  - judge 子类（DeepSeekCustomJudge）真实生成
  - 语义评估：golden 用例 × 回答 → AnswerRelevancy 分数
  - 相对对比原则：不做绝对门槛，只看分数可产出

注意：分钟级（每次 metric 调 judge LLM），--quick 只跑 2 个用例。
弱 judge 模型风险：分数只做相对对比（PRD FR-5）。
"""

import os
import sys

sys.path.insert(0, str(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

fails = []


def check(name, cond, extra=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name} {extra}")
    if not cond:
        fails.append(name)


def main():
    quick = "--quick" in sys.argv
    from dotenv import load_dotenv

    load_dotenv()
    from evals.evaluator import semantic_eval_available, DeepSeekCustomJudge, run_semantic_eval

    print("[1] 降级检测")
    check("DEEPSEEK key 存在 → 可用", semantic_eval_available() is True)

    print("[2] judge 子类真实生成（自定义端点适配）")
    j = DeepSeekCustomJudge()
    r = j.generate("用一句话回答：2+2 等于几？")
    check("judge 生成非空", bool(r and r.strip()), f"(={r[:30]})")

    print("[3] 语义评估（真实 LLM judge）")
    if quick:
        cases = [
            {"query": "计算 25 乘以 1.8 再加 32 等于多少？", "expected_fields": ["77"]},
            {"query": "北京天气怎么样？", "expected_fields": ["北京"]},
        ]
        actual = ["77", "北京气温25摄氏度"]
    else:
        from evals.golden_cases import GOLDEN_CASES

        cases = GOLDEN_CASES
        actual = ["77", "已保存笔记《agent简介》", "笔记不存在", "77", "不允许", "你好", "现在时间", "上海和深圳天气"]
    res = run_semantic_eval(cases, actual)
    check("评估可产出", res.get("available") is True)
    scores = res.get("scores", [])
    check("分数已计算（非 None）", all(s["score"] is not None for s in scores), f"(共 {len(scores)} 条)")
    avg = sum(s["score"] or 0 for s in scores) / max(1, len(scores))
    print(f"  平均分: {avg:.2f}（相对对比参考，不做绝对门槛）")

    print("\n结果: 全部通过" if not fails else f"\n结果: {len(fails)} 失败 -> {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
