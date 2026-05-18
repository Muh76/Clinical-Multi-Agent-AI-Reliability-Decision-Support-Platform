from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Clinical AI Reliability & Decision Intelligence Platform"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    enable_docs: bool = True

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://clinical_ai:clinical_ai@localhost:5432/clinical_ai"
    )
    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")

    log_level: str = "INFO"
    log_json: bool = True
    otel_service_name: str = "clinical-ai-api"
    otel_exporter_otlp_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()

