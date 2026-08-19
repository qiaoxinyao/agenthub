"""Agent 相关数据模型：agents 表 + agent_kb_bindings 绑定表。

注：agent_kb_bindings.knowledge_base_id 暂不设外键——
knowledge_bases 表在模块 2 才建立，届时补齐 FK（见 decisions.md）。
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    prompt_template: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str] = mapped_column(String(64), default="qwen-turbo")
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    max_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    use_rag: Mapped[bool] = mapped_column(Boolean, default=False)
    tools: Mapped[list] = mapped_column(JSON, default=list)   # 绑定的工具名列表，如 ["kb_search", "get_time"]
    status: Mapped[int] = mapped_column(Integer, default=1)   # 1=启用 0=停用
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # 与绑定表的一对多关系；删 Agent 时级联清空绑定行
    bindings: Mapped[list["AgentKbBinding"]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentKbBinding(Base):
    __tablename__ = "agent_kb_bindings"
    __table_args__ = (UniqueConstraint("agent_id", "knowledge_base_id", name="uq_agent_kb"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_id: Mapped[int] = mapped_column(ForeignKey("agents.id"), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(Integer, nullable=False)  # 模块2 补 FK
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    agent: Mapped[Agent] = relationship(back_populates="bindings")