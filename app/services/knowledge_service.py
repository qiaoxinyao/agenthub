"""知识库业务逻辑：知识库/文档管理 + 「上传→切块→向量→入库」链路 + 检索。

【大白话】这是"知识库的管家"，干三件事：
1. 建/查知识库、查/删文档（台账管理）
2. 上传文档时的完整入库链路：
   读文件 → 提取文字（PDF 特麻烦）→ 让 Go 切块 → 每块向量化 → 存进向量库
3. 检索：用户提问 → 字面验证 → 语义找最相关片段

对外函数返回响应模型（与 agent_service 同一约定），在数据库会话内完成计算再返回。
"""

import io
from pathlib import Path

import pypdf  # 专门解析 PDF：能把 PDF 的每一页文字抽出来
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import chunker, llm  # chunker: 调 Go 切块; llm: 调百炼做向量
from app.models import Document, KnowledgeBase
from app.schemas.knowledge import (
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseOut,
    SearchResponse,
    SearchResult,
)
from app.services import vector_store

# 允许上传的文件类型白名单。key=扩展名，value=类型名
ALLOWED_TYPES = {"pdf": "pdf", "txt": "txt", "md": "md"}

# 检索相关性阈值（余弦距离）。超过该值视为"无关"并过滤，避免搜无关词也硬凑结果。
# 余弦距离范围一般 0~2：越小越像。0.6 这个值是我们调过的分水岭（可继续微调）。
SEARCH_RELEVANCE_THRESHOLD = 0.6


# ---------- 内部工具 ----------

def _kb_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    """按 id 找知识库，找不到抛 404。"""
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"知识库 {kb_id} 不存在")
    return kb


def _doc_or_404(db: Session, doc_id: int) -> Document:
    """按 id 找文档，找不到抛 404。"""
    doc = db.get(Document, doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文档 {doc_id} 不存在")
    return doc


def _to_kb_out(kb: KnowledgeBase, doc_count: int = 0) -> KnowledgeBaseOut:
    """数据库对象 → 响应模型（doc_count 由调用方算好传进来）。"""
    return KnowledgeBaseOut(
        id=kb.id, name=kb.name, description=kb.description,
        doc_count=doc_count, created_at=kb.created_at,
    )


def _to_doc_out(d: Document) -> DocumentOut:
    """数据库对象 → 响应模型。"""
    return DocumentOut(
        id=d.id, kb_id=d.kb_id, filename=d.filename, file_type=d.file_type,
        size_bytes=d.size_bytes, status=d.status, chunk_count=d.chunk_count,
        error_msg=d.error_msg, created_at=d.created_at,
    )


def _extract_text(filename: str, data: bytes) -> str:
    """从上传的原始字节里取出纯文本。

    【为什么按扩展名分叉】三种文件本质不同：
    - txt/md：就是普通文本，直接按 utf-8 解码
    - pdf：是"排版格式"文件，文字藏在流里，得靠 pypdf 逐页解析抽出来
    PDF 是这里唯一的"麻烦精"，也是面试常问的"你们怎么处理 PDF"。
    """
    ext = Path(filename).suffix.lower().lstrip(".")  # 取出扩展名如 .pdf → "pdf"
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"仅支持 PDF/TXT/MD，收到 .{ext}")
    if ext == "pdf":
        # io.BytesIO：把内存里的字节"伪装成一个文件对象"，pypdf 就能读了（不用真存到磁盘）
        reader = pypdf.PdfReader(io.BytesIO(data))
        # 逐页 extract_text()（可能返回空串，用 or '' 顶掉），再用换行拼起来
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    # txt / md：errors="replace" 表示遇到无法解码的字节用 � 代替，不抛异常中断
    return data.decode("utf-8", errors="replace")


# ---------- 知识库 ----------

def create_kb(db: Session, payload: KnowledgeBaseCreate) -> KnowledgeBaseOut:
    """创建知识库。重名返回 409。"""
    if db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == payload.name)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"知识库 '{payload.name}' 已存在")
    kb = KnowledgeBase(name=payload.name, description=payload.description)
    db.add(kb)
    db.commit()
    db.refresh(kb)
    return _to_kb_out(kb)


