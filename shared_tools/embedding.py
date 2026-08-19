"""embedding.py —— 在线 embedding 客户端（RAG 档1，FR-6）。

可选依赖：未配置 SILICONFLOW_API_KEY 时 get_embedding_client() 返回 None，
Retriever 自动降级到 n-gram 检索（档2）。零强制依赖（urllib 调 OpenAI 兼容端点）。

对齐 vaultrag 经验：云端 embedding（用户明确不用本地小模型）+ fail-open。
"""

import json
import os
import urllib.request

DEFAULT_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
DEFAULT_MODEL = os.getenv("SILICONFLOW_EMBED_MODEL", "BAAI/bge-m3")


class EmbeddingClient:
    """OpenAI 兼容 embedding 客户端（SiliconFlow 等端点）。"""

    def __init__(self, api_key=None, base_url=None, model=None):
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.model = model or DEFAULT_MODEL

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def embed_query(self, query: str):
        """单条查询向量；失败返回 None（fail-open）。"""
        res = self._call([query])
        if not res:
            return None
        return res[0]

    def embed_texts(self, texts: list[str]):
        """批量文档向量；失败返回 None（fail-open）。"""
        return self._call(texts)

    def _call(self, texts: list[str]):
        if not self.available:
            return None
        try:
            payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/embeddings",
                data=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
            data = resp.get("data", [])
            # 按 index 排序保证顺序稳定
            data.sort(key=lambda d: d.get("index", 0))
            return [d["embedding"] for d in data]
        except Exception:
            return None


_client = None


def get_embedding_client() -> EmbeddingClient | None:
    """返回全局 embedding 客户端；未配置 key 时返回 None（触发降级链）。"""
    global _client
    if _client is None:
        c = EmbeddingClient()
        _client = c if c.available else None
    return _client
