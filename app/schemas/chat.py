"""对话服务的 Pydantic 请求与响应模型。

【大白话】定义"对话接口"收什么、吐什么。
- ChatRequest：前端发来一条消息要带什么（选哪个助手、哪条会话、说了什么）
- ChatResponse：后端回什么（回答文本 + 会话号 + 用的模型）
"""

import uuid

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """对话请求体。"""

    agent_id: int = Field(..., description="用哪个 Agent 来回答")
    # 会话号：前端生成（推荐 UUID，一串不会重复的随机串）。
    # 模块3 阶段还没存历史（那是模块4 的 Redis），先收下并原样返回，
    # 让"同一会话"有身份，后续多轮就靠它。
    session_id: str = Field(
        default_factory=lambda: uuid.uuid4().hex,
        min_length=1,
        max_length=64,
        description="会话号（推荐前端用 UUID 生成）",
    )
    message: str = Field(..., min_length=1, description="用户说的话")
    stream: bool = Field(default=False, description="true 时后端用 SSE 流式推送回答（打字机效果）")


class ChatResponse(BaseModel):
    """对话响应体。"""

    agent_id: int
    session_id: str
    model: str          # 实际用的哪个模型（方便前端展示/调试）
    reply: str          # 大模型的回答