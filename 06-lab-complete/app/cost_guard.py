"""Cost guard. Tổng chi phí trong ngày vượt ngân sách → 402."""
import time

from fastapi import HTTPException

from app.config import settings
from app.redis_client import get_redis

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _cost_key() -> str:
    return "cost:" + time.strftime("%Y-%m-%d")


def _client():
    client = get_redis()
    if client is None:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return client


def _spent() -> float:
    raw = _client().get(_cost_key())
    return float(raw or 0)


def check_budget() -> None:
    try:
        spent = _spent()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    if spent >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    cost = (input_tokens / 1000) * PRICE_INPUT_PER_1K + (output_tokens / 1000) * PRICE_OUTPUT_PER_1K
    try:
        client = _client()
        client.incrbyfloat(_cost_key(), cost)
        client.expire(_cost_key(), 3 * 24 * 3600)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Redis unavailable") from exc
    return cost
