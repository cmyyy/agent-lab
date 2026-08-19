"""langchain：LangChain/LangGraph 1.0 版 Agent（FR-1.2）。

与 handcrafted/ 共享同一套工具（shared_tools + langchain/tool_adapter.py），
仅替换循环编排——对比叙事成立的前提：同工具、同 model、同 temperature。

设计（对照手写版）：
- 手写版：自己写 while 循环（调 LLM → 分发 → 回填 → 跳出）
- 本版：LangGraph create_agent（1.0 API，替代已弃用的 create_react_agent）
- 工具：tool_adapter.get_langchain_tools()（registry → StructuredTool）

LLM 接入（PRD 架构决策 2）：统一 OpenAI 兼容层（langchain_openai.ChatOpenAI），
不用 langchain-deepseek 的 ChatDeepSeek——自定义 base_url + deepseek-v4-flash
模型名只兼容 OpenAI 兼容端点。
"""

import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from langchain.tool_adapter import get_langchain_tools

load_dotenv()

DEFAULT_SYSTEM_PROMPT = "你是一个能使用工具的智能助手。回答简洁。"


def build_agent(model=None, temperature=0):
    """构建 LangChain agent（1.0 API：langchain.agents.create_agent）。

    对比公平性：与手写版同 model、同 temperature=0（PRD FR-1.3）。
    """
    model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    llm = ChatOpenAI(
        model=model,
        api_key=os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL"),
        temperature=temperature,
        max_tokens=1024,
    )
    return create_agent(llm, get_langchain_tools())


class LangChainAgent:
    """LangChain 版 Agent：与 handcrafted.AgentLoop 同构的接口（run 方法）。

    两版接口对齐（run(user_input, ...)）——共享 eval 的基础（FR-1.4）。
    """

    def __init__(self, model=None, temperature=0):
        self.model = model
        self.temperature = temperature
        self.agent = build_agent(model=model, temperature=temperature)

    def run(self, user_input, system_prompt=DEFAULT_SYSTEM_PROMPT, session_id=None, history=None):
        """执行一轮对话（接口与 handcrafted.AgentLoop.run 对齐）。"""
        messages = [SystemMessage(content=system_prompt)]
        if history:
            messages.extend(history)
        messages.append(HumanMessage(content=user_input))
        result = self.agent.invoke(messages)
        return result["messages"][-1].content
