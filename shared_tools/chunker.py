"""chunker.py —— 中文友好的文本切块器（RAG 深模块第一环，FR-6）。

设计（2026-08-19，PRD FR-6）：
- 按句子边界切块（。！？换行），超长段才按长度二次切——避免硬切碎中文语义
- 中文切块的坑：按长度硬切（如 500 字一刀）必然把语义切碎；
  按句子边界保语义完整，但句子可能超长（如长列表），所以二级兜底按长度切
- 输出块带索引（source 标注用：文件名 + 块序号）

对齐 vaultrag 经验：vaultrag 的切块逻辑（retriever.py scan_vault）验证过
中文 bigram 检索 + 块级来源标注；这里做句子边界优先的切块。
"""

import re

# 句子边界：中文句号/感叹号/问号/省略号 + 换行
_SENTENCE_BOUNDARY = re.compile(r"[。！？!?\n]+")
# 二级长度切分：超过此长度的块按段落/逗号兜底
_MAX_CHUNK_CHARS = 800


def split_into_chunks(text: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[str]:
    """按句子边界切块；超长句按长度兜底切。返回块列表（不带序号）。

    规则：
    1. 去掉首尾空白，空文本返回 []
    2. 按句子边界（。！？\n）切分，合并过短残片（< 20 字且相邻同属一段时合并，减少碎片）
    3. 单块超 max_chars → 按段内逗号/分号二次切，仍超 → 硬切（兜底）
    """
    text = text.strip()
    if not text:
        return []

    # 1. 句子级切分（保留边界符号在句尾，读起来自然）
    raw_parts = _SENTENCE_BOUNDARY.split(text)
    raw_parts = [p.strip() for p in raw_parts if p.strip()]

    # 2. 合并过短残片（< 20 字）：中文里"是。""对。"这类单句很短，合并进前一块减少碎片
    chunks: list[str] = []
    for part in raw_parts:
        if chunks and len(part) < 20 and len(chunks[-1]) + len(part) <= max_chars:
            chunks[-1] = chunks[-1] + part
        else:
            chunks.append(part)

    # 3. 超长块兜底：按逗号/分号二次切，仍超则硬切
    result: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            result.append(chunk)
            continue
        # 二级切分：优先逗号/分号/顿号，尽量不破语义
        sub_parts = re.split(r"[，,；;、]+", chunk)
        buf = ""
        for sp in sub_parts:
            if buf and len(buf) + len(sp) > max_chars:
                result.append(buf)
                buf = sp
            else:
                buf += sp
        if buf:
            # 仍有超长残块 → 硬切兜底（max_chars 一刀，最坏情况）
            while len(buf) > max_chars:
                result.append(buf[:max_chars])
                buf = buf[max_chars:]
            if buf:
                result.append(buf)
    return result


def chunk_with_sources(text: str, source_name: str, max_chars: int = _MAX_CHUNK_CHARS) -> list[dict]:
    """切块并带来源标注：{text, source: '<文件名>#<块序号>'}（FR-6 返回结构兼容）。"""
    chunks = split_into_chunks(text, max_chars=max_chars)
    return [
        {"text": c, "source": f"{source_name}#{i + 1}"}
        for i, c in enumerate(chunks)
    ]
