# TradeMaster 部署配置

## macOS LaunchAgent (K线自动更新)

### 安装
```bash
cp deploy/com.trademaster.kline.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trademaster.kline.plist
```

### 检查状态
```bash
launchctl list | grep trademaster
```

### 查看日志
```bash
tail -f logs/kline_launchd.log
```

### 卸载
```bash
launchctl unload ~/Library/LaunchAgents/com.trademaster.kline.plist
```

## 配置说明

- **更新频率**: 每 5 分钟
- **脚本**: `scripts/futu_update_once.py`
- **内置市场时间判断**: 非交易时段自动跳过

### 交易时段 (台北时间)
| 时段 | 冬令时 | 夏令时 |
|------|--------|--------|
| 盘前 | 17:00-22:30 | 16:00-21:30 |
| 正式交易 | 22:30-05:00 | 21:30-04:00 |
| 盘后 | 05:00-09:00 | 04:00-08:00 |

脚本会自动检测当前是冬令时还是夏令时。
