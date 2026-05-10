"""Runtime configuration loaded from config/settings.yaml + env overrides."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheConfig(BaseModel):
    db_path: str = "data/cache.db"
    parquet_root: str = "data/holdings"


class IngestConfig(BaseModel):
    request_sleep_seconds: float = 0.2
    max_retries: int = 3
    default_lookback_years: int = 5


class UIConfig(BaseModel):
    default_page_size: int = 50
    cache_ttl_seconds: int = 3600


class LLMConfig(BaseModel):
    model: str = "claude-sonnet-4-6"
    max_tokens_etf: int = 700
    max_tokens_strategy: int = 1100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__",
        env_prefix="ETF_DASH__",
        case_sensitive=False,
    )

    cache: CacheConfig = CacheConfig()
    ingest: IngestConfig = IngestConfig()
    ui: UIConfig = UIConfig()
    llm: LLMConfig = LLMConfig()


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_YAML = PROJECT_ROOT / "config" / "settings.yaml"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings.yaml once, then overlay environment variables."""
    file_data: dict = {}
    if SETTINGS_YAML.exists():
        file_data = yaml.safe_load(SETTINGS_YAML.read_text()) or {}
    return Settings(**file_data)


def resolve_path(relative: str) -> Path:
    """Resolve a settings-relative path against PROJECT_ROOT if not absolute."""
    p = Path(relative)
    return p if p.is_absolute() else PROJECT_ROOT / p
