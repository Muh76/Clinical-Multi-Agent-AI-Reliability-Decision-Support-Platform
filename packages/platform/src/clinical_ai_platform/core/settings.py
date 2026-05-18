import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, PostgresDsn, RedisDsn, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class LlmProvider(StrEnum):
    NONE = "none"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"


class VectorProvider(StrEnum):
    NONE = "none"
    PGVECTOR = "pgvector"
    QDRANT = "qdrant"
    PINECONE = "pinecone"


class AppSettings(BaseModel):
    name: str
    version: str
    environment: Environment
    debug: bool
    secret_key: SecretStr | None


class ApiSettings(BaseModel):
    host: str
    port: int
    workers: int
    enable_docs: bool
    cors_allowed_origins: list[str]


class DatabaseSettings(BaseModel):
    url: PostgresDsn
    pool_size: int
    max_overflow: int
    pool_timeout: int
    pool_recycle: int
    echo: bool


class RedisSettings(BaseModel):
    url: RedisDsn
    max_connections: int
    socket_timeout: float
    socket_connect_timeout: float
    health_check_interval: int
    key_prefix: str


class ObservabilitySettings(BaseModel):
    log_level: str
    log_json: bool
    otel_service_name: str
    otel_exporter_otlp_endpoint: str | None
    sentry_dsn: SecretStr | None
    metrics_enabled: bool
    tracing_enabled: bool


class LlmSettings(BaseModel):
    provider: LlmProvider
    default_model: str | None
    api_key: SecretStr | None
    base_url: str | None
    timeout_seconds: float
    max_retries: int


class VectorDatabaseSettings(BaseModel):
    provider: VectorProvider
    url: str | None
    api_key: SecretStr | None
    collection_prefix: str
    embedding_model: str | None


