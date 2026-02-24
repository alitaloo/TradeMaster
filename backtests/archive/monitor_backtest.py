#!/usr/bin/env python3
"""回測進度監控腳本"""

import subprocess
import os
from datetime import datetime

LOG_FILE = "/tmp/backtest_monitor.log"

# 檢查後台任務
result = subprocess.run(
    "ps aux | grep generate_backtest | grep -v grep | wc -l",
    shell=True,
    capture_output=True,
    text=True
)
task_count = int(result.stdout.strip()) if result.stdout.strip() else 0

# 獲取最後進度
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'r') as f:
        lines = f.readlines()
        last_lines = lines[-5:] if len(lines) >= 5 else lines
        progress = ''.join(last_lines).strip()
else:
    progress = "無日誌檔案"

# 獲取最新報告
reports = subprocess.run(
    "ls -t /Users/alita/.openclaw/workspace/codes/TradeMaster_v2/docs/*backtest*.md 2>/dev/null | head -1",
    shell=True,
    capture_output=True,
    text=True
)
latest_report = reports.stdout.strip() if reports.stdout.strip() else "無報告"

# 生成報告
timestamp = datetime.now().strftime("%H:%M:%S")
report = f"""
===
🔄 回測監控 - {timestamp}
===
後台任務數: {task_count}
最新報告: {latest_report}

進度日誌:
{progress}
"""

print(report)

# 寫入日誌
with open(LOG_FILE, 'w') as f:
    f.write(report)

# 發送到主會話
print("回報給用戶...")
