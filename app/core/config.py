"""集中读取 .env / 环境变量。这是全项目唯一读配置的地方。

【大白话】这个文件是整个项目的"总配电房"。
- 你在 .env 文件里填的各种配置（密钥、数据库地址、模型名……），都从这里读出来。
- 业务代码里别直接去翻环境变量，统一找这里要，以后改配置只改 .env 就行。
"""

from functools import lru_cache

# pydantic-settings：一个把"环境变量/.env 文件"自动变成「规整配置对象」的库。
# 我们用下面这个 Settings 类描述"有哪些配置项"，
# 启动时它会自动去读 .env 文件里同名（大小写不敏感）的变量来填充。
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有配置项都在这里定义。.env 里的同名变量会自动覆盖默认值。

    【说明】每一行 = 一个配置项。左边是字段名（代码里用 settings.xxx 读它），
    右边是默认值。假如 .env 里写了 MYSQL_HOST=xxx，这里 mysql_host 就会被覆盖。
    """

    model_config = SettingsConfigDict(
        env_file=".env",       # 从项目根目录的 .env 文件读取（已被 gitignore 忽略，不会上传）
        env_file_encoding="utf-8",   # 文件编码（中文注释也认）
        extra="ignore",        # .env 里多余键直接忽略，防止手滑写错字段名导致启动报错
    )

    # ---- 应用基础信息 ----
    app_name: str = "AgentHub"   # 项目显示名（出现在 /docs 标题、/health 返回里）
    app_version: str = "0.1.0"   # 版本号
    debug: bool = True           # 调试模式开关（开发期 True；以后上线要改 False 关掉调试信息）

    # ---- 大模型（阿里云百炼 / OpenAI 兼容端点）----
    # 【重点】这就是"模型抽象层"的开关：
    #   改下面三个 .env 配置，就能换模型/换厂商，业务代码一行都不用动。
    dashscope_api_key: str = ""       # 对应环境变量 DASHSCOPE_API_KEY：你的百炼密钥
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 对应 LLM_BASE_URL：百炼的 OpenAI 兼容接口地址
    chat_model: str = "qwen3.7-plus"  # 对应 CHAT_MODEL：对话用的模型（用户账号有免费额度）
    embedding_model: str = "text-embedding-v4"  # 对应 EMBEDDING_MODEL：把文字变成向量用的模型

    # ---- MySQL（模块1 起用到：存 Agent 配置、文档台账等业务数据）----
    mysql_host: str = "127.0.0.1"     # 数据库地址（本机开发就是 127.0.0.1）
    mysql_port: int = 3306            # MySQL 默认端口
    mysql_user: str = "root"          # 登录账号
    mysql_password: str = ""          # 登录密码
    mysql_database: str = "agenthub"  # 用哪个库

    # ---- Redis（模块4 起用到：存多轮会话历史，天然带过期）----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379           # Redis 默认端口
    redis_db: int = 0                 # 用的第几个"格子"（Redis 里可以分多个库，用 0 号）

    # ---- Chroma 向量库（模块2 起用到：存文档切块后的向量，做语义检索）----
    chroma_dir: str = "./data/chroma"  # 向量数据存本地哪个文件夹（data/ 已被 gitignore）

    # ---- Go 切分微服务（模块2 起用到：负责把长文本切成小块）----
    chunker_url: str = "http://127.0.0.1:8080"  # Go 服务监听地址

    # ---- Elasticsearch（模块6 起用到：关键词检索，配合向量做双路检索）----
    es_host: str = "http://127.0.0.1:9200"

    @property
    def mysql_url(self) -> str:
        """拼出 SQLAlchemy 需要的 MySQL 连接串（模块1 起用）。

        【为什么单独写个方法】连接串是"一堆配置拼起来的字符串"，
        写在属性里，任何需要连数据库的地方直接 settings.mysql_url 拿，不用到处拼。
        """
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
            # charset=utf8mb4：用完整的 UTF-8，中文（包括 emoji）都能存
        )

    @property
    def redis_url(self) -> str:
        """拼出 Redis 连接串（模块4 起用）。"""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


# lru_cache：让 get_settings() 的结果只算一次并缓存。
# 【为什么】Settings 会被很多地方 import，如果每次都新建实例，等于反复读文件、建一堆对象，
# 没必要。加缓存后整个进程只初始化一次，节省开销。
@lru_cache
def get_settings() -> Settings:
    """获取配置对象（带缓存，全局唯一）。"""
    return Settings()


# 模块级"单例"：其它文件这样 import 后直接用，不用自己调 get_settings()
#   用法：from app.core.config import settings
settings = get_settings()