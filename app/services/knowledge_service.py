"""知识库业务逻辑：知识库/文档管理 + 「上传→切块→向量→入库」链路 + 检索。

对外函数返回响应模型（与 agent_service 同一约定），在 session 内完成懒加载，
避免序列化时踩"session 已关闭"的坑。
"""

import io
from pathlib import Path

import pypdf
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import chunker, llm
from app.models import Document, KnowledgeBase
from app.schemas.knowledge import (
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    SearchResponse,
    SearchResult,
)
from app.services import vector_store

ALLOWED_TYPES = {"pdf": "pdf", "txt": "txt", "md": "md"}

# 检索相关性阈值（余弦距离）。超过该值视为"无关"并过滤，避免搜无关词也硬凑结果。
SEARCH_RELEVANCE_THRESHOLD = 0.6


# ---------- 内部工具 ----------

def _kb_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"知识库 {kb_id} 不存在")
    return kb


def _doc_or_404(db: Session, doc_id: int) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文档 {doc_id} 不存在")
    return doc


def _to_kb_out(kb: KnowledgeBase, doc_count: int = 0) -> KnowledgeBaseOut:
    return KnowledgeBaseOut(
        id=kb.id, name=kb.name, description=kb.description,
        doc_count=doc_count, created_at=kb.created_at,
    )


def _to_doc_out(d: Document) -> DocumentOut:
    return DocumentOut(
        id=d.id, kb_id=d.kb_id, filename=d.filename, file_type=d.file_type,
        size_bytes=d.size_bytes, status=d.status, chunk_count=d.chunk_count,
        error_msg=d.error_msg, created_at=d.created_at,
    )


def _extract_text(filename: str, data: bytes) -> str:
    """按扩展名提取纯文本。PDF 用 pypdf 逐页拼文本；TXT/MD 直接解码。"""
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"仅支持 PDF/TXT/MD，收到 .{ext}")
    if ext == "pdf":
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="replace")


# ---------- 知识库 ----------

def create_kb(db: Session, payload: KnowledgeBaseCreate) -> KnowledgeBaseOut:
    if db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == payload.name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"知识库 '{payload.name}' 已存在")
    kb = KnowledgeBase(name=payload.name, description=payload.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return _to_kb_out(kb)


def list_kbs(db: Session, page: int = 1, size: int = 20) -> tuple[list[KnowledgeBaseOut], int]:
    total = db.scalar(select(func.count()).select_from(KnowledgeBase)) or 0
    kbs = db.scalars(
        select(KnowledgeBase).order_by(KnowledgeBase.id).offset((page - 1) * size).limit(size)
    ).all()
    items = []
    for kb in kbs:
        cnt = db.scalar(
            select(func.count()).select_from(Document).where(Document.kb_id == kb.id)
        ) or 0
        items.append(_to_kb_out(kb, cnt))
    return items, total


# ---------- 文档：上传入库（核心链路） ----------

def create_document(db: Session, kb_id: int, filename: str, data: bytes) -> DocumentOut:
    """上传文档 → 提取文本 → Go 切块 → 向量化 → 写 Chroma → 更新台账。

    模块 2 阶段选择"同步处理"（文件小、实时反馈；异步留给后续优化），
    见 decisions.md。失败时文档标 failed 并给出原因。
    """
    _kb_or_404(db, kb_id)
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"仅支持 PDF/TXT/MD，收到 .{ext}")

    doc = Document(
        kb_id=kb_id, filename=filename, file_type=ext,
        size_bytes=len(data), status="processing",
    )
    db.add(doc)
    db.commit()  # 先落 id，后面向量库要用 doc.id

    try:
        text = _extract_text(filename, data)
        if not text.strip():
            raise ValueError("未能提取出文本（PDF 可能是扫描图片）")
        chunks = chunker.chunk_text(text)          # 调 Go 服务切块
        embeddings = llm.embed_texts(chunks)       # 百炼 text-embedding-v4
        vector_store.add_document_chunks(kb_id, doc.id, chunks, embeddings)
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error_msg = ""
    except Exception as e:  # noqa: BLE001 统一转为 failed，关键看 error_msg
        # 清理可能已写入的半截向量
        try:
            vector_store.delete_document_chunks(doc.id)
        except Exception:  # noqa: BLE001
            pass
        doc = db.get(Document, doc.id)  # 重新取（避免 session 状态异常）
        doc.status = "failed"
        doc.error_msg = str(e)[:500]

    db.commit()
    db.refresh(doc)
    return _to_doc_out(doc)


