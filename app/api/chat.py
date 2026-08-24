"""对话服务的 RESTful 接口：POST /api/chat。

【大白话】整个平台的"门面接口"：
外部系统、控制台、演示页，都通过这一个接口跟 Agent 对话。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(tags=["对话服务"])


@router.post("/chat", response_model=ChatResponse, summary="对话（agent_id + session_id + message）")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """发送一条消息给指定 Agent，返回它的回答。"""
    return chat_service.chat_message(db, payload)