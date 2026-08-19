"""数据库连接与会话管理（SQLAlchemy）。全项目唯一的 engine/Session 入口。"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类，create_all 依赖它注册的表。"""


engine = create_engine(
    settings.mysql_url,
    pool_pre_ping=True,   # 取连接前先探活，服务重启后连接不失效
    echo=False,           # 想调试 SQL 时改为 True
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends 用的依赖：每个请求一个会话，用后必关。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """按模型建表（开发期够用；不引入 Alembic，见 decisions.md）。"""
    import app.models  # noqa: F401  确保所有模型注册进 Base.metadata
    Base.metadata.create_all(bind=engine)