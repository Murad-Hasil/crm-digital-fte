"""
Async PostgreSQL connection pool using asyncpg.
Call init_db_pool() on app startup, close_db_pool() on shutdown.
Use get_db_pool() anywhere a connection is needed.
"""

import asyncpg
import logging
import os

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None


async def init_db_pool() -> None:
    """Create the global asyncpg connection pool."""
    global _pool
    dsn = os.environ["DATABASE_URL"]
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=2,
        max_size=10,
        command_timeout=60,
        statement_cache_size=0,
    )
    logger.info("Database connection pool initialised.")


async def close_db_pool() -> None:
    """Gracefully close the connection pool on app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed.")


async def get_db_pool() -> asyncpg.Pool:
    """
    Return the active pool.
    Raises RuntimeError if called before init_db_pool().
    """
    if _pool is None:
        raise RuntimeError("Database pool is not initialised. Call init_db_pool() first.")
    return _pool
