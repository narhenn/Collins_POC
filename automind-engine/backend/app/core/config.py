from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/automind"

    @property
    def async_database_url(self) -> str:
        """Convert postgres:// to postgresql+asyncpg:// for Render compatibility."""
        url = self.DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    REDIS_URL: str = "redis://localhost:6379/0"
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_HOURS: int = 24
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    RESEND_API_KEY: str = ""
    SLACK_WEBHOOK_URL: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    DEBUG: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
