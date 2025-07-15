# bot_improved.py - Enhanced version with robust network error handling
import asyncio
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.utils.backoff import BackoffConfig
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from aiogram.exceptions import TelegramNetworkError, TelegramServerError, TelegramRetryAfter

from handlers import user
from config import BOT_TOKEN
from timeout_config import get_session_timeout, get_timeout_config, get_all_settings

# Enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_network.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class NetworkStatsCollector:
    """Collect network statistics for monitoring"""
    def __init__(self):
        self.reset_stats()
    
    def reset_stats(self):
        self.stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'network_errors': 0,
            'server_errors': 0,
            'timeouts': 0,
            'disconnections': 0,
            'last_error': None,
            'last_success': None,
            'start_time': datetime.now()
        }
    
    def record_success(self):
        self.stats['total_requests'] += 1
        self.stats['successful_requests'] += 1
        self.stats['last_success'] = datetime.now()
    
    def record_error(self, error_type: str, error_msg: str = ""):
        self.stats['total_requests'] += 1
        self.stats['last_error'] = datetime.now()
        
        if 'network' in error_type.lower() or 'disconnect' in error_type.lower():
            self.stats['network_errors'] += 1
            if 'disconnect' in error_type.lower():
                self.stats['disconnections'] += 1
        elif 'server' in error_type.lower():
            self.stats['server_errors'] += 1
        elif 'timeout' in error_type.lower():
            self.stats['timeouts'] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        uptime = datetime.now() - self.stats['start_time']
        success_rate = 0
        if self.stats['total_requests'] > 0:
            success_rate = (self.stats['successful_requests'] / self.stats['total_requests']) * 100
        
        return {
            **self.stats,
            'uptime_seconds': uptime.total_seconds(),
            'success_rate': success_rate,
            'error_rate': 100 - success_rate
        }

# Global stats collector
network_stats = NetworkStatsCollector()

class RobustAiohttpSession(AiohttpSession):
    """Enhanced aiohttp session with robust error handling and monitoring"""
    
    def __init__(self):
        super().__init__()
        self.config = get_all_settings()
        self.last_reconnect = datetime.now()
        
    async def create_session(self) -> aiohttp.ClientSession:
        """Create aiohttp session with robust settings for unstable networks"""
        logger.info(f"Creating session with config: {self.config}")
        
        # Create connector with enhanced settings for unstable networks
        connector = aiohttp.TCPConnector(
            limit=self.config['connection_limit'],
            limit_per_host=self.config['connection_limit_per_host'],
            ttl_dns_cache=self.config['dns_cache_ttl'],
            use_dns_cache=True,
            keepalive_timeout=self.config['keepalive_timeout'],
            enable_cleanup_closed=True,  # Clean up closed connections
            force_close=True,  # Force close connections to avoid reuse issues
            ssl=False,  # Disable SSL verification if problematic
        )
        
        # Create timeout with current config
        timeout = aiohttp.ClientTimeout(
            total=self.config['total_timeout'],
            connect=self.config['connect_timeout'],
            sock_read=self.config['read_timeout'],
        )
        
        session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                'User-Agent': 'TNVED-Bot/1.0 (Enhanced Network Handler)',
                'Connection': 'keep-alive',
                'Keep-Alive': 'timeout=300, max=100'
            }
        )
        
        return session
    
    async def make_request(self, *args, **kwargs):
        """Override make_request with enhanced error handling"""
        max_retries = 3
        base_delay = 1.0
        
        for attempt in range(max_retries + 1):
            try:
                result = await super().make_request(*args, **kwargs)
                network_stats.record_success()
                return result
                
            except TelegramNetworkError as e:
                error_msg = str(e)
                logger.warning(f"Network error on attempt {attempt + 1}/{max_retries + 1}: {error_msg}")
                network_stats.record_error("TelegramNetworkError", error_msg)
                
                if "ServerDisconnectedError" in error_msg or "disconnect" in error_msg.lower():
                    network_stats.record_error("ServerDisconnectedError", error_msg)
                    logger.warning("Server disconnected - will recreate session after delay")
                    
                    # Force session recreation on disconnect
                    if hasattr(self, '_session') and self._session:
                        await self._session.close()
                        self._session = None
                
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    logger.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    logger.error(f"Max retries exceeded. Last error: {error_msg}")
                    raise
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Unexpected error on attempt {attempt + 1}: {error_msg}")
                network_stats.record_error(type(e).__name__, error_msg)
                
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise

