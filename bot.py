#!/usr/bin/env python3
"""
Memory-Optimized TNVED Bot
Features: Basic error handling, network resilience, minimal monitoring for low memory usage
Memory optimizations: Disabled auto-restart, reduced monitoring, simplified health checks, garbage collection
"""

import asyncio
import logging
import time
import sys
import os
import gc
import signal
import psutil
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.utils.backoff import BackoffConfig
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Update
from aiogram.exceptions import TelegramNetworkError, TelegramServerError, TelegramRetryAfter, TelegramBadRequest

from handlers import user
from config import BOT_TOKEN
from utils.error_recovery import recovery_manager

# Enhanced logging configuration
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_FILE = 'bot.log'

# Setup logging with both file and console output
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Global configuration
@dataclass
class BotConfig:
    """Bot configuration with enhanced settings"""
    # Connection settings
    connection_timeout: float = 30.0
    read_timeout: float = 25.0
    connect_timeout: float = 10.0
    
    # Retry settings
    max_retry_attempts: int = 5
    retry_delay: float = 2.0
    exponential_backoff: bool = True
    
    # Health check settings (minimal)
    health_check_interval: float = 3600.0  # 1 hour (very reduced frequency)
    health_check_timeout: float = 10.0
    
    # Polling settings
    polling_timeout: int = 60
    polling_retry_after: int = 5
    polling_relax: float = 0.1
    
    # Auto-restart settings (disabled for memory optimization)
    auto_restart_enabled: bool = False
    max_restart_attempts: int = 0
    restart_delay: float = 10.0
    
    # Monitoring settings (minimal)
    enable_monitoring: bool = False
    stats_log_interval: float = 3600.0  # 1 hour (minimal logging)
    
    # Error handling
    ignore_conflict_errors: bool = False
    log_all_errors: bool = False

config = BotConfig()

# Enhanced Statistics and Monitoring
@dataclass  
class NetworkStats:
    """Simplified network statistics tracking"""
    success_count: int = 0
    error_count: int = 0
    retry_count: int = 0
    timeout_count: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    
    def record_success(self):
        self.success_count += 1
    
    def record_error(self, error_type: str, error_msg: str = ""):
        self.error_count += 1
        # Only log critical errors to reduce memory
        if "Conflict" in error_msg:
            logger.error(f"⚠️ Bot conflict detected: {error_msg}")
    
    def record_retry(self):
        self.retry_count += 1
    
    def record_timeout(self):
        self.timeout_count += 1
    
    def get_stats(self) -> Dict[str, Any]:
        total = self.success_count + self.error_count
        uptime = datetime.now() - self.start_time
        return {
            'success_rate': (self.success_count / max(total, 1)) * 100,
            'total_requests': total,
            'retry_count': self.retry_count,
            'timeout_count': self.timeout_count,
            'uptime_seconds': uptime.total_seconds()
        }

# Global stats instance
network_stats = NetworkStats()

