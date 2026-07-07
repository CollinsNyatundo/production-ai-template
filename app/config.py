from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = Field(default="development", validation_alias="APP_ENV")
    port: int = Field(default=8000, validation_alias="PORT")
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Provider Keys (Mocked or real)
    openai_api_key: str = Field(default="mock-key", validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="mock-key", validation_alias="ANTHROPIC_API_KEY")

    # Database Settings
    database_url: str = Field(default="sqlite:///app.db", validation_alias="DATABASE_URL")

    # Security Settings
    jwt_secret: str = Field(default="production-super-secret-key-change-me", validation_alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")

    # Resilience Throttling
    rate_limit_calls: int = Field(default=60, validation_alias="RATE_LIMIT_CALLS")
    rate_limit_period: int = Field(default=60, validation_alias="RATE_LIMIT_PERIOD")

    # Resilience Circuit Breaker
    circuit_breaker_failure_threshold: int = Field(default=5, validation_alias="CB_FAILURE_THRESHOLD")
    circuit_breaker_recovery_timeout: int = Field(default=30, validation_alias="CB_RECOVERY_TIMEOUT")

    # Observability Config
    langfuse_public_key: str = Field(default="", validation_alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", validation_alias="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(default="https://cloud.langfuse.com", validation_alias="LANGFUSE_HOST")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
