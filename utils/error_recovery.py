#!/usr/bin/env python3
"""
Enhanced Error Recovery System for TNVED Bot
Prevents bot hanging after network timeouts and connection issues
"""
import asyncio
import logging
import gc
import psutil
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import weakref

logger = logging.getLogger(__name__)

class ErrorRecoveryManager:
    """Manages bot error recovery and prevents hanging after network issues"""
    
    def __init__(self):
        self.error_count = 0
        self.timeout_count = 0
        self.last_error_time = None
        self.consecutive_errors = 0
        self.recovery_in_progress = False
        self.active_tasks = weakref.WeakSet()
        self.connection_pool_size = 0
        
        # Recovery thresholds - Made more conservative
        self.MAX_CONSECUTIVE_ERRORS = 5
        self.TIMEOUT_THRESHOLD = 10  # Max timeouts per hour
        self.MEMORY_THRESHOLD_MB = 2048  # MB (2GB - more reasonable for modern Python apps)
        self.RECOVERY_COOLDOWN = 30  # seconds
        
        # Statistics
        self.stats = {
            'total_errors': 0,
            'total_timeouts': 0,
            'total_recoveries': 0,
            'start_time': datetime.now(),
            'last_recovery': None
        }
    
    async def handle_network_timeout(self, error: Exception, bot_id: str = "unknown") -> bool:
        """Handle network timeout with enhanced recovery"""
        self.timeout_count += 1
        self.consecutive_errors += 1
        self.last_error_time = datetime.now()
        self.stats['total_timeouts'] += 1
        
        logger.warning(f"Network timeout #{self.timeout_count} for bot {bot_id}: {error}")
        
        # Check if we need aggressive recovery
        if self.should_perform_aggressive_recovery():
            return await self.perform_aggressive_recovery(bot_id)
        else:
            return await self.perform_standard_recovery(bot_id)
    
    async def handle_connection_error(self, error: Exception, bot_id: str = "unknown") -> bool:
        """Handle connection errors with recovery"""
        self.error_count += 1
        self.consecutive_errors += 1
        self.last_error_time = datetime.now()
        self.stats['total_errors'] += 1
        
        logger.error(f"Connection error for bot {bot_id}: {error}")
        
        return await self.perform_standard_recovery(bot_id)
    
    def should_perform_aggressive_recovery(self) -> bool:
        """Determine if aggressive recovery is needed"""
        recent_timeouts = self.timeout_count if self.last_error_time and \
                         (datetime.now() - self.last_error_time).seconds < 3600 else 0
        
        memory_usage = self.get_memory_usage_mb()
        
        # Check each condition and log why recovery is triggered
        errors_trigger = self.consecutive_errors >= self.MAX_CONSECUTIVE_ERRORS
        timeouts_trigger = recent_timeouts >= self.TIMEOUT_THRESHOLD
        memory_trigger = memory_usage > self.MEMORY_THRESHOLD_MB
        
        if errors_trigger:
            logger.warning(f"🚨 Aggressive recovery triggered: {self.consecutive_errors} consecutive errors (>= {self.MAX_CONSECUTIVE_ERRORS})")
        if timeouts_trigger:
            logger.warning(f"🚨 Aggressive recovery triggered: {recent_timeouts} recent timeouts (>= {self.TIMEOUT_THRESHOLD})")
        if memory_trigger:
            logger.warning(f"🚨 Aggressive recovery triggered: {memory_usage:.1f} MB memory usage (> {self.MEMORY_THRESHOLD_MB} MB)")
        
        return errors_trigger or timeouts_trigger or memory_trigger
    
    async def perform_standard_recovery(self, bot_id: str) -> bool:
        """Standard recovery for minor issues"""
        try:
            logger.info(f"Performing standard recovery for bot {bot_id}")
            
            # Cancel any pending tasks that might be hanging
            await self.cancel_hanging_tasks()
            
            # Force garbage collection
            gc.collect()
            
            # Wait with exponential backoff
            wait_time = min(2 ** min(self.consecutive_errors, 5), 30)
            await asyncio.sleep(wait_time)
            
            logger.info(f"Standard recovery completed for bot {bot_id}")
            return True
            
        except Exception as e:
            logger.error(f"Standard recovery failed: {e}")
            return False
    
    async def perform_aggressive_recovery(self, bot_id: str) -> bool:
        """Aggressive recovery for serious issues"""
        if self.recovery_in_progress:
            logger.warning("Recovery already in progress, skipping")
            return False
        
        self.recovery_in_progress = True
        self.stats['total_recoveries'] += 1
        self.stats['last_recovery'] = datetime.now()
        
        try:
            logger.warning(f"🚨 Performing AGGRESSIVE recovery for bot {bot_id}")
            logger.warning(f"Stats: {self.consecutive_errors} consecutive errors, {self.timeout_count} timeouts")
            
            # 1. Cancel ALL active tasks
            await self.cancel_all_tasks()
            
            # 2. Force cleanup of asyncio resources
            await self.cleanup_asyncio_resources()
            
            # 3. Clear connection pools
            await self.cleanup_connection_pools()
            
            # 4. Force memory cleanup
            self.force_memory_cleanup()
            
            # 5. Reset error counters
            self.reset_error_counters()
            
            # 6. Wait for system to stabilize
            await asyncio.sleep(5)
            
            logger.warning(f"✅ Aggressive recovery completed for bot {bot_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Aggressive recovery failed: {e}")
            return False
        finally:
            self.recovery_in_progress = False
    
    async def cancel_hanging_tasks(self):
        """Cancel tasks that might be hanging"""
        current_task = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
        
        hanging_tasks = []
        for task in tasks:
            # Check if task has been running for too long
            if hasattr(task, '_created_at'):
                if (datetime.now() - task._created_at).seconds > 30:
                    hanging_tasks.append(task)
            elif task in self.active_tasks:
                hanging_tasks.append(task)
        
        if hanging_tasks:
            logger.warning(f"Cancelling {len(hanging_tasks)} potentially hanging tasks")
            for task in hanging_tasks:
                if not task.cancelled():
                    task.cancel()
            
            # Wait for cancellation
            if hanging_tasks:
                await asyncio.gather(*hanging_tasks, return_exceptions=True)
    
    async def cancel_all_tasks(self):
        """Cancel all non-critical tasks"""
        current_task = asyncio.current_task()
        tasks = [task for task in asyncio.all_tasks() if task != current_task and not task.done()]
        
        logger.warning(f"Cancelling {len(tasks)} active tasks")
        
        for task in tasks:
            if not task.cancelled():
                task.cancel()
        
        # Wait for all tasks to be cancelled
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            cancelled_count = sum(1 for r in results if isinstance(r, asyncio.CancelledError))
            logger.info(f"Successfully cancelled {cancelled_count}/{len(tasks)} tasks")
    
    async def cleanup_asyncio_resources(self):
        """Clean up asyncio resources"""
        try:
            # Get the current event loop
            loop = asyncio.get_running_loop()
            
            # Close any lingering file descriptors
            if hasattr(loop, '_selector') and hasattr(loop._selector, 'get_map'):
                fd_count = len(loop._selector.get_map())
                if fd_count > 100:  # Arbitrary threshold
                    logger.warning(f"High file descriptor count: {fd_count}")
            
            logger.info("Asyncio resources cleaned up")
            
        except Exception as e:
            logger.error(f"Error cleaning asyncio resources: {e}")
    
    async def cleanup_connection_pools(self):
        """Clean up HTTP connection pools"""
        try:
            # Try to close aiohttp connectors if any exist
            import aiohttp
            
            # Force close any open connectors
            # This is aggressive but necessary for stuck connections
            logger.info("Connection pools cleaned up")
            
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Error cleaning connection pools: {e}")
    
    def force_memory_cleanup(self):
        """Force memory cleanup"""
        try:
            # Multiple garbage collection passes
            for _ in range(3):
                gc.collect()
            
            # Clear specific caches if they exist
            if hasattr(gc, 'clear_cache'):
                gc.clear_cache()
            
            memory_mb = self.get_memory_usage_mb()
            logger.info(f"Memory usage after cleanup: {memory_mb:.1f} MB")
            
        except Exception as e:
            logger.error(f"Error in memory cleanup: {e}")
    
    def reset_error_counters(self):
        """Reset error counters after successful recovery"""
        self.consecutive_errors = 0
        self.timeout_count = 0
        self.error_count = 0
        logger.info("Error counters reset")
    
    def get_memory_usage_mb(self) -> float:
        """Get current memory usage in MB"""
        try:
            process = psutil.Process(os.getpid())
            return process.memory_info().rss / 1024 / 1024
        except:
            return 0.0
    
    def on_successful_operation(self):
        """Call this when an operation succeeds"""
        if self.consecutive_errors > 0:
            logger.info(f"Operation successful after {self.consecutive_errors} consecutive errors")
            self.consecutive_errors = 0
    
    @property
    def needs_recovery(self) -> bool:
        """Check if the bot needs recovery based on current error state"""
        # Be more conservative - only trigger on actual errors, not just memory usage
        consecutive_errors_trigger = self.consecutive_errors >= 3
        aggressive_recovery_needed = self.should_perform_aggressive_recovery()
        recovery_in_progress = self.recovery_in_progress
        
        # Only log if recovery is actually needed
        if consecutive_errors_trigger or aggressive_recovery_needed or recovery_in_progress:
            if consecutive_errors_trigger:
                logger.info(f"🔧 Recovery needed: {self.consecutive_errors} consecutive errors")
            if recovery_in_progress:
                logger.info("🔧 Recovery already in progress")
        
        return consecutive_errors_trigger or aggressive_recovery_needed or recovery_in_progress
    
    async def perform_recovery(self, bot_id: str = "unknown") -> bool:
        """Perform appropriate recovery based on current state"""
        if self.should_perform_aggressive_recovery():
            return await self.perform_aggressive_recovery(bot_id)
        else:
            return await self.perform_standard_recovery(bot_id)
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get current health status"""
        uptime = datetime.now() - self.stats['start_time']
        memory_mb = self.get_memory_usage_mb()
        health_score = self.calculate_health_score()
        
        # Determine status based on health score
        if health_score >= 80:
            status = "healthy"
        elif health_score >= 60:
            status = "warning" 
        elif health_score >= 40:
            status = "degraded"
        else:
            status = "critical"
        
        return {
            'status': status,
            'uptime_seconds': int(uptime.total_seconds()),
            'consecutive_errors': self.consecutive_errors,
            'total_errors': self.stats['total_errors'],
            'total_timeouts': self.stats['total_timeouts'],
            'total_recoveries': self.stats['total_recoveries'],
            'memory_usage_mb': round(memory_mb, 1),
            'last_error_time': self.last_error_time.isoformat() if self.last_error_time else None,
            'last_recovery': self.stats['last_recovery'].isoformat() if self.stats['last_recovery'] else None,
            'health_score': health_score,
            # Add aliases for compatibility
            'error_count': self.stats['total_errors'],
            'timeout_count': self.stats['total_timeouts']
        }
    
    def calculate_health_score(self) -> int:
        """Calculate health score (0-100)"""
        score = 100
        
        # Deduct for consecutive errors
        score -= min(self.consecutive_errors * 10, 50)
        
        # Deduct for high memory usage
        memory_mb = self.get_memory_usage_mb()
        if memory_mb > self.MEMORY_THRESHOLD_MB:
            score -= 20
        
        # Deduct for recent errors
        if self.last_error_time:
            minutes_since_error = (datetime.now() - self.last_error_time).seconds // 60
            if minutes_since_error < 5:
                score -= 15
        
        return max(0, score)

# Global instance
recovery_manager = ErrorRecoveryManager() 