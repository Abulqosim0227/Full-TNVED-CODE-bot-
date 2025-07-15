import asyncio
import logging
import sys
import time
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import aiohttp
from handlers import user
from config import BOT_TOKEN

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Bot configuration with better session management
session = AiohttpSession(
    timeout=aiohttp.ClientTimeout(total=30, connect=10),
    connector=aiohttp.TCPConnector(
        limit=100,
        limit_per_host=10,
        ttl_dns_cache=300,
        use_dns_cache=True,
        keepalive_timeout=30,
        enable_cleanup_closed=True
    )
)

bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

# Register handlers
dp.include_router(user.router)

# Auto-restart configuration
MAX_RESTART_ATTEMPTS = 5
RESTART_DELAY = 30  # seconds
restart_count = 0

async def graceful_shutdown():
    """Graceful shutdown procedure"""
    logger.info("🔄 Initiating graceful shutdown...")
    
    try:
        # Close the session
        await bot.session.close()
        logger.info("✅ Bot session closed successfully")
    except Exception as e:
        logger.error(f"❌ Error closing bot session: {e}")
    
    # Wait a moment for cleanup
    await asyncio.sleep(2)
    logger.info("✅ Graceful shutdown completed")

async def check_bot_health():
    """Check bot health and restart if needed"""
    global restart_count
    
    while True:
        try:
            # Test bot connection
            me = await bot.get_me()
            logger.info(f"✅ Bot health check passed: @{me.username}")
            restart_count = 0  # Reset counter on successful check
            
        except Exception as e:
            logger.error(f"❌ Bot health check failed: {e}")
            
            if restart_count < MAX_RESTART_ATTEMPTS:
                restart_count += 1
                logger.warning(f"🔄 Attempting restart {restart_count}/{MAX_RESTART_ATTEMPTS}")
                await asyncio.sleep(RESTART_DELAY)
                continue
            else:
                logger.critical(f"💀 Max restart attempts reached. Manual intervention required.")
                sys.exit(1)
                
        # Wait before next health check
        await asyncio.sleep(300)  # Check every 5 minutes

async def start_polling_with_retry():
    """Start polling with automatic retry mechanism"""
    global restart_count
    
    while restart_count < MAX_RESTART_ATTEMPTS:
        try:
            logger.info("🚀 Starting bot polling...")
            
            # Start health check in background
            health_task = asyncio.create_task(check_bot_health())
            
            # Start polling
            await dp.start_polling(
                bot,
                skip_updates=True,
                handle_signals=True,
                fast=True,
                relax=0.1,
                timeout=20,
                retry_after=5
            )
            
        except KeyboardInterrupt:
            logger.info("🛑 Received KeyboardInterrupt, shutting down...")
            break
            
        except Exception as e:
            restart_count += 1
            logger.error(f"❌ Polling error (attempt {restart_count}/{MAX_RESTART_ATTEMPTS}): {e}")
            
            if restart_count < MAX_RESTART_ATTEMPTS:
                logger.info(f"🔄 Restarting in {RESTART_DELAY} seconds...")
                await asyncio.sleep(RESTART_DELAY)
                
                # Create new session for retry
                try:
                    await bot.session.close()
                except:
                    pass
                    
                global session
                session = AiohttpSession(
                    timeout=aiohttp.ClientTimeout(total=30, connect=10),
                    connector=aiohttp.TCPConnector(
                        limit=100,
                        limit_per_host=10,
                        ttl_dns_cache=300,
                        use_dns_cache=True,
                        keepalive_timeout=30,
                        enable_cleanup_closed=True
                    )
                )
                
                # Create new bot instance
                global bot
                bot = Bot(token=BOT_TOKEN, session=session)
                
                continue
            else:
                logger.critical(f"💀 Max restart attempts reached. Exiting.")
                break
    
    # Cleanup
    await graceful_shutdown()

async def main():
    """Main function with comprehensive error handling"""
    logger.info("🤖 TNVED Bot starting up...")
    
    try:
        # Test initial connection
        me = await bot.get_me()
        logger.info(f"✅ Bot connected successfully: @{me.username} (ID: {me.id})")
        
        # Start polling with retry mechanism
        await start_polling_with_retry()
        
    except Exception as e:
        logger.critical(f"💀 Fatal error during startup: {e}")
        await graceful_shutdown()
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.critical(f"💀 Unexpected error: {e}")
        sys.exit(1) 