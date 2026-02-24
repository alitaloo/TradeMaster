"""run_full_backtest.py

全面回測（多策略 × 多股票 × 多週期），資料來源統一 MySQL。

重點：
- 使用 BatchBacktestEngine（可選 thread/process；預設 process）
- 全量結果落地到：
  - CSV：data/backtest_results/<batch_id>.csv
  - MySQL：strategy_results（全量） + best_selections（best 可審計） + stock_strategies（部署用 best mapping）

best 選擇規則（可調）：
- 先套用 min_trades（按 timeframe）
- 再用 ranking score 排名：score = sharpe * sqrt(trades)
  並以 return_pct / max_dd / trades 做 tie-breaker

用法：
  python3 run_full_backtest.py
"""

import sys
import json
import math
import hashlib
from datetime import datetime
from pathlib import Path

import pandas as pd
import pymysql

sys.path.insert(0, "/Users/alita/.openclaw/workspace/codes/TradeMaster_v2")

from backtest.batch_backtest import BatchBacktestEngine
from backtest.strategy_registry import get_registry


DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "alita",
    "password": "alitamysql",
    "database": "trademaster",
    "charset": "utf8mb4",
}


def _safe_float(x, default=None):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _safe_int(x, default=None):
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _json_dumps_sorted(obj) -> str:
    return json.dumps(obj or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _score(sharpe: float, trades: int) -> float:
    if sharpe is None or trades is None or trades <= 0:
        return float("-inf")
    return float(sharpe) * math.sqrt(float(trades))


def run_full_backtest():
    batch_id = f"full_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # best selection rule
    min_trades = {"5m": 30, "1h": 20, "1d": 10}
    selection_rule = {
        "min_trades": min_trades,
        "score": "sharpe * sqrt(trades)",
        "tie_breakers": ["return_pct desc", "max_dd asc", "trades desc"],
    }

    print("=" * 70)
    print(f"🚀 全面回測 - {batch_id}")
    print("=" * 70)

    # 1) 股票清單（MySQL）
    from backtests.get_db_symbols import get_trading_symbols

    symbols = get_trading_symbols()
    print(f"\n📈 股票數: {len(symbols)}")

    # 2) 策略發現
    registry = get_registry()
    registry.discover()
    strategy_infos = registry.list_strategies()
    strategy_names = [s.name for s in strategy_infos]
    print(f"📊 策略數: {len(strategy_names)}")

    # 3) 三週期（與信號生成一致）
    # 先跑 1d/1h 讓你更快看到 progress（create_tasks 的順序會影響前幾個 task 的耗時）
    timeframes = ["1d", "1h", "5m"]
    print(f"⏱️  週期: {timeframes}")

    # 4) 建 task + 跑批次
    # 這輪數據已補齊：固定回測區間，確保可重現
    start_date = "2025-01-01"
    end_date = "2026-02-18"

    engine = BatchBacktestEngine(
        max_workers=4,
        timeout=3600,
        executor_type="process",  # 改回 process：避開 thread/GIL 造成的超慢與假卡死
        progress_every=50,
    )

    tasks = engine.create_tasks(
        strategies=strategy_names,
        symbols=symbols,
        timeframes=timeframes,
        start_date=start_date,
        end_date=end_date,
    )

    print(f"\n🔄 總任務數: {len(tasks)}")
    print(f"   = {len(strategy_names)} 策略 × {len(symbols)} 股票 × {len(timeframes)} 週期")

    results = engine.run_batch(tasks, batch_id=batch_id)

    # 5) 彙整全量結果（4032 rows）
    rows = []
    for t in results.tasks:
        if not t.result:
            continue
        m = t.result

        sharpe = _safe_float(m.get("sharpe"), None)
        if sharpe is None:
            sharpe = _safe_float(m.get("sharpe_ratio"), None)

        ret = _safe_float(m.get("return_pct"), None)
        if ret is None:
            ret = _safe_float(m.get("annualized_return"), None)

        win_rate = _safe_float(m.get("win_rate"), None)

        trades = m.get("trades")
        if trades is None:
            trades = m.get("total_trades")
        trades = _safe_int(trades, None)

        max_dd = _safe_float(m.get("max_dd"), None)
        if max_dd is None:
            max_dd = _safe_float(m.get("max_drawdown"), None)

        params_json = _json_dumps_sorted(t.params)
        params_hash = _sha256_hex(params_json)
        score = _score(sharpe, trades)

        rows.append(
            {
                "batch_id": batch_id,
                "symbol": t.symbol,
                "timeframe": t.timeframe,
                "indicator": t.strategy_name,
                "params": params_json,
                "params_hash": params_hash,
                "sharpe": sharpe,
                "return_pct": ret,
                "max_dd": max_dd,
                "win_rate": win_rate,
                "trades": trades,
                "score": score,
            }
        )

    df = pd.DataFrame(rows)

    # 6) 選 best：每個 (symbol,timeframe) 一筆
    def rank_key(r):
        return (
            r.get("score", float("-inf")),
            r.get("return_pct") if r.get("return_pct") is not None else -1e9,
            -(r.get("max_dd") if r.get("max_dd") is not None else 1e9),
            r.get("trades") if r.get("trades") is not None else 0,
        )

    best_map = {}
    for r in rows:
        tf = r["timeframe"]
        thr = min_trades.get(tf, 0)
        # apply min_trades filter
        if r.get("trades") is None or r["trades"] < thr:
            continue

        key = (r["symbol"], r["timeframe"])
        if key not in best_map or rank_key(r) > rank_key(best_map[key]):
            best_map[key] = r

    # fallback：若某個 (symbol,timeframe) 被 filter 掉（理論上不應該），就用不過濾的最高 score
    if len(best_map) != len(symbols) * len(timeframes):
        by_key = {}
        for r in rows:
            key = (r["symbol"], r["timeframe"])
            if key not in by_key or rank_key(r) > rank_key(by_key[key]):
                by_key[key] = r
        for key, r in by_key.items():
            if key not in best_map:
                best_map[key] = r

    best_rows = list(best_map.values())

    # 7) 落地：CSV + MySQL（全量 + best + 部署 best mapping）
    out_dir = Path("/Users/alita/.openclaw/workspace/codes/TradeMaster_v2/data/backtest_results")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{batch_id}.csv"
    if not df.empty:
        df.to_csv(out_path, index=False)

    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            # backtest_runs
            cur.execute(
                "INSERT INTO backtest_runs (batch_id, selection_rule, notes) VALUES (%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE selection_rule=VALUES(selection_rule), notes=VALUES(notes)",
                (batch_id, json.dumps(selection_rule, ensure_ascii=False), "full run"),
            )

            # strategy_results (all)
            sql_all = (
                "INSERT INTO strategy_results "
                "(batch_id,symbol,timeframe,indicator,params,params_hash,sharpe,return_pct,max_dd,win_rate,trades,score) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "sharpe=VALUES(sharpe),return_pct=VALUES(return_pct),max_dd=VALUES(max_dd),win_rate=VALUES(win_rate),"
                "trades=VALUES(trades),score=VALUES(score)"
            )
            all_vals = [
                (
                    r["batch_id"],
                    r["symbol"],
                    r["timeframe"],
                    r["indicator"],
                    r["params"],
                    r["params_hash"],
                    r["sharpe"],
                    r["return_pct"],
                    r["max_dd"],
                    r["win_rate"],
                    r["trades"],
                    (None if (r["score"] == float("-inf")) else r["score"]),
                )
                for r in rows
            ]
            cur.executemany(sql_all, all_vals)

            # best_selections
            sql_best = (
                "INSERT INTO best_selections "
                "(batch_id,symbol,timeframe,indicator,params,sharpe,return_pct,max_dd,win_rate,trades,score,selection_rule) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                "indicator=VALUES(indicator),params=VALUES(params),sharpe=VALUES(sharpe),return_pct=VALUES(return_pct),"
                "max_dd=VALUES(max_dd),win_rate=VALUES(win_rate),trades=VALUES(trades),score=VALUES(score),"
                "selection_rule=VALUES(selection_rule)"
            )
            rule_json = json.dumps(selection_rule, ensure_ascii=False)
            best_vals = [
                (
                    r["batch_id"],
                    r["symbol"],
                    r["timeframe"],
                    r["indicator"],
                    r["params"],
                    r["sharpe"],
                    r["return_pct"],
                    r["max_dd"],
                    r["win_rate"],
                    r["trades"],
                    (None if (r["score"] == float("-inf")) else r["score"]),
                    rule_json,
                )
                for r in best_rows
            ]
            cur.executemany(sql_best, best_vals)

            # stock_strategies (deploy mapping)
            sql_map = (
                "INSERT INTO stock_strategies "
                "(symbol,timeframe,indicator,params,sharpe,return_pct,win_rate,trades,batch_id,score,selection_rule,created_at,updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW()) "
                "ON DUPLICATE KEY UPDATE "
                "indicator=VALUES(indicator),params=VALUES(params),sharpe=VALUES(sharpe),return_pct=VALUES(return_pct),"
                "win_rate=VALUES(win_rate),trades=VALUES(trades),batch_id=VALUES(batch_id),score=VALUES(score),"
                "selection_rule=VALUES(selection_rule),updated_at=NOW()"
            )
            map_vals = [
                (
                    r["symbol"],
                    r["timeframe"],
                    r["indicator"],
                    r["params"],
                    r["sharpe"],
                    r["return_pct"],
                    r["win_rate"],
                    r["trades"],
                    batch_id,
                    (None if (r["score"] == float("-inf")) else r["score"]),
                    rule_json,
                )
                for r in best_rows
            ]
            cur.executemany(sql_map, map_vals)

        conn.commit()
    finally:
        conn.close()

    # Summary
    print("\n✅ 完成")
    print(f"- 任務總數: {len(tasks)}")
    print(f"- 有結果: {len(rows)}")
    print(f"- best (symbol,timeframe): {len(best_rows)}/{len(symbols)*len(timeframes)}")
    print(f"- 全量結果 CSV: {out_path}")

    if best_rows:
        top = sorted(best_rows, key=lambda r: r.get("score", float("-inf")), reverse=True)[:10]
        print("\n🏆 Best (Top 10 by score = sharpe*sqrt(trades)):")
        for i, r in enumerate(top, 1):
            print(
                f"  {i}. {r['symbol']} {r['timeframe']} {r['indicator']} "
                f"score={r.get('score')} sharpe={r.get('sharpe')} trades={r.get('trades')} "
                f"return={r.get('return_pct')} maxDD={r.get('max_dd')}"
            )


if __name__ == "__main__":
    run_full_backtest()
