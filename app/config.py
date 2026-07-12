from typing import List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The one insecure default we ship. If this value is still active outside of
# development, Settings refuses to construct (see check_production_secrets below)
# instead of silently allowing the fail-open dev auth bypass in auth.py to run
# unnoticed in a real deployment.
_INSECURE_DEFAULT_JWT_SECRET = "production-super-secret-key-change-me"  # nosec B105 - sentinel value compared against, never used as a real secret


class Settings(BaseSettings):
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    port: int = Field(default=8000, validation_alias="PORT")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # NVIDIA NIM / build.nvidia.com - OpenAI-compatible chat completions endpoint.
    # This is the only LLM provider actually wired into the app; see app/services/llm_client.py.
    nvidia_api_key: str = Field(default="", validation_alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", validation_alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="meta/llama-3.1-70b-instruct", validation_alias="NVIDIA_MODEL")
    llm_request_timeout_s: float = Field(default=30.0, validation_alias="LLM_REQUEST_TIMEOUT_S")

    # Database Settings
    database_url: str = Field(default="sqlite:///app.db", validation_alias="DATABASE_URL")

    # Security Settings
    jwt_secret: str = Field(default=_INSECURE_DEFAULT_JWT_SECRET, validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")

    # CORS - explicit allow-list, comma-separated in the env. Never combine
    # allow_origins=["*"] with credentials; see app/main.py.
    cors_allowed_origins_raw: str = Field(
        default="http://localhost:8501,http://localhost:3000",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    # Resilience Throttling
    rate_limit_calls: int = Field(default=60, validation_alias="RATE_LIMIT_CALLS")
    rate_limit_period: int = Field(default=60, validation_alias="RATE_LIMIT_PERIOD")

    # Resilience Circuit Breaker
    circuit_breaker_failure_threshold: int = Field(default=5, validation_alias="CB_FAILURE_THRESHOLD")
    circuit_breaker_recovery_timeout: int = Field(default=30, validation_alias="CB_RECOVERY_TIMEOUT")

    # Observability: LangSmith (LLM call tracing) - separate from the OpenTelemetry
    # tracer in observability/tracer.py, which handles general request/tenant spans.
    langsmith_api_key: str = Field(default="", validation_alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field(default="production-ai-template", validation_alias="LANGSMITH_PROJECT")
    langsmith_endpoint: str = Field(default="https://api.smith.langchain.com", validation_alias="LANGSMITH_ENDPOINT")
    langsmith_tracing_enabled: bool = Field(default=False, validation_alias="LANGSMITH_TRACING_ENABLED")

    @property
    def cors_allowed_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_allowed_origins_raw.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def check_production_secrets(self) -> "Settings":
        """
        Refuse to boot outside development with the published default JWT secret.

        Without this guard, auth.py's unauthenticated-request fallback (full-admin
        access when app_env == "development") combined with this settings default
        is a fail-open trap the moment APP_ENV drifts from exactly "development"
        in a real deployment while the JWT secret is still untouched.
        """
        if self.app_env not in ("development", "test", "testing") and self.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                f"Refusing to start: APP_ENV='{self.app_env}' but JWT_SECRET is still the "
                "published default. Set a real JWT_SECRET (e.g. `openssl rand -hex 32`) "
                "before running outside development."
            )
        return self


settings = Settings()
