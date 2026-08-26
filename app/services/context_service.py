"""上下文管理：会话历史在 Redis 里的存取 + 多轮拼接的"滑窗"策略。

【大白话】这是治好助手"金鱼记忆"的地方。原理：
- 大模型本身没记忆，每次调用只看得见我们传给它的 messages。
- 所以每轮对话后，把"用户问了什么、助手答了什么"追加存进 Redis；
  下次对话前，把最近几轮取出来拼进 messages，模型就"记得"了。

【滑窗策略】历史不能无限拼——消息越多 token 越贵、越慢，还可能超出模型上限。
所以只取"最近 N 轮"（一个窗口），窗口外的老消息自然被挤出。
本版用固定窗口（默认最近 5 轮 = 10 条消息）；"可选摘要"留作后续优化。

【存储格式】Redis 的 List：每个会话一个 key，值为按时间顺序的消息 JSON 串：
  key:   chat:history:{session_id}
  value: ['{"role":"user","content":"我叫小明"}', '{"role":"assistant","content":"你好小明"}', ...]
选 List 的原因：左右两端操作都是 O(1)，天然适合"追加消息 + 截取最近 N 条"。
"""

import json

from redis import Redis

from app.core.redis import get_redis

# 会话历史的过期时间（秒）：2 小时不聊就自动清空。
# 为什么设 TTL：会话是临时数据，无限堆积既占内存也没意义；到期自动删是 Redis 的看家本领。
HISTORY_TTL_SECONDS = 2 * 60 * 60

# 滑窗大小：拼接进 prompt 的"最多轮数"。1 轮 = 1 条用户消息 + 1 条助手回答。
# 可调：调大记得更久但更贵更慢；默认 5 轮是成本与效果的平衡。
MAX_HISTORY_ROUNDS = 5


def _key(session_id: str) -> str:
    """拼出某个会话在 Redis 里的 key。加 chat:history: 前缀是为了不跟其它业务的数据混淆。"""
    return f"chat:history:{session_id}"


def append_message(session_id: str, role: str, content: str, r: Redis | None = None) -> None:
    """往会话末尾追加一条消息，并刷新过期时间。

    【为什么每次都 expire】TTL 是"整个 key"的倒计时。聊一句续一次命，
    保证只要还在持续对话，历史就不会中途消失；停止对话 2 小时后才清空。
    """
    r = r or get_redis()
    k = _key(session_id)
    msg = json.dumps({"role": role, "content": content}, ensure_ascii=False)
    # ensure_ascii=False：中文原样存（可读性好），不转成 \\uXXXX
    r.rpush(k, msg)                       # rpush = 从列表右端（末尾）追加
    r.expire(k, HISTORY_TTL_SECONDS)      # 续命：重置 2 小时倒计时


def get_history(
    session_id: str,
    max_rounds: int = MAX_HISTORY_ROUNDS,
    r: Redis | None = None,
) -> list[dict[str, str]]:
    """取出某会话"最近 max_rounds 轮"的历史（滑窗核心）。

    返回形如 [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}, ...]

    【实现细节】lrange(key, -N, -1) = 取列表最后 N 个元素（负数下标从尾部数），
    一条命令搞定"只拿最近几条"，不用先查总长再算偏移。
    N 取 max_rounds*2：因为 1 轮 = 用户 + 助手两条。
    """
    r = r or get_redis()
    k = _key(session_id)
    n_messages = max_rounds * 2
    raw_list = r.lrange(k, -n_messages, -1)  # 取末尾 N 条
    return [json.loads(x) for x in raw_list]


def clear_history(session_id: str, r: Redis | None = None) -> None:
    """清空某会话的历史（前端"新开会话"时可用）。"""
    r = r or get_redis()
    r.delete(_key(session_id))
