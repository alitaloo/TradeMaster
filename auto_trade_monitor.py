#!/usr/bin/env python3
"""
TradeMaster v2 - 自動策略監控腳本 (整合信號生成)
功能：每 3 分鐘執行策略掃描 + 信號生成，僅在美股開盤時間運行
考慮夏令時 (DST) 與冬令時 (EST)
"""

import sys
import time
import logging
import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# 導入信號生成器
from signal_generator import SignalGenerator

# 設置日誌
logs_dir = Path(__file__).parent / "logs"
logs_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(logs_dir / f"autoscan_{datetime.now():%Y%m%d}.log")
    ]
)
logger = logging.getLogger(__name__)

# 時區常數
US_EASTERN = ZoneInfo("America/New_York")

# 市場開盤時間 (美股開盤時間)
MARKET_OPEN = "09:30"
MARKET_CLOSE = "16:00"

# 執行間隔 (秒)
SCAN_INTERVAL = 180  # 3 分鐘

# 信號文件
SIGNALS_DIR = Path(__file__).parent / "signals"


def is_market_open_utc() -> bool:
    """檢查當前是否為美股開盤時間 (UTC)"""
    from datetime import datetime
    
    now_utc = datetime.now(timezone.utc)
    
    # 判斷是否為夏令時 (美國)
    year = now_utc.year
    
    # DST 開始：3月第二個週日 02:00 UTC
    dst_start = get_nth_weekday(year, 3, 2, 0)
    # DST 結束：11月第一個週日 02:00 UTC
    dst_end = get_nth_weekday(year, 11, 1, 0)
    
    if dst_start <= now_utc < dst_end:
        # 夏令時 (EDT, UTC-4)
        market_open = 13  # 13:30 UTC
        market_close = 20  # 20:00 UTC
        logger.debug(f"夏令時模式 (EDT, UTC-4), 開盤 {market_open}:30 UTC")
    else:
        # 冬令時 (EST, UTC-5)
        market_open = 14  # 14:00 UTC
        market_close = 21  # 21:00 UTC
        logger.debug(f"冬令時模式 (EST, UTC-5), 開盤 {market_open}:00 UTC")
    
    current_hour = now_utc.hour
    current_minute = now_utc.minute
    
    # 轉換為 minutes 便於比較
    current_mins = current_hour * 60 + current_minute
    open_mins = market_open * 60 + 30 if market_open == 13 else market_open * 60
    close_mins = market_close * 60
    
    # 檢查是否在開盤與收盤之間
    if open_mins <= current_mins < close_mins:
        # 檢查是否為週一到週五 (UTC)
        now_eastern = now_utc.astimezone(US_EASTERN)
        if now_eastern.weekday() < 5:
            return True
    
    return False


def get_nth_weekday(year: int, month: int, n: int, weekday: int) -> datetime:
    """取得指定年月中第 n 個星期幾的日期"""
    from datetime import timedelta
    
    if n > 0:
        date = datetime(year, month, 1)
        days_ahead = (weekday - date.weekday() + 7) % 7
        date += timedelta(days=days_ahead)
        date += timedelta(weeks=n-1)
        return date
    else:
        date = datetime(year, month + 1, 1) - timedelta(days=1)
        while date.weekday() != weekday:
            date -= timedelta(days=1)
        return date


def run_strategy_scan() -> bool:
    """執行策略掃描"""
    try:
        logger.info("🚀 開始執行策略掃描...")
        
        project_dir = Path(__file__).parent
        subprocess.run(
            ["python3", "main.py", "scan"],
            cwd=str(project_dir),
            check=True
        )
        
        logger.info("✅ 策略掃描完成")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ 策略掃描失敗: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ 執行時出錯: {e}")
        return False


