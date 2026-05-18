import asyncio
from arq.connections import RedisSettings
from app.config import settings

async def send_notification_task(ctx, user_id: int, message: str):
    """
    Example background task to send a notification.
    """
    print(f"--- Sending notification to User {user_id}: {message} ---")
    # Simulate I/O bound work
    await asyncio.sleep(2)
    print(f"--- Notification sent to User {user_id} ---")

async def startup(ctx):
    print("--- Worker Starting ---")

async def shutdown(ctx):
    print("--- Worker Shutting Down ---")

class WorkerSettings:
    """
    Configuration for the arq worker.
    """
    functions = [send_notification_task]
    redis_settings = RedisSettings(host=settings.REDIS_HOST, port=settings.REDIS_PORT)
    on_startup = startup
    on_shutdown = shutdown
