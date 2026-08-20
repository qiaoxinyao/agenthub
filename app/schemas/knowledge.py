"""知识库/文档/检索的 Pydantic 请求与响应模型。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------- 知识库 ----------

class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    doc_count: int = 0      # 库内文档数（service 计算）
    created_at: datetime


class KnowledgeBaseList(BaseModel):
    items: list[KnowledgeBaseOut]
    total: int


# ---------- 文档 ----------

class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kb_id: int
    filename: str
    file_type: str
    size_bytes: int
    status: str             # pending/processing/ready/failed
    chunk_count: int
    error_msg: str
    created_at: datetime


class DocumentList(BaseModel):
    items: list[DocumentOut]
    total: int


# ---------- 检索 ----------

class SearchResult(BaseModel):
    chunk_text: str
    score: float            # 相似度（cosine 距离越小越像，demo 里直接展示）
    document_id: int
    filename: str
    chunk_index: int


class SearchResponse(BaseModel):
    query: str
    kb_id: int
    results: list[SearchResult]