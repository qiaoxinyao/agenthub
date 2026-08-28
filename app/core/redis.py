"""Redis 连接管理。全项目唯一直接操作 Redis 的入口（业务层通过 context_service 用它）。

【大白话】Redis 是一个"把数据放内存里"的极快数据库，最大的特点是：
- 快：读写都是微秒级（MySQL 是毫秒级）
- 自带过期：存数据时可以指定"多少秒后自动删除"（TTL）

这两点正好契合"会话历史"的需求：聊天记录要读得快、且一段时间不聊就该清掉。
所以设计为：消息内容存 Redis（带 TTL 自动过期），元数据存 MySQL。
"""

import redis

from app.core.config import settings

# 缓存的连接池客户端。None = 还没建。
_r: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """惰性单例：拿到 Redis 客户端。

    【为什么用 decode_responses=True】Redis 存的都是字节，默认取出来是 b"xxx"；
    加这个参数让它自动解码成普通字符串 "xxx"，业务代码少写一堆 decode()。
    【为什么 protocol=2】redis-py 8 默认用 RESP3 协议握手（发 HELLO 命令），
    而 HELLO 是 Redis 6 才有的命令；开发机的 Redis 5.0 不认识会直接报错。
    显式锁 RESP2 协议（新旧服务器都支持），兼容性最好。
    【为什么有 ping】连接可能因 Redis 重启而失效，每次拿客户端时探活最稳。
    """
    global _r
    if _r is None:
        _r = redis.Redis.from_url(
            settings.redis_url,          # 形如 redis://127.0.0.1:6379/0，来自 .env
            decode_responses=True,
            protocol=2,                  # 锁定 RESP2：兼容 Redis 5.x 开发环境
        )
    _r.ping()  # 探活：连不上直接抛异常，让问题尽早暴露
    return _r