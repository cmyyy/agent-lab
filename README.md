# agent-lab：双实现 Agent 实验室（nano hermes）

同一套 6 个工具，两套实现（手写 vs LangChain），共享 eval 套件——对比两种技术路线的架构差异、调试体验与边界表现。全链路观测（Langfuse）、行为评估（DeepEval）、评估驱动自进化（human-in-the-loop）。详见 [PRD.md](PRD.md)（v1.0）。

## 结构

    agent-lab/
    ├── shared_tools/    6 个共享工具（schema + 实现 + 分发表 + ToolRegistry）
    │   ├── tools.py     工具实现（永不抛异常，错误转结构化 dict）
    │   └── registry.py  ToolRegistry（register / get_definitions / dispatch / check_fn）
    ├── handcrafted/     手写版（纯 OpenAI SDK，不依赖 Agent 框架）
    │   ├── agent.py     AgentLoop：循环 + ToolRegistry + 错误自愈 + LLM 重试
    │   └── run.py       演示入口（3 个场景）
    ├── langchain/       LangChain/LangGraph 1.0 版（复用同一套工具）
    │   ├── tool_adapter.py  registry schema → StructuredTool（工具适配层）
    │   ├── agent.py     create_agent 编排（1.0 API）
    │   └── run.py       演示入口（与手写版相同的 3 个场景）
    ├── evals/           eval 套件（结构断言 + golden 回归）
    │   ├── verify_core.py      手写版结构断言（零依赖秒级，硬门槛）
    │   └── verify_langchain.py LangChain 版结构断言（离线）
    └── README.md

## 运行

    python -m handcrafted.run    # 手写版（需要 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL 在 .env）
    python -m langchain.run      # LangChain 版（需要 langchain>=1.0 已安装）

## 验证

    python evals/verify_core.py         # 手写版：registry/dispatch/循环 断言（离线，秒级）
    python evals/verify_langchain.py    # LangChain 版：适配层/工具契约/agent 构建（离线）

## 6 个工具

| 工具 | 说明 | 升级方向 |
|------|------|---------|
| get_weather | 查天气（模拟数据） | 真实 API（可选加分项） |
| get_time | 当前时间 | 时区库 |
| calculator | 安全计算（白名单+禁 builtins） | — |
| search_knowledge | 关键词搜索 | RAG（语义检索，PRD FR-6） |
| save_note / read_note | 本地笔记读写 | SQLite 记忆（FR-3） |

## 设计溯源（面试用）

每个模块标注了参考的 Hermes 源码位置（22 万+ star 的开源 Agent）：
- 工具 schema -> 模型菜单：参考 model_tools.py 的 get_tool_definitions
- 分发表（TOOL_MAP）：参考 tools/registry.py 的注册模式（简化版）
- 错误自愈第一层：参考 _sanitize_tool_error 思路
- 迭代上限：参考 run_conversation 的 max_iterations 预算
- run(session_id, history)：参考 run_conversation(messages, session_id)（FR-2/3/4 前置）

## 双实现对比（FR-1）

- **同工具**：shared_tools 单一注册中心，两版共用 schema + 实现
- **同模型**：deepseek-v4-flash（统一 OpenAI 兼容层，不用 ChatDeepSeek）
- **同温度**：temperature=0（对比公平性约定，PRD FR-1.3）
- **差异**：仅循环编排（手写 while vs LangGraph create_agent）+ 工具适配层

详见 `docs/architecture-compare.md`（三向对比：手写 vs LangChain vs Hermes，M1 交付）。
