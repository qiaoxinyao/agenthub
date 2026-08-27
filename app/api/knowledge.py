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

# 声明路由组：tags 是 Swagger 里的分组名；这里不写 prefix，
# 由 main.py 统一加 /api 前缀（每个接口路径里已写全）
router = APIRouter(tags=["知识库管理"])


# 注册 POST 接口（路径 = /api/knowledge-bases）：创建一个知识库
@router.post("/knowledge-bases", response_model=KnowledgeBaseOut, status_code=201, summary="创建知识库")
def create_kb(payload: KnowledgeBaseCreate, db: Session = Depends(get_db)):
    """创建一个知识库（比如"产品手册库"）。"""
    return knowledge_service.create_kb(db, payload)


# 注册 GET 接口（路径 = /api/knowledge-bases）：列出所有知识库
@router.get("/knowledge-bases", response_model=KnowledgeBaseList, summary="知识库列表")
def list_kbs(
    # Query() = URL 查询参数；ge=1 表示最小值 1（页码从 1 起）、le=100 限制每页最多 100 条
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """列出所有知识库（含每个库的文档数）。"""
    items, total = knowledge_service.list_kbs(db, page=page, size=size)
    return {"items": items, "total": total}


# 注册 DELETE 接口（路径 = /api/knowledge-bases/{kb_id}）：
# 删除知识库会级联清理库内文档、向量、Agent 绑定
@router.delete("/knowledge-bases/{kb_id}", status_code=204, summary="删除知识库（级联清文档与绑定）")
def delete_kb(kb_id: int, db: Session = Depends(get_db)):
    """删除一个知识库及其全部内容。"""
    knowledge_service.delete_kb(db, kb_id)


# 注册 POST 接口（路径 = /api/knowledge-bases/{kb_id}/documents）：上传文档。
# 这是唯一带文件上传的接口：{kb_id} 指定传到哪个知识库
@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=DocumentOut,
    status_code=201,
    summary="上传文档（PDF/TXT/MD，同步切块入库）",
)
def upload_document(
    kb_id: int,  # 路径参数：知识库 id
    # File(...) 表示这个参数是"上传的文件"（multipart/form-data 表单）；
    # ... 表示必填。FastAPI 会自动解析 multipart 并包成 UploadFile 对象
    file: UploadFile = File(...),
    db: Session = Depends(get_db),  # 依赖注入：本请求专用的数据库会话
):
    """上传一份文档并切块入库（同步处理：等切块+向量化完才返回）。"""
    content = file.file.read()  # 读出文件的二进制内容（在内存里，不落盘）
    return knowledge_service.create_document(db, kb_id, file.filename or "unnamed", content)


# 注册 GET 接口（路径 = /api/documents）：文档列表，可按 kb_id 过滤
@router.get("/documents", response_model=DocumentList, summary="文档列表（可按知识库过滤）")
def list_documents(
    # kb_id 可选：传了就只看某个库的文档；int | None 表示"整数或都不传"
    kb_id: int | None = Query(default=None, description="不传则查全部"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """列出文档。传 kb_id 就只看某个知识库。"""
    items, total = knowledge_service.list_documents(db, kb_id=kb_id, page=page, size=size)
    return {"items": items, "total": total}


# 注册 DELETE 接口（路径 = /api/documents/{doc_id}）；204 = 删除成功无返回体
@router.get("/documents/{doc_id}/chunks", summary="查看文档内容（入库后的切块）")
def inspect_document(doc_id: int, db: Session = Depends(get_db)):
    """查看一份文档被切块后的内容。文档未就绪时 chunks 为空。"""
    return knowledge_service.inspect_document(db, doc_id)


@router.delete("/documents/{doc_id}", status_code=204, summary="删除文档（同步清理向量）")
def delete_document(doc_id: int, db: Session = Depends(get_db)):
    """删除文档。会同步把向量库里的内容也清掉（防脏数据 + 防重复计费）。"""
    knowledge_service.delete_document(db, doc_id)


# 注册 GET 接口（路径 = /api/knowledge-bases/{kb_id}/search）：检索测试。
# 注意它是 GET 但带业务参数——检索是"只读"操作，所以用 GET 而不是 POST
@router.get(
    "/knowledge-bases/{kb_id}/search",
    response_model=SearchResponse,
    summary="检索测试（模块6 前为向量单路）",
)
def search(
    kb_id: int,  # 路径参数：在哪个知识库里搜
    # Query(..., min_length=1) 里的 ... 表示必填；min_length=1 至少 1 个字符
    query: str = Query(..., min_length=1, description="检索词"),
    top_k: int = Query(default=5, ge=1, le=20),  # 返回最相关的几条（默认 5）
    db: Session = Depends(get_db),
):
    """检索测试：在一个知识库内搜与 query 最相关的片段。"""
    return knowledge_service.search_kb(db, kb_id, query, top_k)