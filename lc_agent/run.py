"""agent-lab LangChain 版入口：跑与手写版相同的演示场景（对比公平性）。"""

from lc_agent.agent import LangChainAgent

DEMO_CASES = [
    # 场景 1：多工具连续调用（weather -> calculator 链式）——与 handcrafted/run.py 完全相同
    ("北京天气怎么样？拿到摄氏温度后用 摄氏*1.8+32 换算成华氏温度告诉我。", "多工具链"),
    # 场景 2：知识库搜索 + 保存笔记
    ("搜索一下知识库里关于 agent 的介绍，然后保存成一条笔记，标题叫 agent简介。", "搜索+保存"),
    # 场景 3：错误自愈（读不存在的笔记）
    ("读取笔记《不存在的笔记》，如果读不到就告诉我。", "错误自愈"),
]


def main():
    agent = LangChainAgent()
    for prompt, label in DEMO_CASES:
        print(f"\n{'='*60}\n场景: {label}\n提问: {prompt}\n{'='*60}")
        answer = agent.run(prompt)
        print(f"\n最终回答: {answer}")


if __name__ == "__main__":
    main()
