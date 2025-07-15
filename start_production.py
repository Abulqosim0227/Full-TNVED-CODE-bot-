#!/usr/bin/env python3
"""
TNVED Bot - Production Startup Script
Features: Immediate shutdown on Ctrl+C, no hanging, production-ready
"""
import os
import sys
import subprocess

def main():
    print("🔥 STARTING TNVED BOT IN PRODUCTION MODE")
    print("💀 Ctrl+C will IMMEDIATELY terminate the bot")
    print("🚀 Perfect for server deployment")
    print("=" * 50)
    
    # Set production environment variables
    env = os.environ.copy()
    env['PRODUCTION_MODE'] = 'true'
    env['IMMEDIATE_SHUTDOWN'] = 'true'
    
    # Additional production settings
    env['PYTHONUNBUFFERED'] = '1'  # Force stdout/stderr to be unbuffered
    env['PYTHONDONTWRITEBYTECODE'] = '1'  # Don't write .pyc files
    
    try:
        # Start the bot with production environment
        process = subprocess.Popen([
            sys.executable, 'bot.py'
        ], env=env)
        
        # Wait for the process to complete
        process.wait()
        
    except KeyboardInterrupt:
        print("\n💀 PRODUCTION MODE: Immediate termination requested")
        if process:
            process.terminate()
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        sys.exit(1)
    
    print("🏁 Production bot stopped")

if __name__ == "__main__":
    main() 