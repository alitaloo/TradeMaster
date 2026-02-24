"""
run_walkforward_batch.py - Vectorized version

Purpose: Run walkforward optimization on top candidates using vectorized engine
- 280 days total -> 4:1 split (224 IS, 56 OOS)
"""

import sys
import json
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

import pandas as pd
import pymysql

sys.path.insert(0, "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2")

# Import vectorized engine
import importlib.util
spec = importlib.util.spec_from_file_location("vectorized", "../backtest_vectorized.py")
vectorized_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vectorized_mod)
VectorizedBacktestEngine = vectorized_mod.VectorizedBacktestEngine

from backtest.strategy_registry import get_registry

DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "alita",
    "password": "alitamysql",
    "database": "trademaster",
    "charset": "utf8mb4",
}


def load_candidates():
    with open("/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/walkforward_candidates.json") as f:
        return json.load(f)


def get_data(symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Load data from MySQL"""
    interval_map = {"1d": "1d", "1h": "1h", "5m": "5m"}
    interval = interval_map.get(timeframe, "1d")
    
    conn = pymysql.connect(**DB_CONFIG)
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT timestamp, open_price, high_price, low_price, close_price, volume 
            FROM kline_cache 
            WHERE symbol = %s AND interval_val = %s
            AND timestamp BETWEEN %s AND %s
            ORDER BY timestamp
        """, (symbol, interval, start_date, end_date))
        rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return None
    
    df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    return df


def run_walkforward_batch(candidates, max_tasks=50):
    """Run walkforward on candidates using vectorized engine"""
    
    registry = get_registry()
    engine = VectorizedBacktestEngine(initial_capital=100000)
    
    results = []
    completed = 0
    
    for cand in candidates[:max_tasks]:
        symbol = cand['symbol']
        indicator = cand['indicator']
        timeframe = cand['timeframe']
        
        # Time split: 4:1 (280 days total)
        # 1d: 224 IS + 56 OOS = 280 days
        # 1h: 1344 + 336 = 1680 bars
        # 5m: 16128 + 4032 = 20160 bars
        
        if timeframe == "1d":
            is_bars, oos_bars = 224, 56
            oos_start_offset = 224
        elif timeframe == "1h":
            is_bars, oos_bars = 1344, 336
            oos_start_offset = 1344
        else:  # 5m
            is_bars, oos_bars = 16128, 4032
            oos_start_offset = 16128
        
        print(f"  {symbol} {indicator} {timeframe}...", end=" ", flush=True)
        
        # Get strategy
        StrategyClass = registry.get_strategy(indicator)
        if not StrategyClass:
            print(f"SKIP (not found)")
            continue
        
        try:
            strategy = StrategyClass()
        except:
            print(f"SKIP (init failed)")
            continue
        
        # Load full data
        df = get_data(symbol, timeframe, "2024-01-01", "2026-02-20")
        if df is None or len(df) < is_bars + oos_bars:
            print(f"SKIP (insufficient data: {len(df) if df else 0} bars)")
            continue
        
        # Split: IS = first 224 bars, OOS = last 56 bars
        df_is = df.iloc[:is_bars]
        df_oos = df.iloc[is_bars:is_bars+oos_bars]
        
        try:
            # Run IS backtest
            result_is = engine.run(symbol, strategy, df_is, indicator)
            
            # Run OOS backtest  
            result_oos = engine.run(symbol, strategy, df_oos, indicator)
            
            oos_return = result_oos.total_return if result_oos else -999
            
            print(f"OK (oos={oos_return*100:.1f}%)")
            
            results.append({
                "symbol": symbol,
                "indicator": indicator,
                "timeframe": timeframe,
                "is_return": result_is.total_return if result_is else None,
                "oos_return": oos_return,
                "is_sharpe": result_is.sharpe_ratio if result_is else None,
                "oos_sharpe": result_oos.sharpe_ratio if result_oos else None,
            })
            
        except Exception as e:
            print(f"FAIL ({str(e)[:30]})")
            continue
        
        completed += 1
        if completed >= max_tasks:
            break
    
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-tasks", type=int, default=50)
    args = ap.parse_args()
    
    print("=" * 60)
    print(f"🚀 Walkforward Optimization (Vectorized)")
    print(f"   Max tasks: {args.max_tasks}")
    print("=" * 60)
    
    candidates = load_candidates()
    print(f"\n📊 Loaded {len(candidates)} candidates")
    
    results = run_walkforward_batch(candidates, args.max_tasks)
    
    print(f"\n✅ Completed {len(results)} optimizations")
    
    # Save results
    with open("/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/walkforward_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # Show summary
    if results:
        print("\nTop OOS performers:")
        sorted_results = sorted(results, key=lambda x: x['oos_return'] if x['oos_return'] else -999, reverse=True)[:5]
        for r in sorted_results:
            print(f"  {r['symbol']} {r['indicator']} {r['timeframe']}: {r['oos_return']*100:.1f}%")
    
    print(f"\nSaved to walkforward_results.json")


if __name__ == "__main__":
    main()
