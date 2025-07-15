#!/usr/bin/env python3
"""
Memory Optimization System for TNVED Bot
Comprehensive memory management to reduce memory usage from 1.7GB to under 500MB
"""

import gc
import os
import sys
import time
import logging
import threading
import psutil
from typing import Optional, Dict, Any, List
from functools import wraps
import weakref

logger = logging.getLogger(__name__)

class MemoryMonitor:
    """Advanced memory monitoring and optimization"""
    
    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.initial_memory = self.get_memory_mb()
        self.peak_memory = self.initial_memory
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes
        self.memory_threshold = 800  # MB - trigger cleanup at 800MB
        self.critical_threshold = 1200  # MB - force aggressive cleanup
        
        # Memory tracking
        self.memory_history = []
        self.max_history = 100
        
        # Component tracking
        self.component_registry = weakref.WeakValueDictionary()
        
        logger.info(f"🔧 Memory Monitor initialized - Initial memory: {self.initial_memory:.1f}MB")
    
    def get_memory_mb(self) -> float:
        """Get current memory usage in MB"""
        try:
            return self.process.memory_info().rss / 1024 / 1024
        except:
            return 0.0
    
    def get_memory_percent(self) -> float:
        """Get memory usage as percentage of system memory"""
        try:
            return self.process.memory_percent()
        except:
            return 0.0
    
    def update_peak_memory(self):
        """Update peak memory tracking"""
        current = self.get_memory_mb()
        if current > self.peak_memory:
            self.peak_memory = current
        
        # Add to history
        self.memory_history.append({
            'timestamp': time.time(),
            'memory_mb': current,
            'memory_percent': self.get_memory_percent()
        })
        
        # Limit history size
        if len(self.memory_history) > self.max_history:
            self.memory_history = self.memory_history[-self.max_history:]
    
    def register_component(self, name: str, component: Any):
        """Register a component for memory tracking"""
        self.component_registry[name] = component
        logger.debug(f"📋 Registered component: {name}")
    
    def should_cleanup(self) -> bool:
        """Check if memory cleanup is needed"""
        current_memory = self.get_memory_mb()
        current_time = time.time()
        
        # Time-based cleanup
        time_based = (current_time - self.last_cleanup) > self.cleanup_interval
        
        # Memory threshold-based cleanup
        memory_based = current_memory > self.memory_threshold
        
        # Critical memory threshold
        critical = current_memory > self.critical_threshold
        
        return time_based or memory_based or critical
    
    def force_cleanup(self) -> Dict[str, Any]:
        """Force immediate memory cleanup"""
        memory_before = self.get_memory_mb()
        objects_before = len(gc.get_objects())
        
        logger.info(f"🧹 Starting memory cleanup - Current: {memory_before:.1f}MB")
        
        # Clear weak references to cleaned components
        dead_refs = []
        for name, ref in self.component_registry.items():
            if ref is None:
                dead_refs.append(name)
        
        for name in dead_refs:
            del self.component_registry[name]
        
        # Clear CUDA cache if available
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.info("🧹 CUDA cache cleared")
        except ImportError:
            pass
        
        # Aggressive garbage collection
        collected_objects = 0
        for i in range(3):  # Multiple passes
            collected = gc.collect()
            collected_objects += collected
            if collected == 0:
                break
        
        memory_after = self.get_memory_mb()
        objects_after = len(gc.get_objects())
        
        self.last_cleanup = time.time()
        
        result = {
            'memory_before_mb': memory_before,
            'memory_after_mb': memory_after,
            'memory_saved_mb': memory_before - memory_after,
            'objects_before': objects_before,
            'objects_after': objects_after,
            'objects_collected': collected_objects,
            'components_tracked': len(self.component_registry)
        }
        
        logger.info(f"🧹 Memory cleanup completed: -{result['memory_saved_mb']:.1f}MB saved, "
                   f"{result['objects_collected']} objects collected")
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        current_memory = self.get_memory_mb()
        self.update_peak_memory()
        
        return {
            'current_memory_mb': current_memory,
            'peak_memory_mb': self.peak_memory,
            'initial_memory_mb': self.initial_memory,
            'memory_growth_mb': current_memory - self.initial_memory,
            'memory_percent': self.get_memory_percent(),
            'last_cleanup_ago_seconds': time.time() - self.last_cleanup,
            'should_cleanup': self.should_cleanup(),
            'components_tracked': len(self.component_registry),
            'gc_objects': len(gc.get_objects()),
            'gc_stats': gc.get_stats() if hasattr(gc, 'get_stats') else None
        }

