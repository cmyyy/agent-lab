# PRD：agent-lab — 双实现、可观测、可评估、可进化的 Agent 实验室（nano hermes）

> 状态：v1.0（2026-08-19，三视角头脑风暴整合版）
> 目标读者：项目作者（开发者本人）、Codex 执行会话、面试官
> 定位：nano hermes——同一套工具双实现（手写 / LangChain），全链路观测（Langfuse），
> 行为评估（DeepEval），评估驱动自进化闭环（human-in-the-loop）
> 决策输入：架构师 / 产品经理 / 面试官 三视角审查（2026-08-19）

---

## 1. Problem Statement（问题陈述）

作者正在准备 Agent 方向求职（8/20 投简历、9 月面试），需要一份能同时证明「理解底层机制」与「会用主流框架」的作品。当前 `agent-lab` 只有手写版雏形，存在四个缺口：

1. 知识检索是硬编码关键词匹配：知识库写死在代码里，无法动态扩展，语义相近的提问无法命中；
2. LangChain 版尚未建立，「同一套工具两套实现」的对比叙事不成立；
3. 没有可观测性（每次 LLM 调用与工具调用的成本、延迟、成败）与回归基线，两版差异无法量化；
4. eval 只有结构断言雏形，未达「重构不改语义」的回归基线，也缺少「失败→改进→复测」的闭环。

**面试风险（必须正视）**：对比叙事若没有预期结论 = 为对比而对比（面试官一问即穿）；
叙事超前于现实 = 面试前做不完则整套降级。因此 v1.0 同时定义「完整目标」与「降级路径」。

## 2. Solution（解决方案）

把 `agent-lab` 建成一个共享工具、双实现、可观测、可评估、可进化的 Agent 实验室：

- **同一套 6 工具**：通过单一 ToolRegistry 暴露给两版实现，行为契约一致；
- **双实现**：手写纯 SDK 版（讲原理）+ LangChain/LangGraph 版（接生态），共享 eval；
- **观测**：Langfuse 全链路 trace（会话 / LLM 调用 / 工具调用），可选依赖、无 key 降级；
- **评估**：DeepEval 场景评估（双版本同测 + 相对对比）+ verify_core 结构断言（硬门槛）；
- **自进化**：评估驱动经验闭环（失败入库 → 经验沉淀 → 场景扩充 → 进化报告），human-in-the-loop。

**验收以「可观察行为」为准**：`python evals/verify_core.py` 全绿、三个演示场景跑通
（每场景有最小断言）、新增知识库文档无需改代码即可命中、双版本同一 eval 通过率一致。

## 3. Definition of Done（验收标准，DoD）

每条可自动或半自动验证：

| # | 验收项 | 验证方式 | 可测性 |
|---|--------|---------|--------|
| D1 | verify_core.py 全绿 | `python evals/verify_core.py` exit 0 | ✅ 自动 |
| D2 | 3 个演示场景跑通（含最小断言） | 场景2：notes/ 文件存在且含关键内容；场景3：回答含"不存在"类措辞 | ✅ 自动/半自动 |
| D3 | 新增知识库文档无需改代码即可命中 | 固定 query，断言 top-k 内出现该文档 source | ✅ 自动 |
| D4 | 故障降级（目录缺失/embedding 不可用 → 结构化错误） | 自动化进 verify_core | ✅ 自动 |
| D5 | 语义命中不依赖关键词 | 固定 query 固定断言（含反例：关键词无关但语义相关） | ✅ 自动 |
| D6 | 双版本同一 eval 通过率一致（差异 ≤ 1 场景） | 同一 golden 集两版各跑，对比 | ✅ 自动 |
| D7 | 观测可产出两版对比表（token/延迟/成败） | 脚本从 SQLite/Langfuse 出表 | ✅ 自动 |
| D8 | 自进化最小闭环可用 | 失败入库 → 经验沉淀 → 复测通过 → 报告显示失败数变化 | ✅ 自动+人工确认 |
| D9 | 面试就绪：README 三分钟讲法 + demo 一键跑通（含 --mock） | 面试官视角验收 | 半自动 |
| D10 | 未配置 Langfuse/DeepEval key 时项目照常运行 | 降级验证（key 不存在 + key 无效两种情况） | ✅ 自动 |

