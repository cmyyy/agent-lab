"""retriever.py —— RAG 深模块：混合检索（BM25 + 向量 → RRF），对齐 vaultrag 成熟实现。

参考（2026-08-19，按用户指示复用已验证实现）：
- vaultrag 插件 retriever.py 的 BM25Index + hybrid_search（RRF 融合）
- skill: rag-retrieval-pipeline（混合检索 Recall@5 0.695→0.816，MRR@3 +39.7%）

对外稳定接口：`search(query, top_k=4) -> {"results": [...]}`（深模块，FR-6）。

三档降级链（embedding 离线怎么来）：
  档1 在线 embedding（SiliconFlow）→ 混合检索（BM25 + 向量 → RRF）
  档2 无 embedding → 纯 BM25（零依赖，精确匹配）
  档3 无语料 → 空结果（{"results": []}，check_fn 决定是否暴露工具）

fail-open：任何异常返回空结果，绝不抛异常（FR-6 契约）。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np

from shared_tools.chunker import chunk_with_sources

# 知识库根目录（可被环境变量覆盖；默认 agent-lab/knowledge/）
DEFAULT_KB_ROOT = Path(__file__).resolve().parent.parent / "knowledge"
_KB_ROOT = Path(os.getenv("AGENT_LAB_KB_ROOT", str(DEFAULT_KB_ROOT)))

_MD_EXTS = {".md", ".txt"}
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    """中英混合分词：中文按字符 bigram，英文/数字按单词（对齐 vaultrag BM25Index）。"""
    text = text.lower()
    tokens = []
    for seg in _CJK_RE.findall(text):
        seg_tokens = list(seg) if len(seg) <= 2 else [seg[i:i + 2] for i in range(len(seg) - 1)]
        tokens.extend(seg_tokens)
    tokens.extend(re.findall(r"[a-z0-9]+", text))
    return tokens


class BM25Index:
    """BM25 关键词检索（纯 numpy，零依赖，对齐 vaultrag 实现）。

    为什么加 BM25（arXiv 2604.01733 基准 + 实测）：
      - 语义检索补不了精确匹配：缩写/术语/ID（"MoA"）靠关键词
      - 短确认消息在文档里几乎不出现 → BM25 分数趋零，源头过滤噪音
      - 同一基准里 BM25 多数指标甚至优于 text-embedding-3-large
    """

    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.doc_terms = [self._tokenize(t) for t in texts]
        self.doc_len = [len(t) for t in self.doc_terms]
        self.avgdl = sum(self.doc_len) / max(1, len(self.doc_len))
        self.N = len(self.doc_terms)
        df = {}
        for terms in self.doc_terms:
            for term in set(terms):
                df[term] = df.get(term, 0) + 1
        self.df = df
        self.k1 = k1
        self.b = b

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return _tokenize(text)

    def score(self, query: str) -> np.ndarray:
        """对每个文档算 BM25 分，返回 (N,) 数组。"""
        q_terms = self._tokenize(query)
        scores = np.zeros(self.N, dtype=np.float32)
        if not q_terms:
            return scores
        for term in q_terms:
            idf = np.log(1 + (self.N - self.df.get(term, 0) + 0.5) / (self.df.get(term, 0) + 0.5))
            for i, terms in enumerate(self.doc_terms):
                tf = terms.count(term)
                if tf == 0:
                    continue
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                scores[i] += idf * tf * (self.k1 + 1) / denom
        return scores


class Retriever:
    """知识库检索器（深模块：目录加载 + 切块 + 混合检索 + 降级链）。"""

    def __init__(self, kb_root=None, embedding=None):
        self.kb_root = Path(kb_root) if kb_root else _KB_ROOT
        self.embedding = embedding  # 可选：embedding 客户端（embed_query / embed_texts）
        self._docs: list[dict] = []  # [{text, source}]
        self._vectors: np.ndarray | None = None  # (N, D) 语义向量缓存
        self._bm25: BM25Index | None = None
        self.load()

    # -- 语料加载 ---------------------------------------------------------

    def load(self) -> None:
        """扫描知识库目录，切块建索引（幂等：重复调用重新加载）。"""
        self._docs = []
        self._vectors = None
        self._bm25 = None

        if not self.kb_root.is_dir():
            return

        for path in sorted(self.kb_root.rglob("*")):
            if path.suffix.lower() not in _MD_EXTS:
                continue
            if any(part.startswith(".") for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            blocks = chunk_with_sources(text, source_name=path.stem)
            self._docs.extend(blocks)

        if self._docs:
            self._bm25 = BM25Index([d["text"] for d in self._docs])

    @property
    def size(self) -> int:
        return len(self._docs)

    # -- 检索接口（深模块的唯一对外方法）----------------------------------

    def search(self, query: str, top_k: int = 4) -> dict:
        """混合检索。返回 {"results": [...]}，每项 {text, source, score}。

        降级链：有 embedding → 混合检索（BM25+向量→RRF）；无 → 纯 BM25。
        fail-open：异常返回空结果。
        """
        query = (query or "").strip()
        if not query or not self._docs or self._bm25 is None:
            return {"results": []}
        try:
            if self.embedding is not None:
                return self._hybrid_search(query, top_k)
            return self._bm25_only(query, top_k)
        except Exception:
            return {"results": []}

    # -- 混合检索（BM25 + 向量 → RRF，对齐 vaultrag hybrid_search）---------

    def _hybrid_search(self, query: str, top_k: int) -> dict:
        if self._vectors is None:
            self._vectors = self._embed_all()
            if self._vectors is None:
                return self._bm25_only(query, top_k)  # embedding 失败 → 降档
        qv = self.embedding.embed_query(query)
        if qv is None:
            return self._bm25_only(query, top_k)

        # 两路各自取 top_k*3（多召回，融合后再截断）
        recall = top_k * 3
        dense_scores = self._vectors @ np.asarray(qv, dtype=np.float32)
        dense_top = np.argsort(-dense_scores)[:recall]

        bm25_scores = self._bm25.score(query)
        bm25_top = np.argsort(-bm25_scores)[:recall]

        # RRF 融合：1/(rank + k)，k=60（滑铁卢+Google 2019）
        k_rrf = 60.0
        fusion: dict[int, float] = {}
        for rank, i in enumerate(dense_top):
            fusion[i] = fusion.get(i, 0.0) + 1.0 / (rank + 1 + k_rrf)
        for rank, i in enumerate(bm25_top):
            fusion[i] = fusion.get(i, 0.0) + 1.0 / (rank + 1 + k_rrf)

        ranked = sorted(fusion.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
        results = [
            {**self._docs[i], "score": round(float(dense_scores[i]), 4)}
            for i, _ in ranked
            if dense_scores[i] > 0
        ]
        return {"results": results}

    def _bm25_only(self, query: str, top_k: int) -> dict:
        """档2：纯 BM25（无 embedding 时的离线降级）。"""
        scores = self._bm25.score(query)
        top_ids = np.argsort(-scores)[:top_k]
        results = [
            {**self._docs[i], "score": round(float(scores[i]), 4)}
            for i in top_ids
            if scores[i] > 0
        ]
        return {"results": results}

    def _embed_all(self) -> np.ndarray | None:
        """批量 embedding（失败返回 None → 降档）。"""
        try:
            texts = [d["text"] for d in self._docs]
            vecs = self.embedding.embed_texts(texts)
            if vecs is None:
                return None
            arr = np.asarray(vecs, dtype=np.float32)
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            return arr / norms
        except Exception:
            return None
