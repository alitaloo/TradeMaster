"""run_param_optimization.py

目的：對 Top 候選策略進行參數優化 + Walkforward 驗證

用法：
  python3 -u run_param_optimization.py --batch-id seg_full_backtest_20260220_simple --top-n 5

流程：
1. 從 strategy_results 撈出 top-N 候選（per symbol per timeframe）
2. 對每個候選策略跑參數網格優化
3. 用 Walkforward 驗證參數
4. 把最佳參數寫回 MySQL
"""

import sys
import json
import math
import hashlib
import argparse
from datetime import datetime
from collections import defaultdict

import pandas as pd
import pymysql

sys.path.insert(0, "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2")

from backtest.batch_backtest import BatchBacktestEngine
from backtest.strategy_registry import get_registry
from backtest.walkforward import get_backtest_engine


DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "alita",
    "password": "alitamysql",
    "database": "trademaster",
    "charset": "utf8mb4",
}

START_DATE = "2025-01-01"
END_DATE = "2026-02-18"


# 參數網格定義
PARAM_GRIDS = {
    "MACDTrend": {
        "fast_period": [8, 12, 16],
        "slow_period": [20, 24, 28],
        "signal_period": [6, 8, 9],
    },
    "AD_Accumulation": {
        "period": [10, 14, 20],
    },
    "DualMomentum": {
        "period": [10, 14, 20],
        "threshold": [0.01, 0.02, 0.03],
    },
    "Stochastic_Momentum": {
        "k_period": [10, 14, 20],
        "d_period": [3, 5, 7],
    },
    "RSI_Divergence": {
        "period": [10, 14, 20],
        "oversold": [25, 30, 35],
    },
    "BollingerWidth_Expansion": {
        "period": [14, 20, 30],
        "std_dev": [1.5, 2.0, 2.5],
    },
    "ATRTrailingStop": {
        "atr_period": [10, 14, 20],
        "multiplier": [2.0, 3.0, 4.0],
    },
    "ADX_DI_Crossover": {
        "adx_period": [10, 14, 20],
        "adx_threshold": [15, 20, 25],
    },
    "RSI_SMA_Strategy": {
        "rsi_period": [10, 14, 20],
        "sma_period": [20, 50, 200],
    },
}


def get_top_candidates(conn, batch_id, top_n=5, min_trades=30):
    """取得 top-N 候選"""
    cur = conn.cursor()
    cur.execute("""
        SELECT symbol, timeframe, indicator, sharpe, return_pct, trades,
               sharpe * SQRT(trades) as score
        FROM strategy_results 
        WHERE batch_id=%s 
        AND trades >= %s
        AND sharpe IS NOT NULL
        ORDER BY symbol, timeframe, score DESC
    """, (batch_id, min_trades))
    
    rows = cur.fetchall()
    # Group by symbol+timeframe, take top N
    top_candidates = defaultdict(list)
    for r in rows:
        key = (r[0], r[1])  # symbol, timeframe
        if len(top_candidates[key]) < top_n:
            top_candidates[key].append({
                "symbol": r[0],
                "timeframe": r[1],
                "indicator": r[2],
                "sharpe": float(r[3]) if r[3] else None,
                "return_pct": float(r[4]) if r[4] else None,
                "trades": r[5],
                "score": float(r[6]) if r[6] else None,
            })
    
    cur.close()
    return top_candidates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-id", default="seg_full_backtest_20260220_simple")
    ap.add_argument("--top-n", type=int, default=5, help="Top N candidates per symbol/timeframe")
    ap.add_argument("--min-trades", type=int, default=30, help="Minimum trades filter")
    args = ap.parse_args()
    
    conn = pymysql.connect(**DB_CONFIG)
    
    print("=" * 70)
    print(f"🚀 Param Optimization for Top Candidates")
    print(f"   batch: {args.batch_id}, top-n: {args.top_n}, min_trades: {args.min_trades}")
    print("=" * 70)
    
    # 1. 取得 top候選
    candidates = get_top_candidates(conn, args.batch_id, args.top_n, args.min_trades)
    print(f"\n📊 Found {len(candidates)} symbol/timeframe combinations")
    
    total = sum(len(v) for v in candidates.values())
    print(f"   Total candidates: {total}")
    
    # 顯示候選
    for (sym, tf), items in sorted(candidates.items()):
        print(f"\n=== {sym} {tf} ===")
        for item in items:
            print(f"  {item['indicator']} score={item['score']:.2f}")
    
    # TODO: 2. 對每個候選跑參數優化 + Walkforward
    # 這需要比較複雜的實現...
    print("\n⚠️  Param optimization + Walkforward not yet implemented")
    print("   需要定義每個策略的 param grid，然後用 engine.run() 跑優化")
    
    conn.close()


if __name__ == "__main__":
    main()
