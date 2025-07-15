# bot_v2.py - Improved version with proper timeout handling
import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.utils.backoff import BackoffConfig
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
import logging
import aiohttp
from typing import Optional

from handlers import user
from config import BOT_TOKEN

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizedAiohttpSession(AiohttpSession):
    """Custom session with optimized timeout handling for slow networks"""
    
    def __init__(self, timeout: Optional[float] = 120.0):
        super().__init__()
        self._timeout_value = timeout
    
    @property
    def timeout(self) -> Optional[float]:
        """Return timeout as a number, not ClientTimeout object"""
        return self._timeout_value
    
    async def create_session(self) -> aiohttp.ClientSession:
        """Create aiohttp session with optimized settings for slow networks"""
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=120,  # 2 minutes total timeout for slow networks
                connect=45,  # 45 seconds to establish connection
                sock_read=90,  # 90 seconds to read response
            ),
            connector=aiohttp.TCPConnector(
                limit=100,
                limit_per_host=30,
                ttl_dns_cache=300,  # 5 minutes DNS cache
                use_dns_cache=True,
                keepalive_timeout=300,  # 5 minutes keep-alive
            )
        )

# Create custom session with optimized timeout settings
session = OptimizedAiohttpSession(timeout=120.0)

# Initialize bot with custom session and timeout settings
bot = Bot(
    token=BOT_TOKEN, 
    parse_mode=ParseMode.HTML,
    session=session
)
dp = Dispatcher(storage=MemoryStorage())

async def on_startup():
    # Delete any existing webhook
    await bot.delete_webhook(drop_pending_updates=True)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="predict", description="Поиск кода ТН ВЭД")
    ])
    logger.info("✅ Bot is up and running with optimized timeout settings!")

async def main():
    dp.include_router(user.router)
    await on_startup()
    
    # Optimized polling with custom timeout settings
    try:
        logger.info(f"Starting polling with 60s timeout (optimized for slow networks)")
        await dp.start_polling(
            bot,
            polling_timeout=60,  # Long polling timeout: 60 seconds (slow preset)
            handle_as_tasks=True,  # Process updates as tasks for better performance
            backoff_config=BackoffConfig(
                min_delay=1.0,  # Minimum retry delay: 1 second
                max_delay=60.0,  # Maximum retry delay: 60 seconds
                factor=1.5,  # Backoff factor
                jitter=0.1,  # Random jitter for backoff
            ),
            allowed_updates=None,  # Allow all update types
        )
    except Exception as e:
        logger.error(f"Polling error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        raise
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        logger.info("🚀 Starting TNVED Bot with optimized settings for slow networks...")
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}") 