# Enhanced Session with Auto-Recovery
class RobustAiohttpSession(AiohttpSession):
    """Enhanced session with comprehensive error handling and auto-recovery"""
    
    def __init__(self):
        # Initialize with default settings first
        super().__init__()
        self.consecutive_errors = 0
        self.last_successful_request = datetime.now()
        self.session = None
        self.connector = None
        
    async def create_session(self):
        """Create session with optimized settings"""
        # Close existing session if it exists
        await self.close_session()
        
        # Create simple connector with reduced limits for memory optimization
        self.connector = aiohttp.TCPConnector(
            limit=20,           # Reduced from 100
            limit_per_host=5,   # Reduced from 10
            ttl_dns_cache=60,   # Reduced from 300
            use_dns_cache=False, # Disabled to save memory
            keepalive_timeout=15, # Reduced from 30
            enable_cleanup_closed=True
        )
        
        # Create session with optimized settings
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=aiohttp.ClientTimeout(
                total=config.connection_timeout,
                connect=config.connect_timeout,
                sock_read=config.read_timeout
            ),
            headers={
                'User-Agent': 'TNVED-Bot/2.0 (Enhanced)'
            }
        )
        
        # Set the session
        self._session = self.session
        
        return self.session
    
    async def close_session(self):
        """Properly close session and connector"""
        try:
            if hasattr(self, 'session') and self.session:
                if not self.session.closed:
                    await self.session.close()
                    await asyncio.sleep(0.1)  # Give time for cleanup
                    logger.debug("✅ Session closed successfully")
                else:
                    logger.debug("ℹ️ Session was already closed")
                self.session = None
                
            if hasattr(self, 'connector') and self.connector:
                if not self.connector.closed:
                    await self.connector.close()
                    await asyncio.sleep(0.1)  # Give time for cleanup
                    logger.debug("✅ Connector closed successfully")
                self.connector = None
                
        except Exception as e:
            logger.warning(f"⚠️ Error closing session: {e}")
            # Still clear references even if close failed
            try:
                self.session = None
                self.connector = None
            except Exception:
                pass
    
    async def close(self):
        """Close method for compatibility"""
        await self.close_session()
        try:
            await super().close()
        except Exception as e:
            logger.warning(f"⚠️ Error closing parent session: {e}")
    
    @property
    def closed(self):
        """Check if session is closed"""
        if not hasattr(self, 'session') or self.session is None:
            return True
        return self.session.closed
    
    async def make_request(self, *args, **kwargs) -> Any:
        """Enhanced request with retry logic and error handling"""
        method = kwargs.get('method', 'GET')
        url = kwargs.get('url', 'unknown')
        
        for attempt in range(config.max_retry_attempts + 1):
            try:
                # Add delay for subsequent attempts
                if attempt > 0:
                    delay = config.retry_delay
                    if config.exponential_backoff:
                        delay *= (2 ** (attempt - 1))
                    
                    logger.info(f"🔄 Retry {attempt}/{config.max_retry_attempts} after {delay:.1f}s")
                    await asyncio.sleep(delay)
                    network_stats.record_retry()
                
                # Make the request
                result = await super().make_request(*args, **kwargs)
                
                # Success
                network_stats.record_success()
                self.consecutive_errors = 0
                self.last_successful_request = datetime.now()
                
                # Notify recovery manager of successful operation
                recovery_manager.on_successful_operation()
                
                return result
                
            except TelegramRetryAfter as e:
                retry_after = e.retry_after
                logger.warning(f"⏳ Rate limited, waiting {retry_after}s")
                await asyncio.sleep(retry_after)
                continue
                
            except TelegramNetworkError as e:
                error_msg = str(e)
                network_stats.record_error("TelegramNetworkError", error_msg)
                self.consecutive_errors += 1
                
                # Handle specific errors
                if "ServerDisconnectedError" in error_msg:
                    logger.warning("🔌 Server disconnected, retrying...")
                elif "Conflict" in error_msg and "getUpdates" in error_msg:
                    if config.ignore_conflict_errors:
                        logger.warning("⚠️ Conflict ignored (another bot instance)")
                        await asyncio.sleep(5)
                        continue
                    else:
                        logger.error("❌ Bot conflict detected! Stopping to prevent issues.")
                        raise
                elif "TimeoutError" in error_msg or "timeout" in error_msg.lower():
                    network_stats.record_timeout()
                    logger.warning(f"⏰ Timeout on attempt {attempt + 1}")
                    
                    # Use enhanced recovery manager for timeouts
                    await recovery_manager.handle_network_timeout(e, str(BOT_TOKEN[-10:]))
                
                # If too many consecutive errors, use recovery manager
                if self.consecutive_errors >= 3:
                    # Let recovery manager handle this situation
                    await recovery_manager.handle_connection_error(e, str(BOT_TOKEN[-10:]))
                    # Additional delay based on recovery recommendations
                    extra_delay = min(30, self.consecutive_errors * 2)
                    logger.warning(f"🛑 Too many errors, adding {extra_delay}s delay")
                    await asyncio.sleep(extra_delay)
                
                if attempt < config.max_retry_attempts:
                    continue
                else:
                    logger.error(f"❌ All retry attempts failed: {error_msg}")
                    raise
                    
            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                network_stats.record_error(error_type, error_msg)
                
                if attempt < config.max_retry_attempts:
                    logger.warning(f"🔄 Unexpected error on attempt {attempt + 1}: {error_type}")
                    continue
                else:
                    logger.error(f"❌ Unexpected error after all retries: {error_type} - {error_msg}")
                    raise
        
        # Should not reach here
        raise RuntimeError("Maximum retry attempts exceeded")

