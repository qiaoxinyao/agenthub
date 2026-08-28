"""工具调用日志表（tool_call_logs）。

【大白话】每次 Agent 调用了哪个工具、传了什么参数、返回了什么、花了多久，
都记一行。用途有两层：
1. 业务：会话审计、排查"这个回答为什么这样"
2. 演示：一句"调用了什么工具、结果是什么"清清楚楚，这是"工具调用留证"的证据

注意：它和生产数据不同——它只记"发生过什么"，不承载主流程。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ToolCallLog(Base):
    """一次工具调用 = 一行。"""

    __tablename__ = "tool_call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # 哪个会话里调的
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="SET NULL"), nullable=True  # 删 Agent 时日志保留
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)  # 工具名，如 kb_search
    # 入参/出参存 JSON：灵活，工具五花八门，不用为此设计多张表
    params: Mapped[dict] = mapped_column(JSON, default=dict)   # 调用参数（如 {"query":"xxx"}）
    result: Mapped[dict] = mapped_column(JSON, default=dict)   # 返回结果（截断后的）
    status: Mapped[str] = mapped_column(String(16), default="success")  # success / error
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)  # 耗时
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())