class AgentSystemSettings(BaseModel):
    enabled: bool
    max_concurrent_runs: int
    run_timeout_seconds: int
    memory_ttl_seconds: int
    workflow_state_ttl_seconds: int


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Clinical AI Reliability & Decision Intelligence Platform"
    app_version: str = "0.1.0"
    environment: Environment = Environment.LOCAL
    app_debug: bool = False
    app_secret_key: SecretStr | None = None

    enable_docs: bool = True
    api_host: str = "0.0.0.0"
    api_port: int = Field(default=8000, ge=1, le=65535)
    api_workers: int = Field(default=2, ge=1)
    cors_allowed_origins: str = ""

    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://clinical_ai:clinical_ai@localhost:5432/clinical_ai"
    )
    database_pool_size: int = Field(default=5, ge=1)
    database_max_overflow: int = Field(default=10, ge=0)
    database_pool_timeout: int = Field(default=30, ge=1)
    database_pool_recycle: int = Field(default=1800, ge=60)
    database_echo: bool = False

    redis_url: RedisDsn = Field(default="redis://localhost:6379/0")
    redis_max_connections: int = Field(default=20, ge=1)
    redis_socket_timeout: float = Field(default=5.0, gt=0)
    redis_socket_connect_timeout: float = Field(default=5.0, gt=0)
    redis_health_check_interval: int = Field(default=30, ge=0)
    redis_key_prefix: str = "clinical_ai"

    log_level: str = "INFO"
    log_json: bool = True
    otel_service_name: str = "clinical-ai-api"
    otel_exporter_otlp_endpoint: str | None = None
    sentry_dsn: SecretStr | None = None
    metrics_enabled: bool = True
    tracing_enabled: bool = True

    llm_provider: LlmProvider = LlmProvider.NONE
    llm_default_model: str | None = None
    llm_api_key: SecretStr | None = None
    llm_base_url: str | None = None
    llm_timeout_seconds: float = Field(default=60.0, gt=0)
    llm_max_retries: int = Field(default=2, ge=0)

    vector_provider: VectorProvider = VectorProvider.NONE
    vector_database_url: str | None = None
    vector_database_api_key: SecretStr | None = None
    vector_collection_prefix: str = "clinical_ai"
    vector_embedding_model: str | None = None

    agents_enabled: bool = True
    agent_max_concurrent_runs: int = Field(default=10, ge=1)
    agent_run_timeout_seconds: int = Field(default=900, ge=1)
    agent_memory_ttl_seconds: int = Field(default=86_400, ge=60)
    workflow_state_ttl_seconds: int = Field(default=86_400, ge=60)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if normalized not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return normalized

    @field_validator("redis_key_prefix", "vector_collection_prefix")
    @classmethod
    def validate_prefix(cls, value: str) -> str:
        if not value:
            raise ValueError("prefix cannot be empty")
        if any(character.isspace() for character in value):
            raise ValueError("prefix cannot contain whitespace")
        return value

    @field_validator(
        "app_secret_key",
        "sentry_dsn",
        "llm_api_key",
        "vector_database_api_key",
        mode="before",
    )
    @classmethod
    def empty_secret_to_none(cls, value: object) -> object | None:
        if value == "":
            return None
        return value

    @field_validator(
        "otel_exporter_otlp_endpoint",
        "llm_default_model",
        "llm_base_url",
        "vector_database_url",
        "vector_embedding_model",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: object) -> object | None:
        if value == "":
            return None
        return value

    @computed_field
    @property
    def app(self) -> AppSettings:
        return AppSettings(
            name=self.app_name,
            version=self.app_version,
            environment=self.environment,
            debug=self.app_debug,
            secret_key=self.app_secret_key,
        )

    @computed_field
    @property
    def api(self) -> ApiSettings:
        return ApiSettings(
            host=self.api_host,
            port=self.api_port,
            workers=self.api_workers,
            enable_docs=self.enable_docs,
            cors_allowed_origins=_parse_csv(self.cors_allowed_origins),
        )

    @computed_field
    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(
            url=self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_timeout=self.database_pool_timeout,
            pool_recycle=self.database_pool_recycle,
            echo=self.database_echo,
        )

    @computed_field
    @property
    def redis(self) -> RedisSettings:
        return RedisSettings(
            url=self.redis_url,
            max_connections=self.redis_max_connections,
            socket_timeout=self.redis_socket_timeout,
            socket_connect_timeout=self.redis_socket_connect_timeout,
            health_check_interval=self.redis_health_check_interval,
            key_prefix=self.redis_key_prefix,
        )

    @computed_field
    @property
    def observability(self) -> ObservabilitySettings:
        return ObservabilitySettings(
            log_level=self.log_level,
            log_json=self.log_json,
            otel_service_name=self.otel_service_name,
            otel_exporter_otlp_endpoint=self.otel_exporter_otlp_endpoint,
            sentry_dsn=self.sentry_dsn,
            metrics_enabled=self.metrics_enabled,
            tracing_enabled=self.tracing_enabled,
        )

    @computed_field
    @property
    def llm(self) -> LlmSettings:
        return LlmSettings(
            provider=self.llm_provider,
            default_model=self.llm_default_model,
            api_key=self.llm_api_key,
            base_url=self.llm_base_url,
            timeout_seconds=self.llm_timeout_seconds,
            max_retries=self.llm_max_retries,
        )

    @computed_field
    @property
    def vector_database(self) -> VectorDatabaseSettings:
        return VectorDatabaseSettings(
            provider=self.vector_provider,
            url=self.vector_database_url,
            api_key=self.vector_database_api_key,
            collection_prefix=self.vector_collection_prefix,
            embedding_model=self.vector_embedding_model,
        )

    @computed_field
    @property
    def agents(self) -> AgentSystemSettings:
        return AgentSystemSettings(
            enabled=self.agents_enabled,
            max_concurrent_runs=self.agent_max_concurrent_runs,
            run_timeout_seconds=self.agent_run_timeout_seconds,
            memory_ttl_seconds=self.agent_memory_ttl_seconds,
            workflow_state_ttl_seconds=self.workflow_state_ttl_seconds,
        )

    def validate_for_runtime(self) -> None:
        if self.environment == Environment.PRODUCTION:
            if self.app_debug:
                raise ValueError("APP_DEBUG must be false in production")
            if self.enable_docs:
                raise ValueError("ENABLE_DOCS must be false in production")
            if self.log_level == "DEBUG":
                raise ValueError("LOG_LEVEL must not be DEBUG in production")
            if self.app_secret_key is None:
                raise ValueError("APP_SECRET_KEY is required in production")

        if self.llm_provider != LlmProvider.NONE and self.llm_provider != LlmProvider.LOCAL:
            if self.llm_api_key is None:
                raise ValueError("LLM_API_KEY is required for hosted LLM providers")

        if self.vector_provider in {VectorProvider.QDRANT, VectorProvider.PINECONE}:
            if self.vector_database_url is None:
                raise ValueError("VECTOR_DATABASE_URL is required for external vector providers")


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_files() -> tuple[str, ...]:
    environment = os.getenv("ENVIRONMENT", Environment.LOCAL.value)
    candidates = (".env", f".env.{environment}")
    return tuple(str(path) for candidate in candidates if (path := Path(candidate)).exists())


@lru_cache
def get_settings() -> Settings:
    settings = Settings(_env_file=_env_files() or None)
    settings.validate_for_runtime()
    return settings
