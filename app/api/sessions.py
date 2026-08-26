"""会话管理的 RESTful 接口：GET /api/sessions（模块 4 配套）。

【大白话】列出"有过哪些对话"。数据来自 MySQL sessions 表（持久台账），
所以即使 Redis 里的消息过期了，会话列表还在。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.models import Session
from app.services.agent_service import to_out

router = APIRouter(tags=["上下文管理"])


# 注册 GET 接口（路径 = /api/sessions）：会话列表，可按 agent_id 过滤。
# 响应用手写的 dict 结构：只挑列表页需要的字段，不暴露内部细节
@router.get("/sessions", summary="会话列表（可按 Agent 过滤）")
def list_sessions(
    # Query() = URL 查询参数；不传 agent_id 就列全部会话
    agent_id: int | None = Query(default=None, description="按 Agent 过滤"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: DBSession = Depends(get_db),
):
    """列出会话台账（标题/条数/时间）。按最后活跃时间倒序——最近的在最上面。"""
    stmt = select(Session)
    count_stmt = select(func.count()).select_from(Session)
    if agent_id is not None:
        stmt = stmt.where(Session.agent_id == agent_id)
        count_stmt = count_stmt.where(Session.agent_id == agent_id)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(Session.updated_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return {
        "items": [
            {
                "session_id": s.session_id,
                "agent_id": s.agent_id,
                "title": s.title,
                "message_count": s.message_count,
                "created_at": to_out_iso(s.created_at),
                "updated_at": to_out_iso(s.updated_at),
            }
            for s in rows
        ],
        "total": total,
    }


def to_out_iso(dt):
    """datetime 转 ISO 字符串（JSON 里日期要用字符串；None 安全转空串）。"""
    return dt.isoformat() if dt else ""