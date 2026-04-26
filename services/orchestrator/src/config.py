from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    REDIS_URL: str = "redis://localhost:6379"
    GRPC_PORT: int = 50051
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    SUPERVISOR_MODEL: str = "claude-sonnet-4-20250514"
    WORKER_MODEL: str = "claude-sonnet-4-20250514"
    SANDBOX_GRPC_URL: str = "localhost:50052"
    CONTEXT_GRPC_URL: str = "localhost:50053"
    LOG_LEVEL: str = "info"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
