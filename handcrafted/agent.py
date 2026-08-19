"""handcrafted：手写版 Agent 循环（纯 OpenAI SDK，不依赖 Agent 框架）。

从 agent-learning/day09/react_agent_native.py 演化而来，接上 shared_tools 的
6 个工具。核心循环只有 3 件事，面试 30 秒能讲清：

    while 循环:
        1. 调 LLM（带上工具菜单 TOOLS_SCHEMA）
        2. 若模型返回 tool_calls → 逐个执行工具 → 结果回填成 tool 消息 → 回到 1
        3. 若模型返回纯文本 → 这就是最终回答，跳出循环

设计取舍（对照 Hermes 的 run_conversation）：
  - Hermes 5800 行主循环里 2/3 是容错恢复；这里只保留最基本的
    try/except 兜底 + 迭代上限，其余容错（重试/退避/fallback/压缩）
    是后续加固阶段（Day 10-11）的目标，先在注释里标注出处。
"""
import json
import logging
import random
import time

from shared_tools import registry

logger = logging.getLogger(__name__)


class AgentLoop:
    """手写版 Agent：ToolRegistry + 循环 + 错误自愈第一层。

    错误自愈第一层：工具执行抛异常时，把异常信息转成结构化 dict 喂回 LLM，
    让模型根据错误自行调整（对应 Hermes 的 _sanitize_tool_error 思路）。
    """

    def __init__(self, client, model="deepseek-v4-flash", max_iterations=10, temperature=0, max_retries=3, max_context_messages=20):
        self.client = client
        self.model = model
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.max_retries = max_retries
        self.max_context_messages = max_context_messages  # FR-2 滑动窗口大小
        self.registry = registry

    def _llm_call(self, messages):
        """带重试的 LLM 调用：指数退避 + jitter（FR-1.1，2026-08-19）。

        调用层容错（区别于工具层）：LLM API 失败（网络/429/超时）重试，
        最多 max_retries 次；工具失败不走这里（那是 registry.dispatch 的
        结构化错误回喂）。面试点：两种重试的语义不同——LLM 调用重试要幂等
        （同一 messages 重发），工具调用重试要小心副作用。
        """
        for attempt in range(1, self.max_retries + 1):
            try:
                return self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.registry.get_definitions(),
                    max_tokens=1024,
                    temperature=self.temperature,
                )
            except Exception as e:
                if attempt >= self.max_retries:
                    raise
                # 指数退避 + jitter：0.5s * 2^(attempt-1) 附近随机 ±30%
                base = 0.5 * (2 ** (attempt - 1))
                sleep = base * random.uniform(0.7, 1.3)
                logger.warning("LLM 调用失败（第 %d/%d 次）：%s，%.2fs 后重试", attempt, self.max_retries, e, sleep)
                time.sleep(sleep)

    def run(self, user_input, system_prompt="你是一个能使用工具的智能助手。回答简洁。", session_id=None, history=None):
        """执行一轮对话。

        Args:
            user_input: 本轮用户输入
            system_prompt: 系统提示词
            session_id: 会话标识（FR-3 记忆 / FR-4 观测按会话归组的前置，2026-08-19）
            history: 既有消息历史（多轮对话 / 恢复会话用；None 则从零开始）

        session_id / history 是本项目 FR-2/3/4 的前置签名（PRD 架构决策 6，
        对齐 Hermes run_conversation(messages, session_id) 设计）。
        不传时行为与旧版完全一致（verify_core 兼容）。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        if history:
            # 既有历史在前，本轮输入追加在尾部（保持 role 交替合法）
            messages = list(history) + [{"role": "user", "content": user_input}]

        for i in range(1, self.max_iterations + 1):
            # FR-2 上下文管理（轻量版）：滑动窗口 + 截断，防长对话爆窗口
            from shared_tools.context import apply_sliding_window, apply_message_truncation

            windowed = apply_sliding_window(messages, system_prompt, max_messages=self.max_context_messages)
            windowed = apply_message_truncation(windowed)
            logger.info("第 %d 轮：调 LLM（模型=%s，窗口内消息=%d，总 token≈%d）",
                        i, self.model, len(windowed),
                        sum(len(str(m.get("content", ""))) for m in windowed))
            response = self._llm_call(windowed)
            msg = response.choices[0].message

            # 模型没有要求调用工具 = 这就是最终回答
            if not msg.tool_calls:
                logger.info("模型返回纯文本，跳出循环（第 %d 轮）", i)
                return msg.content

            # 模型要求调用工具：把 assistant 消息（含 tool_calls）加进历史
            # 统一转 dict（真实 client 返回 pydantic 对象、fake 返回自定义对象，
            # 滑动窗口/截断只认 dict——FR-2 前置）
            try:
                messages.append(msg.model_dump())
            except AttributeError:
                messages.append({
                    "role": "assistant",
                    "content": getattr(msg, "content", None),
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in (msg.tool_calls or [])
                    ],
                })

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                logger.info("  [工具] %s(%s)", name, args)

                # 注册表分发：未知工具 / 异常都在 dispatch 内部转结构化错误
                result = self.registry.dispatch(name, args)

                logger.info("  [结果] %s", result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        return "达到最大迭代次数，未能完成。"
