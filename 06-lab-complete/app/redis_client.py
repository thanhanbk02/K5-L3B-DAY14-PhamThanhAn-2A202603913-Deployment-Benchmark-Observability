"""Redis client. Không ping lúc import — app phải khởi động được khi Redis chưa có."""
import redis

from app.config import settings

_client = None


def get_redis():
    """Trả về client, hoặc None nếu không cấu hình REDIS_URL."""
    global _client
    if _client is not None or not settings.redis_url:
        return _client
    _client = redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    return _client


def redis_healthy() -> bool:
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except redis.RedisError:
        return False
