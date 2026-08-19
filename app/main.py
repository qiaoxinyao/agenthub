"""AgentHub 后端入口。

启动：uvicorn app.main:app --reload --port 8000
文档：http://127.0.0.1:8000/docs（Swagger 自动生成）
"""

from fastapi import FastAPI

from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="面向企业内部的 Agent 应用管理平台后端（简化版 Dify）",
)

# 路由按模块逐步挂载（一次一个功能）：
#   from app.api import agents, knowledge, chat, sessions, tool_logs
#   app.include_router(agents.router, prefix="/api", tags=["Agent 管理"])


@app.get("/", include_in_schema=False)
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
        "message": "AgentHub 后端已启动。去 /docs 看接口文档。",
    }


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}