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
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800
    database_echo: bool = False

    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = 20
    redis_socket_timeout: float = 5.0
    redis_socket_connect_timeout: float = 5.0
    redis_health_check_interval: int = 30
    redis_key_prefix: str = "clinical_ai"

    log_level: str = "INFO"
    log_json: bool = True
    otel_service_name: str = "clinical-ai-api"
    otel_exporter_otlp_endpoint: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
