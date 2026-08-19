"""shared_tools：6 个共享工具（两个版本共用同一套工具与 schema）。

从 agent-learning/day04-05/weather_agent.py 提取，两个实现版本（handcrafted / langchain）
共用这里的 TOOLS_SCHEMA（给 LLM 的菜单）和 TOOL_MAP（名字 -> 函数），
保证"同一套工具两套实现"的对比成立。

工具清单：
  1. get_weather        查询城市天气（模拟数据）
  2. get_time           查询城市当前时间
  3. calculator         安全执行数学表达式（白名单 + 禁用 __builtins__）
  4. search_knowledge   搜索本地知识库（关键词匹配，后续可升级 RAG）
  5. save_note          保存笔记到 ./notes/
  6. read_note          读取已保存的笔记

设计原则（面试点）：
  - 工具函数永不抛异常：所有错误返回 {"error": "..."} 字典，
    LLM 能读懂结构化错误并自我调整（错误自愈的第一层）
"""
import os


# =====================================================================
# 工具 Schema（给 LLM 看的"菜单"）
# =====================================================================
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气（温度、天气状况、湿度）",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称，如'北京'"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_time",
            "description": "获取指定城市的当前时间",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "执行数学表达式计算",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "数学表达式，如 '(25 * 1.8) + 32'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "搜索本地知识库，查找与关键词相关的内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "搜索关键词"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "保存笔记到本地文件（./notes/ 目录下）",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "笔记标题（将用作文件名）"},
                    "content": {"type": "string", "description": "笔记内容"},
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_note",
            "description": "读取已保存的笔记内容",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "笔记标题（即保存时使用的标题）"}
                },
                "required": ["title"],
            },
        },
    },
]


# =====================================================================
# 工具实现（永远不抛异常，错误转成结构化 dict 回喂给 LLM）
# =====================================================================
def get_weather(city):
    """查询指定城市的天气（模拟数据，实际项目可换真实 API）。"""
    data = {
        "北京": {"temp": 25, "condition": "晴", "humidity": "45%"},
        "上海": {"temp": 28, "condition": "多云", "humidity": "70%"},
        "深圳": {"temp": 32, "condition": "雷阵雨", "humidity": "85%"},
    }
    return data.get(city, {"temp": 20, "condition": "未知", "humidity": "50%"})


def get_time(city):
    """获取指定城市的当前时间（本地系统时间模拟，未做时区换算）。"""
    from datetime import datetime

    return f"{city}当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def calculator(expression):
    """安全执行数学表达式：字符白名单 + 禁用 __builtins__，防注入。"""
    allowed = set("0123456789+-*/().% ^")
    if not all(c in allowed or c.isspace() for c in expression):
        return {"error": "表达式包含不允许的字符"}
    try:
        return {"result": eval(expression, {"__builtins__": {}}, {})}
    except Exception as e:
        return {"error": f"计算失败: {e}"}


def search_knowledge(query):
    """本地知识库关键词搜索（后续升级方向：embedding + 向量库 = RAG）。"""
    kb = {
        "python": "Python由Guido van Rossum于1991年创建，是一种解释型高级语言。",
        "agent": "AI Agent是能自主使用工具完成任务的智能系统。",
        "api": "API定义了软件组件间的交互方式。",
    }
    for k, v in kb.items():
        if k in query.lower():
            return {"results": [v]}
    return {"results": ["未找到相关内容"]}


def save_note(title, content):
    """保存笔记为本地文本文件（./notes/<标题>.txt）。"""
    os.makedirs("./notes", exist_ok=True)
    path = f"./notes/{title}.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return {"status": "ok", "path": path}


def read_note(title):
    """读取已保存的笔记；文件不存在时返回结构化错误（不抛异常）。"""
    path = f"./notes/{title}.txt"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return {"title": title, "content": f.read()}
    return {"error": f"未找到笔记: {title}"}


# 工具名 -> 实现函数的映射（分发表）
TOOL_MAP = {
    "get_weather": get_weather,
    "get_time": get_time,
    "calculator": calculator,
    "search_knowledge": search_knowledge,
    "save_note": save_note,
    "read_note": read_note,
}
