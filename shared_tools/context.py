"""context.py —— 上下文管理（FR-2 轻量版，2026-08-19）。

设计（PRD FR-2，明确不做总结式压缩）：
- 滑动窗口：保 system + 最近 N 条消息（超窗丢弃中间旧消息）
- 工具结果截断：单条工具结果超限截断 + 提示"结果已截断"（RAG 落地后
  检索结果可能几百 token，直接撑爆窗口）
- token 估算：粗估算（中文 ~1 token/字，英文 ~4 字符/token），不引入 tiktoken
  （个人项目够用，对齐 Hermes 的简化估算思路）

为什么不做 summarization：复杂度高、效果难验证、面试收益低；
标注"对照 Hermes ContextCompressor 的后续项"（README 已用此手法）。

对比公平性：两版共用本模块（handcrafted / lc_agent 都 import）。
"""

# 默认窗口：保 system + 最近 N 条消息
DEFAULT_MAX_MESSAGES = 20
# 单条消息最大字符数（超限截断）
DEFAULT_MAX_MSG_CHARS = 3000
# 工具结果截断上限
DEFAULT_MAX_TOOL_CHARS = 2000


def estimate_tokens(text: str) -> int:
    """粗 token 估算：中文按字符数，英文按 4 字符/token。"""
    if not text:
        return 0
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - cjk
    return cjk + other // 4 + 1


def truncate_tool_result(result_text: str, max_chars: int = DEFAULT_MAX_TOOL_CHARS) -> str:
    """工具结果截断：超限截断并标注，防撑爆窗口（FR-2）。"""
    if len(result_text) <= max_chars:
        return result_text
    return result_text[:max_chars] + f"\n...[结果已截断，原始 {len(result_text)} 字符]"


def apply_sliding_window(
    messages: list[dict],
    system_prompt: str,
    max_messages: int = DEFAULT_MAX_MESSAGES,
) -> list[dict]:
    """滑动窗口：保 system + 最近 max_messages 条，丢弃中间旧消息。

    Args:
        messages: 完整消息列表（可能含 system）
        system_prompt: 系统提示词（窗口收缩时重新注入，保证 system 永远在）

    Returns:
        窗口内的消息列表（system 在前 + 最近 N 条）
    """
    if len(messages) <= max_messages:
        return messages
    # 去掉原 system（若有），保留最近 N 条，前面重新放 system
    tail = [m for m in messages if m.get("role") != "system"][-max_messages:]
    return [{"role": "system", "content": system_prompt}] + tail


def apply_message_truncation(
    messages: list[dict],
    max_msg_chars: int = DEFAULT_MAX_MSG_CHARS,
    max_tool_chars: int = DEFAULT_MAX_TOOL_CHARS,
) -> list[dict]:
    """单条消息截断：工具消息用 truncate_tool_result，其他超限截断。"""
    out = []
    for m in messages:
        m = dict(m)
        content = m.get("content")
        if isinstance(content, str):
            if m.get("role") == "tool":
                m["content"] = truncate_tool_result(content, max_tool_chars)
            elif len(content) > max_msg_chars:
                m["content"] = content[:max_msg_chars] + "...[截断]"
        out.append(m)
    return out


def total_tokens(messages: list[dict]) -> int:
    """估算消息列表总 token（含 content 与 role）。"""
    return sum(estimate_tokens(str(m.get("content", ""))) + 2 for m in messages)
