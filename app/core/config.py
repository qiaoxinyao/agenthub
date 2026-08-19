"""集中读取 .env / 环境变量。这是全项目唯一读配置的地方，业务代码一律不直接访问 os.environ。"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """所有配置项都在这里定义。.env 里的同名变量（大小写不敏感）会自动覆盖默认值。"""

    model_config = SettingsConfigDict(
        env_file=".env",       # 从项目根目录的 .env 读（已被 gitignore 忽略）
        env_file_encoding="utf-8",
        extra="ignore",        # 忽略 .env 里多余键，防止手滑写错字段名直接报错
    )

    # ---- 应用 ----
    app_name: str = "AgentHub"
    app_version: str = "0.1.0"
    debug: bool = True

    # ---- 大模型（阿里云百炼 / OpenAI 兼容端点）----
    # 模型抽象层：改 .env 的这三项即可切换模型/厂商，业务代码零改动
    dashscope_api_key: str = ""       # 对应环境变量 DASHSCOPE_API_KEY
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 对应 LLM_BASE_URL
    chat_model: str = "qwen-turbo"    # 对应 CHAT_MODEL
    embedding_model: str = "text-embedding-v4"  # 对应 EMBEDDING_MODEL

    # ---- MySQL（模块1 起用到）----
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "agenthub"

    # ---- Redis（模块4 起用到）----
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0

    # ---- Chroma 向量库（模块2 起用到）----
    chroma_dir: str = "./data/chroma"

    # ---- Go 切分微服务（模块2 起用到）----
    chunker_url: str = "http://127.0.0.1:8080"

    # ---- Elasticsearch（模块6 起用到）----
    es_host: str = "http://127.0.0.1:9200"

    @property
    def mysql_url(self) -> str:
        """SQLAlchemy 用的连接串（模块1 起用）。"""
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        """Redis 连接串（模块4 起用）。"""
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    """带缓存，整个进程只初始化一次。"""
    return Settings()


# 模块级单例，其他文件直接 from app.core.config import settings
settings = get_settings()