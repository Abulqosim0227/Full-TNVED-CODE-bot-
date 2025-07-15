"""
Enhanced Bot Configuration for Stability and Monitoring
"""

import os
import logging
from datetime import datetime

# Bot stability settings
BOT_STABILITY_CONFIG = {
    # Connection settings
    'connection_timeout': 30,
    'read_timeout': 20,
    'connect_timeout': 10,
    
    # Retry settings
    'max_retry_attempts': 5,
    'retry_delay': 30,
    'exponential_backoff': True,
    
    # Health check settings
    'health_check_interval': 300,  # 5 minutes
    'health_check_timeout': 10,
    
    # Polling settings
    'polling_timeout': 20,
    'polling_retry_after': 5,
    'polling_relax': 0.1,
    
    # Connection pool settings
    'connection_pool_size': 100,
    'connection_pool_per_host': 10,
    'connection_keepalive': 30,
    'dns_cache_ttl': 300,
    
    # Monitoring settings
    'enable_monitoring': True,
    'log_level': logging.INFO,
    'log_file': 'bot.log',
    'log_max_size': 10 * 1024 * 1024,  # 10MB
    'log_backup_count': 5,
    
    # Auto-restart settings
    'auto_restart_on_error': True,
    'max_auto_restarts': 5,
    'restart_delay': 30,
    
    # Performance settings
    'enable_fast_polling': True,
    'skip_pending_updates': True,
    'handle_signals': True,
    'close_session_on_exit': True,
}

# Network optimization settings
NETWORK_CONFIG = {
    # SSL/TLS settings
    'ssl_verify': True,
    'ssl_timeout': 30,
    
    # TCP settings
    'tcp_keepalive': True,
    'tcp_nodelay': True,
    'tcp_keepintvl': 75,
    'tcp_keepcnt': 9,
    
    # HTTP settings
    'http_version': '1.1',
    'enable_compression': True,
    'max_redirects': 10,
    
    # Proxy settings (if needed)
    'proxy_url': None,
    'proxy_auth': None,
}

# Logging configuration
def setup_logging():
    """Setup enhanced logging for the bot"""
    
    # Create logs directory if it doesn't exist
    os.makedirs('logs', exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=BOT_STABILITY_CONFIG['log_level'],
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.handlers.RotatingFileHandler(
                BOT_STABILITY_CONFIG['log_file'],
                maxBytes=BOT_STABILITY_CONFIG['log_max_size'],
                backupCount=BOT_STABILITY_CONFIG['log_backup_count']
            ),
            logging.StreamHandler()
        ]
    )
    
    # Set specific loggers
    aiogram_logger = logging.getLogger('aiogram')
    aiogram_logger.setLevel(logging.WARNING)
    
    aiohttp_logger = logging.getLogger('aiohttp')
    aiohttp_logger.setLevel(logging.WARNING)
    
    return logging.getLogger(__name__)

# Error handling configuration
ERROR_HANDLING_CONFIG = {
    # Telegram API errors
    'telegram_api_errors': {
        'network_error': {'retry': True, 'delay': 5, 'max_retries': 3},
        'timeout_error': {'retry': True, 'delay': 10, 'max_retries': 5},
        'rate_limit_error': {'retry': True, 'delay': 60, 'max_retries': 10},
        'bot_blocked': {'retry': False, 'log_level': logging.WARNING},
        'chat_not_found': {'retry': False, 'log_level': logging.INFO},
    },
    
    # Database errors
    'database_errors': {
        'connection_error': {'retry': True, 'delay': 5, 'max_retries': 3},
        'query_error': {'retry': True, 'delay': 1, 'max_retries': 2},
        'timeout_error': {'retry': True, 'delay': 10, 'max_retries': 3},
    },
    
    # General errors
    'general_errors': {
        'memory_error': {'retry': False, 'restart_bot': True},
        'ssl_error': {'retry': True, 'delay': 30, 'max_retries': 5},
        'dns_error': {'retry': True, 'delay': 60, 'max_retries': 3},
    }
}

# Bot status monitoring
def get_bot_status():
    """Get current bot status information"""
    return {
        'timestamp': datetime.now().isoformat(),
        'uptime': None,  # Will be calculated by the bot
        'memory_usage': None,  # Will be calculated by the bot
        'cpu_usage': None,  # Will be calculated by the bot
        'active_connections': None,  # Will be calculated by the bot
        'errors_count': 0,  # Will be updated by error handlers
        'last_error': None,  # Will be updated by error handlers
        'restart_count': 0,  # Will be updated by restart handler
    }

# Health check configuration
HEALTH_CHECK_CONFIG = {
    'enabled': True,
    'interval': 300,  # 5 minutes
    'timeout': 10,
    'checks': [
        'telegram_api_connectivity',
        'database_connectivity',
        'memory_usage',
        'response_time',
        'error_rate'
    ]
}

# Bot commands for monitoring
MONITORING_COMMANDS = {
    'restart': 'python restart_bot.py restart',
    'stop': 'python restart_bot.py stop',
    'start': 'python restart_bot.py start',
    'status': 'python restart_bot.py status',
    'monitor': 'python restart_bot.py monitor',
    'logs': 'tail -f bot.log',
}

# Environment-specific settings
def get_environment_config():
    """Get environment-specific configuration"""
    
    # Detect environment
    is_windows = os.name == 'nt'
    is_development = os.getenv('DEVELOPMENT', 'false').lower() == 'true'
    
    config = {
        'platform': 'windows' if is_windows else 'unix',
        'development': is_development,
        'python_path': os.path.dirname(os.path.abspath(__file__)),
        'log_path': os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs'),
        'restart_script': 'restart_bot.py',
        'service_name': 'tnved-bot',
    }
    
    return config 