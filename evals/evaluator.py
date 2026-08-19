"""evaluator.py —— DeepEval 语义评估（FR-5，自定义 judge + 可选依赖）。

设计（PRD FR-5，2026-08-19 排坑要点）：
- eval 分层：结构断言（verify_*.py，秒级硬门槛）+ 语义评估（本模块，分钟级相对对比）
- DeepEval 原生 DeepSeekModel 只支持官方端点 + deepseek-chat 模型名；
  自定义 base_url + deepseek-v4-flash 需继承 DeepEvalBaseLLM 写自定义 judge 子类
- 只用代码 API，不用 pytest 插件（避免 Confident AI 账号绑定）
- 弱 judge 模型风险：语义分数只做"两版相对对比"，不做绝对门槛
- 无 deepeval / 无 key → 自动跳过（可选依赖降级）
"""

import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:  # 可选依赖：未安装 deepeval 时降级
    from deepeval.models import DeepEvalBaseLLM

    _DEEPEVAL_AVAILABLE = True
except ImportError:
    _DEEPEVAL_AVAILABLE = False

# 统一 OpenAI 兼容层（PRD 架构决策 2）：不用 langchain-deepseek 的 ChatDeepSeek
from openai import OpenAI


class DeepSeekCustomJudge(DeepEvalBaseLLM):
    """指向自定义 base_url 的 judge 模型（DeepEval × 自定义端点适配）。

    背景：DeepEval 原生 DeepSeekModel 硬编码官方端点 + deepseek-chat 模型名，
    本项目用 deepseek-v4-flash + 自定义 base_url，必须自定义子类。
    """

    def __init__(self, model=None):
        from dotenv import load_dotenv

        load_dotenv()
        self.model_name_ = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url=os.getenv("DEEPSEEK_BASE_URL"),
        )

    def load_model(self):
        return self.client

    def generate(self, prompt: str) -> str:
        resp = self.client.chat.completions.create(
            model=self.model_name_,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        return resp.choices[0].message.content or ""

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)

    def get_model_name(self) -> str:
        return self.model_name_


def semantic_eval_available() -> bool:
    """降级检测：未装 deepeval / 无 DEEPSEEK key → False。"""
    return _DEEPEVAL_AVAILABLE and bool(os.getenv("DEEPSEEK_API_KEY"))


def run_semantic_eval(cases: list[dict], actual_outputs: list[str]) -> dict:
    """跑语义评估（相对对比，不做绝对门槛）。

    Args:
        cases: golden 用例（含 query / expected_fields）
        actual_outputs: 与 cases 等长的实际回答列表

    Returns:
        {"available": bool, "scores": [...], "passed": [...]}
        未装 deepeval 或无 key → {"available": False}（跳过，不崩）
    """
    if not semantic_eval_available():
        return {"available": False}

    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
    from deepeval.test_case import LLMTestCase

    judge = DeepSeekCustomJudge()
    results = []
    for case, output in zip(cases, actual_outputs):
        tc = LLMTestCase(
            input=case["query"],
            actual_output=output,
            # 无参考上下文时 AnswerRelevancy 够用（Faithfulness 需要 context）
        )
        metric = AnswerRelevancyMetric(model=judge)
        try:
            metric.measure(tc)
            results.append({"query": case["query"][:30], "score": metric.score, "passed": metric.is_successful()})
        except Exception as e:
            results.append({"query": case["query"][:30], "score": None, "passed": False, "error": str(e)[:80]})
    return {"available": True, "scores": results}
