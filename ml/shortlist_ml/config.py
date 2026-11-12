from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """ML/ingestion settings. All overridable via env vars or .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://shortlist:shortlist_dev_only@localhost:5433/shortlist"
    raw_dir: Path = Path("data/raw")
    raw_retention_days: int = 14
    request_interval_s: float = 1.0  # minimum gap between requests to the same host
    timezone: str = "America/Phoenix"  # defines "today" for the raw-file skip rule and the schedule
    companies_file: Path = Path("companies.yaml")
    candidates_file: Path = Path("companies.candidates.yaml")
    # Generic on purpose: no personal contact details are sent to third parties.
    user_agent: str = "shortlist-ingest/0.1 (personal job-search project)"


@lru_cache
def get_settings() -> Settings:
    return Settings()
