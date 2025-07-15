#!/usr/bin/env python3
"""
TNVED Bot Restart Script
Safely restarts the bot with proper cleanup and monitoring
"""

import os
import sys
import time
import signal
import psutil
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('restart_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def find_bot_processes():
    """Find all running bot processes"""
    bot_processes = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Look for Python processes running main.py
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('main.py' in arg for arg in cmdline):
                    bot_processes.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return bot_processes

def stop_bot_processes():
    """Stop all running bot processes"""
    logger.info("🔍 Looking for running bot processes...")
    processes = find_bot_processes()
    
    if not processes:
        logger.info("✅ No bot processes found")
        return True
    
    logger.info(f"📋 Found {len(processes)} bot process(es)")
    
    for proc in processes:
        try:
            logger.info(f"🛑 Stopping process {proc.pid}")
            proc.terminate()
            
            # Wait for graceful shutdown
            proc.wait(timeout=10)
            logger.info(f"✅ Process {proc.pid} stopped gracefully")
            
        except psutil.TimeoutExpired:
            logger.warning(f"⚠️ Process {proc.pid} didn't stop gracefully, killing...")
            proc.kill()
            logger.info(f"💀 Process {proc.pid} killed")
            
        except Exception as e:
            logger.error(f"❌ Error stopping process {proc.pid}: {e}")
    
    # Wait a moment for cleanup
    time.sleep(2)
    return True

def start_bot():
    """Start the bot"""
    logger.info("🚀 Starting TNVED Bot...")
    
    # Change to bot directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    # Start the bot
    try:
        import subprocess
        result = subprocess.Popen([
            sys.executable, 'main.py'
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        logger.info(f"✅ Bot started with PID: {result.pid}")
        
        # Wait a moment and check if it's still running
        time.sleep(5)
        if result.poll() is None:
            logger.info("✅ Bot is running successfully")
            return True
        else:
            stdout, stderr = result.communicate()
            logger.error(f"❌ Bot failed to start:")
            logger.error(f"STDOUT: {stdout.decode()}")
            logger.error(f"STDERR: {stderr.decode()}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error starting bot: {e}")
        return False

def restart_bot():
    """Restart the bot completely"""
    logger.info("🔄 Restarting TNVED Bot...")
    logger.info(f"📅 Restart initiated at: {datetime.now()}")
    
    # Stop existing processes
    if stop_bot_processes():
        logger.info("✅ Bot processes stopped")
    else:
        logger.error("❌ Failed to stop bot processes")
        return False
    
    # Start the bot
    if start_bot():
        logger.info("✅ Bot restarted successfully")
        return True
    else:
        logger.error("❌ Failed to restart bot")
        return False

def check_bot_status():
    """Check if the bot is running"""
    processes = find_bot_processes()
    
    if processes:
        logger.info(f"✅ Bot is running ({len(processes)} process(es))")
        for proc in processes:
            try:
                logger.info(f"   PID: {proc.pid}, CPU: {proc.cpu_percent():.1f}%, Memory: {proc.memory_percent():.1f}%")
            except:
                logger.info(f"   PID: {proc.pid}")
        return True
    else:
        logger.info("❌ Bot is not running")
        return False

def monitor_bot():
    """Monitor bot health and restart if needed"""
    logger.info("🔍 Starting bot monitoring...")
    
    restart_attempts = 0
    max_restarts = 5
    
    while restart_attempts < max_restarts:
        if not check_bot_status():
            restart_attempts += 1
            logger.warning(f"⚠️ Bot not running, attempting restart {restart_attempts}/{max_restarts}")
            
            if restart_bot():
                restart_attempts = 0  # Reset counter on successful restart
                logger.info("✅ Bot restarted successfully, monitoring continues...")
            else:
                logger.error(f"❌ Failed to restart bot (attempt {restart_attempts}/{max_restarts})")
                
            time.sleep(60)  # Wait 1 minute before checking again
        else:
            time.sleep(300)  # Check every 5 minutes if bot is running
    
    logger.critical("💀 Maximum restart attempts reached. Manual intervention required.")

def main():
    """Main function"""
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'restart':
            restart_bot()
        elif command == 'stop':
            stop_bot_processes()
        elif command == 'start':
            start_bot()
        elif command == 'status':
            check_bot_status()
        elif command == 'monitor':
            monitor_bot()
        else:
            print("Usage: python restart_bot.py [restart|stop|start|status|monitor]")
    else:
        print("🤖 TNVED Bot Manager")
        print("Commands:")
        print("  restart - Restart the bot")
        print("  stop    - Stop the bot")
        print("  start   - Start the bot")
        print("  status  - Check bot status")
        print("  monitor - Monitor and auto-restart bot")

if __name__ == "__main__":
    main() 