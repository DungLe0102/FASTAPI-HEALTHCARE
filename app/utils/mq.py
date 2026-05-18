from arq import create_pool
from arq.connections import RedisSettings
from app.config import settings

_redis_pool = None

async def get_redis_pool():
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = await create_pool(
            RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
        )
    return _redis_pool

async def enqueue_job(func_name: str, *args, **kwargs):
    """
    Helper to enqueue a background task.
    """
    pool = await get_redis_pool()
    await pool.enqueue_job(func_name, *args, **kwargs)
