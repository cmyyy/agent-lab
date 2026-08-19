# agent-lab：双实现 Agent 实验室

同一套 6 个工具，两套实现（手写 vs LangChain），共享 eval 套件——对比两种技术路线的架构差异、调试体验与边界表现。

## 结构

    agent-lab/
    ├── shared_tools/    6 个共享工具（schema + 实现 + 分发表）
    │   └── tools.py
    ├── handcrafted/     手写版（纯 OpenAI SDK，不依赖 Agent 框架）
    │   ├── agent.py     AgentLoop：循环 + ToolRegistry + 错误自愈第一层
    │   └── run.py       演示入口（3 个场景）
    ├── langchain/       LangChain 版（待建）
    ├── evals/           eval 套件（待建）
    └── README.md

## 6 个工具

| 工具 | 说明 | 升级方向 |
|------|------|---------|
| get_weather | 查天气（模拟数据） | 真实 API |
| get_time | 当前时间 | 时区库 |
| calculator | 安全计算（白名单+禁 builtins） | — |
| search_knowledge | 关键词搜索 | RAG（embedding+向量库） |
| save_note / read_note | 本地笔记读写 | — |

## 运行

    python -m handcrafted.run     # 需要 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL 在 .env

## 设计溯源（面试用）

每个模块标注了参考的 Hermes 源码位置（22 万+ star 的开源 Agent）：
- 工具 schema -> 模型菜单：参考 model_tools.py 的 get_tool_definitions
- 分发表（TOOL_MAP）：参考 tools/registry.py 的注册模式（简化版）
- 错误自愈第一层：参考 _sanitize_tool_error 思路
- 迭代上限：参考 run_conversation 的 max_iterations 预算
