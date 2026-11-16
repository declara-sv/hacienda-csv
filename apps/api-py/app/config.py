from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local `.env`)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "Development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/accounting_dev"

    jwt_issuer: str = "Accounting.Api"
    jwt_audience: str = "Accounting.Web"
    jwt_signing_key: str = "CAMBIAR_ESTA_LLAVE_EN_PRODUCCION_32+"
    jwt_access_token_minutes: int = 20
    jwt_refresh_token_days: int = 30

    storage_provider: str = "Local"  # Local | AzureBlob
    storage_upload_container: str = "uploads"
    storage_output_container: str = "outputs"
    storage_local_root_path: str = "App_Data/files"
    storage_azure_blob_connection_string: str = ""

    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    cors_allow_vercel_subdomains: bool = True
    enable_swagger: bool = False

    worker_enabled: bool = True
    worker_poll_interval_seconds: float = 3.0
    worker_run_timeout_minutes: int = 10

    # AI fallback for PDFs the deterministic parser cannot read. Disabled when no key is set.
    anthropic_api_key: str = ""
    ai_extraction_model: str = "claude-opus-5-5"
    ai_extraction_enabled: bool = True

    max_upload_bytes: int = 20_000_000

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
