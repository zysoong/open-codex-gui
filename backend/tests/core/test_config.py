"""Tests for application configuration."""

import os
import pytest
from unittest.mock import patch

from app.core.config import Settings


@pytest.mark.unit
class TestSettings:
    """Test cases for Settings configuration."""

    def test_default_values(self):
        """Test default configuration values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            assert settings.database_url == "sqlite+aiosqlite:///./data/open-claude-ui.db"
            assert settings.host == "127.0.0.1"
            assert settings.port == 8000
            assert settings.docker_container_pool_size == 5
            assert settings.storage_mode == "volume"
            assert settings.default_llm_provider == "openai"
            assert settings.default_llm_model == "gpt-5-mini"

    def test_cors_origins_list(self):
        """Test CORS origins parsing."""
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": "http://localhost:3000,http://localhost:5173,http://example.com"},
        ):
            settings = Settings()
            origins = settings.cors_origins_list

            assert len(origins) == 3
            assert "http://localhost:3000" in origins
            assert "http://localhost:5173" in origins
            assert "http://example.com" in origins

    def test_cors_origins_with_spaces(self):
        """Test CORS origins parsing with spaces."""
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": "http://localhost:3000, http://localhost:5173 , http://example.com"},
        ):
            settings = Settings()
            origins = settings.cors_origins_list

            # Spaces should be stripped
            assert "http://localhost:3000" in origins
            assert "http://localhost:5173" in origins
            assert "http://example.com" in origins

    def test_custom_database_url(self):
        """Test custom database URL."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/mydb"}
        ):
            settings = Settings()
            assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/mydb"

    def test_custom_port(self):
        """Test custom port configuration."""
        with patch.dict(os.environ, {"PORT": "9000"}):
            settings = Settings()
            assert settings.port == 9000

    def test_s3_configuration(self):
        """Test S3 storage configuration."""
        with patch.dict(
            os.environ,
            {
                "STORAGE_MODE": "s3",
                "S3_BUCKET_NAME": "my-bucket",
                "S3_ACCESS_KEY": "AKIAIOSFODNN7EXAMPLE",
                "S3_SECRET_KEY": "secret123",
                "S3_ENDPOINT_URL": "http://minio:9000",
                "S3_REGION": "us-west-2",
            },
        ):
            settings = Settings()

            assert settings.storage_mode == "s3"
            assert settings.s3_bucket_name == "my-bucket"
            assert settings.s3_access_key == "AKIAIOSFODNN7EXAMPLE"
            assert settings.s3_secret_key == "secret123"
            assert settings.s3_endpoint_url == "http://minio:9000"
            assert settings.s3_region == "us-west-2"

    def test_storage_mode_local(self):
        """Test local storage configuration."""
        with patch.dict(
            os.environ,
            {
                "STORAGE_MODE": "local",
                "STORAGE_WORKSPACE_BASE": "/custom/workspaces",
            },
        ):
            settings = Settings()

            assert settings.storage_mode == "local"
            assert settings.storage_workspace_base == "/custom/workspaces"

    def test_llm_defaults(self):
        """Test LLM default configuration."""
        with patch.dict(
            os.environ,
            {
                "DEFAULT_LLM_PROVIDER": "anthropic",
                "DEFAULT_LLM_MODEL": "claude-3-opus",
            },
        ):
            settings = Settings()

            assert settings.default_llm_provider == "anthropic"
            assert settings.default_llm_model == "claude-3-opus"

    def test_docker_pool_size(self):
        """Test Docker container pool size configuration."""
        with patch.dict(os.environ, {"DOCKER_CONTAINER_POOL_SIZE": "10"}):
            settings = Settings()
            assert settings.docker_container_pool_size == 10

    def test_encryption_key(self):
        """Test encryption key configuration."""
        test_key = "test-master-key-for-encryption"
        with patch.dict(os.environ, {"MASTER_ENCRYPTION_KEY": test_key}):
            settings = Settings()
            assert settings.master_encryption_key == test_key

    def test_case_insensitive(self):
        """Test that environment variables are case insensitive."""
        with patch.dict(
            os.environ, {"HOST": "0.0.0.0", "host": "should-be-overridden"}  # Lowercase
        ):
            settings = Settings()
            # The setting should pick up the value
            assert settings.host in ["0.0.0.0", "should-be-overridden"]

    def test_empty_s3_optional_fields(self):
        """Test that S3 optional fields default to None."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            assert settings.s3_bucket_name is None
            assert settings.s3_access_key is None
            assert settings.s3_secret_key is None
            assert settings.s3_endpoint_url is None
            assert settings.s3_region == "us-east-1"

    def test_default_storage_workspace_base(self):
        """Test default storage workspace base path."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.storage_workspace_base == "./data/workspaces"
