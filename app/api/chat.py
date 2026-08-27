"""对话服务的 RESTful 接口：POST /api/chat。

【大白话】整个平台的"门面接口"：
- 默认（stream=false）：一次性返回完整回答（JSON）。
- stream=true：用 SSE 流式逐块推送回答（打字机效果），前端收到一个字显示一个字。
"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(tags=["对话服务"])


# 注册 POST 接口（路径 = /api/chat）：发一条消息、拿一句回答。
# 用 POST 而不是 GET：消息放在请求体里（比 URL 参数安全、能传长文本）
@router.post("/chat", response_model=ChatResponse, summary="对话（agent_id + session_id + message，可流式）")
def chat(payload: ChatRequest, db: Session = Depends(get_db)):
    """发送一条消息给指定 Agent。

    payload.stream 为 true 时返回 SSE 流（text/event-stream），
    每行是 data: {...} 的 JSON（type=delta 表示回答片段，type=tool 表示正在调用工具）。
    """
    if payload.stream:
        # StreamingResponse 会把生成器逐块写给客户端（不走 response_model）
        return StreamingResponse(
            chat_service.chat_stream(db, payload),
            media_type="text/event-stream",
        )
    return chat_service.chat_message(db, payload)