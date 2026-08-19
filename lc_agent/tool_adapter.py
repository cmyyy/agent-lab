"""工具适配层：shared_tools registry 的 OpenAI function schema → LangChain StructuredTool。

FR-1.3（2026-08-19）：双实现共享同一套工具，但手写版用 OpenAI 原生
function schema（registry.get_definitions()），LangChain 版需要
StructuredTool（pydantic args_schema）。本模块是两版之间的桥。

设计要点：
- 从 registry 的 OpenAI schema dict 动态生成 pydantic 模型（零手写 schema 重复）
- 复用 TOOL_MAP 的实现函数（同一套工具实现，两版行为一致）
- 工具失败仍返回 {"error": ...} 结构化 dict（错误契约不变，永不抛异常）

注意（LangChain 1.0 排坑）：
- pydantic v2：字段名不能用 python 关键字；required 列表外的字段要给默认值
- StructuredTool.from_function 的 args_schema 必须是 pydantic 模型类
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, create_model, Field

from shared_tools import TOOL_MAP, registry


def _build_pydantic_model(tool_name: str, properties: Dict, required: List[str]) -> type[BaseModel]:
    """把 OpenAI function schema 的 properties 转成 pydantic 模型类。

    - required 里的字段：必填（无默认值）
    - 非 required 字段：给默认值 None（pydantic v2 要求非必填必须有默认值）
    - 字段描述从 schema 里带过来（模型能看懂参数含义）
    """
    fields: Dict[str, Any] = {}
    for pname, pdef in (properties or {}).items():
        ptype = pdef.get("type", "string")
        # OpenAI schema type → python 类型（本项目工具只有 string/number）
        pytype = str if ptype == "string" else float if ptype == "number" else Any
        desc = pdef.get("description", "")
        if pname in (required or []):
            fields[pname] = (pytype, Field(description=desc))
        else:
            fields[pname] = (Optional[pytype], Field(default=None, description=desc))
    return create_model(f"{tool_name}Args", **fields)


def _make_langchain_tool(name: str, handler: Callable, schema: Dict):
    """registry 工具 → LangChain StructuredTool（复用 handler，包一层错误契约）。"""
    from langchain_core.tools import StructuredTool

    fn = schema["function"]
    params = fn.get("parameters", {})
    args_model = _build_pydantic_model(name, params.get("properties", {}), params.get("required", []))

    def _safe_handler(**kwargs) -> str:
        # 错误契约不变：永不抛异常，失败返回结构化 dict 的 JSON 字符串
        try:
            result = handler(**{k: v for k, v in kwargs.items() if v is not None})
        except Exception as e:  # pragma: no cover - 兜底（handler 本身已保证不抛）
            result = {"error": f"工具执行失败: {e}"}
        return json.dumps(result, ensure_ascii=False)

    return StructuredTool.from_function(
        func=_safe_handler,
        name=name,
        description=fn.get("description", ""),
        args_schema=args_model,
    )


def get_langchain_tools() -> List[Any]:
    """把 registry 当前暴露的工具（含 check_fn 过滤）转成 LangChain 工具列表。"""
    tools = []
    for t in registry.get_definitions():
        name = t["function"]["name"]
        handler = TOOL_MAP[name]
        tools.append(_make_langchain_tool(name, handler, t))
    return tools
