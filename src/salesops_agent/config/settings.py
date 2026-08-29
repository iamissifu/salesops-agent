"""Centralized runtime configuration."""

from pathlib import Path
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: str = ""
    openai_base_url: str = "https://openai.vocareum.com/v1"
    openai_model: str = "gpt-3.5-turbo"
    temperature: float = 0.0
    max_tokens: int = 1000

    data_dir: Path = Path("data")
    logs_dir: Path = Path("logs")
    traces_dir: Path = Path("traces")
    reports_dir: Path = Path("reports")

    sandbox_timeout_seconds: int = 5
    sandbox_allowed_modules: List[str] = Field(
        default_factory=lambda: [
            "statistics",
            "math",
            "collections",
            "datetime",
            "json",
            "re",
            "decimal",
            "functools",
            "itertools",
            "pandas",
        ]
    )

    blocked_hr_keywords: List[str] = Field(
        default_factory=lambda: [
            "salary",
            "bonus",
            "compensation",
            "equity",
            "layoff",
            "laid off",
            "fired",
            "termination",
            "severance",
            "performance improvement",
        ]
    )
    blocked_financial_keywords: List[str] = Field(
        default_factory=lambda: [
            "m&a",
            "m and a",
            "acquisition",
            "acquire",
            "merger",
            "confidential strategy",
            "ceo bonus",
            "executive compensation",
        ]
    )

    def ensure_dirs(self) -> None:
        for directory in (self.data_dir, self.logs_dir, self.traces_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
