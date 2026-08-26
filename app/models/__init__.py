"""数据模型注册表。

【大白话】SQLAlchemy 的建表命令 create_all 需要知道"项目里一共有哪些表"。
这个文件把所有模型 import 一遍，等于把表清单汇总到一个地方。
以后每新增一张表模型，就在这里加一行 import。
"""

from app.models.agent import Agent, AgentKbBinding
from app.models.knowledge import Document, KnowledgeBase
from app.models.session import Session

# __all__：声明"这个包对外提供哪些名字"，方便 from app.models import * 时一次拿全
__all__ = ["Agent", "AgentKbBinding", "Document", "KnowledgeBase", "Session"]