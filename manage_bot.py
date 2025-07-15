#!/usr/bin/env python3
"""
Bot Management Script for TNVED Bot
Helps manage bot instances and switch to improved network handling
"""

import asyncio
import logging
import psutil
import sys
import os
import time
import signal
from pathlib import Path
from typing import List, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def find_bot_processes() -> List[psutil.Process]:
    """Find all running bot processes"""
    bot_processes = []
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline and isinstance(cmdline, list):
                cmdline_str = ' '.join(cmdline)
                
                # Look for bot.py, bot_v2.py, or bot_improved.py processes
                if any(bot_file in cmdline_str for bot_file in ['bot.py', 'bot_v2.py', 'bot_improved.py']):
                    # Make sure it's not this management script
                    if 'manage_bot.py' not in cmdline_str:
                        bot_processes.append(proc)
                        logger.info(f"Found bot process: PID {proc.info['pid']}, CMD: {cmdline_str}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    return bot_processes

def stop_bot_processes(force: bool = False) -> bool:
    """Stop all running bot processes"""
    processes = find_bot_processes()
    
    if not processes:
        logger.info("No bot processes found running")
        return True
    
    logger.info(f"Found {len(processes)} bot process(es) to stop")
    
    # First try graceful shutdown
    for proc in processes:
        try:
            logger.info(f"Sending SIGTERM to process {proc.pid}")
            proc.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            logger.warning(f"Could not terminate process {proc.pid}")
    
    # Wait for processes to terminate
    time.sleep(5)
    
    # Check if any processes are still running
    still_running = []
    for proc in processes:
        try:
            if proc.is_running():
                still_running.append(proc)
        except psutil.NoSuchProcess:
            pass
    
    if still_running and force:
        logger.warning("Some processes still running, forcing shutdown...")
        for proc in still_running:
            try:
                logger.info(f"Sending SIGKILL to process {proc.pid}")
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                logger.warning(f"Could not kill process {proc.pid}")
        
        time.sleep(2)
    
    # Final check
    final_processes = find_bot_processes()
    if final_processes:
        logger.error(f"Failed to stop {len(final_processes)} process(es)")
        for proc in final_processes:
            logger.error(f"  Still running: PID {proc.pid}")
        return False
    
    logger.info("All bot processes stopped successfully")
    return True

def check_network_status() -> dict:
    """Check current network connectivity status"""
    import subprocess
    
    status = {
        'internet': False,
        'telegram_api': False,
        'dns': False
    }
    
    try:
        # Check internet connectivity
        result = subprocess.run(['ping', '-c', '1', '8.8.8.8'], 
                              capture_output=True, timeout=5)
        status['internet'] = result.returncode == 0
        
        # Check DNS resolution
        result = subprocess.run(['nslookup', 'api.telegram.org'], 
                              capture_output=True, timeout=5)
        status['dns'] = result.returncode == 0
        
        # Check Telegram API connectivity
        result = subprocess.run(['ping', '-c', '1', 'api.telegram.org'], 
                              capture_output=True, timeout=10)
        status['telegram_api'] = result.returncode == 0
        
    except Exception as e:
        logger.warning(f"Network check error: {e}")
    
    return status

def validate_bot_files() -> dict:
    """Validate that bot files exist and are properly configured"""
    base_dir = Path(__file__).parent
    
    files_status = {
        'bot.py': (base_dir / 'bot.py').exists(),
        'timeout_config.py': (base_dir / 'timeout_config.py').exists(),
        'config.py': (base_dir / 'config.py').exists(),
        'handlers/user.py': (base_dir / 'handlers' / 'user.py').exists(),
    }
    
    logger.info("Bot files validation:")
    for file, exists in files_status.items():
        status = "✅ EXISTS" if exists else "❌ MISSING"
        logger.info(f"  {file}: {status}")
    
    return files_status

async def test_database_connection():
    """Test database connectivity"""
    try:
        from utils.db import get_connection
        conn = await get_connection()
        
        # Test a simple query
        result = await conn.fetchval("SELECT 1")
        await conn.close()
        
        if result == 1:
            logger.info("✅ Database connection test passed")
            return True
        else:
            logger.error("❌ Database connection test failed: unexpected result")
            return False
            
    except Exception as e:
        logger.error(f"❌ Database connection test failed: {e}")
        return False

def start_improved_bot() -> Optional[psutil.Process]:
    """Start the enhanced bot version"""
    base_dir = Path(__file__).parent
    bot_script = base_dir / 'bot.py'
    
    if not bot_script.exists():
        logger.error(f"Bot script not found: {bot_script}")
        return None
    
    try:
        import subprocess
        
        logger.info(f"Starting improved bot: {bot_script}")
        
        # Start the bot as a subprocess
        process = subprocess.Popen([
            sys.executable, str(bot_script)
        ], 
        cwd=str(base_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
        )
        
        # Give it a moment to start
        time.sleep(3)
        
        # Check if it's still running
        if process.poll() is None:
            logger.info(f"✅ Bot started successfully with PID {process.pid}")
            return psutil.Process(process.pid)
        else:
            stdout, stderr = process.communicate()
            logger.error(f"❌ Bot failed to start")
            logger.error(f"STDOUT: {stdout.decode()}")
            logger.error(f"STDERR: {stderr.decode()}")
            return None
            
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        return None

async def main():
    """Main management function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='TNVED Bot Management Script')
    parser.add_argument('action', choices=['status', 'stop', 'restart', 'start', 'check'], 
                       help='Action to perform')
    parser.add_argument('--force', action='store_true', 
                       help='Force stop processes if needed')
    
    args = parser.parse_args()
    
    logger.info(f"🤖 TNVED Bot Manager - Action: {args.action}")
    
    if args.action == 'status':
        # Show current status
        processes = find_bot_processes()
        logger.info(f"Bot processes running: {len(processes)}")
        
        network_status = check_network_status()
        logger.info(f"Network status: {network_status}")
        
        files_status = validate_bot_files()
        all_files_ok = all(files_status.values())
        logger.info(f"All required files present: {all_files_ok}")
        
        db_ok = await test_database_connection()
        logger.info(f"Database connection: {'OK' if db_ok else 'FAILED'}")
    
    elif args.action == 'stop':
        # Stop all bot processes
        success = stop_bot_processes(force=args.force)
        if success:
            logger.info("✅ All bot processes stopped")
        else:
            logger.error("❌ Failed to stop some processes")
            sys.exit(1)
    
    elif args.action == 'start':
        # Start improved bot
        existing_processes = find_bot_processes()
        if existing_processes:
            logger.warning(f"Found {len(existing_processes)} existing bot process(es)")
            logger.warning("Use 'stop' action first or 'restart' to replace them")
            sys.exit(1)
        
        # Validate environment
        files_status = validate_bot_files()
        if not all(files_status.values()):
            logger.error("❌ Some required files are missing")
            sys.exit(1)
        
        db_ok = await test_database_connection()
        if not db_ok:
            logger.error("❌ Database connection failed")
            sys.exit(1)
        
        network_status = check_network_status()
        if not network_status['internet']:
            logger.warning("⚠️ No internet connectivity detected")
        
        # Start the bot
        process = start_improved_bot()
        if process:
            logger.info("✅ Bot started successfully")
        else:
            logger.error("❌ Failed to start bot")
            sys.exit(1)
    
    elif args.action == 'restart':
        # Stop existing and start improved
        logger.info("🔄 Restarting bot with improved network handling...")
        
        success = stop_bot_processes(force=args.force)
        if not success:
            logger.error("❌ Failed to stop existing processes")
            sys.exit(1)
        
        # Wait a moment
        time.sleep(2)
        
        # Start improved version
        process = start_improved_bot()
        if process:
            logger.info("✅ Bot restarted successfully with improved network handling")
        else:
            logger.error("❌ Failed to restart bot")
            sys.exit(1)
    
    elif args.action == 'check':
        # Comprehensive system check
        logger.info("🔍 Performing comprehensive system check...")
        
        # 1. Check processes
        processes = find_bot_processes()
        logger.info(f"Running bot processes: {len(processes)}")
        
        # 2. Check files
        files_status = validate_bot_files()
        all_files_ok = all(files_status.values())
        logger.info(f"Required files check: {'✅ PASS' if all_files_ok else '❌ FAIL'}")
        
        # 3. Check database
        db_ok = await test_database_connection()
        logger.info(f"Database connection: {'✅ PASS' if db_ok else '❌ FAIL'}")
        
        # 4. Check network
        network_status = check_network_status()
        logger.info(f"Network connectivity:")
        logger.info(f"  Internet: {'✅' if network_status['internet'] else '❌'}")
        logger.info(f"  DNS: {'✅' if network_status['dns'] else '❌'}")
        logger.info(f"  Telegram API: {'✅' if network_status['telegram_api'] else '❌'}")
        
        # 5. Overall health
        overall_health = all_files_ok and db_ok and network_status['telegram_api']
        logger.info(f"Overall system health: {'✅ HEALTHY' if overall_health else '❌ ISSUES DETECTED'}")
        
        if not overall_health:
            logger.warning("⚠️ System issues detected. Consider running 'restart' action.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Management script interrupted by user")
    except Exception as e:
        logger.error(f"Management script error: {e}")
        sys.exit(1) 