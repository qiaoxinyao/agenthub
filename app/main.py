"""AgentHub 后端入口。

【大白话】这是整个后端程序的"大门口"：
- 启动时创建 FastAPI 应用（相当于把餐厅开起来）
- 把各个模块的路由"挂"进来（相当于把菜品的窗口摆好）
- 提供一个静态前端入口 /ui（相当于门口的展示柜）
- 提供 /health 健康检查（阿里云/监控用它确认你活着）

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
    """应用"生命周期"：启动时 / 关闭时执行的挂钩。

    【大白话】这里放"服务启动时要做的准备工作"。我们只有一件事：
    启动时按数据模型自动建表（如果表还不存在）。the `yield` 之前是启动前、之后是关闭后。
    """
    # 启动时按模型建表（开发期够用，不引入迁移工具）
    init_db()
    yield


# 创建 FastAPI 应用本体。title/version/description 会显示在 /docs 页面顶部。
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="面向企业内部的 Agent 应用管理平台后端（简化版 Dify）",
    lifespan=lifespan,
)

# 路由按模块逐步挂载（一次一个功能）：invoke include_router 把某个模块的所有接口接进来。
# prefix="/api"：统一让所有接口都以 /api 开头（比如 /api/agents、/api/knowledge-bases）
from app.api import agents, chat, knowledge, sessions, tool_logs  # noqa: E402

app.include_router(agents.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(tool_logs.router, prefix="/api")

# 控制台前端（静态托管）：/ui → web/index.html
# html=True：访问 /ui 时自动返回 index.html（相当于"打开这个文件夹时默认给首页"）
app.mount("/ui", StaticFiles(directory=WEB_DIR, html=True), name="ui")


@app.get("/", include_in_schema=False)
def root():
    """首页接口：给个导航信息，方便人打开根路径就知道去哪。include_in_schema=False = 不出现在 Swagger 里。"""
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
    """健康检查：监控/部署系统用它确认服务活着。返回固定 JSON。"""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}