"""工具调用相关的数据结构（Pydantic）。

大白话：
- ToolSpec：一个工具的"双件套"——definition（给大模型的说明书）+ execute（真执行的函数）
- ToolCallContext：工具执行时需要的"外部环境"（数据库会话、Agent 配置），
  因为工具不是纯函数，有的要查数据库（如知识库检索）
"""

from typing import Awaitable, Callable

from pydantic import BaseModel

from app.schemas.agent import AgentOut


class ToolSpec(BaseModel):
    """一个工具的规格：说明 + 执行函数。"""

    name: str
    definition: dict                      # 给模型看的说明书（含 parameters schema）
    execute: Callable                     # 真执行：execute(ctx, **kwargs) -> dict


class ToolCallContext(BaseModel):
    """传给工具执行的"环境"：Agent 配置 + （未来的 db 等）。"""

    agent: AgentOut                       # Agent 的配置（工具常需要知道绑定了哪些知识库等）