# 🔧 TNVED Bot Stability and Auto-Restart Guide

## 🚨 **Problem Solved**
Your bot was stopping unexpectedly due to SSL connection timeouts and network issues. This guide provides solutions to keep your bot running 24/7.

## 🛠️ **New Features Added**

### 1. **Enhanced Main Bot (`main.py`)**
- ✅ **Auto-restart mechanism** - Bot restarts itself on errors
- ✅ **Better connection handling** - Optimized SSL/TCP settings
- ✅ **Health monitoring** - Regular connectivity checks
- ✅ **Graceful shutdown** - Proper cleanup on exit
- ✅ **Comprehensive logging** - Track all issues

### 2. **Restart Manager (`restart_bot.py`)**
- ✅ **Process monitoring** - Find and manage bot processes
- ✅ **Smart restart** - Graceful stop and start
- ✅ **Status checking** - Check if bot is running
- ✅ **Auto-monitoring** - Continuous health checks

### 3. **Windows Manager (`restart_bot.bat`)**
- ✅ **Easy GUI** - Simple menu interface
- ✅ **One-click restart** - No command line needed
- ✅ **Log viewing** - Check bot logs easily
- ✅ **Status monitoring** - Real-time bot status

---

## 🚀 **How to Use**

### **Method 1: Quick Restart (Recommended)**
```bash
cd bot
python restart_bot.py restart
```

### **Method 2: Windows GUI**
1. Double-click `restart_bot.bat`
2. Choose option 1 (Restart Bot)
3. Bot will restart automatically

### **Method 3: Auto-Monitoring**
```bash
cd bot
python restart_bot.py monitor
```
This will monitor the bot and auto-restart if it crashes.

---

## 🔧 **Command Reference**

### Python Commands
```bash
# Restart bot (stops and starts)
python restart_bot.py restart

# Stop bot completely
python restart_bot.py stop

# Start bot
python restart_bot.py start

# Check if bot is running
python restart_bot.py status

# Monitor and auto-restart
python restart_bot.py monitor
```

### Batch File Options
```
1. Restart Bot       - Stop and start the bot
2. Stop Bot          - Stop the bot completely
3. Start Bot         - Start the bot
4. Check Status      - See if bot is running
5. Monitor Bot       - Auto-restart on crashes
6. View Recent Logs  - Check bot logs
7. Exit              - Close the manager
```

---

## 📊 **Monitoring Your Bot**

### **Check Bot Status**
```bash
python restart_bot.py status
```
**Output:**
```
✅ Bot is running (1 process(es))
   PID: 12345, CPU: 2.1%, Memory: 1.5%
```

### **Monitor Continuously**
```bash
python restart_bot.py monitor
```
**What it does:**
- Checks bot health every 5 minutes
- Auto-restarts if bot crashes
- Logs all restart attempts
- Stops after 5 failed restarts

---

## 🔍 **Log Files**

### **Bot Logs**
- **File**: `bot.log`
- **Contains**: All bot activity, errors, restarts
- **Rotation**: Automatic (10MB max, 5 backups)

### **Restart Logs**
- **File**: `restart_bot.log`
- **Contains**: Restart attempts, process management
- **View**: Check for restart history

### **View Logs**
```bash
# View bot logs
tail -f bot.log

# View restart logs  
tail -f restart_bot.log

# Or use the batch file (option 6)
```

---

## 🛡️ **Error Handling**

### **SSL Connection Errors**
- **What happens**: Bot loses connection to Telegram
- **Solution**: Auto-retry with exponential backoff
- **Settings**: Up to 5 retries, 30-second delays

### **Network Timeouts**
- **What happens**: Network request times out
- **Solution**: Shorter timeouts, faster retries
- **Settings**: 20-second timeout, 5-second retry delay

### **Memory Issues**
- **What happens**: Bot runs out of memory
- **Solution**: Automatic restart
- **Settings**: Monitor memory usage, restart if needed

---

## 🔄 **Auto-Restart Configuration**

