#!/bin/bash
# 安裝模擬交易 Cron Jobs

echo "=== 安裝模擬交易 Cron Jobs ==="

# 獲取專案路徑
PROJECT_DIR="$HOME/.openclaw/workspace/codes/TradeMaster_v2"

echo "專案路徑: $PROJECT_DIR"

# 清除舊的 paper cron 任務
crontab -l 2>/dev/null | grep -v "cron_paper" | crontab -

# 添加輪詢訂單 Cron (每分鐘)
echo "添加: 每分鐘輪詢訂單..."
(crontab -l 2>/dev/null; echo "* * * * * cd $PROJECT_DIR \&\& python3 cron_paper_poll.py >> logs/cron_poll.log 2>&1") | crontab -

# 添加每日結算 Cron (早上 9:00 盤前)
echo "添加: 每日 09:00 結算推送 (早上盤前)..."
(crontab -l 2>/dev/null; echo "0 9 * * 1-5 cd $PROJECT_DIR \&\& python3 cron_paper_daily.py >> logs/cron_daily.log 2>&1") | crontab -

echo ""
echo "✅ Cron Jobs 安裝完成！"
echo ""
echo "當前 Cron 列表:"
crontab -l | grep -E "cron_paper"
echo ""
echo "日誌位置:"
echo "  - logs/cron_poll.log (輪詢訂單)"
echo "  - logs/cron_daily.log (每日結算)"
echo ""
echo "時間安排:"
echo "  - 每分鐘: 輪詢訂單狀態"
echo "  - 09:00: 每日結算推送 (美股開盤前)"
