from functools import lru_cache
from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_CLERK_ISSUER = "https://exciting-gopher-5507.clerk.accounts.dev"
# Vercel preview/production deployments; used for CORS and for Clerk's `azp` claim.
VERCEL_ORIGIN_PATTERN = r"https://[A-Za-z0-9.-]+\.vercel\.app"


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables (or a local `.env`)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "Development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/accounting_dev"

    # Clerk session tokens (identity only; tenancy lives in `accounts`). The JWKS URL defaults to
    # `{clerk_issuer}/.well-known/jwks.json`.
    clerk_issuer: str = DEV_CLERK_ISSUER
    clerk_jwks_url: str = ""
    # Accepted `azp` (origin of the frontend that requested the token). `https://*.vercel.app` is
    # also accepted when `cors_allow_vercel_subdomains` is on.
    clerk_authorized_parties: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    storage_provider: str = "Local"  # Local | AzureBlob | S3 (Supabase Storage, AWS S3, R2, ...)
    storage_upload_container: str = "uploads"
    storage_output_container: str = "outputs"
    storage_local_root_path: str = "App_Data/files"
    storage_azure_blob_connection_string: str = ""
    # S3-compatible storage. For Supabase: endpoint https://<project-ref>.storage.supabase.co/storage/v1/s3,
    # region = the project's region, keys from Storage > S3 Connection, and a private bucket.
    storage_s3_endpoint_url: str = ""
    storage_s3_region: str = ""
    storage_s3_access_key_id: str = ""
    storage_s3_secret_access_key: str = ""
    storage_s3_bucket: str = ""
    storage_s3_force_path_style: bool = True

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

    @model_validator(mode="after")
    def _derive_clerk_jwks_url(self) -> Self:
        self.clerk_issuer = self.clerk_issuer.strip().rstrip("/")
        if not self.clerk_jwks_url.strip():
            self.clerk_jwks_url = f"{self.clerk_issuer}/.well-known/jwks.json"
        return self

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