## 4. 功能需求（FR）

### FR-1 双实现（手写版 / LangChain 版共享工具）

**目标**：同一套 6 工具两种实现，对比叙事成立且有数据支撑。

**子项**：
- FR-1.1 手写版加固：保留 AgentLoop 核心，补 LLM 调用重试（指数退避 + jitter，2-3 次）
- FR-1.2 LangChain 版：LangGraph/LangChain 1.0，复用 shared_tools，工具适配层（registry schema → StructuredTool）
- FR-1.3 对比公平性约定：**同一 system prompt、同一模型、temperature=0**（叙事成立的前提）
- FR-1.4 对比文档：`docs/architecture-compare.md` 三向对比（手写 vs LangChain vs Hermes），每模块标注 Hermes 源码位置

**验收**：D6 + D9。**工时**：12-20h。**面试价值**：★★★（核心叙事）

**关键技术约束（2026-08-19 核实）**：
- LangChain/LangGraph 已发布 1.0，API 大改：`create_react_agent` 已弃用（prompt= 参数消失），迁到 `langchain.agents.create_agent`；旧功能拆进 `langchain-classic`。**网上 2024 年教程全部过时**。锁版本 `langchain>=1.0, langgraph>=1.0`，Python 3.10+
- 工具适配层是核心工作量：registry 的 OpenAI 格式 function schema dict → `StructuredTool.from_function`（pydantic v2 字段命名坑）
- LLM 接入**统一走 OpenAI 兼容层**（`langchain_openai.ChatOpenAI(model="deepseek-v4-flash", base_url=..., api_key=...)`），**不用 langchain-deepseek 的 ChatDeepSeek**（它面向官方端点，自定义 base_url/模型名不兼容）
- 手写版用 openai SDK、LangChain 版用 ChatOpenAI，两路径同构，观测/对比顺

### FR-2 上下文管理（轻量版）

**目标**：长对话不爆上下文。**轻量实现**：滑动窗口（保 system + 最近 N 条）+ token 计数 + 工具结果截断（超限截断 + 提示"结果已截断"）。

**明确不做（v1.0）**：总结式压缩（summarization）——复杂度高、效果难验证、面试收益低，标注"对照 Hermes ContextCompressor 的后续项"。

**最高杠杆前置改动**：`AgentLoop.run(user_input)` → `run(user_input, session_id=None, history=None)`（允许传入既有消息历史）。FR-3 记忆、FR-4 观测、多轮对话全靠这一个签名。**现在改是 5 分钟，FR-3 落地时改是重构**。对齐 Hermes `run_conversation(messages, session_id)`。

**验收**：长对话（>窗口）不崩、工具结果超限被截断。**工时**：6-10h。**面试价值**：★★

### FR-3 SQLite 记忆

**目标**：会话历史 + 笔记持久化，跨会话可用。

**设计**：
- 纯 `sqlite3` 标准库零依赖
- 记忆（应用数据）与观测（遥测数据）**同一 agent.db 不同 schema 分组**（一份库、两套语义）
- v1.0 用结构化查询（按时间/标签），**不上 embedding 记忆检索**（与 FR-6 重复造轮子）
- 经验表预留 `status` 字段（pending/approved）——FR-7 直接复用，避免二次迁移
- save_note/read_note 的相对路径 bug：`./notes` 从不同 cwd 运行会写到不同位置 → 改项目根锚定路径

**验收**：跨会话读回笔记、经验表可查。**工时**：8-12h。**面试价值**：★★

### FR-4 Langfuse 观测（面试前必达）

**目标**：全链路可观测，两版差异可量化。

**设计**：
- **不自托管**（Docker+Postgres+ClickHouse 太重），用免费托管层
- trace 命名契约提前定义：`trace = 会话`，`observation = LLM 调用 / 工具调用`，两版统一命名——这是"量化两版差异"的数据底座
- 手写版：client 包装（零侵入 AgentLoop）；LangChain 版：优先官方 `langfuse.callback_handler.CallbackHandler`（不侵入图结构，面试加分）；排坑超时退路 = LangChain 版也包装 ChatModel
- 可选依赖降级：`try/except import` + env 检查 + NullTracer 单例；**降级测试要覆盖"key 不存在"和"key 存在但无效"两种情况**（后者 Langfuse 可能打警告不崩）

