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
    registry.register(_name, _schema, TOOL_MAP[_name])

__all__ = ["registry", "ToolRegistry", "TOOLS_SCHEMA", "TOOL_MAP"]
