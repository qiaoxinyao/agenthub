"""工具调用日志查询接口：GET /api/tool-call-logs（模块 5 配套）。

【大白话】把 tool_call_logs 表里的记录列出来。
控制台"工具日志"页签就靠它展示：哪些会话、调了哪个工具、参数/结果、耗时。
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DBSession

from app.core.db import get_db
from app.models import ToolCallLog

router = APIRouter(tags=["工具调用"])


# 注册 GET 接口（路径 = /api/tool-call-logs）：
# 可按 session_id / tool_name 过滤；按时间倒序，最新在前
@router.get("/tool-call-logs", summary="工具调用日志（可按会话/工具过滤）")
def list_tool_logs(
    session_id: str | None = Query(default=None, description="按会话号过滤"),
    tool_name: str | None = Query(default=None, description="按工具名过滤"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: DBSession = Depends(get_db),
):
    """列出工具调用日志。"""
    stmt = select(ToolCallLog)
    count_stmt = select(func.count()).select_from(ToolCallLog)
    if session_id:
        stmt = stmt.where(ToolCallLog.session_id == session_id)
        count_stmt = count_stmt.where(ToolCallLog.session_id == session_id)
    if tool_name:
        stmt = stmt.where(ToolCallLog.tool_name == tool_name)
        count_stmt = count_stmt.where(ToolCallLog.tool_name == tool_name)

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(ToolCallLog.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    return {
        "items": [
            {
                "id": r.id,
                "session_id": r.session_id,
                "agent_id": r.agent_id,
                "tool_name": r.tool_name,
                "params": r.params,
                "result": r.result,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
        "total": total,
    }