**观测→决策闭环（面试点）**：至少承诺一个由数据驱动的决策（如调 top_k、改写工具 description、砍掉一个工具）——没有"观测→决策"的观测是摆设。

**验收**：D7 + D10。**工时**：6-10h。**面试价值**：★★★

### FR-5 DeepEval 评估（面试前必达）

**目标**：语义层评估 + 双版本一致性量化。

**设计**：
- **eval 分层**（关键设计）：
  - `evals/structural`：verify_core 延续——零依赖、秒级、**硬门槛**（结构断言：工具是否暴露、循环轮数、错误契约）
  - `evals/semantic`：DeepEval——可选依赖、分钟级、**只做相对对比**（两版相对、改动前后相对），不设绝对门槛
- golden 用例独立文件 `evals/golden_cases.json`：`{query, expected_tools, expected_fields}`，版本化，≥10 条（含反例）
- DeepEval × DeepSeek 兼容性（2026-08-19 核实）：原生 `DeepSeekModel` 只支持官方端点 + `deepseek-chat`/`deepseek-reasoner`；自定义 `deepseek-v4-flash` + base_url 需**继承 `DeepEvalBaseLLM` 写自定义 judge 子类**（约 30 行，封装 openai SDK）——这是 FR-5 排坑大头，工时已计入
- **只用 DeepEval 代码 API，不用 pytest 插件**（避免 Confident AI 账号绑定）
- 弱 judge 模型风险（flash 级）：分数方差大、绝对值不可信 → 语义分数只做相对对比，硬门槛由结构断言承担
- 语义 eval 是分钟级慢测试，与秒级结构 eval 分开跑（每次改动跑结构，语义定时跑）

**验收**：D6（双版本一致率）+ D5。**工时**：10-16h。**面试价值**：★★★

### FR-6 工具升级 RAG

**目标**：search_knowledge 从关键词匹配升级为语义检索（深模块）。

**设计**：
- **深模块**：对外只暴露 `search(query, top_k) → results`，内部封装文档加载/切块/embedding/检索
- **三档降级链**（关键设计，解决"embedding 离线怎么来"）：
  1. 在线 embedding（SiliconFlow API，bge 系中文模型）
  2. 本地 numpy 向量检索（在线 embedding 结果缓存复用）
  3. 完全离线 → 纯 n-gram/字符相似度检索（stdlib 20 行）
  每档接入 check_fn——embedding 不可用时工具降级暴露或隐藏
- **中文切块**：按句子边界（。！？换行）切块，超长段才按长度二次切——按长度硬切必切碎中文
- 返回结构兼容 `{"results": [...]}`，每项含 text/source（文件名+块序号）/score；统一"未命中"（空 results）与"错误"契约
- 与 PRD 原决策的关系：**RAG 是优先深模块，但双实现先行建立对比基线，RAG 排第二里程碑**（FR 编号不变，只调里程碑序）

**验收**：D3 + D5（语义命中反例）。**工时**：15-25h（依赖链最长）。**面试价值**：★★★

### FR-7 自进化（评估驱动经验闭环，human-in-the-loop）

**目标**：失败被记录、教训被沉淀、场景被扩充、复测证明有效。

**闭环链路**：
```
DeepEval 评估 → 发现失败场景
  → 失败样本入库（evals/failures/，含 query/期望/实际/工具调用链/trace 链接）
  → 经验沉淀（agent.db 经验表，{pattern, solution, source_evidence}，status=pending）
  → 终端人工审批（y/n 确认，human-in-the-loop 硬边界）
  → 审批通过 → 经验转 golden 用例 / 场景扩充（proposed_scenarios.py → 人工 review → scenarios.py）
  → 重跑评估 → 进化报告（两次 eval 运行对比 + 用例数增长）
```

**明确不做（Out of Scope）**：自动改 prompt/代码、经验自动注入 system prompt、审批 UI（终端 y/n 即可）、embedding 记忆检索。

