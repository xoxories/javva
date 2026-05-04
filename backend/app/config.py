from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""
    database_url: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    jwt_secret: str = ""
    cors_origins: str = ""
    env: str = "development"
    log_level: str = "INFO"


settings = Settings()
