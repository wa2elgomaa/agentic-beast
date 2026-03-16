"""Authentication service with JWT and LDAP support."""

from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.logging import get_logger

logger = get_logger(__name__)


class AuthService:
    """Authentication service for local and LDAP authentication."""

    @staticmethod
    def _ensure_bcrypt_limit(password: str) -> bytes:
        password_bytes = password.encode("utf-8")
        if len(password_bytes) > 72:
            raise ValueError("password cannot be longer than 72 bytes, truncate manually if necessary (e.g. my_password[:72])")
        return password_bytes

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against its hash.

        Args:
            plain_password: Plain text password.
            hashed_password: Hashed password.

        Returns:
            True if password matches, False otherwise.
        """
        password_bytes = self._ensure_bcrypt_limit(plain_password)
        return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))

    def get_password_hash(self, password: str) -> str:
        """Hash a password.

        Args:
            password: Plain text password.

        Returns:
            Hashed password.
        """
        password_bytes = self._ensure_bcrypt_limit(password)
        hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
        return hashed.decode("utf-8")

    def create_access_token(self, user_id: str, username: str, expires_delta: Optional[timedelta] = None) -> str:
        """Create a JWT access token.

        Args:
            user_id: User UUID.
            username: Username.
            expires_delta: Optional custom expiration time.

        Returns:
            JWT token.
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=settings.jwt_expiration_hours)

        expire = datetime.utcnow() + expires_delta
        to_encode = {
            "sub": str(user_id),
            "username": username,
            "exp": expire,
            "iat": datetime.utcnow(),
        }

        encoded_jwt = jwt.encode(
            to_encode,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        return encoded_jwt

    def verify_token(self, token: str) -> Optional[dict]:
        """Verify and decode a JWT token.

        Args:
            token: JWT token.

        Returns:
            Token payload dict, or None if invalid.
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            return payload
        except JWTError as e:
            logger.warning("Token verification failed", error=str(e))
            return None

    async def authenticate_ldap(self, username: str, password: str) -> Optional[dict]:
        """Authenticate user against LDAP.

        Args:
            username: Username.
            password: Password.

        Returns:
            User info dict, or None if authentication fails.
        """
        ldap_module = None
        try:
            import ldap as ldap_module  # type: ignore[import-not-found]
        except ImportError:
            logger.error("LDAP package is not installed; LDAP auth unavailable")
            return None

        try:

            # Connect to LDAP server
            conn = ldap_module.initialize(settings.ldap_server)
            user_dn = f"uid={username},{settings.ldap_base_dn}"

            # Try to bind as the user
            conn.simple_bind_s(user_dn, password)
            logger.info("LDAP authentication successful", username=username)

            return {
                "username": username,
                "auth_method": "ldap",
            }

        except ldap_module.INVALID_CREDENTIALS:
            logger.warning("LDAP authentication failed - invalid credentials", username=username)
            return None
        except Exception as e:
            logger.error("LDAP authentication error", username=username, error=str(e))
            return None


# Global auth service instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create the global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
