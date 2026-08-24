"""知识库/文档/检索的 Pydantic 请求与响应模型。

【大白话】同 schemas/agent.py：定义"接口收什么、吐什么"的格式。
Create=请求结构、Out=返回值结构、List=分页结构、Search*=检索结果结构。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- 知识库 ----------

class KnowledgeBaseCreate(BaseModel):
    """创建知识库的请求体。name 必填、唯一。"""

    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)


class KnowledgeBaseOut(BaseModel):
    """知识库的响应模型。doc_count（文档数）是计算出来的，由 service 填。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    doc_count: int = 0      # 库内文档数（service 计算）；默认 0 防止某些返回路径没填
    created_at: datetime


class KnowledgeBaseList(BaseModel):
    """知识库分页列表。"""

    items: list[KnowledgeBaseOut]
    total: int


# ---------- 文档 ----------

class DocumentOut(BaseModel):
    """文档的响应模型（返回给前端的样子，就是 documents 表的字段）。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    filename: str
    file_type: str
    size_bytes: int
    status: str             # pending / processing / ready / failed
    chunk_count: int
    error_msg: str
    created_at: datetime


class DocumentList(BaseModel):
    """文档分页列表。"""

    items: list[DocumentOut]
    total: int


# ---------- 检索 ----------

class SearchResult(BaseModel):
    """一条检索命中结果：一段被检索到的原文 + 它来自哪 + 相关度分数。"""

    chunk_text: str
    score: float            # 相似度分数（chroma 返回的是"余弦距离"，越小越像）
    document_id: int
    filename: str
    chunk_index: int


class SearchResponse(BaseModel):
    """一次检索的完整返回：原 query + 命中的结果列表。"""

    query: str
    kb_id: int
    results: list[SearchResult]