def run_prediction() -> bool:
    """執行預測"""
    try:
        logger.info("🔮 開始執行預測...")
        
        project_dir = Path(__file__).parent
        
        result = subprocess.run(
            ["python3", "full_analysis.py"],
            cwd=str(project_dir),
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode == 0:
            logger.info("✅ 預測完成")
            return True
        else:
            logger.error(f"❌ 預測失敗: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error("⏰ 預測執行超時")
        return False
    except Exception as e:
        logger.error(f"❌ 執行時出錯: {e}")
        return False


def generate_signals() -> bool:
    """
    生成實時交易信號
    使用 strategy_complete_report.txt 中最優策略
    """
    try:
        logger.info("📡 開始生成實時交易信號...")
        
        # 初始化信號生成器
        generator = SignalGenerator()
        
        # 生成所有信號
        result = generator.generate_all_signals()
        
        # 保存信號
        signals_file = SIGNALS_DIR / f"latest_signals.json"
        generator.save_signals(result, signals_file)
        
        # 輸出摘要
        overview = result['overview']
        logger.info(f"📊 信號生成完成:")
        logger.info(f"   🟢 LONG: {overview['long_count']} ({overview['long_ratio']}%)")
        logger.info(f"   🔴 SHORT: {overview['short_count']}")
        logger.info(f"   📈 市場情緒: {overview['market_sentiment']}")
        
        # 輸出 Top 信號
        signals = result['signals']
        strong_signals = sorted(
            [(s, d['signal_strength']) for s, d in signals.items()],
            key=lambda x: -x[1]
        )[:5]
        
        logger.info(f"\n🔥 Top 5 強烈信號:")
        for stock, strength in strong_signals:
            sig = signals[stock]
            emoji = "🟢" if sig['signal'] == 'LONG' else "🔴"
            logger.info(f"   {emoji} {stock}: {sig['signal']} ({strength}%) - {sig['strategy']}")
        
        # 生成摘要消息
        summary_msg = generate_summary_message(result)
        logger.info(f"\n📋 信號摘要:\n{summary_msg}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 生成信號失敗: {e}")
        return False


def generate_summary_message(result: dict) -> str:
    """生成摘要消息"""
    overview = result['overview']
    signals = result['signals']
    
    lines = [
        f"📊 TradeMaster v2 信號摘要",
        f"⏰ {overview['timestamp']}",
        "",
        f"📈 市場情緒: {overview['market_sentiment']} ({overview['long_ratio']}% LONG)",
        f"📊 總股票數: {overview['total_stocks']}",
        f"🟢 LONG: {overview['long_count']} | 🔴 SHORT: {overview['short_count']}",
        "",
        "🔥 強烈買入信號 (強度 > 70%):"
    ]
    
    # 強烈買入
    strong_long = [(s, d) for s, d in signals.items() 
                   if d['signal'] == 'LONG' and d['signal_strength'] >= 70]
    strong_long.sort(key=lambda x: -x[1]['signal_strength'])
    
    if strong_long:
        for stock, sig in strong_long[:5]:
            lines.append(f"   🟢 {stock}: {sig['signal_strength']}% @ ${sig['price']:.2f}")
    else:
        lines.append("   無")
    
    lines.append("")
    lines.append("⚠️ 強烈賣出信號 (強度 > 70%):")
    
    # 強烈賣出
    strong_short = [(s, d) for s, d in signals.items() 
                    if d['signal'] == 'SHORT' and d['signal_strength'] >= 70]
    strong_short.sort(key=lambda x: -x[1]['signal_strength'])
    
    if strong_short:
        for stock, sig in strong_short[:5]:
            lines.append(f"   🔴 {stock}: {sig['signal_strength']}% @ ${sig['price']:.2f}")
    else:
        lines.append("   無")
    
    lines.append("")
    lines.append(f"📁 完整信號: signals/latest_signals.json")
    
    return "\n".join(lines)


def wait_until_market_open():
    """等待直到市場開盤"""
    from datetime import timedelta
    
    while not is_market_open_utc():
        now = datetime.now(timezone.utc)
        eastern_now = now.astimezone(US_EASTERN)
        
        logger.info(f"🕐 現在是 {eastern_now.strftime('%Y-%m-%d %H:%M:%S %Z')}, 市場未開盤")
        logger.info("⏳ 等待 60 秒後再次檢查...")
        
        time.sleep(60)
    
    logger.info("🌟 市場已開盤！開始監控...")


def is_dst_active() -> bool:
    """檢查是否為夏令時"""
    from datetime import datetime
    year = datetime.now().year
    
    dst_start = get_nth_weekday(year, 3, 2, 0)
    dst_end = get_nth_weekday(year, 11, 1, 0)
    
    now = datetime.now(timezone.utc)
    
    return dst_start <= now < dst_end


def main():
    """主函數"""
    logger.info("=" * 60)
    logger.info("📈 TradeMaster v2 自動策略監控啟動 (含信號生成)")
    logger.info(f"⏱️ 執行間隔: {SCAN_INTERVAL // 60} 分鐘")
    logger.info("=" * 60)
    
    # 確保 signals 目錄存在
    SIGNALS_DIR.mkdir(exist_ok=True)
    
    # 顯示時區資訊
    now = datetime.now(timezone.utc)
    eastern_now = now.astimezone(US_EASTERN)
    dst_status = "夏令時 (EDT)" if is_dst_active() else "冬令時 (EST)"
    logger.info(f"🕐 當前時間: {eastern_now.strftime('%Y-%m-%d %H:%M:%S %Z')} ({dst_status})")
    
    run_count = 0
    
    while True:
        try:
            if is_market_open_utc():
                # 市場開盤中，執行掃描
                run_count += 1
                eastern_now = datetime.now(US_EASTERN)
                
                logger.info(f"\n{'='*60}")
                logger.info(f"📊 第 {run_count} 次執行 ({eastern_now.strftime('%Y-%m-%d %H:%M:%S %Z')})")
                logger.info(f"{'='*60}")
                
                # 1. 生成實時信號 (主要功能)
                logger.info("\n--- 📡 信號生成 ---")
                generate_signals()
                
                # 2. 執行策略掃描
                logger.info("\n--- 🚀 策略掃描 ---")
                run_strategy_scan()
                
                # 3. 執行預測分析
                logger.info("\n--- 🔮 預測分析 ---")
                run_prediction()
                
                logger.info(f"\n💤 等待 {SCAN_INTERVAL // 60} 分鐘後再次執行...")
                
            else:
                # 市場未開盤
                if run_count > 0:
                    logger.info(f"\n📊 本次市場時段共執行 {run_count} 次掃描")
                    run_count = 0
                
                wait_until_market_open()
            
            # 睡眠
            time.sleep(SCAN_INTERVAL)
            
        except KeyboardInterrupt:
            logger.info("\n👋 收到中斷信號，正在停止...")
            break
        except Exception as e:
            logger.error(f"❌ 發生錯誤: {e}")
            logger.info("⏳ 30 秒後重試...")
            time.sleep(30)
    
    logger.info("🛑 監控已停止")


if __name__ == "__main__":
    main()
