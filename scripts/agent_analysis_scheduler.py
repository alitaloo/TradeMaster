#!/usr/bin/env python3
"""
Agent Analysis Scheduler
定期調用 TM Agent 進行分析，結果寫入 agent_scores 表

功能：
- 每 30 分鐘執行一次
- 調用 tm-news-finance：分析持倉股票的新聞風險
- 調用 tm-strategist：分析技術面信號
- 結果寫入 agent_scores 表

用法:
    python agent_analysis_scheduler.py [--dry-run]
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from typing import List, Dict

# 項目根目錄
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def is_trading_hours() -> bool:
    """
    檢查是否在美股交易時段
    美股交易時段: 21:30 - 04:00 ET (夏令時)
                    22:30 - 05:00 ET (冬令時)
    
    轉換為台灣時間 (GMT+8):
    - 夏令時: 05:30 - 12:00
    - 冬令時: 06:30 - 13:00
    """
    from datetime import datetime, time
    
    # 獲取當前 UTC 時間
    now_utc = datetime.utcnow()
    
    # 簡單判斷：檢查小時是否在台灣時間 05:30-13:00 範圍內
    # 這涵蓋了夏令時和冬令時的美股交易時段
    taipei_hour = (now_utc.hour + 8) % 24
    
    # 美股交易時段（台灣時間）
    # 夏令時 ET 21:30-04:00 = TW 05:30-12:00
    # 冬令時 ET 22:30-05:00 = TW 06:30-13:00
    # 合併: TW 05:30-13:00
    if 5 <= taipei_hour < 13:
        return True
    
    return False


def run_news_analysis() -> List[Dict]:
    """運行新聞分析"""
    logger.info("=" * 50)
    logger.info("📰 執行 News Finance Analysis...")
    logger.info("=" * 50)
    
    try:
        # 動態導入避免循環依賴
        from news_finance_analysis import run_analysis as run_news
        results = run_news()
        logger.info(f"✅ News Analysis 完成: {len(results)} 檔")
        return results
    except Exception as e:
        logger.error(f"❌ News Analysis 失敗: {e}")
        import traceback
        traceback.print_exc()
        return []


def run_strategy_analysis() -> List[Dict]:
    """運行技術分析"""
    logger.info("=" * 50)
    logger.info("📈 執行 Strategy Analysis...")
    logger.info("=" * 50)
    
    try:
        from strategy_analysis import run_analysis as run_strat
        results = run_strat()
        logger.info(f"✅ Strategy Analysis 完成: {len(results)} 檔")
        return results
    except Exception as e:
        logger.error(f"❌ Strategy Analysis 失敗: {e}")
        import traceback
        traceback.print_exc()
        return []


def run_scheduler(dry_run: bool = False) -> Dict:
    """
    運行調度器
    
    Returns:
    {
        'news_count': int,
        'strategy_count': int,
        'total': int,
        'timestamp': str
    }
    """
    logger.info("=" * 60)
    logger.info("🤖 Agent Analysis Scheduler 開始")
    logger.info(f"   時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"   交易時段: {'是' if is_trading_hours() else '否'}")
    logger.info("=" * 60)
    
    # 檢查是否在交易時段
    if not dry_run and not is_trading_hours():
        logger.info("⏸️ 非美股交易時段，跳過分析")
        return {
            'news_count': 0,
            'strategy_count': 0,
            'skipped': True,
            'reason': 'non_trading_hours',
            'timestamp': datetime.now().isoformat()
        }
    
    news_results = []
    strategy_results = []
    
    # 執行新聞分析
    logger.info("\n--- Step 1: News Finance Analysis ---")
    news_results = run_news_analysis()
    
    # 執行技術分析
    logger.info("\n--- Step 2: Strategy Analysis ---")
    strategy_results = run_strategy_analysis()
    
    # 總結
    total = len(news_results) + len(strategy_results)
    
    logger.info("=" * 60)
    logger.info("✅ Scheduler 完成")
    logger.info(f"   新聞分析: {len(news_results)} 檔")
    logger.info(f"   技術分析: {len(strategy_results)} 檔")
    logger.info(f"   總計: {total} 條記錄")
    logger.info("=" * 60)
    
    return {
        'news_count': len(news_results),
        'strategy_count': len(strategy_results),
        'total': total,
        'timestamp': datetime.now().isoformat()
    }


def main():
    parser = argparse.ArgumentParser(description='Agent Analysis Scheduler')
    parser.add_argument('--dry-run', action='store_true', help='模擬運行，不實際執行分析')
    args = parser.parse_args()
    
    run_scheduler(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