### **Built-in Auto-Restart**
The bot now automatically restarts itself on:
- SSL connection errors
- Network timeouts
- API rate limits
- Memory issues
- Unexpected exceptions

### **External Monitoring**
Use the monitor command for external auto-restart:
```bash
python restart_bot.py monitor
```

---

## 🚨 **Troubleshooting**

### **Bot Still Stops?**
1. **Check logs**: `tail -f bot.log`
2. **Use monitor**: `python restart_bot.py monitor`
3. **Check status**: `python restart_bot.py status`
4. **Restart manually**: `python restart_bot.py restart`

### **Can't Find Bot Process?**
```bash
# Check if bot is running
python restart_bot.py status

# If not running, start it
python restart_bot.py start
```

### **Multiple Bot Instances?**
```bash
# This will find and stop all bot processes
python restart_bot.py stop

# Then start a single instance
python restart_bot.py start
```

### **Permission Issues?**
- Run as administrator on Windows
- Check file permissions on Linux/Mac
- Ensure Python path is correct

---

## 📈 **Performance Optimizations**

### **Connection Settings**
- **Keepalive**: 30 seconds
- **Connection pool**: 100 connections
- **DNS cache**: 5 minutes
- **SSL timeout**: 30 seconds

### **Polling Settings**
- **Timeout**: 20 seconds
- **Retry delay**: 5 seconds
- **Fast polling**: Enabled
- **Signal handling**: Enabled

### **Memory Management**
- **Log rotation**: 10MB max files
- **Connection cleanup**: Automatic
- **Session management**: Proper closure

---

## 🔐 **Security Features**

### **Process Isolation**
- Each bot runs in its own process
- Automatic cleanup on exit
- No orphaned processes

### **Error Logging**
- All errors are logged
- No sensitive data in logs
- Automatic log rotation

### **Graceful Shutdown**
- Proper session cleanup
- Database connections closed
- No data loss on restart

---

## 🎯 **Best Practices**

### **Daily Operations**
1. **Morning**: Check `python restart_bot.py status`
2. **Monitor**: Run `python restart_bot.py monitor` in background
3. **Evening**: Check logs for any issues

### **Weekly Maintenance**
1. **Review logs**: Check `bot.log` for patterns
2. **Update bot**: `git pull` and restart
3. **Clear old logs**: Archive old log files

### **Monthly Tasks**
1. **Check disk space**: Log files can grow
2. **Update dependencies**: `pip install -U -r requirements.txt`
3. **Review performance**: Memory and CPU usage

---

## 🚀 **Production Deployment**

### **Recommended Setup**
1. **Use monitor mode**: `python restart_bot.py monitor`
2. **Set up system service**: Use `tnved_bot.service`
3. **Monitor logs**: Set up log rotation
4. **Health checks**: Regular status checks

### **System Service (Linux)**
```bash
# Copy service file
sudo cp tnved_bot.service /etc/systemd/system/

# Enable and start
sudo systemctl enable tnved-bot
sudo systemctl start tnved-bot

# Check status
sudo systemctl status tnved-bot
```

### **Windows Service**
- Use Windows Task Scheduler
- Set to run on startup
- Configure auto-restart on failure

---

## 📞 **Support**

If your bot is still stopping unexpectedly:

1. **Check logs**: Review `bot.log` and `restart_bot.log`
2. **Use monitor**: `python restart_bot.py monitor`
3. **Test connectivity**: Check internet connection
4. **Update bot**: Ensure you're using the latest version
5. **Contact support**: Provide log files for assistance

---

## ✅ **Summary**

**Your bot will now:**
- ✅ **Auto-restart** on SSL errors
- ✅ **Monitor health** every 5 minutes
- ✅ **Handle timeouts** gracefully
- ✅ **Log all issues** for debugging
- ✅ **Provide easy management** tools

**To start using:**
1. Run `python restart_bot.py restart`
2. Monitor with `python restart_bot.py monitor`
3. Check status anytime with `python restart_bot.py status`

**Your bot should now run 24/7 without interruption!** 🎉 