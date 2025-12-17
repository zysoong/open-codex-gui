"""Application configuration."""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/open-claude-ui.db"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: str = "http://localhost:3000,http://localhost:5173,http://localhost:5174"

    # Docker
    docker_container_pool_size: int = 5

    # Storage Configuration
    storage_mode: str = "volume"  # Options: "local", "volume", "s3"
    storage_workspace_base: str = "./data/workspaces"  # For local mode

    # S3/MinIO Configuration (for storage_mode="s3")
    s3_bucket_name: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_endpoint_url: str | None = None  # For MinIO or custom S3-compatible service
    s3_region: str = "us-east-1"

    # LLM Defaults
    default_llm_provider: str = "openai"
    default_llm_model: str = "gpt-5-mini"  # Use API-native model names (gpt-5, gpt-5-mini, etc.)

    # API Key Encryption
    master_encryption_key: str | None = None

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins as list."""
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Global settings instance
settings = Settings()
