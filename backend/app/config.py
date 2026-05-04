from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    llm_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_default_model: str = "gemini-2.5-flash"

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
