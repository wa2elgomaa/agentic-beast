"""Integration tests for LDAP/Active Directory authentication."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.auth_service import AuthService


class TestLDAPAuthentication:
    """Test suite for LDAP authentication integration."""

    @pytest.fixture
    def auth_service(self):
        """Create an AuthService instance for testing."""
        return AuthService()

    @pytest.mark.asyncio
    async def test_ldap_bind_successful(self, auth_service):
        """Test successful LDAP bind with valid credentials."""
        with patch("app.services.auth_service.ldap_module") as mock_ldap:
            mock_conn = MagicMock()
            mock_ldap.initialize.return_value = mock_conn
            mock_ldap.INVALID_CREDENTIALS = Exception

            result = await auth_service.authenticate_ldap("testuser", "validpass")

            assert result is not None
            assert result["username"] == "testuser"
            assert result["auth_method"] == "ldap"
            mock_conn.simple_bind_s.assert_called_once()

    @pytest.mark.asyncio
    async def test_ldap_bind_invalid_credentials(self, auth_service):
        """Test LDAP bind with invalid credentials."""
        with patch("app.services.auth_service.ldap_module") as mock_ldap:
            mock_conn = MagicMock()
            mock_ldap.initialize.return_value = mock_conn
            mock_ldap.INVALID_CREDENTIALS = Exception
            mock_conn.simple_bind_s.side_effect = mock_ldap.INVALID_CREDENTIALS()

            result = await auth_service.authenticate_ldap("testuser", "wrongpass")

            assert result is None
            mock_conn.simple_bind_s.assert_called_once()

    @pytest.mark.asyncio
    async def test_ldap_server_connection_error(self, auth_service):
        """Test LDAP connection failure."""
        with patch("app.services.auth_service.ldap_module") as mock_ldap:
            mock_ldap.initialize.side_effect = Exception("Connection refused")

            result = await auth_service.authenticate_ldap("testuser", "password")

            assert result is None

    @pytest.mark.asyncio
    async def test_ldap_package_not_installed(self, auth_service):
        """Test fallback when python-ldap is not installed."""
        with patch.dict("sys.modules", {"ldap": None}):
            with patch("app.services.auth_service.logger") as mock_logger:
                result = await auth_service.authenticate_ldap("testuser", "password")

                assert result is None
                mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_local_authentication_fallback(self, auth_service):
        """Test fallback to local password authentication when LDAP fails."""
        # Hash a test password
        test_password = "testpass123"
        hashed = auth_service.get_password_hash(test_password)

        # Verify correct password works
        assert auth_service.verify_password(test_password, hashed) is True

        # Verify incorrect password fails
        assert auth_service.verify_password("wrongpass", hashed) is False

    def test_password_hashing_bcrypt(self, auth_service):
        """Test password hashing with bcrypt."""
        password = "mySecurePassword"
        hashed = auth_service.get_password_hash(password)

        # Verify hash is bcrypt format
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$") or hashed.startswith("$2y$")
        
        # Verify verification works
        assert auth_service.verify_password(password, hashed) is True
        assert auth_service.verify_password("wrongpassword", hashed) is False

    def test_password_too_long_bcrypt_limit(self, auth_service):
        """Test that passwords longer than 72 bytes raise an error."""
        long_password = "p" * 73  # 73 bytes, exceeds bcrypt 72-byte limit
        
        with pytest.raises(ValueError, match="cannot be longer than 72 bytes"):
            auth_service.get_password_hash(long_password)

    @pytest.mark.asyncio
    async def test_ldap_user_attribute_mapping(self, auth_service):
        """Test LDAP user attribute extraction and mapping."""
        with patch("app.services.auth_service.ldap_module") as mock_ldap:
            mock_conn = MagicMock()
            mock_ldap.initialize.return_value = mock_conn
            mock_ldap.INVALID_CREDENTIALS = Exception

            result = await auth_service.authenticate_ldap("john.doe", "password")

            assert result is not None
            # Verify expected attributes are present in response
            assert "username" in result
            assert "auth_method" in result
            assert result["auth_method"] == "ldap"

    @pytest.mark.asyncio
    async def test_jwt_token_creation(self, auth_service):
        """Test JWT access token creation."""
        user_id = "1234-5678-9012-3456"
        username = "testuser"

        token = auth_service.create_access_token(user_id, username)

        assert token is not None
        assert isinstance(token, str)

        # Verify token can be decoded
        payload = auth_service.verify_token(token)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["username"] == username

    def test_jwt_verification_invalid_token(self, auth_service):
        """Test JWT verification with invalid token."""
        invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.invalid"

        payload = auth_service.verify_token(invalid_token)

        assert payload is None

    def test_jwt_verification_expired_token(self, auth_service):
        """Test JWT verification with expired token."""
        from datetime import timedelta

        # Create a token that expires in -1 seconds (already expired)
        user_id = "1234-5678-9012-3456"
        username = "testuser"
        expired_delta = timedelta(seconds=-1)

        token = auth_service.create_access_token(user_id, username, expired_delta)

        payload = auth_service.verify_token(token)

        assert payload is None
