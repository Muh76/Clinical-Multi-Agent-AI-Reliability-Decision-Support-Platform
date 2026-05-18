import pytest

from clinical_ai_platform.core.settings import Environment, LlmProvider, Settings, VectorProvider


def test_settings_exposes_grouped_configuration() -> None:
    settings = Settings()

    assert settings.app.environment == Environment.LOCAL
    assert settings.api.port == 8000
    assert settings.database.pool_size > 0
    assert settings.redis.key_prefix == "clinical_ai"
    assert settings.llm.provider == LlmProvider.NONE
    assert settings.vector_database.provider == VectorProvider.NONE
    assert settings.agents.max_concurrent_runs > 0


def test_production_settings_require_secret_and_hardened_flags() -> None:
    settings = Settings(
        environment=Environment.PRODUCTION,
        enable_docs=False,
        app_secret_key="production-secret",
    )

    settings.validate_for_runtime()


def test_hosted_llm_provider_requires_api_key() -> None:
    settings = Settings(llm_provider=LlmProvider.OPENAI)

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        settings.validate_for_runtime()


def test_external_vector_provider_requires_url() -> None:
    settings = Settings(vector_provider=VectorProvider.QDRANT)

    with pytest.raises(ValueError, match="VECTOR_DATABASE_URL"):
        settings.validate_for_runtime()
