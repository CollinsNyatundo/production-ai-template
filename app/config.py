from typing import List

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_INSECURE_DEFAULT_JWT_SECRET = "production-super-secret-key-change-me"


class Settings(BaseSettings):
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    port: int = Field(default=8000, validation_alias="PORT")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    nvidia_api_key: str = Field(default="", validation_alias="NVIDIA_API_KEY")
    nvidia_base_url: str = Field(default="https://integrate.api.nvidia.com/v1", validation_alias="NVIDIA_BASE_URL")
    nvidia_model: str = Field(default="meta/llama-3.1-70b-instruct", validation_alias="NVIDIA_MODEL")
    llm_request_timeout_s: float = Field(default=30.0, validation_alias="LLM_REEUEST_TIMEOUT_S")

    openkb_base_url: str = Field(default="http://127.0.0.1:7566", validation_alias="OPENKB_BASE_URL")
    openkb_timeout_s: float = Field(default=60.0, validation_alias="OPENKB_TIMEOUT_S")

    database_url: str = Field(default="sqlite:///app.db", validation_alias="DATABASE_URL")

    jwt_secret: str = Field(default=_INSECURE_DEFAULT_JWT_SECRET, validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")

    cors_allowed_origins_raw: str = Field(
        default="http://localhost:8501,http://localhost:3000",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    rate_limit_calls: int = Field(default=60, validation_alias="RATE_LIMIT_CALLS")
    rate_limit_period: int = Field(default=60, validation_alias="RATE_LIMIT_PERIOD")

    circuit_breaker_failure_threshold: int = Field(default=5, validation_alias="CB_FAILURE_THRESHOLD")
    circuit_breaker_recovery_timeout: int = Field(default=30, validation_alias="CB_RECOVERY_TIMEOUT")

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
        if self.app_env not in ("development", "test", "testing") and self.jwt_secret == _INSECURE_DEFAULT_JWT_SECRET:
            raise ValueError(
                f"Refusing to start: APP_ENV='{self.app_env}' but JWT_SECRET is still default."
            )
        return self


settings = Settings()
