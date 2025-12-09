"""Tests for encryption service."""

import os
import pytest
from unittest.mock import patch
from cryptography.fernet import Fernet

from app.core.security.encryption import (
    KeyEncryptionService,
    get_encryption_service,
)


@pytest.mark.unit
class TestKeyEncryptionService:
    """Test cases for KeyEncryptionService."""

    def test_init_with_valid_key(self, encryption_key):
        """Test initialization with a valid encryption key."""
        service = KeyEncryptionService(master_key=encryption_key)
        assert service.cipher is not None

    def test_init_from_environment(self, encryption_key):
        """Test initialization from environment variable."""
        with patch.dict(os.environ, {"MASTER_ENCRYPTION_KEY": encryption_key}):
            service = KeyEncryptionService()
            assert service.cipher is not None

    def test_init_without_key_auto_generates(self, tmp_path):
        """Test that initialization without key auto-generates one."""
        # Create a temporary .env file path
        env_file = tmp_path / ".env"

        with patch.dict(os.environ, {}, clear=True):
            # Remove the key from environment
            os.environ.pop("MASTER_ENCRYPTION_KEY", None)

            # Mock the env_path to use our temp file
            with patch(
                "app.core.security.encryption.os.path.join", return_value=str(env_file)
            ):
                with patch(
                    "app.core.security.encryption.os.path.abspath",
                    return_value=str(env_file),
                ):
                    service = KeyEncryptionService()

                    # Should have auto-generated a key and created the service
                    assert service.cipher is not None

                    # The .env file should have been created with the key
                    assert env_file.exists()
                    content = env_file.read_text()
                    assert "MASTER_ENCRYPTION_KEY=" in content

    def test_init_with_invalid_key_raises(self):
        """Test that initialization with invalid key raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            KeyEncryptionService(master_key="invalid-key")

        assert "Invalid MASTER_ENCRYPTION_KEY" in str(exc_info.value)

    def test_encrypt_plaintext(self, encryption_key):
        """Test encrypting plaintext."""
        service = KeyEncryptionService(master_key=encryption_key)
        plaintext = "sk-test-api-key-12345"

        encrypted = service.encrypt(plaintext)

        assert encrypted is not None
        assert isinstance(encrypted, bytes)
        assert encrypted != plaintext.encode()
        assert len(encrypted) > len(plaintext)

    def test_decrypt_ciphertext(self, encryption_key):
        """Test decrypting ciphertext."""
        service = KeyEncryptionService(master_key=encryption_key)
        plaintext = "sk-test-api-key-12345"

        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_encrypt_empty_string_raises(self, encryption_key):
        """Test that encrypting empty string raises ValueError."""
        service = KeyEncryptionService(master_key=encryption_key)

        with pytest.raises(ValueError) as exc_info:
            service.encrypt("")

        assert "Cannot encrypt empty string" in str(exc_info.value)

    def test_decrypt_empty_bytes_raises(self, encryption_key):
        """Test that decrypting empty bytes raises ValueError."""
        service = KeyEncryptionService(master_key=encryption_key)

        with pytest.raises(ValueError) as exc_info:
            service.decrypt(b"")

        assert "Cannot decrypt empty bytes" in str(exc_info.value)

    def test_decrypt_invalid_ciphertext_raises(self, encryption_key):
        """Test that decrypting invalid ciphertext raises ValueError."""
        service = KeyEncryptionService(master_key=encryption_key)

        with pytest.raises(ValueError) as exc_info:
            service.decrypt(b"invalid-ciphertext")

        assert "Failed to decrypt" in str(exc_info.value)

    def test_encrypt_decrypt_roundtrip(self, encryption_key):
        """Test encryption/decryption roundtrip with various inputs."""
        service = KeyEncryptionService(master_key=encryption_key)

        test_strings = [
            "simple-key",
            "sk-ant-api03-long-key-with-dashes-and-numbers-12345",
            "special!@#$%^&*()characters",
            "unicode-ключ-钥匙-🔑",
            "a" * 1000,  # Long string
        ]

        for original in test_strings:
            encrypted = service.encrypt(original)
            decrypted = service.decrypt(encrypted)
            assert decrypted == original, f"Failed for: {original[:50]}..."

    def test_different_encryptions_for_same_plaintext(self, encryption_key):
        """Test that same plaintext produces different ciphertexts (Fernet uses IV)."""
        service = KeyEncryptionService(master_key=encryption_key)
        plaintext = "test-api-key"

        encrypted1 = service.encrypt(plaintext)
        encrypted2 = service.encrypt(plaintext)

        # Fernet includes a random IV, so encryptions should differ
        assert encrypted1 != encrypted2

        # But both should decrypt to same plaintext
        assert service.decrypt(encrypted1) == plaintext
        assert service.decrypt(encrypted2) == plaintext

    def test_generate_master_key(self):
        """Test generating a new master key."""
        key = KeyEncryptionService.generate_master_key()

        assert key is not None
        assert isinstance(key, str)
        # Fernet key is base64-encoded 32 bytes = 44 characters
        assert len(key) == 44

        # The generated key should be valid for Fernet
        service = KeyEncryptionService(master_key=key)
        assert service.cipher is not None

    def test_generated_key_works(self):
        """Test that generated key works for encryption/decryption."""
        key = KeyEncryptionService.generate_master_key()
        service = KeyEncryptionService(master_key=key)

        plaintext = "test-value"
        encrypted = service.encrypt(plaintext)
        decrypted = service.decrypt(encrypted)

        assert decrypted == plaintext

    def test_different_keys_produce_different_ciphertext(self):
        """Test that different keys produce different ciphertexts."""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        service1 = KeyEncryptionService(master_key=key1)
        service2 = KeyEncryptionService(master_key=key2)

        plaintext = "test-value"

        encrypted1 = service1.encrypt(plaintext)
        encrypted2 = service2.encrypt(plaintext)

        # Different keys produce different ciphertexts
        assert encrypted1 != encrypted2

    def test_wrong_key_fails_decryption(self):
        """Test that wrong key fails decryption."""
        key1 = Fernet.generate_key().decode()
        key2 = Fernet.generate_key().decode()

        service1 = KeyEncryptionService(master_key=key1)
        service2 = KeyEncryptionService(master_key=key2)

        plaintext = "test-value"
        encrypted = service1.encrypt(plaintext)

        # Decrypting with wrong key should fail
        with pytest.raises(ValueError) as exc_info:
            service2.decrypt(encrypted)

        assert "Failed to decrypt" in str(exc_info.value)


@pytest.mark.unit
class TestGetEncryptionService:
    """Test cases for get_encryption_service function."""

    def test_get_encryption_service_singleton(self, encryption_key):
        """Test that get_encryption_service returns singleton."""
        # Reset the global instance
        import app.core.security.encryption as enc_module

        enc_module._encryption_service = None

        with patch.dict(os.environ, {"MASTER_ENCRYPTION_KEY": encryption_key}):
            service1 = get_encryption_service()
            service2 = get_encryption_service()

            assert service1 is service2

        # Reset for other tests
        enc_module._encryption_service = None
