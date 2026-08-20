"""数据模型注册表：让 Base.metadata 能发现所有表。新模型在这里导出。"""

from app.models.agent import Agent, AgentKbBinding
from app.models.knowledge import Document, KnowledgeBase

__all__ = ["Agent", "AgentKbBinding", "Document", "KnowledgeBase"]