def list_kbs(db: Session, page: int = 1, size: int = 20) -> tuple[list[KnowledgeBaseOut], int]:
    """知识库列表 + 总数。对每个库顺手数一下它有多少文档（doc_count）。"""
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
    """上传文档 → 提取文本 → 调 Go 切块 → 向量化 → 写 Chroma → 更新台账。

    【设计取舍：同步处理】这一版选择"上传后同步干完所有活再返回"（而不是异步后台）：
    文件小、能立刻给用户反馈（状态直接从处理中→就绪），且不引入后台任务框架（范围收敛）。
    状态机字段（pending/processing/ready/failed）已预留，将来要异步也兼容。

    关键流程（代码里的 try 块就是这条流水线）：
      1. 先在 documents 表建一行台账（status=processing）
      2. 提取文字 → 切块 → 向量化 → 写入向量库
      3. 成功 → status=ready，记录切了几块；失败 → status=failed，记录原因
    """
    _kb_or_404(db, kb_id)
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in ALLOWED_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"仅支持 PDF/TXT/MD，收到 .{ext}")

    # 先落台账，拿到 doc.id（下面向量库元数据要用它）
    doc = Document(
        kb_id=kb_id, filename=filename, file_type=ext,
        size_bytes=len(data), status="processing",
    )
    db.add(doc)
    db.commit()

    try:
        text = _extract_text(filename, data)   # 1) 提取纯文本
        if not text.strip():
            raise ValueError("未能提取出文本（PDF 可能是扫描图片）")
        chunks = chunker.chunk_text(text)       # 2) 调 Go 服务切块
        embeddings = llm.embed_texts(chunks)    # 3) 每块转成向量
        vector_store.add_document_chunks(kb_id, doc.id, chunks, embeddings)  # 4) 写入向量库
        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.error_msg = ""
    except Exception as e:  # noqa: BLE001 流水线任何一步出错，都统一标记 failed 并记录原因
        # 清理可能已写入的半截向量（防止出错时残留脏数据，也防重复计费）
        try:
            vector_store.delete_document_chunks(doc.id)
        except Exception:  # noqa: BLE001 清理失败不影响主流程
            pass
        doc = db.get(Document, doc.id)  # 重新取（防止会话状态异常）
        doc.status = "failed"
        doc.error_msg = str(e)[:500]    # 只截前 500 字，避免把超长报错塞进数据库

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
    """文档列表 + 总数。传 kb_id 就只看某个知识库的文档；不传就看全部。"""
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
    """删除文档：先清向量，再删台账。

    【为什么必须先清向量】向量库里每个块都是花钱(Embedding)生成的，
    如果文档删了向量却留着，既占空间、检索还会误命中已删除的内容，
    重复上传同一份还会重复计费。所以删除时要同步 from 向量库清掉该文档的所有块。
    """
    doc = _doc_or_404(db, doc_id)
    try:
        vector_store.delete_document_chunks(doc.id)
    except Exception:  # noqa: BLE001 向量清理失败不阻塞删除（记录在案，避免删除卡死）
        pass
    db.delete(doc)
    db.commit()


# ---------- 检索测试 ----------

# 中文关键词切分用简单规则：按"标点/非中文非英文非数字"切，并在"中英交界"再切一刀。
# 这样 "RAG检索" 能拆成 ["RAG", "检索"]，避免中英混写的连续串被整串当成一个词。
# （真正的智能分词要接分词库——模块 6 双路检索时再考虑，这里"够用的朴素切分"。）
def _extract_keywords(query: str) -> list[str]:
    import re
    # 三重切分：
    #  非[中英数]的字符（标点/空格/符号）切一刀
    #  汉字→英文/数字 交界切一刀
    #  英文/数字→汉字 交界切一刀
    parts = re.split(
        r"(?<=[一-鿿])(?=[A-Za-z0-9])|(?<=[A-Za-z0-9])(?=[一-鿿])|[^一-鿿A-Za-z0-9]+",
        query,
    )
    kws: list[str] = []
    for p in parts:
        p = p.strip()
        if len(p) >= 2:  # 至少 2 个字符才算关键词（单字太宽泛，命中率失真）
            kws.append(p)
    return kws


def search_kb(db: Session, kb_id: int, query: str, top_k: int = 5) -> SearchResponse:
    """检索（"字面先行 + 语义兜底"双层，按我方需求定制）：
      1. 把查询拆成关键词，先检查这些词在文档原文里是否真实存在
      2. 全部不存在 → 直接返回空（搜"红烧肉"明确告诉你没有，而不是硬凑）
      3. 存在 → 走向量找最相关，且只保留"既含关键词、向量又相近"的块
    """
    _kb_or_404(db, kb_id)
    if not query.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="query 不能为空")

    # ---- 第一层：字面验证 ----
    keywords = _extract_keywords(query)
    if keywords and not vector_store.keyword_exists(kb_id, keywords):
        return SearchResponse(query=query, kb_id=kb_id, results=[])  # 库里根本没有这个词

    # ---- 第二层：语义检索 ----
    emb = llm.embed_one(query)  # 把查询也转成向量，才能和文档向量比"像不像"
    try:
        hits = vector_store.query(kb_id, emb, top_k)
    except Exception:  # noqa: BLE001 空库/无命中时的兜底
        hits = []
    results = []
    for text, score, meta in hits:
        # 双重约束去噪声：块文本必须真的含某个关键词，才保留（字面+语义都过才给用户）
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
    # 按相似度从近到远排序（score 为余弦距离，越小越像）
    results.sort(key=lambda r: r.score)
    # 相关性阈值过滤：score 超过阈值说明"其实很不像"，剔除掉
    results = [r for r in results if r.score <= SEARCH_RELEVANCE_THRESHOLD]
    return SearchResponse(query=query, kb_id=kb_id, results=results)