**诚实边界**：进化报告**不承诺"能力提升 X%"**（2 周样本量不足 + LLM 非确定性下必然造假或不可复现），降到"两次 eval 运行对比 + 用例数增长"。

**验收**：D8。**工时**：10-16h（最小闭环）。**面试价值**：★★★（讲得清是亮点，讲不清是扣分项）

## 5. 架构决策

1. **版本锁定**：LangChain/LangGraph 1.0，Python 3.10+；requirements 分 core/optional 两层（optional = langchain、langfuse、deepeval）——落实"可选依赖降级"
2. **LLM 接入统一 OpenAI 兼容层**：provider 集中 `llm.py`，禁用 ChatDeepSeek（自定义端点不兼容）
3. **工具适配层**：registry schema → LangChain StructuredTool（FR-1 核心工作量，显式规划）
4. **Langfuse 不自托管**；trace 命名契约（trace=session，observation=llm/tool）；两版观测路径（手写 client 包装 / LangChain callback handler）
5. **eval 分层**：structural（硬门槛秒级）+ semantic（相对对比分钟级）
6. **run() 签名 session 化**：`run(user_input, session_id=None, history=None)`（FR-2/3/4 前置）
7. **为什么用 Python 不用 Java/Spring AI**：生态先行（DeepEval/Langfuse/Hermes 都是 Python），Java 线走另一条求职轨（已有 5 年经验无需证明编码能力，LLM 集成能力语言无关）
8. **配置集中化**：.env 读取 + 降级开关集中到 `config.py`（LANGFUSE_ENABLED / DEEPSEEK_* / SILICONFLOW_*）
9. **日志 vs print**：手写版 agent.py 的 print 统一改 logging（观测层从 logger 取数，避免后期全局替换）

## 6. 里程碑（按 8/20 投简历倒排，每周 15-20h）

| 里程碑 | 内容 | 工时 | 面试前定位 |
|--------|------|------|-----------|
| M1 | FR-1 双实现 + 工具适配层 + 对比公平性 + 三向对比文档起步 | 12-20h | ✅ 必达（1-1.5 周） |
| M2 | FR-6 RAG（深模块 + 三档降级 + 中文切块）| 15-25h | ✅ 必达（提前排） |
| M3 | FR-2 上下文轻量版 + run() session 化 | 6-10h | ✅ 必达 |
| M4 | FR-4 Langfuse 观测 + 对比报告脚本 | 6-10h | ✅ 必达 |
| M5 | FR-5 DeepEval（自定义 judge + golden 用例集）| 10-16h | ✅ 必达 |
| M6 | FR-3 SQLite 记忆 + FR-7 自进化最小闭环 | 18-28h | ✅ 必达（合并推进） |
| M7 | 面试就绪包（README 三分钟讲法 + demo --mock + 叙事文档 + 风险降级预案）| 6-10h | ✅ 必达 |

> 排序逻辑：双实现 + RAG 是叙事核心先行；观测/评估紧随（面试官要数字）；自进化最后（最小闭环）。
> 每个里程碑"完成 = 验收命令可跑"（DoD 对应项）。

## 7. Out of Scope（范围外）

- 真实天气/时区 API 接入（改可选加分项：接一个免费额度真实 API 是最便宜的工程说服力）
- Web 前端、聊天界面、多模态与语音
- 重型向量数据库生产化部署；Langfuse 自托管
- 上下文总结式压缩（标注为 Hermes ContextCompressor 后续项）
- 自进化的自动改代码 / 经验自动注入 / 审批 UI
- 记忆的 embedding 检索（v1.0 用结构化查询）
- Spring AI / Java 实现线（另一条求职轨）
- Hermes 全量能力复制：多 Agent 协作、插件动态发现、20+ 平台网关

## 8. 面试叙事（Interview Narrative）

### 8.1 电梯演讲（30 秒）

> "我把同一套 6 工具的 Agent 用两种方式实现：手写纯 SDK 版讲得清每个设计决策（对应 Hermes 源码），LangChain 版证明我能接生态。两版共用 DeepEval 场景评估，跑同一批 golden 测试——通过率一致，证明框架只是实现细节、行为才是契约。全部调用链接 Langfuse 可复盘，评估发现的失败自动沉淀经验、同类问题下次不再犯。"

