"""数据库连接与会话管理（SQLAlchemy）。

【大白话】这个文件负责两件事：
1. 建立"项目 → MySQL 数据库"的连接（数据库引擎 engine）。
2. 给每个请求配一个"数据库会话"（相当于给每个来办事的人发一张临时工牌，
   办完事立刻收回并断开，避免连接泄漏）。
它是全项目唯一的 engine/Session 入口，别的地方都从这里拿数据库。
"""

from collections.abc import Generator

from sqlalchemy import create_engine
# DeclarativeBase：写"数据模型"用的基类。
# 你定义一张表 = 写一个继承 Base 的类（比如下面的模型放 models/ 里），
# SQLAlchemy 会自动把它变成一张真实的数据库表。
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。

    【为什么要有基类】ORM（对象关系映射）= 把 Python 类和数据库表对应起来。
    所有表模型都要继承 Base，这样 SQLAlchemy 才能统一管理"我有哪些表"，
    建表命令 create_all 才知道要建哪些。
    """


# 创建数据库引擎 = 建立真正连数据库的通道。
# create_engine 会把 settings.mysql_url（形如 mysql+pymysql://...）解析成一个能连数据库的对象。
engine = create_engine(
    settings.mysql_url,
    pool_pre_ping=True,  # 每次用连接前先"探个活"——万一数据库重启过，旧连接失效，能自动换新的
    echo=False,          # 设为 True 会在控制台打印所有 SQL 语句（调试用；平时关掉，太吵）
)

# sessionmaker：一个"生产数据库会话的工厂"。
# 它本身不连接，每次调用才真正开一个会话。绑定上面那个 engine。
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 的"依赖注入"，给每个请求发一个数据库会话，用完必关。

    【大白话】FastAPI 的每个接口都可以声明"我依赖一个数据库会话"，
    框架会在请求开始时调用这个函数给你一个 db，请求结束自动把连接还回去。
    这样就不会出现"哪个接口用完忘了关连接、把数据库连接池撑爆"的问题。

    用法：在接口函数的参数里写 db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db   # 把这个会话交给接口用
    finally:
        db.close()  # 接口处理完（哪怕报错），也保证关闭


def init_db() -> None:
    """启动时按模型自动建表（开发期够用；不引入 Alembic，见 decisions.md）。

    【为什么用它建表】我们表只有 6 张，且是开发期，create_all 足够。
    引入 Alembic（专门的迁移工具）对这个小项目是"过度设计"——体现范围收敛意识。
    """
    import app.models  # noqa: F401   # 确保所有模型都被 import 进内存、注册到 Base.metadata
    Base.metadata.create_all(bind=engine)  # 把 Base 上已注册的所有表，在数据库里建出来（已存在的跳过）