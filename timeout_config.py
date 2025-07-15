# timeout_config.py
"""
Timeout configuration for TNVED Bot
Adjust these values based on your network conditions and requirements
"""

# HTTP Client Timeouts (in seconds)
TOTAL_TIMEOUT = 90  # Total request timeout
CONNECT_TIMEOUT = 30  # Connection establishment timeout
READ_TIMEOUT = 60  # Socket read timeout

# Connection Pool Settings
CONNECTION_LIMIT = 100  # Maximum number of connections in pool
CONNECTION_LIMIT_PER_HOST = 30  # Maximum connections per host
DNS_CACHE_TTL = 300  # DNS cache time-to-live (5 minutes)
KEEPALIVE_TIMEOUT = 300  # Keep-alive timeout (5 minutes)

# Polling Settings
POLLING_TIMEOUT = 45  # Long polling timeout (increased from default 10)

# Backoff/Retry Settings
MIN_RETRY_DELAY = 1.0  # Minimum delay between retries
MAX_RETRY_DELAY = 30.0  # Maximum delay between retries
RETRY_MULTIPLIER = 1.5  # Backoff multiplier
MAX_RETRIES = 10  # Maximum number of retries

# Network Quality Presets
NETWORK_PRESETS = {
    "fast": {
        "total_timeout": 60,
        "connect_timeout": 15,
        "read_timeout": 30,
        "polling_timeout": 30,
        "max_retry_delay": 15.0,
    },
    "stable": {
        "total_timeout": 90,
        "connect_timeout": 30,
        "read_timeout": 60,
        "polling_timeout": 45,
        "max_retry_delay": 30.0,
    },
    "slow": {
        "total_timeout": 120,
        "connect_timeout": 45,
        "read_timeout": 90,
        "polling_timeout": 60,
        "max_retry_delay": 60.0,
    }
}

# Current preset (change this based on your network)
CURRENT_PRESET = "slow"  # Options: "fast", "stable", "slow"

def get_timeout_config():
    """Get timeout configuration based on current preset"""
    if CURRENT_PRESET in NETWORK_PRESETS:
        return NETWORK_PRESETS[CURRENT_PRESET]
    return NETWORK_PRESETS["stable"]

def get_all_settings():
    """Get all timeout settings"""
    preset = get_timeout_config()
    return {
        "total_timeout": preset.get("total_timeout", TOTAL_TIMEOUT),
        "connect_timeout": preset.get("connect_timeout", CONNECT_TIMEOUT),
        "read_timeout": preset.get("read_timeout", READ_TIMEOUT),
        "polling_timeout": preset.get("polling_timeout", POLLING_TIMEOUT),
        "max_retry_delay": preset.get("max_retry_delay", MAX_RETRY_DELAY),
        "connection_limit": CONNECTION_LIMIT,
        "connection_limit_per_host": CONNECTION_LIMIT_PER_HOST,
        "dns_cache_ttl": DNS_CACHE_TTL,
        "keepalive_timeout": KEEPALIVE_TIMEOUT,
        "min_retry_delay": MIN_RETRY_DELAY,
        "retry_multiplier": RETRY_MULTIPLIER,
        "max_retries": MAX_RETRIES,
    }

def get_session_timeout():
    """Get aiohttp.ClientTimeout object with current settings"""
    import aiohttp
    config = get_timeout_config()
    return aiohttp.ClientTimeout(
        total=config.get("total_timeout", TOTAL_TIMEOUT),
        connect=config.get("connect_timeout", CONNECT_TIMEOUT),
        sock_read=config.get("read_timeout", READ_TIMEOUT),
    )

# Usage example:
# from timeout_config import get_session_timeout, get_timeout_config
# from aiogram.client.session.aiohttp import AiohttpSession
# session = AiohttpSession(timeout=get_session_timeout()) 