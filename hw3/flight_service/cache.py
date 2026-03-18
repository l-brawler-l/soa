"""Redis cache manager for Flight Service."""
import json
import logging
from typing import Optional, Any
import redis

from .config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Redis cache manager with Cache-Aside pattern."""

    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5
        )
        self.ttl = settings.cache_ttl

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        try:
            value = self.redis_client.get(key)
            if value:
                logger.info(f"Cache HIT: {key}")
                return json.loads(value)
            logger.info(f"Cache MISS: {key}")
            return None
        except Exception as e:
            logger.error(f"Cache GET error for key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (default: settings.cache_ttl)

        Returns:
            True if successful, False otherwise
        """
        try:
            ttl = ttl or self.ttl
            serialized = json.dumps(value)
            self.redis_client.setex(key, ttl, serialized)
            logger.info(f"Cache SET: {key} (TTL: {ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Cache SET error for key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if successful, False otherwise
        """
        try:
            self.redis_client.delete(key)
            logger.info(f"Cache DELETE: {key}")
            return True
        except Exception as e:
            logger.error(f"Cache DELETE error for key {key}: {e}")
            return False

    def delete_pattern(self, pattern: str) -> bool:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Key pattern (e.g., "flight:*")

        Returns:
            True if successful, False otherwise
        """
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Cache DELETE pattern: {pattern} ({len(keys)} keys)")
            return True
        except Exception as e:
            logger.error(f"Cache DELETE pattern error for {pattern}: {e}")
            return False

    def invalidate_flight(self, flight_id: int):
        """Invalidate all cache entries related to a flight."""
        self.delete(f"flight:{flight_id}")
        self.delete_pattern("search:*")

    def health_check(self) -> bool:
        """Check if Redis is available."""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False


# Global cache instance
cache = CacheManager()
