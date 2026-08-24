"""知识库管理的 6 个 RESTful 接口：知识库建/列 + 文档上传/列/删 + 检索测试。

【大白话】同 api/agents.py：薄薄一层，负责"路由 + 参数 + 把活交给 service"。
前端控制台和 Swagger 调的都是这些接口。
"""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.knowledge import (
    DocumentList,
    DocumentOut,
    KnowledgeBaseCreate,
    KnowledgeBaseList,
    KnowledgeBaseOut,
    SearchResponse,
)
from app.services import knowledge_service

# tags=["知识库管理"]：在 Swagger 归到"知识库管理"分组。路径不带前缀，由 main.py 统一加 /api
router = APIRouter(tags=["知识库管理"])


@router.post("/knowledge-bases", response_model=KnowledgeBaseOut, status_code=201, summary="创建知识库")
def create_kb(payload: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    """创建一个知识库（比如"产品手册库"）。"""
    return knowledge_service.create_kb(db, payload)


@router.get("/knowledge-bases", response_model=KnowledgeBaseList, summary="知识库列表")
def list_kbs(
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """列出所有知识库（含每个库的文档数）。"""
    items, total = knowledge_service.list_kbs(db, page=page, size=size)
    return {"items": items, "total": total}


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentOut,
    status_code=201,
    summary="上传文档（PDF/TXT/MD，同步切块入库）",
)
def upload_document(
    kb_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传一份文档并切块入库。

    file: UploadFile = File(...) —— 声明这是个"文件上传"参数（multipart/form-data）。
    处理是同步的：等它切块+向量化完才返回，所以一个响应就能看到处理结果。
    """
    content = file.file.read()  # UploadFile 的底层文件对象，同步读二进制内容
    return knowledge_service.create_document(db, kb_id, file.filename or "unnamed", content)


@router.get("/documents", response_model=DocumentList, summary="文档列表（可按知识库过滤）")
def list_documents(
    kb_id: int | None = Query(default=None, description="不传则查全部"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """列出文档。传 kb_id 就只看某个知识库。"""
    items, total = knowledge_service.list_documents(db, kb_id=kb_id, page=page, size=size)
    return {"items": items, "total": total}


@router.delete("/documents/{doc_id}", status_code=204, summary="删除文档（同步清理向量）")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """删除文档。会同步把向量库里的内容也清掉（防脏数据 + 防重复计费）。"""
    knowledge_service.delete_document(db, doc_id)


@router.get(
    "/knowledge-bases/{kb_id}/search",
    response_model=SearchResponse,
    summary="检索测试（模块6 前为向量单路）",
)
def search(
    kb_id: int,
    query: str = Query(..., min_length=1, description="检索词"),
    top_k: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """检索测试：在一个知识库内搜与 query 最相关的片段。"""
    return knowledge_service.search_kb(db, kb_id, query, top_k)