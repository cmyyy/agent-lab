"""shared_tools 包：6 个共享工具，两个实现版本共用。

统一入口：registry（ToolRegistry 单例）——所有版本（handcrafted / langchain）
都从 registry.get_definitions() 拿 schema、registry.dispatch() 分发工具，
保证"同一套工具两套实现"的对比成立。

向后兼容：TOOLS_SCHEMA / TOOL_MAP 保留导出（等价于 registry 的内容）。
"""

from .registry import ToolRegistry, registry
from .tools import (
    TOOLS_SCHEMA,
    TOOL_MAP,
    calculator,
    get_time,
    get_weather,
    read_note,
    save_note,
    search_knowledge,
)

# 把 6 个工具注册进 registry（schema 与 handler 配对登记，对标 Hermes 源码末尾的
# registry.register(name=..., toolset=..., schema=..., handler=..., check_fn=...) 模式）
for _schema in TOOLS_SCHEMA:
    _name = _schema["function"]["name"]
    # search_knowledge 依赖知识库语料：无语料时不暴露（check_fn，模型看不到=不会幻觉调用）
    _check_fn = None
    if _name == "search_knowledge":
        from .tools import _knowledge_available

        _check_fn = _knowledge_available
    registry.register(_name, _schema, TOOL_MAP[_name], check_fn=_check_fn)

__all__ = ["registry", "ToolRegistry", "TOOLS_SCHEMA", "TOOL_MAP"]
