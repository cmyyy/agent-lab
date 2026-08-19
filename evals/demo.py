"""demo.py —— 一键演示入口（M7 面试就绪包）。

用法（在 agent-lab 目录下）：
    python -m evals.demo              # 真实 API（需要 DEEPSEEK_API_KEY）
    python -m evals.demo --mock       # 离线 mock（面试现场/无 key 必跑通）

--mock 模式：fake LLM 客户端按预设脚本返回（先调工具再给答案），
跑 3 个演示场景 + 打印工具调用轨迹——不依赖网络，现场必跑通。

面试点（每场景对应讲什么）：
  场景1 多工具链：weather → calculator 链式（工具结果作为下一轮输入）
  场景2 搜索+保存：工具链 + 副作用工具（RAG 检索注入）
  场景3 错误自愈：结构化错误回喂，模型基于错误调整
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _FakeMsg:
    def __init__(self, tool_calls=None, content=None):
        self.tool_calls = tool_calls
        self.content = content


class _FakeToolCall:
    def __init__(self, id, name, args):
        self.id = id
        self.function = type("F", (), {"name": name, "arguments": args})()


class _MockClient:
    """按场景预设的工具调用序列（离线，0 网络）。"""

    def __init__(self, scenario):
        self.scenario = scenario
        self.calls = 0

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kw):
        self.calls += 1
        if self.scenario == 1:
            seq = [
                [("get_weather", {"city": "北京"})],
                [("calculator", {"expression": "25 * 1.8 + 32"})],
                None,  # 纯文本结束
            ]
        elif self.scenario == 2:
            seq = [
                [("search_knowledge", {"query": "agent"})],
                [("save_note", {"title": "agent简介", "content": "AI Agent 是能自主使用工具的智能系统。"})],
                None,
            ]
        else:  # 3 错误自愈
            seq = [
                [("read_note", {"title": "不存在的笔记"})],
                None,  # 模型基于错误回答
            ]
        if self.calls <= len(seq) and seq[self.calls - 1] is not None:
            tcs = [_FakeToolCall(f"c{i}", n, json.dumps(a)) for i, (n, a) in enumerate(seq[self.calls - 1])]
            return type("R", (), {"choices": [type("C", (), {"message": _FakeMsg(tool_calls=tcs)})]})()
        # 最终回答（按场景给含关键信息的文本）
        final = {
            1: "北京气温25°C，换算成华氏是 77°F。",
            2: "已搜索到 agent 介绍并保存为笔记《agent简介》。",
            3: "笔记《不存在的笔记》不存在，无法读取。",
        }[self.scenario]
        return type("R", (), {"choices": [type("C", (), {"message": _FakeMsg(content=final)})]})()


DEMO_CASES = [
    (1, "北京天气怎么样？拿到摄氏温度后用 摄氏*1.8+32 换算成华氏温度告诉我。", "多工具链"),
    (2, "搜索一下知识库里关于 agent 的介绍，然后保存成一条笔记，标题叫 agent简介。", "搜索+保存"),
    (3, "读取笔记《不存在的笔记》，如果读不到就告诉我。", "错误自愈"),
]


def main():
    mock = "--mock" in sys.argv
    from evals.trace_util import ToolCallRecorder

    if mock:
        print("=== demo（离线 mock 模式，无网络依赖）===\n")
    else:
        import os
        from dotenv import load_dotenv
        from openai import OpenAI

        load_dotenv()

    for idx, prompt, label in DEMO_CASES:
        print(f"{'='*56}\n场景 {idx}: {label}\n提问: {prompt}\n{'='*56}")
        if mock:
            from handcrafted.agent import AgentLoop

            agent = AgentLoop(_MockClient(idx))
        else:
            client = OpenAI(
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=os.getenv("DEEPSEEK_BASE_URL"),
            )
            from handcrafted.agent import AgentLoop

            agent = AgentLoop(client)
        with ToolCallRecorder() as rec:
            answer = agent.run(prompt)
        print(f"  工具调用轨迹: {rec.tool_calls}")
        print(f"  最终回答: {answer}\n")


if __name__ == "__main__":
    main()
