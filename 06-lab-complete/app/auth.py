"""API key. Thiếu hoặc sai header X-API-Key → 401."""
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="Missing or invalid API key")
    return api_key
