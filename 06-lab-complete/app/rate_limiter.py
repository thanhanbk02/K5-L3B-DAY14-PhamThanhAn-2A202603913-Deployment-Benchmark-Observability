"""Sliding window rate limit. Bộ đếm nằm trong Redis để còn sau khi restart."""
import time
import uuid

from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis

_WINDOW_SECONDS = 60
_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
  local score = 0
  if oldest[2] then score = tonumber(oldest[2]) end
  return {0, count, score}
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window + 5)
return {1, count + 1, 0}
"""


def check_rate_limit(key: str) -> None:
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    now = time.time()
    try:
        allowed, _count, oldest = client.eval(
            _SCRIPT,
            1,
            f"rl:{key}",
            now,
            _WINDOW_SECONDS,
            settings.rate_limit_per_minute,
            f"{now}:{uuid.uuid4().hex}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    if int(allowed) == 1:
        return
    retry_after = max(1, int(float(oldest) + _WINDOW_SECONDS - now) + 1)
    raise HTTPException(
        status_code=429,
        detail="Rate limit exceeded",
        headers={"Retry-After": str(retry_after)},
    )
