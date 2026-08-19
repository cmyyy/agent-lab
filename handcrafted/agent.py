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

from shared_tools import registry


class AgentLoop:
    """手写版 Agent：ToolRegistry + 循环 + 错误自愈第一层。

    错误自愈第一层：工具执行抛异常时，把异常信息转成结构化 dict 喂回 LLM，
    让模型根据错误自行调整（对应 Hermes 的 _sanitize_tool_error 思路）。
    """

    def __init__(self, client, model="deepseek-v4-flash", max_iterations=10):
        self.client = client
        self.model = model
        self.max_iterations = max_iterations
        self.registry = registry

    def run(self, user_input, system_prompt="你是一个能使用工具的智能助手。回答简洁。"):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        for i in range(1, self.max_iterations + 1):
            print(f"\n--- 第 {i} 轮 ---")
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.registry.get_definitions(),
                max_tokens=1024,
            )
            msg = response.choices[0].message

            # 模型没有要求调用工具 = 这就是最终回答
            if not msg.tool_calls:
                return msg.content

            # 模型要求调用工具：把 assistant 消息（含 tool_calls）加进历史
            messages.append(msg)

            for tc in msg.tool_calls:
                name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                print(f"  [工具] {name}({args})")

                # 注册表分发：未知工具 / 异常都在 dispatch 内部转结构化错误
                result = self.registry.dispatch(name, args)

                print(f"  [结果] {result}")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })

        return "达到最大迭代次数，未能完成。"
