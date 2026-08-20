"""Chroma 向量库封装。全项目唯一直接操作向量库的地方。

要点：入库/查询都**显式传向量**，不配 embedding_function，
这样 Chroma 不会去下载本地 embedding 模型——Embedding 统一走百炼 text-embedding-v4。
"""

import chromadb

from app.core.config import settings

_client = None
_COLLECTION = "doc_chunks"


def get_client() -> chromadb.Client:
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    return _client


def get_collection():
    coll = get_client().get_or_create_collection(
        name=_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    return coll


def add_document_chunks(
    kb_id: int,
    doc_id: int,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    """把一个文档的全部切块 + 向量写入向量库。id 形如 "doc_id-块序号"。"""
    coll = get_collection()
    coll.add(
        ids=[f"{doc_id}-{i}" for i in range(len(chunks))],
        embeddings=embeddings,
        documents=chunks,
        metadatas=[
            {"kb_id": kb_id, "doc_id": doc_id, "chunk_index": i}
            for i in range(len(chunks))
        ],
    )


def delete_document_chunks(doc_id: int) -> None:
    """按 metadata 过滤删除某个文档的全部向量（文档删除时调用，防重复计费）。"""
    coll = get_collection()
    coll.delete(where={"doc_id": doc_id})


def query(
    kb_id: int,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[tuple[str, float, dict]]:
    """在某个知识库内做向量检索。返回 [(片段文本, 相似度, 元数据)]。"""
    coll = get_collection()
    res = coll.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"kb_id": kb_id},
    )
    texts = res["documents"][0]
    scores = res["distances"][0]
    metadatas = res["metadatas"][0]
    return [(t, s, m) for t, s, m in zip(texts, scores, metadatas)]


def keyword_exists(kb_id: int, keywords: list[str]) -> bool:
    """字面验证：查询拆出的关键词是否真实存在于某知识库的入库文本里。

    用于"字面+语义结合"检索的第一层：只要任一关键词在文档原文中出现，
    就认为这个词存在；若全部关键词都不存在，则上层直接判为"无命中"。
    （模块 6 接入 ES 后将改用真正的关键词全文检索，此处先用块文本子串做近似。）
    """
    if not keywords:
        return False
    coll = get_collection()
    # 取出该知识库全部块文本（本阶段库小、块少，直接全量遍历够用）
    res = coll.get(where={"kb_id": kb_id}, include=["documents"])
    texts = res["documents"] or []
    for kw in keywords:
        kw_l = kw.lower()
        if any(kw_l in (t or "").lower() for t in texts):
            return True
    return False