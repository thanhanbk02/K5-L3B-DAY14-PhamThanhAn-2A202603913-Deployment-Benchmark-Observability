"""Config — mọi giá trị đọc từ biến môi trường."""
import os
from dataclasses import dataclass, field


def _float_env(*names: str, default: float) -> float:
    for name in names:
        raw = os.getenv(name)
        if raw:
            return float(raw)
    return default


@dataclass
class Settings:
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", ""))
    rate_limit_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    )
    daily_budget_usd: float = field(
        default_factory=lambda: _float_env("DAILY_BUDGET_USD", "MONTHLY_BUDGET_USD", default=1.0)
    )


settings = Settings()
