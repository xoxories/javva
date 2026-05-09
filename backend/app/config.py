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

    # Vertex AI configuration. When use_vertex_ai=True, the LLM client is
    # built against Google Cloud Vertex AI (uses GCP credits, ADC auth).
    # Otherwise it uses aistudio.google.com Gemini API direct (api_key auth,
    # 20 RPD free tier cap).
    use_vertex_ai: bool = False
    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"

    # API auth — when set, all /chat endpoints require X-API-Key header
    # matching this value. When unset (None or empty), auth is disabled
    # and a warning is logged at startup (dev-mode bypass).
    api_key: str | None = None

    database_url: str = ""
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    # Langfuse observability — when keys are set and `langfuse_enabled=True`,
    # every chat() call is wrapped in a Langfuse span with input / output /
    # metadata. Free tier: 50K observations/month at cloud.langfuse.com.
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_enabled: bool = True
    jwt_secret: str = ""
    cors_origins: str = ""
    env: str = "development"
    log_level: str = "INFO"


settings = Settings()
