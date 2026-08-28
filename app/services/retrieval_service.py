"""双路检索服务：向量（Chroma）+ 关键词（ES）融合排序。

【大白话】这个文件是模块 6 的核心——让检索更准：
- 向量检索（Chroma）：找"语义相近"的段落（搜"咋登录"能命中"登录方法"）
- 关键词检索（ES）：找"字面匹配"的段落（搜"红烧肉"必须文档里真有这仨字）
- 融合排序：把两路结果按权重算综合分，排个序返回最相关的

【为什么双路】单靠向量会"矮子里拔将军"——哪怕你搜的词跟文档完全无关，
它也能硬凑出几条"最像的"。加上 ES 字面验证后：所有关键词都不存在 → 直接返回空，
不硬凑。这才是用户想要的"搜红烧肉，没有就说没有"。
"""

from app.core.es import get_es, es_index_name
from app.services.vector_store import query as chroma_query


# ---- 融合排序权重（可调整）----
# 【为什么 0.6/0.4】向量是"语义理解"的主力，给高权重；ES 是"字面验证"，给低权重但必须存在。
# 后续可根据实测效果微调（比如发现用户更在意字面匹配，可调成 0.5/0.5）。
VECTOR_WEIGHT = 0.6   # 向量分数权重
ES_WEIGHT = 0.4       # ES 分数权重


def _extract_keywords(query: str) -> list[str]:
    """把用户查询拆成关键词列表。

    【当前策略】按空格/标点切分（简单但够用）。
    例："红烧肉的做法" → ["红烧肉", "做法"]
    后续优化：可接入中文分词器（如 jieba/IK），但当前简单切分已能跑通。
    """
    import re
    # 按空格、中文标点（，。？！；：）切分，过滤空串
    parts = re.split(r"[,\s,.,?,!,;,;]+", query)
    return [p.strip() for p in parts if p.strip()]


def _keyword_exists_in_text(keywords: list[str], text: str) -> bool:
    """检查所有关键词是否至少有一个出现在文本中。

    【为什么不是全部匹配】用户搜"红烧肉的做法"，文档里可能只写"红烧肉烹饪技巧"——
    "做法"没出现，但"红烧肉"出现了，这就算命中。
    只要有一个关键词出现，就认为"字面匹配"通过。
    """
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def search(kb_id: int, query: str, top_k: int = 3) -> list[dict]:
    """双路检索入口：ES 关键词 + Chroma 向量，融合排序返回。

    完整流程：
    1. 拆关键词
    2. ES 检索（第一路）→ 拿 bm25 分数
    3. 字面验证：所有关键词都不存在 → 返回空
    4. 把 query 转成向量，Chroma 检索（第二路）→ 拿余弦距离（越小越像）
    5. 融合排序：综合分 = 0.6×(1-余弦距离) + 0.4×ES 分
    6. 返回 top_k

    Args:
        kb_id: 知识库 ID（只在这个库里搜）
        query: 用户查询（如"红烧肉的做法"）
        top_k: 返回几段

    Returns:
        [{"text": "...", "score": 0.95, "kb_id": 123, "source": "xxx.pdf"}, ...]
    """
    from app.core import llm  # 这里才需要向量化

    keywords = _extract_keywords(query)

    # ========== 第一路：ES 关键词检索 ==========
    es = get_es()
    index = es_index_name(kb_id)

    # 检查索引是否存在
    if not es.indices.exists(index=index):
        # ES 里没这个库 → 字面验证直接失败，返回空
        return []

    # ES match_query：自动分词 + BM25 评分
    es_resp = es.search(
        index=index,
        query={"match": {"text": query}},  # 用整个 query 去匹配，ES 自己会分词
        size=top_k * 2,  # 先多拿点，融合后再截断
    )

    es_hits = es_resp.get("hits", {}).get("hits", [])
    if not es_hits:
        # ES 没命中任何文档 → 字面验证失败，返回空
        return []

    # 字面验证：检查关键词是否真的在结果文本里
    es_results = []
    for hit in es_hits:
        text = hit["_source"].get("text", "")
        if _keyword_exists_in_text(keywords, text):
            es_results.append({
                "text": text,
                "es_score": hit["_score"],  # BM25 原始分
                "kb_id": kb_id,
                "source": hit["_source"].get("source", "unknown"),
            })

    if not es_results:
        # 有命中但关键词都不在 → 返回空
        return []

    # ========== 第二路：Chroma 向量检索 ==========
    # 先把 query 转成向量
    emb = llm.embed_one(query)
    # chroma_query 返回 [(text, distance, metadata), ...]，distance 是余弦距离（越小越像）
    chroma_hits = chroma_query(kb_id, emb, top_k=top_k * 2)

    # ========== 融合排序 ==========
    # 建一个"文本→ES 分数"的字典，方便后面查
    es_score_map = {r["text"]: r["es_score"] for r in es_results}

    fused = []
    for text, distance, meta in chroma_hits:
        # 只融合那些"字面验证通过"的结果（ES 命中的）
        if text in es_score_map:
            es_score = es_score_map[text]
            # 余弦距离转相似度：1 - distance（距离越小→相似度越高）
            # Chroma 的余弦距离范围 [0, 2]，但实际使用多在 [0, 1]
            vector_sim = max(0, 1 - distance)  # 确保非负
            combined = VECTOR_WEIGHT * vector_sim + ES_WEIGHT * es_score
            fused.append({
                "text": text[:500],  # 截断防太长
                "score": round(combined, 4),
                "kb_id": kb_id,
                "source": meta.get("source", "unknown"),
            })

    # 按综合分从高到低排
    fused.sort(key=lambda x: x["score"], reverse=True)
    return fused[:top_k]


def add_document_to_es(kb_id: int, doc_id: int, chunks: list[str]) -> None:
    """把文档切块写入 ES 索引（供 knowledge_service 调用）。

    【什么时候用】文档上传成功时，除了写 Chroma，也同步写 ES 索引。
    【写入格式】每个切块一条文档：
      {
        "doc_id": 123,
        "text": "切块原文",
        "source": "filename.pdf|123",  // 方便前端反推文件名
        "chunk_index": 0,
      }
    """
    es = get_es()
    index = es_index_name(kb_id)

    # 检查索引是否存在，不存在就创建
    if not es.indices.exists(index=index):
        es.indices.create(
            index=index,
            mappings={
                "properties": {
                    "doc_id": {"type": "integer"},
                    "text": {"type": "text", "analyzer": "standard"},  # standard 分词器（中文按字切）
                    "source": {"type": "keyword"},
                    "chunk_index": {"type": "integer"},
                }
            },
        )

    # 批量写入
    from elasticsearch.helpers import bulk

    def actions():
        for i, chunk in enumerate(chunks):
            yield {
                "_index": index,
                "_source": {
                    "doc_id": doc_id,
                    "text": chunk,
                    "source": f"doc_{doc_id}",  # 简化：只用 doc_id 标识来源
                    "chunk_index": i,
                },
            }

    bulk(es, actions())


def delete_document_from_es(kb_id: int, doc_id: int) -> None:
    """从 ES 索引中删除某个文档的所有切块（供 delete_document 调用）。

    【为什么需要】删文档时必须同步清 ES，否则检索时会命中已删除的内容。
    【删除方式】用 delete_by_query：找到所有 doc_id 匹配的文档，批量删。
    """
    es = get_es()
    index = es_index_name(kb_id)

    if not es.indices.exists(index=index):
        return  # 索引都不存在，没啥可删的

    es.delete_by_query(
        index=index,
        query={"term": {"doc_id": doc_id}},
        conflicts="proceed",  # 并发冲突时继续删
    )
