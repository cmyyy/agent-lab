"""ToolRegistry：工具注册与分发中心（对标 Hermes tools/registry.py 的简化版）。

Hermes 的 registry 做什么（面试对照）：
  - register(name, toolset, schema, handler, check_fn)：工具在源码末尾配对登记
  - get_definitions()：按启用的 toolset + check_fn 过滤，产出给 LLM 的 schema 列表
  - 分发时按名字找 handler 执行

本版精简点（面试要能讲清"为什么简化"）：
  - 无 toolset 分组：6 个工具不需要"平台/场景收窄"，全量暴露
  - check_fn 保留：未来"依赖没装就不暴露该工具"（如 RAG 需要向量库）直接复用此机制
  - 多 Agent/插件发现（扫描目录动态加载）是 Hermes 为插件生态设计的，个人项目用不上

设计原则：
  - 工具永不抛异常：所有错误转 {"error": "..."} 结构化 dict 回喂 LLM（错误自愈第一层）
"""


class ToolRegistry:
    def __init__(self):
        self._tools = {}  # name -> {"schema": dict, "handler": callable, "check_fn": callable|None}

    def register(self, name, schema, handler, check_fn=None):
        """登记一个工具：schema（给 LLM 的菜单）+ handler（实现函数）+ 可选 check_fn（可用性检查）。"""
        self._tools[name] = {
            "schema": schema,
            "handler": handler,
            "check_fn": check_fn,
        }
        return self  # 支持链式调用

    def get_definitions(self):
        """产出给 LLM 的 schema 列表：check_fn 返回 False 的工具不暴露（模型看不到=不会幻觉调用）。"""
        return [
            t["schema"]
            for t in self._tools.values()
            if t["check_fn"] is None or t["check_fn"]()
        ]

    def has(self, name):
        return name in self._tools

    def dispatch(self, name, args):
        """按名分发。未知工具 / handler 异常都转结构化错误，永不抛异常。"""
        tool = self._tools.get(name)
        if tool is None:
            return {"error": f"未知工具: {name}"}
        try:
            return tool["handler"](**args)
        except Exception as e:
            return {"error": f"工具执行失败: {e}"}


# 模块级单例：各实现版本共用同一个注册表（保证"同一套工具"）
registry = ToolRegistry()