# ---------- 文档：列表与删除 ----------

def list_documents(
    db: Session,
    kb_id: int | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[DocumentOut], int]:
    stmt = select(Document)
    count_stmt = select(func.count()).select_from(Document)
    if kb_id is not None:
        stmt = stmt.where(Document.kb_id == kb_id)
        count_stmt = count_stmt.where(Document.kb_id == kb_id)
    total = db.scalar(count_stmt) or 0
    docs = db.scalars(
        stmt.order_by(Document.id.desc()).offset((page - 1) * size).limit(size)
    ).all()
    return [_to_doc_out(d) for d in docs], total


def delete_document(db: Session, doc_id: int) -> None:
    """删除文档：先清向量（防重复计费），再删台账。"""
    doc = _doc_or_404(db, doc_id)
    try:
        vector_store.delete_document_chunks(doc.id)
    except Exception:  # noqa: BLE001 向量清理失败不阻塞删除
        pass
    db.delete(doc)
    db.commit()


# ---------- 检索测试 ----------

# 中文分词用简单规则：按"词边界/标点/空"以及"中英文交界"切分，太短的词（单字）不纳入。
# 这样 "RAG检索" 能拆成 ["RAG","检索"]，避免中英混写连续串整串判空。
# （真正的智能分词要接分词库，模块 6 双路检索时一并考虑。）
def _extract_keywords(query: str) -> list[str]:
    import re
    # 在中英文、中英数字交界处也插入分隔：在"汉字"与"非汉字"相邻处切一刀
    parts = re.split(
        r"(?<=[一-龥])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[一-龥])|[^一-龥A-Za-z0-9]+",
        query,
    )
    kws: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:
            kws.append(p)
    return kws


def search_kb(db: Session, kb_id: int, query: str, top_k: int = 5) -> SearchResponse:
    _kb_or_404(db, kb_id)
    if not query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="query 不能为空")

    # 第一层：字面验证 —— 用户查询的关键词在文档里是否存在。
    # 只要没有一个关键词真的出现在入库文本里，就直接判"无命中"，不再走向量硬凑。
    keywords = _extract_keywords(query)
    if keywords and not vector_store.keyword_exists(kb_id, keywords):
        return SearchResponse(query=query, kb_id=kb_id, results=[])

    # 第二层：语义检索 —— 关键词存在时，用向量找最相关的块。
    emb = llm.embed_one(query)
    try:
        hits = vector_store.query(kb_id, emb, top_k)
    except Exception:  # noqa: BLE001 空库/无命中时的兜底
        hits = []
    results = []
    for text, score, meta in hits:
        # 只保留真正"命中关键词"的块，进一步去噪声（字面+语义双重约束）
        if keywords and not any(kw.lower() in (text or "").lower() for kw in keywords):
            continue
        doc_id = meta.get("doc_id") or 0
        doc = db.get(Document, doc_id) if doc_id else None
        results.append(SearchResult(
            chunk_text=text,
            score=round(float(score), 4),
            document_id=doc_id,
            filename=doc.filename if doc else "",
            chunk_index=meta.get("chunk_index", 0),
        ))
    # 按相似度从近到远排序（score 为 cosine 距离，越小越像）
    results.sort(key=lambda r: r.score)
    # 相关性阈值：余弦距离超过此值视为"无关"，过滤掉（搜无关词不再硬凑结果）
    results = [r for r in results if r.score <= SEARCH_RELEVANCE_THRESHOLD]
    return SearchResponse(query=query, kb_id=kb_id, results=results)