class ComponentMemoryManager:
    """Memory manager for individual components like models and indexes"""
    
    def __init__(self, monitor: MemoryMonitor):
        self.monitor = monitor
        self.components = {}
        self.usage_tracking = {}
        self.last_used = {}
    
    def register(self, name: str, component: Any, size_estimate_mb: float = 0):
        """Register a component for memory management"""
        self.components[name] = component
        self.usage_tracking[name] = 0
        self.last_used[name] = time.time()
        
        if size_estimate_mb > 0:
            logger.info(f"📦 Registered component '{name}' (~{size_estimate_mb:.1f}MB)")
        else:
            logger.info(f"📦 Registered component '{name}'")
        
        self.monitor.register_component(name, component)
    
    def use_component(self, name: str):
        """Mark component as used (for LRU tracking)"""
        if name in self.usage_tracking:
            self.usage_tracking[name] += 1
            self.last_used[name] = time.time()
    
    def unload_component(self, name: str) -> bool:
        """Unload a specific component to free memory"""
        if name not in self.components:
            return False
        
        try:
            component = self.components[name]
            
            # Clean up component-specific memory
            if hasattr(component, 'cleanup'):
                component.cleanup()
            elif hasattr(component, 'clear'):
                component.clear()
            elif hasattr(component, '__del__'):
                del component
            
            # Remove from tracking
            del self.components[name]
            del self.usage_tracking[name]
            del self.last_used[name]
            
            # Force garbage collection
            gc.collect()
            
            logger.info(f"🗑️ Unloaded component: {name}")
            return True
            
        except Exception as e:
            logger.error(f"Error unloading component {name}: {e}")
            return False
    
    def unload_least_used(self, count: int = 1) -> List[str]:
        """Unload least recently used components"""
        if not self.components:
            return []
        
        # Sort by last used time (oldest first)
        sorted_components = sorted(
            self.last_used.items(),
            key=lambda x: x[1]
        )
        
        unloaded = []
        for name, _ in sorted_components[:count]:
            if self.unload_component(name):
                unloaded.append(name)
        
        return unloaded
    
    def cleanup_unused(self, max_age_seconds: int = 1800) -> List[str]:
        """Cleanup components not used for a specified time (30 minutes default)"""
        current_time = time.time()
        to_unload = []
        
        for name, last_used_time in self.last_used.items():
            if current_time - last_used_time > max_age_seconds:
                to_unload.append(name)
        
        unloaded = []
        for name in to_unload:
            if self.unload_component(name):
                unloaded.append(name)
        
        return unloaded