# Create enhanced session
session = RobustAiohttpSession()

# Initialize bot with enhanced session
bot = Bot(
    token=BOT_TOKEN, 
    parse_mode=ParseMode.HTML,
    session=session
)

dp = Dispatcher(storage=MemoryStorage())

async def on_startup():
    """Enhanced startup with connection validation"""
    try:
        # Delete any existing webhook with retries
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await bot.delete_webhook(drop_pending_updates=True)
                break
            except Exception as e:
                logger.warning(f"Webhook deletion attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    logger.error("Failed to delete webhook after all retries")
        
        # Set bot commands with retries
        commands = [
            BotCommand(command="start", description="Начать"),
            BotCommand(command="predict", description="Поиск кода ТН ВЭД"),
            BotCommand(command="stats", description="Статистика подключения")
        ]
        
        for attempt in range(max_retries):
            try:
                await bot.set_my_commands(commands)
                break
            except Exception as e:
                logger.warning(f"Commands setup attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
        
        # Get bot info to validate connection
        try:
            me = await bot.get_me()
            logger.info(f"✅ Bot connected successfully: @{me.username} (ID: {me.id})")
            
            # Log network configuration
            config = get_all_settings()
            logger.info(f"Network config: {config}")
            
        except Exception as e:
            logger.error(f"Failed to get bot info: {e}")
            
    except Exception as e:
        logger.error(f"Startup error: {e}")
        raise

async def periodic_stats_logger():
    """Periodically log network statistics"""
    while True:
        await asyncio.sleep(300)  # Log every 5 minutes
        stats = network_stats.get_stats()
        logger.info(f"Network Stats - Success Rate: {stats['success_rate']:.1f}%, "
                   f"Total Requests: {stats['total_requests']}, "
                   f"Network Errors: {stats['network_errors']}, "
                   f"Disconnections: {stats['disconnections']}")

async def health_check():
    """Periodic health check"""
    while True:
        await asyncio.sleep(60)  # Check every minute
        try:
            await bot.get_me()
        except Exception as e:
            logger.warning(f"Health check failed: {e}")

async def main():
    """Enhanced main function with robust error handling"""
    dp.include_router(user.router)
    await on_startup()
    
    # Start background tasks
    stats_task = asyncio.create_task(periodic_stats_logger())
    health_task = asyncio.create_task(health_check())
    
    # Enhanced polling configuration
    config = get_timeout_config()
    
    try:
        logger.info(f"🚀 Starting enhanced polling with {config['polling_timeout']}s timeout")
        logger.info("Network resilience features enabled:")
        logger.info("- Automatic reconnection on disconnect")
        logger.info("- Exponential backoff retry strategy")
        logger.info("- Connection pool optimization")
        logger.info("- Network statistics monitoring")
        
        await dp.start_polling(
            bot,
            polling_timeout=config['polling_timeout'],
            handle_as_tasks=True,
            backoff_config=BackoffConfig(
                min_delay=config.get('min_retry_delay', 1.0),
                max_delay=config.get('max_retry_delay', 60.0),
                factor=config.get('retry_multiplier', 1.5),
                jitter=0.2,  # Increased jitter to avoid thundering herd
            ),
            allowed_updates=None,
        )
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Polling error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Log final stats
        final_stats = network_stats.get_stats()
        logger.info(f"Final Network Stats: {final_stats}")
        raise
    finally:
        # Cleanup
        stats_task.cancel()
        health_task.cancel()
        
        try:
            await bot.session.close()
            logger.info("Bot session closed successfully")
        except Exception as e:
            logger.error(f"Error closing session: {e}")

if __name__ == "__main__":
    try:
        logger.info("🚀 Starting Enhanced TNVED Bot with network resilience...")
        logger.info(f"Configuration: {get_all_settings()}")
        
        # Run with enhanced error handling
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Critical error: {e}")
        import traceback
        logger.error(f"Full traceback: {traceback.format_exc()}")
        
        # Wait a bit before potential restart
        time.sleep(5) 