### 8.2 双实现对比的预期结论（必须立住，否则 Q1 击穿）

实现后用真实数据填充，方向承诺：
1. **框架在 30 行循环上是过度设计**——LangGraph 状态机对手写版能跑通的规模，样板代码 > 收益
2. **框架价值在生态与边界情况**——工具适配层、callback handler、错误传播路径是框架替你做好的部分
3. **手写版 token 更省、LangChain 版容错更全**——用观测数据（token/延迟/轮数）量化差异
4. **选型判断**：什么规模/团队/约束下选框架 vs 裸写（明确立场，不说"都行"）

### 8.3 Hermes 深度洞察清单（5 条，每条能展开 2 分钟）

1. 为什么 Hermes 主循环 2/3 是容错恢复（重试/退避/fallback/压缩）——个人项目砍了哪些、为什么
2. ToolRegistry 的 toolset 分组解决什么问题（平台/场景收窄）
3. check_fn 可用性过滤（模型看不到 = 不会幻觉调用）
4. 上下文压缩的设计权衡（threshold/protect_first_n/目标比例）
5. 为什么 run_conversation 带 session_id（观测/记忆/多轮的前置）

### 8.4 降级路径（面试前做不完的预案）

- 若 LangChain 版未完成 → 叙事降级为"手写版 + 框架调研笔记 + 适配层设计文档"
- 若 RAG 未完成 → 降级为"关键词版 + 深模块设计文档"
- 若观测/评估未完成 → 降级为"设计 + 最小 SQLite 记录"
- 降级叙事仍然完整：**每个功能有"30 秒讲法 + 10 分钟演示"才算完成，否则白做**

### 8.5 Java 岗翻译（5 年工程肌肉的差异化）

- ToolRegistry ≈ SPI / 服务注册发现；check_fn ≈ @ConditionalOnXxx 特性开关
- 永不抛异常 + 结构化错误 ≈ 防腐层 + 错误码约定（"异常 vs 错误码"是 Java 架构老话题，有明确立场）
- golden eval 只断言外部行为 ≈ 契约测试 / Pact（重构安全网）
- Langfuse trace ≈ 全链路追踪（trace_id ↔ conversation_id）
- 手写 vs LangChain ≈ 原生 JDBC vs Spring 的框架选型判断
- 一句话立场："框架负责编排、我负责边界——注册中心、错误契约、回归测试这三件事框架替我做不了，这才是工程师的位置。"

## 9. 技术风险登记（Top 5）

| # | 风险 | 影响 | 缓解 |
|---|------|------|------|
| 1 | LangChain/LangGraph 1.0 API 大改（2024 教程全过时） | M1 排坑时间被低估 2-3 倍 | 锁版本；只跟官方 docs；PRD 已锁 `>=1.0` |
| 2 | deepseek-v4-flash + 自定义 base_url 与生态工具不兼容 | FR-1/FR-5 两线可能卡住 | 统一 OpenAI 兼容层；DeepEval 自定义 judge 子类；不用 with_structured_output（DeepSeek 已知 bug #29282） |
| 3 | 弱 judge 模型评估噪声 | 语义分数误导决策 | eval 分层：结构断言=硬门槛，语义=相对对比 |
| 4 | RAG 依赖链最长（SiliconFlow 限流 + 中文切块 + 降级链） | M2 翻车概率最高 | embedding 抽象先行；切块器离线独立验证；三档降级链 |
| 5 | 排期 vs 9 月面试（必达项多） | 面试时叙事不完整 | 里程碑按面试价值排序；每 M 验收命令可跑；降级路径已定义 |

## 10. 已知局限（面试自曝）

- 中文 embedding 质量：SiliconFlow bge 系对中文效果优于通用模型，但切块边界仍可能碎语义
- 关键词残留：降级链第 3 档（n-gram）会退化成类关键词匹配
- 语义命中 vs 关键词命中：语料小时统计上分不出差别——用固定反例 query 演示（关键词搜不到、语义能搜到）
- 6 工具是 toy：真实 API 是可选加分项，不阻塞核心叙事