class CacheManager:
    """Optimized cache management with memory limits"""
    
    def __init__(self, max_size: int = 50, max_memory_mb: float = 50.0):
        self.max_size = max_size
        self.max_memory_mb = max_memory_mb
        self.cache = {}
        self.access_times = {}
        self.memory_estimates = {}
        self.total_memory_estimate = 0.0
    
    def estimate_object_size(self, obj: Any) -> float:
        """Estimate object size in MB"""
        try:
            size_bytes = sys.getsizeof(obj)
            if hasattr(obj, '__dict__'):
                size_bytes += sum(sys.getsizeof(v) for v in obj.__dict__.values())
            return size_bytes / 1024 / 1024
        except:
            return 1.0  # Default estimate
    
    def put(self, key: str, value: Any, force: bool = False):
        """Add item to cache with memory management"""
        estimated_size = self.estimate_object_size(value)
        
        # Check if we need to make space
        while (len(self.cache) >= self.max_size or 
               self.total_memory_estimate + estimated_size > self.max_memory_mb):
            if not self._remove_oldest():
                break
        
        # Add to cache
        if key in self.cache:
            self.total_memory_estimate -= self.memory_estimates.get(key, 0)
        
        self.cache[key] = value
        self.access_times[key] = time.time()
        self.memory_estimates[key] = estimated_size
        self.total_memory_estimate += estimated_size
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache and update access time"""
        if key in self.cache:
            self.access_times[key] = time.time()
            return self.cache[key]
        return None
    
    def _remove_oldest(self) -> bool:
        """Remove oldest accessed item"""
        if not self.cache:
            return False
        
        oldest_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        self.remove(oldest_key)
        return True
    
    def remove(self, key: str):
        """Remove specific item from cache"""
        if key in self.cache:
            self.total_memory_estimate -= self.memory_estimates.get(key, 0)
            del self.cache[key]
            del self.access_times[key]
            del self.memory_estimates[key]
    
    def clear(self):
        """Clear entire cache"""
        self.cache.clear()
        self.access_times.clear()
        self.memory_estimates.clear()
        self.total_memory_estimate = 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        return {
            'cache_size': len(self.cache),
            'max_size': self.max_size,
            'memory_estimate_mb': self.total_memory_estimate,
            'max_memory_mb': self.max_memory_mb,
            'memory_usage_percent': (self.total_memory_estimate / self.max_memory_mb) * 100
        }

class MemoryOptimizer:
    """Main memory optimization coordinator"""
    
    _instance: Optional['MemoryOptimizer'] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.monitor = MemoryMonitor()
        self.component_manager = ComponentMemoryManager(self.monitor)
        self.cache = CacheManager(max_size=50, max_memory_mb=30.0)
        
        # Background monitoring
        self._monitoring = False
        self._monitor_thread = None
        
        # Performance tracking
        self.cleanup_count = 0
        self.total_memory_saved = 0.0
        
        self._initialized = True
        logger.info("🚀 Memory Optimizer initialized")
    
    def start_monitoring(self, interval: int = 60):
        """Start background memory monitoring"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self._monitor_thread.start()
        logger.info(f"📊 Started memory monitoring (interval: {interval}s)")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)
        logger.info("⏹️ Stopped memory monitoring")
    
    def _monitor_loop(self, interval: int):
        """Background monitoring loop"""
        while self._monitoring:
            try:
                if self.monitor.should_cleanup():
                    self.cleanup()
                time.sleep(interval)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
    
    def register_component(self, name: str, component: Any, size_estimate_mb: float = 0):
        """Register a component for memory management"""
        self.component_manager.register(name, component, size_estimate_mb)
    
    def use_component(self, name: str):
        """Mark component as used"""
        self.component_manager.use_component(name)
    
    def cache_result(self, key: str, value: Any):
        """Cache a result with memory management"""
        self.cache.put(key, value)
    
    def get_cached_result(self, key: str) -> Optional[Any]:
        """Get cached result"""
        return self.cache.get(key)
    
    def cleanup(self, aggressive: bool = False) -> Dict[str, Any]:
        """Perform memory cleanup"""
        memory_before = self.monitor.get_memory_mb()
        
        # Clean up unused components
        if aggressive:
            unused = self.component_manager.cleanup_unused(max_age_seconds=600)  # 10 minutes
            if not unused:
                # If no unused components, unload least used
                unused = self.component_manager.unload_least_used(count=2)
        else:
            unused = self.component_manager.cleanup_unused()
        
        # Clear cache if memory is high
        if memory_before > self.monitor.memory_threshold:
            self.cache.clear()
        
        # Force memory cleanup
        cleanup_result = self.monitor.force_cleanup()
        
        self.cleanup_count += 1
        self.total_memory_saved += cleanup_result['memory_saved_mb']
        
        result = {
            **cleanup_result,
            'unused_components_unloaded': unused,
            'cache_cleared': memory_before > self.monitor.memory_threshold,
            'total_cleanups': self.cleanup_count,
            'total_memory_saved_mb': self.total_memory_saved
        }
        
        return result
    
    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory and performance statistics"""
        return {
            'memory': self.monitor.get_stats(),
            'cache': self.cache.get_stats(),
            'components': {
                'count': len(self.component_manager.components),
                'names': list(self.component_manager.components.keys())
            },
            'optimizer': {
                'cleanup_count': self.cleanup_count,
                'total_memory_saved_mb': self.total_memory_saved,
                'monitoring_active': self._monitoring
            }
        }

# Decorator for automatic memory management
def monitor_memory(component_name: str = None, cleanup_after: bool = False):
    """Decorator to monitor memory usage of functions"""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            optimizer = MemoryOptimizer()
            
            if component_name:
                optimizer.use_component(component_name)
            
            memory_before = optimizer.monitor.get_memory_mb()
            
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                memory_after = optimizer.monitor.get_memory_mb()
                memory_delta = memory_after - memory_before
                
                if memory_delta > 50:  # Significant memory increase
                    logger.warning(f"Function {func.__name__} increased memory by {memory_delta:.1f}MB")
                
                if cleanup_after and optimizer.monitor.should_cleanup():
                    optimizer.cleanup()
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            optimizer = MemoryOptimizer()
            
            if component_name:
                optimizer.use_component(component_name)
            
            memory_before = optimizer.monitor.get_memory_mb()
            
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                memory_after = optimizer.monitor.get_memory_mb()
                memory_delta = memory_after - memory_before
                
                if memory_delta > 50:  # Significant memory increase
                    logger.warning(f"Function {func.__name__} increased memory by {memory_delta:.1f}MB")
                
                if cleanup_after and optimizer.monitor.should_cleanup():
                    optimizer.cleanup()
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

# Global instance
_memory_optimizer = None

def get_memory_optimizer() -> MemoryOptimizer:
    """Get global memory optimizer instance"""
    global _memory_optimizer
    if _memory_optimizer is None:
        _memory_optimizer = MemoryOptimizer()
    return _memory_optimizer

# Convenience functions
def cleanup_memory(aggressive: bool = False) -> Dict[str, Any]:
    """Quick cleanup function"""
    return get_memory_optimizer().cleanup(aggressive)

def get_memory_stats() -> Dict[str, Any]:
    """Quick stats function"""
    return get_memory_optimizer().get_comprehensive_stats()

def log_memory_usage():
    """Log current memory usage"""
    optimizer = get_memory_optimizer()
    current_memory = optimizer.monitor.get_memory_mb()
    logger.info(f"📊 Current memory usage: {current_memory:.1f}MB")

# Import asyncio for decorator
import asyncio 