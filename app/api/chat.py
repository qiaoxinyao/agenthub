"""对话服务的 RESTful 接口：POST /api/chat。

【大白话】整个平台的"门面接口"：
外部系统、控制台、演示页，都通过这一个接口跟 Agent 对话。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

# 声明路由组：tags 是 Swagger 里的分组名；路径前缀由 main.py 统一加 /api
router = APIRouter(tags=["对话服务"])


# 注册 POST 接口（路径 = /api/chat）：发一条消息、拿一句回答。
# 用 POST 而不是 GET：因为消息内容放在请求体里（比 URL 参数安全、能传长文本）
@router.post("/chat", response_model=ChatResponse, summary="对话（agent_id + session_id + message）")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """发送一条消息给指定 Agent，返回它的回答。"""
    return chat_service.chat_message(db, payload)