"""AgentHub 后端入口。

启动：uvicorn app.main:app --reload --port 8000
文档：http://127.0.0.1:8000/docs（Swagger 自动生成）
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.db import init_db

# 控制台前端：web/ 目录由 FastAPI 直接托管，访问 http://127.0.0.1:8000/ui
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时按模型建表（开发期够用，不引入迁移工具）
    init_db()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="面向企业内部的 Agent 应用管理平台后端（简化版 Dify）",
    lifespan=lifespan,
)

# 路由按模块逐步挂载（一次一个功能）：当前有 Agent 管理、知识库管理
from app.api import agents, knowledge  # noqa: E402

app.include_router(agents.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
# 后续模块完成后再挂载：
#   from app.api import chat, sessions, tool_logs
#   app.include_router(chat.router, prefix="/api")
#   ...

# 控制台前端（静态托管）：/ui → web/index.html
app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "ui": "/ui",
        "health": "/health",
        "message": "AgentHub 后端已启动。控制台在 /ui，接口文档在 /docs。",
    }


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}