# Health Monitor
class HealthMonitor:
    """Simplified health monitoring system"""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.health_status = "healthy"
        
    async def check_health(self, bot: Bot) -> bool:
        """Simplified health check"""
        try:
            # Simple connectivity check
            await bot.get_me()
            
            # Only check for extreme memory usage 
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            if memory_mb > 2000:  # Only flag truly excessive memory usage (2GB+)
                logger.warning(f"⚠️ High memory usage: {memory_mb:.1f}MB")
                self.health_status = "warning"
                return False
            
            self.health_status = "healthy"
            return True
            
        except Exception as e:
            self.health_status = "critical"
            logger.error(f"❌ Health check failed: {e}")
            return False

# Global health monitor
health_monitor = HealthMonitor()

# Restart manager removed for memory optimization (auto-restart disabled)

# Enhanced Bot Class
class EnhancedBot(Bot):
    """Enhanced Bot with additional monitoring and error handling"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_update_time = datetime.now()
        self.processed_updates = 0
        
    async def process_update(self, update: Update):
        """Process update with enhanced error handling"""
        self.last_update_time = datetime.now()
        self.processed_updates += 1
        
        try:
            return await super().process_update(update)
        except Exception as e:
            logger.error(f"❌ Error processing update {update.update_id}: {e}")
            # Don't re-raise to prevent bot crash
            return None

# Will be created in async context
session = None
bot = None

# Dispatcher with enhanced error handling
dp = Dispatcher(storage=MemoryStorage())

# Background Tasks
async def minimal_health_check():
    """Minimal health monitoring (disabled by default)"""
    global bot
    
    while True:
        try:
            await asyncio.sleep(config.health_check_interval)
            
            if config.enable_monitoring and bot:
                # Just check basic connectivity, no restarts
                await health_monitor.check_health(bot)
                    
        except Exception as e:
            logger.error(f"❌ Health check task error: {e}")
            await asyncio.sleep(300)  # Wait 5 minutes before retry

async def periodic_stats_logging():
    """Minimal statistics logging"""
    while True:
        try:
            await asyncio.sleep(config.stats_log_interval)
            
            if config.enable_monitoring:
                stats = network_stats.get_stats()
                logger.info(f"📊 Bot uptime: {stats['uptime_seconds']:.0f}s, "
                           f"requests: {stats['total_requests']}")
                    
        except Exception as e:
            logger.error(f"❌ Stats logging error: {e}")
            await asyncio.sleep(60)

async def memory_cleanup():
    """Periodic memory cleanup for optimization"""
    while True:
        try:
            await asyncio.sleep(1800)  # Clean up every 30 minutes
            
            # Force garbage collection
            collected = gc.collect()
            
            # Clean up predictor memory
            try:
                from utils.predictor import get_enhanced_prediction_system
                predictor = get_enhanced_prediction_system()
                if predictor:
                    predictor.cleanup_memory()
            except Exception as e:
                logger.error(f"❌ Error cleaning predictor memory: {e}")
            
            # Log current memory usage
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            logger.info(f"🧹 Memory cleanup: collected {collected} objects")
            logger.info(f"📊 Current memory usage: {memory_mb:.1f}MB")
                    
        except Exception as e:
            logger.error(f"❌ Memory cleanup error: {e}")
            await asyncio.sleep(300)

async def health_monitoring():
    """Monitor bot health and handle critical issues - DISABLED FOR STABILITY"""
    # Health monitoring disabled to prevent hanging issues
    logger.info("🔒 Health monitoring disabled for memory optimization and stability")
    
    while True:
        try:
            # Just sleep indefinitely - this task exists but does nothing
            await asyncio.sleep(3600)  # Check every hour but do nothing
            
            # Only do minimal health check if really needed
            if recovery_manager.consecutive_errors > 20:
                logger.warning("🚨 Critical: Many consecutive errors detected")
                await recovery_manager.perform_recovery()
                
        except Exception as e:
            logger.error(f"❌ Health monitoring error: {e}")
            await asyncio.sleep(600)  # Sleep 10 minutes on error

# Enhanced startup
async def on_startup():
    """Enhanced startup with comprehensive initialization"""
    global session, bot
    
    try:
        logger.info("🚀 Starting TNVED Bot with enhanced features...")
        
        # Create session and bot in async context
        session = RobustAiohttpSession()
        await session.create_session()
        bot = EnhancedBot(
            token=BOT_TOKEN,
            parse_mode=ParseMode.HTML,
            session=session
        )
        
        # Clear webhook
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("✅ Webhook cleared")
        
        # Set bot commands
        commands = [
            BotCommand(command="start", description="Начать работу с ботом"),
            BotCommand(command="search", description="Поиск кода ТН ВЭД"),
            BotCommand(command="help", description="Помощь"),
            BotCommand(command="language", description="Сменить язык"),
            BotCommand(command="contacts", description="Контакты"),
            BotCommand(command="myinfo", description="Информация о пользователе")
        ]
        await bot.set_my_commands(commands)
        logger.info("✅ Bot commands set")
        
        # Get bot info
        me = await bot.get_me()
        logger.info(f"✅ Bot started successfully: @{me.username} (ID: {me.id})")
        
        # Set initial health status
        health_monitor.health_status = "healthy"
        
        # Start background tasks (minimal monitoring)
        asyncio.create_task(memory_cleanup())  # Always run memory cleanup
        
        if config.enable_monitoring:
            asyncio.create_task(minimal_health_check())
            asyncio.create_task(periodic_stats_logging())
            logger.info("✅ Background monitoring started")
        else:
            logger.info("✅ Bot started (monitoring disabled for memory optimization)")
        
    except Exception as e:
        logger.error(f"❌ Startup error: {e}")
        raise

# Configuration for production mode
PRODUCTION_MODE = os.getenv('PRODUCTION_MODE', 'false').lower() == 'true'
IMMEDIATE_SHUTDOWN = os.getenv('IMMEDIATE_SHUTDOWN', 'false').lower() == 'true' or PRODUCTION_MODE

if PRODUCTION_MODE or IMMEDIATE_SHUTDOWN:
    logger.info("🔥 PRODUCTION MODE ENABLED - Immediate shutdown on Ctrl+C")

# Global shutdown flag and state
shutdown_event = None
shutdown_initiated = False
shutdown_attempts = 0

def signal_handler(signum, frame):
    """NUCLEAR SHUTDOWN HANDLER - Immediate response to Ctrl+C"""
    global shutdown_initiated, shutdown_attempts
    
    shutdown_attempts += 1
    
    # PRODUCTION MODE: IMMEDIATE DEATH - NO WAITING
    if PRODUCTION_MODE or IMMEDIATE_SHUTDOWN:
        logger.error(f"🚨 PRODUCTION MODE - IMMEDIATE TERMINATION ON Ctrl+C #{shutdown_attempts}")
        print(f"\n💀 PRODUCTION MODE: KILLING BOT IMMEDIATELY (attempt #{shutdown_attempts})")
        try:
            os._exit(1)  # Immediate death, no cleanup
        except:
            import subprocess
            subprocess.run(['taskkill', '/F', '/PID', str(os.getpid())], shell=True)
        return
    
    # FIRST Ctrl+C: Immediate graceful shutdown (max 2 seconds)
    if shutdown_attempts == 1:
        shutdown_initiated = True
        logger.info(f"📨 Received signal {signum} - IMMEDIATE SHUTDOWN INITIATED")
        
        # Remove signal handlers to prevent loops
        try:
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
        except Exception:
            pass
        
        # Set shutdown event immediately
        global shutdown_event
        if shutdown_event and not shutdown_event.is_set():
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(shutdown_event.set)
            except Exception:
                pass
        
        # AGGRESSIVE: Force shutdown after just 2 seconds (not 5!)
        import threading
        def nuclear_shutdown():
            import time
            time.sleep(2)  # Only 2 seconds for graceful shutdown
            if shutdown_initiated:
                logger.error("🚨 NUCLEAR SHUTDOWN - Forcing immediate exit")
                try:
                    # Try multiple exit methods
                    os._exit(1)  # Immediate exit without cleanup
                except:
                    import subprocess
                    subprocess.run(['taskkill', '/F', '/PID', str(os.getpid())], shell=True)
        
        threading.Thread(target=nuclear_shutdown, daemon=True).start()
        
    # SECOND Ctrl+C: INSTANT DEATH - NO MERCY
    elif shutdown_attempts >= 2:
        logger.error("🚨 SECOND Ctrl+C - INSTANT TERMINATION")
        print("\n💀 FORCING IMMEDIATE SHUTDOWN - NO CLEANUP")
        try:
            os._exit(1)  # Immediate death
        except:
            import subprocess
            subprocess.run(['taskkill', '/F', '/PID', str(os.getpid())], shell=True)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Enhanced shutdown with robust task cancellation
async def on_shutdown():
    """Enhanced shutdown with cleanup"""
    global session, bot
    
    try:
        logger.info("🛑 Shutting down bot...")
        
        # Get current task to exclude it from cancellation
        current_task = asyncio.current_task()
        
        # Get all tasks except the current one and already done ones
        tasks = [
            task for task in asyncio.all_tasks() 
            if not task.done() and task != current_task
        ]
        
        if tasks:
            logger.info(f"🔄 Cancelling {len(tasks)} running tasks...")
            
            # Cancel tasks
            for task in tasks:
                try:
                    task.cancel()
                except Exception:
                    pass  # Ignore cancellation errors
            
            # Wait for tasks to complete cancellation with proper error handling
            if tasks:
                try:
                    # Use asyncio.wait instead of gather to handle cancellations better
                    done, pending = await asyncio.wait(
                        tasks, 
                        timeout=2.0,  # Reduced timeout
                        return_when=asyncio.ALL_COMPLETED
                    )
                    
                    if pending:
                        logger.warning(f"⏰ {len(pending)} tasks didn't cancel within timeout")
                        # Force cancel remaining tasks
                        for task in pending:
                            try:
                                task.cancel()
                            except Exception:
                                pass
                        
                        # Give them one more second
                        try:
                            await asyncio.wait(pending, timeout=0.5)
                        except Exception:
                            pass
                            
                except asyncio.CancelledError:
                    logger.warning("⚠️ Shutdown was cancelled during task cleanup - proceeding with direct cleanup")
                    raise  # Re-raise to handle at function level
                except Exception as e:
                    logger.warning(f"⚠️ Error during task cancellation: {e}")
        
        # Close sessions with error handling
        try:
            if session and not session.closed:
                await session.close()
                logger.info("✅ Custom session closed")
        except Exception as e:
            logger.warning(f"⚠️ Error closing custom session: {e}")
    
    except asyncio.CancelledError:
        logger.info("🛑 Shutdown function cancelled - performing synchronous cleanup")
        # Perform synchronous cleanup when async operations are cancelled
        try:
            # Force cleanup without async operations
            if session and hasattr(session, '_session') and session._session:
                try:
                    if hasattr(session._session, '_connector') and session._session._connector:
                        session._session._connector.close()
                    session._session = None
                except:
                    pass
                logger.info("🧹 Sync session cleanup")
            
            if bot and hasattr(bot, 'session') and bot.session:
                try:
                    if hasattr(bot.session, '_session') and bot.session._session:
                        bot.session._session = None
                except:
                    pass
                logger.info("🧹 Sync bot cleanup")
            
            logger.info("✅ Sync cleanup completed")
        except Exception as e:
            logger.warning(f"⚠️ Error in sync cleanup: {e}")
        finally:
            logger.info("🛑 Cleanup cancelled - performing direct cleanup")
            # Direct cleanup for when everything else fails
            try:
                if session and hasattr(session, 'close'):
                    logger.info("🧹 Direct session cleanup")
                if bot and hasattr(bot, 'session'):  
                    logger.info("🧹 Direct bot cleanup")
                logger.info("✅ Direct cleanup completed")
            except:
                pass
            logger.info("🏁 Bot shutdown finished")
        return  # Exit cleanly
    
    except Exception as e:
        logger.error(f"❌ Unexpected error in shutdown: {e}")
        return
        
    # Continue with normal shutdown if no exceptions
    try:
        if bot and hasattr(bot, 'session') and bot.session:
            if hasattr(bot.session, 'close') and not bot.session.closed:
                await bot.session.close()
                logger.info("✅ Bot session closed")
    except Exception as e:
        logger.warning(f"⚠️ Error closing bot session: {e}")
    
    # Log final stats (with error handling)
    try:
        final_stats = network_stats.get_stats()
        logger.info(f"📊 Final stats: {final_stats['success_rate']:.1f}% success, "
                   f"{final_stats['total_requests']} total requests, "
                   f"uptime: {final_stats['uptime_seconds']:.0f}s")
    except Exception as e:
        logger.warning(f"⚠️ Error getting final stats: {e}")
    
    logger.info("🏁 Bot shutdown finished")
    print("✅ Bot shutdown completed normally")
    print("🏁 Bot process finished")

# Main function with enhanced error handling
async def main():
    """Enhanced main function with comprehensive error handling"""
    global bot, shutdown_event
    
    # Initialize shutdown event in async context
    shutdown_event = asyncio.Event()
    
    # Include router
    dp.include_router(user.router)
    
    # Set up startup only (shutdown will be handled manually)
    dp.startup.register(on_startup)
    
    # Create a temporary bot instance for polling
    # The actual bot will be created in the on_startup handler
    temp_bot = Bot(token=BOT_TOKEN)
    
    polling_task = None
    health_task = None
    
    try:
        logger.info("🚀 Starting bot polling...")
        
        # Create tasks with names for better tracking
        polling_task = asyncio.create_task(
            dp.start_polling(
                temp_bot,
                polling_timeout=config.polling_timeout,
                handle_as_tasks=True,
                backoff_config=BackoffConfig(
                    min_delay=1.0,
                    max_delay=60.0,
                    factor=2.0,
                    jitter=0.1
                ),
                allowed_updates=None,
                drop_pending_updates=True,
                relax=config.polling_relax,
                retry_after=config.polling_retry_after
            ),
            name="polling_task"
        )
        
        # Create a task for health monitoring
        health_task = asyncio.create_task(health_monitoring(), name="health_task")
        
        # Wait for shutdown event or polling completion
        done, pending = await asyncio.wait(
            [polling_task, health_task, asyncio.create_task(shutdown_event.wait())],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        # If shutdown was triggered, log it
        if shutdown_event.is_set():
            logger.info("🛑 Shutdown event received")
        
        # Cancel pending tasks
        for task in pending:
            task.cancel()
        
    except KeyboardInterrupt:
        logger.info("📨 KeyboardInterrupt received, shutting down...")
    except asyncio.CancelledError:
        logger.info("🛑 Main task cancelled, shutting down...")
    except Exception as e:
        logger.error(f"❌ Critical polling error: {e}")
    
    finally:
        # Signal shutdown to any remaining tasks
        try:
            shutdown_event.set()
        except Exception:
            pass
        
        # Cancel remaining tasks gracefully with timeout
        tasks_to_cancel = []
        if polling_task and not polling_task.done():
            tasks_to_cancel.append(polling_task)
        if health_task and not health_task.done():
            tasks_to_cancel.append(health_task)
        
        if tasks_to_cancel:
            logger.info(f"🔄 Cancelling {len(tasks_to_cancel)} main tasks...")
            for task in tasks_to_cancel:
                try:
                    task.cancel()
                except Exception:
                    pass
            
            # Wait briefly for cancellation
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                    timeout=1.5
                )
            except Exception:
                logger.warning("⏰ Some main tasks didn't cancel cleanly")
        
        # Perform final cleanup with cancellation handling
        logger.info("🧹 Performing final cleanup...")
        try:
            await asyncio.wait_for(on_shutdown(), timeout=3.0)
            logger.info("✅ Graceful shutdown completed")
        except asyncio.TimeoutError:
            logger.warning("⏰ Cleanup timeout - forcing shutdown")
        except asyncio.CancelledError:
            logger.info("🛑 Cleanup cancelled - performing direct cleanup")
            # Perform direct cleanup without async operations
            try:
                global session, bot
                if session and hasattr(session, '_session'):
                    logger.info("🧹 Direct session cleanup")
                if bot and hasattr(bot, 'session'):
                    logger.info("🧹 Direct bot cleanup")
                logger.info("✅ Direct cleanup completed")
            except Exception as e:
                logger.warning(f"⚠️ Direct cleanup warning: {e}")
        except Exception as e:
            logger.error(f"❌ Error during cleanup: {e}")
        
        logger.info("🏁 Bot shutdown finished")

# Entry point with enhanced error handling
if __name__ == "__main__":
    try:
        # Print startup banner
        print("=" * 60)
        print("🤖 TNVED Bot - Memory Optimized Edition")
        print("🧠 Low memory usage, Basic monitoring, Stable operation")
        if PRODUCTION_MODE or IMMEDIATE_SHUTDOWN:
            print("🔥 PRODUCTION MODE: Ctrl+C = IMMEDIATE SHUTDOWN")
        else:
            print("⚡ DEV MODE: Ctrl+C = 2 sec graceful shutdown")
            print("💡 For server deployment, use: python start_production.py")
        print("🌐 Network errors will auto-recover (normal behavior)")
        print("=" * 60)
        
        # Check if another instance is running (less restrictive)
        current_pid = os.getpid()
        bot_instances = []
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['pid'] != current_pid and proc.info['name'] and 'python' in proc.info['name'].lower():
                    if proc.info['cmdline'] and any('bot.py' in arg for arg in proc.info['cmdline']):
                        bot_instances.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Only stop if there are multiple bot instances
        if len(bot_instances) > 1:
            print(f"⚠️ Multiple bot instances detected (PIDs: {bot_instances})")
            print("🛑 Stopping to prevent conflicts...")
            sys.exit(1)
        elif len(bot_instances) == 1:
            print(f"ℹ️ Found one other bot instance (PID: {bot_instances[0]}), but continuing...")
        else:
            print("✅ No conflicting bot instances found")
        
        # Run the bot with proper exception handling
        try:
            asyncio.run(main())
            print("✅ Bot shutdown completed normally")
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user (KeyboardInterrupt)")
            print("✅ Bot stopped by user")
        except SystemExit:
            print("✅ Bot stopped by system")
        except Exception as e:
            logger.error(f"❌ Fatal error in main: {e}")
            print(f"❌ Bot crashed: {e}")
        
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user (outer)")
        print("✅ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal startup error: {e}")
        print(f"❌ Bot startup failed: {e}")
        sys.exit(1)
    
    print("🏁 Bot process finished")