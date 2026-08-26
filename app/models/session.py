"""会话元数据表（sessions）。

【大白话】模块 4 的"双层存储"设计：
- MySQL sessions 表（本文件）：只记"会话存在过"——谁开的、几句了、最后活跃时间。
- Redis（见 context_service）：存消息本体，带 TTL 自动过期。

【为什么分两层】
- 消息内容是"临时性"的（过期就该消失），放内存型 Redis 又快又省心；
  但如果全放 Redis，TTL 一到连"有过这个会话"都查不到了。
- 所以 MySQL 留一层"户口"：列表页能展示历史会话、统计有据可查；
  消息本体过期不影响台账。
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Session(Base):
    """一次多轮对话 = 一个 Session。每行 = 一场对话的"户口"。"""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # 会话号：前端生成传来的唯一串（UUID 式）。用业务号而不是自增 id 当对外标识，
    # 是为了不让外部猜到内部主键（安全习惯），且前端可以离线生成。
    session_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # agent_id 可空 + 删除置空（ondelete="SET NULL"）：
    # 删掉 Agent 时会话台账保留（历史不该消失），只是"属于谁"变成未知。
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), default="")   # 会话标题（首轮消息截断，列表展示用）
    message_count: Mapped[int] = mapped_column(Integer, default=0)  # 消息条数（用户+助手合计）
    is_active: Mapped[bool] = mapped_column(default=True)          # 预留：将来支持"删除/归档"会话
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )