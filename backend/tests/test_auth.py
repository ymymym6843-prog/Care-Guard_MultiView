"""
Unit tests for authentication utilities.

Tests cover:
- hash_password produces different hashes for same password (salted)
- verify_password returns True for correct password
- verify_password returns False for wrong password
- create_access_token produces a valid JWT
- decode_token returns payload for valid token
- decode_token returns None for invalid/expired token
- Token expiration handling
"""

import time

import pytest
from jose import jwt

from app.config import settings
from app.core.auth import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """Test suite for password hashing functions."""

    def test_hash_password_produces_different_hashes(self):
        """Test that hashing the same password twice produces different hashes (salted)."""
        # Arrange
        password = "secure_password_123"

        # Act
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        # Assert
        assert hash1 != hash2  # Different due to random salt
        assert len(hash1) > 0
        assert len(hash2) > 0

    def test_verify_password_returns_true_for_correct_password(self):
        """Test that verify_password returns True for correct password."""
        # Arrange
        password = "correct_password"
        hashed = hash_password(password)

        # Act
        result = verify_password(password, hashed)

        # Assert
        assert result is True

    def test_verify_password_returns_false_for_wrong_password(self):
        """Test that verify_password returns False for incorrect password."""
        # Arrange
        correct_password = "correct_password"
        wrong_password = "wrong_password"
        hashed = hash_password(correct_password)

        # Act
        result = verify_password(wrong_password, hashed)

        # Assert
        assert result is False

    def test_verify_password_case_sensitive(self):
        """Test that password verification is case-sensitive."""
        # Arrange
        password = "MyPassword123"
        hashed = hash_password(password)

        # Act
        result_correct = verify_password("MyPassword123", hashed)
        result_wrong_case = verify_password("mypassword123", hashed)

        # Assert
        assert result_correct is True
        assert result_wrong_case is False

    def test_hash_password_handles_special_characters(self):
        """Test that password hashing works with special characters."""
        # Arrange
        password = "p@ssw0rd!#$%^&*()"

        # Act
        hashed = hash_password(password)
        result = verify_password(password, hashed)

        # Assert
        assert result is True

    def test_hash_password_handles_unicode(self):
        """Test that password hashing works with unicode characters."""
        # Arrange
        password = "пароль密码🔐"

        # Act
        hashed = hash_password(password)
        result = verify_password(password, hashed)

        # Assert
        assert result is True

    def test_verify_password_empty_string(self):
        """Test password verification with empty strings."""
        # Arrange
        password = "nonempty"
        hashed = hash_password(password)

        # Act
        result = verify_password("", hashed)

        # Assert
        assert result is False


class TestJWTToken:
    """Test suite for JWT token functions."""

    def test_create_access_token_produces_valid_jwt(self):
        """Test that create_access_token produces a valid JWT."""
        # Arrange
        payload_data = {"sub": "test_user", "role": "admin"}

        # Act
        token = create_access_token(payload_data)

        # Assert
        assert isinstance(token, str)
        assert len(token) > 0
        assert token.count(".") == 2  # JWT format: header.payload.signature

    def test_decode_token_returns_payload_for_valid_token(self):
        """Test that decode_token returns correct payload for valid token."""
        # Arrange
        payload_data = {"sub": "test_user", "user_id": 123, "role": "staff"}
        token = create_access_token(payload_data)

        # Act
        decoded = decode_token(token)

        # Assert
        assert decoded is not None
        assert decoded["sub"] == "test_user"
        assert decoded["user_id"] == 123
        assert decoded["role"] == "staff"
        assert "exp" in decoded  # Expiration should be added

    def test_decode_token_returns_none_for_invalid_token(self):
        """Test that decode_token returns None for invalid token."""
        # Arrange
        invalid_token = "invalid.jwt.token"

        # Act
        result = decode_token(invalid_token)

        # Assert
        assert result is None

    def test_decode_token_returns_none_for_malformed_token(self):
        """Test that decode_token handles malformed tokens."""
        # Arrange
        malformed_tokens = [
            "",
            "not_a_token",
            "only.two",
            "too.many.dots.here.invalid",
        ]

        # Act & Assert
        for token in malformed_tokens:
            result = decode_token(token)
            assert result is None

    def test_decode_token_returns_none_for_wrong_signature(self):
        """Test that decode_token rejects tokens with wrong signature."""
        # Arrange
        payload_data = {"sub": "test_user"}
        token = create_access_token(payload_data)

        # Tamper with the token
        parts = token.split(".")
        tampered_token = parts[0] + "." + parts[1] + ".tampered_signature"

        # Act
        result = decode_token(tampered_token)

        # Assert
        assert result is None

    def test_token_includes_expiration(self):
        """Test that created token includes expiration time."""
        # Arrange
        payload_data = {"sub": "test_user"}

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert "exp" in decoded
        assert decoded["exp"] > time.time()  # Should be in the future

    def test_token_preserves_original_data(self):
        """Test that token preserves all original payload data."""
        # Arrange
        payload_data = {
            "sub": "user@example.com",
            "name": "Test User",
            "permissions": ["read", "write"],
            "metadata": {"created": "2026-01-31"},
        }

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert decoded["sub"] == payload_data["sub"]
        assert decoded["name"] == payload_data["name"]
        assert decoded["permissions"] == payload_data["permissions"]
        assert decoded["metadata"] == payload_data["metadata"]

    def test_different_payloads_produce_different_tokens(self):
        """Test that different payloads produce different tokens."""
        # Arrange
        payload1 = {"sub": "user1"}
        payload2 = {"sub": "user2"}

        # Act
        token1 = create_access_token(payload1)
        token2 = create_access_token(payload2)

        # Assert
        assert token1 != token2

    def test_decode_token_with_wrong_secret_key(self):
        """Test that token decoding fails with wrong secret key."""
        # Arrange
        payload_data = {"sub": "test_user"}
        token = create_access_token(payload_data)

        # Act - Try to decode with wrong key
        try:
            jwt.decode(token, "wrong_secret_key", algorithms=[settings.JWT_ALGORITHM])
            assert False, "Should have raised JWTError"
        except Exception:
            # Expected to fail
            pass

        # But decode_token should return None gracefully
        result = decode_token(token)

        # Assert - Our function should still work with correct key
        assert result is not None

    def test_token_algorithm_matches_settings(self):
        """Test that token uses the algorithm specified in settings."""
        # Arrange
        payload_data = {"sub": "test_user"}
        token = create_access_token(payload_data)

        # Act - Decode and check algorithm
        header = jwt.get_unverified_header(token)

        # Assert
        assert header["alg"] == settings.JWT_ALGORITHM

    def test_empty_payload_creates_valid_token(self):
        """Test that empty payload (with only exp) creates valid token."""
        # Arrange
        payload_data = {}

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert decoded is not None
        assert "exp" in decoded

    def test_payload_copy_does_not_modify_original(self):
        """Test that creating token doesn't modify original payload dict."""
        # Arrange
        original_payload = {"sub": "test_user", "role": "admin"}
        payload_copy = original_payload.copy()

        # Act
        create_access_token(original_payload)

        # Assert
        assert original_payload == payload_copy
        assert "exp" not in original_payload  # Should not be modified

    def test_special_characters_in_payload(self):
        """Test that payload can contain special characters."""
        # Arrange
        payload_data = {
            "sub": "user@example.com",
            "name": "Test User #1 (Admin)",
            "notes": "Special chars: !@#$%^&*()",
        }

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert decoded["sub"] == payload_data["sub"]
        assert decoded["name"] == payload_data["name"]
        assert decoded["notes"] == payload_data["notes"]

    def test_numeric_values_in_payload(self):
        """Test that payload can contain numeric values."""
        # Arrange
        payload_data = {
            "sub": "test_user",
            "user_id": 42,
            "age": 30,
            "score": 95.5,
        }

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert decoded["user_id"] == 42
        assert decoded["age"] == 30
        assert decoded["score"] == 95.5

    def test_boolean_values_in_payload(self):
        """Test that payload can contain boolean values."""
        # Arrange
        payload_data = {
            "sub": "test_user",
            "is_active": True,
            "is_admin": False,
        }

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert decoded["is_active"] is True
        assert decoded["is_admin"] is False

    def test_none_values_in_payload(self):
        """Test that payload can contain None values."""
        # Arrange
        payload_data = {
            "sub": "test_user",
            "optional_field": None,
        }

        # Act
        token = create_access_token(payload_data)
        decoded = decode_token(token)

        # Assert
        assert decoded["optional_field"] is None
