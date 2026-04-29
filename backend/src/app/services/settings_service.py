"""Settings service for runtime configuration management with caching and encryption."""

import asyncio
from typing import Any, Dict, Optional
from cryptography.fernet import Fernet, InvalidToken
import structlog

from app.db.session import AsyncSessionLocal
from app.models import AppSettingModel

logger = structlog.get_logger(__name__)


class SettingsService:
    """Service for managing runtime application settings with Redis caching and Fernet encryption."""

    def __init__(self, redis_client=None):
        self.redis = redis_client
        self.cache_ttl = 60  # seconds

    async def get_setting(self, key: str) -> Optional[str]:
        """Get a setting by key. Decrypts if is_secret=true.
        
        Args:
            key: Setting key.
            
        Returns:
            Setting value (decrypted if secret), or None if not found.
        """
        # Try Redis cache first
        if self.redis:
            cached = await self._get_redis_cached(key)
            if cached is not None:
                return cached

        # Fetch from database
        async with AsyncSessionLocal() as session:
            stmt = sa.select(AppSettingModel).where(AppSettingModel.key == key)
            result = await session.execute(stmt)
            setting = result.scalar_one_or_none()

        if setting is None:
            return None

        # If secret, decrypt; otherwise return as-is
        value = setting.value
        if setting.is_secret:
            try:
                value = await self._decrypt_value(value)
            except Exception as e:
                logger.error("Failed to decrypt setting", key=key, error=str(e))
                return None

        # Cache result
        if self.redis:
            await self._set_redis_cached(key, value)

        return value

    async def get_all_settings(self) -> Dict[str, str]:
        """Get all settings, masking secret values in response.
        
        Returns:
            Dict of {key: value or "***"} for secrets.
        """
        async with AsyncSessionLocal() as session:
            stmt = sa.select(AppSettingModel)
            result = await session.execute(stmt)
            settings = result.scalars().all()

        output = {}
        for setting in settings:
            if setting.is_secret:
                output[setting.key] = "***"  # Mask secret values
            else:
                try:
                    output[setting.key] = setting.value
                except Exception as e:
                    logger.error("Error reading setting", key=setting.key, error=str(e))
                    output[setting.key] = "[ERROR]"

        return output

    async def set_setting(self, key: str, value: str, is_secret: bool = False) -> bool:
        """Set or update a setting. Encrypts if is_secret=true.
        
        Args:
            key: Setting key.
            value: Setting value.
            is_secret: Whether to encrypt this value.
            
        Returns:
            True if successful, False otherwise.
        """
        encrypted_value = value
        if is_secret:
            try:
                encrypted_value = await self._encrypt_value(value)
            except Exception as e:
                logger.error("Failed to encrypt setting", key=key, error=str(e))
                return False

        async with AsyncSessionLocal() as session:
            stmt = sa.select(AppSettingModel).where(AppSettingModel.key == key)
            result = await session.execute(stmt)
            setting = result.scalar_one_or_none()

            if setting:
                setting.value = encrypted_value
                setting.is_secret = is_secret
            else:
                setting = AppSettingModel(key=key, value=encrypted_value, is_secret=is_secret)
                session.add(setting)

            await session.commit()

        # Invalidate cache
        if self.redis:
            await self._invalidate_redis_cache(key)

        logger.info("Setting updated", key=key, is_secret=is_secret)
        return True

    async def get_effective_provider_config(self) -> Dict[str, Any]:
        """Get the effective AI provider configuration from DB or env.
        
        This is the authoritative source for provider config at runtime.
        Agents MUST call this method to get current provider settings,
        not read config.py directly.
        
        Returns:
            Dict with {provider, model, api_key, ...} for the active provider.
        """
        from app.config import settings

        provider_name = await self.get_setting("AI_PROVIDER") or settings.ai_provider
        model_name = await self.get_setting("ORCHESTRATOR_MODEL") or settings.ai_model
        api_key = await self.get_setting("OPENAI_API_KEY") or settings.openai_api_key

        return {
            "provider": provider_name,
            "model": model_name,
            "api_key": api_key,
            "bedrock_region": await self.get_setting("AWS_REGION") or settings.aws_region,
        }

    async def _get_redis_cached(self, key: str) -> Optional[str]:
        """Retrieve setting from Redis cache."""
        if not self.redis:
            return None
        try:
            cached = self.redis.get(f"setting:{key}")
            if cached:
                logger.debug("Setting cache hit", key=key)
                return cached.decode() if isinstance(cached, bytes) else cached
        except Exception as e:
            logger.warning("Redis cache lookup failed", key=key, error=str(e))
        return None

    async def _set_redis_cached(self, key: str, value: str) -> None:
        """Store setting in Redis cache with TTL."""
        if not self.redis:
            return
        try:
            self.redis.setex(f"setting:{key}", self.cache_ttl, value)
        except Exception as e:
            logger.warning("Redis cache update failed", key=key, error=str(e))

    async def _invalidate_redis_cache(self, key: str) -> None:
        """Remove setting from Redis cache."""
        if not self.redis:
            return
        try:
            self.redis.delete(f"setting:{key}")
        except Exception as e:
            logger.warning("Redis cache invalidation failed", key=key, error=str(e))

    async def _encrypt_value(self, value: str) -> str:
        """Encrypt a secret value using Fernet."""
        from app.config import settings

        if not settings.settings_encryption_key:
            raise ValueError("SETTINGS_ENCRYPTION_KEY not configured")

        cipher = Fernet(settings.settings_encryption_key.encode())
        encrypted = cipher.encrypt(value.encode())
        return encrypted.decode()

    async def _decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a secret value using Fernet."""
        from app.config import settings

        if not settings.settings_encryption_key:
            raise ValueError("SETTINGS_ENCRYPTION_KEY not configured")

        cipher = Fernet(settings.settings_encryption_key.encode())
        try:
            decrypted = cipher.decrypt(encrypted_value.encode())
            return decrypted.decode()
        except InvalidToken as e:
            logger.error("Fernet decryption failed", error=str(e))
            raise


# Global settings service instance
_settings_service: Optional[SettingsService] = None


async def get_settings_service(redis_client=None) -> SettingsService:
    """Get or create the global settings service instance."""
    global _settings_service
    if _settings_service is None:
        _settings_service = SettingsService(redis_client=redis_client)
    return _settings_service


# Import for type hints only
import sqlalchemy as sa
