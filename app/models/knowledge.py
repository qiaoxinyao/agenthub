"""知识库相关数据模型：knowledge_bases 表 + documents 表。

【大白话】
- knowledge_bases：一个"知识库"就是一个装资料的柜子（比如"产品手册库"）。
- documents：柜子里装的每一份文件（哪份文档、处理完没有、切了几块）。

【关键设计】文档的正文和切块向量**不放进 MySQL**：
- 上传时内存里读完就处理，不存正文；
- 切块后的段落+向量存在 Chroma（专门的向量库），MySQL 只记"台账"。
这样 MySQL 表保持轻、职责单一（各存储各司其职）。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class KnowledgeBase(Base):
    """知识库表：每行 = 一个知识库。"""

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # 名称唯一
    description: Mapped[str] = mapped_column(String(255), default="")           # 描述
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Document(Base):
    """文档台账表：每行 = 一份上传过的文件（正文/向量在 Chroma，这里只记"状态"）。

    状态 status 的取值（设计成字符串，方便人读）：
      pending   排队中（还没开始处理）
      processing 处理中（切块+向量化进行时）
      ready     处理完成，可被检索
      failed    处理失败（error_msg 记录原因）
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False)  # 属于哪个库
    filename: Mapped[str] = mapped_column(String(255), nullable=False)   # 原始文件名
    file_type: Mapped[str] = mapped_column(String(8), nullable=False)    # pdf / txt / md
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)          # 文件大小（字节）
    status: Mapped[str] = mapped_column(String(16), default="pending")   # 处理状态（见上面说明）
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)         # 切了几块（处理完回填）
    error_msg: Mapped[str] = mapped_column(String(512), default="")      # 失败原因（失败时填，方便排查）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())