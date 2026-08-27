"""Chroma 向量库封装。全项目唯一直接操作向量库的地方。

【大白话】Chroma 是一个"轻量向量数据库"，本职是存"一串串数字 + 每一串附带的文字"，
然后能极快地回答一个问题：给我和这句话"最像"的几段文字。
我们把它当"知识库的搜索引擎"用：存文档切块，检索时找最近似的块。

关键：入库/查询都**显式传向量**（embeddings），不配 embedding_function。
【为什么】配了 embedding_function，Chroma 会在本地自己做一个 embedding 模型来转文字，
既占内存又和我们用的百炼模型不一致；我们显式给向量，Chroma 就纯当"存储+检索器"用。
"""

import chromadb

from app.core.config import settings

_client = None
_COLLECTION = "doc_chunks"  # 向量库里的"集合"名（类似一张表）


def get_client() -> chromadb.Client:
    """惰性单例：拿到 Chroma 客户端（连接保存在本地文件夹 settings.chroma_dir）。"""
    global _client
    if _client is None:
        # PersistentClient：数据持久化到本地目录（./data/chroma），重启不丢
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
    return _client


def get_collection():
    """获取/创建文档块集合。

    metadata={"hnsw:space": "cosine"}：用"余弦距离"衡量两个向量像不像（越小越像）。
    get_or_create：没有就建、有了就用（幂等，重启动也能用同一个集合）。
    """
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
    """把一个文档的全部切块 + 向量写入向量库。

    【每一条记录的样子】id（块唯一编号，形如 "文档id-块序号"）+ 向量 + 原文 + 元数据。
    元数据（metadata）用来"按条件筛选"：
      - kb_id：检索时只在某个知识库内找（where 过滤）
      - doc_id + chunk_index：删文档时按 doc_id 一键全删；展示时知道来自第几块
    """
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


def get_document_chunks(doc_id: int) -> list[tuple[int, str]]:
    """取回某文档的所有切块原文，按块序号排序。返回 [(chunk_index, 文本)]。

    【用途】文档"查看内容"：Chroma 里存着每块原文和序号，从这里读出来，
    前端即可展示这份文档被切成什么样子后入库的。
    """
    coll = get_collection()
    res = coll.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
    items = [
        (m.get("chunk_index", 0), d)
        for d, m in zip(res["documents"] or [], res["metadatas"] or [])
    ]
    items.sort(key=lambda x: x[0])
    return items


def query(
    kb_id: int,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[tuple[str, float, dict]]:
    """在某个知识库内做向量检索。返回 [(片段文本, 余弦距离, 元数据)]。

    【原理】把查询向量和集合里所有向量比"方向远近"，取最近的 top_k 个。
    where={"kb_id": kb_id} 限定只在当前知识库内比，不跨库。
    """
    coll = get_collection()
    res = coll.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where={"kb_id": kb_id},
    )
    texts = res["documents"][0]   # Chroma 返回格式是嵌套两层，取 [0]
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
        # 任何一个关键词，只要有某块文本包含它 → 说明这个词真实存在
        if any(kw_l in (t or "").lower() for t in texts):
            return True
    return False