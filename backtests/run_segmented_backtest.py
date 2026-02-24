"""run_segmented_backtest.py

目的：把「全量回測」拆成可恢復的分段流程，避免一次 4032 任務中途掛掉。

策略：
- 用同一個 batch_id，依序跑 timeframe: 1d -> 1h -> 5m
- 每跑完一段，就把該 timeframe 的 strategy_results / best_selections / stock_strategies 落地到 MySQL
- 若中途失敗，重跑同一支腳本會以 ON DUPLICATE KEY UPDATE 續寫（同 batch_id）

用法：
  python3 -u run_segmented_backtest.py

（固定區間：2025-01-01 ~ 2026-02-18）
"""

import sys
import json
import math
import hashlib
import argparse
from datetime import datetime

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

START_DATE = "2025-01-01"
END_DATE = "2026-02-18"


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


def _rank_key(r: dict):
    return (
        r.get("score", float("-inf")),
        r.get("return_pct") if r.get("return_pct") is not None else -1e9,
        -(r.get("max_dd") if r.get("max_dd") is not None else 1e9),
        r.get("trades") if r.get("trades") is not None else 0,
    )


def load_symbols():
    from backtests.get_db_symbols import get_trading_symbols

    return get_trading_symbols()


def get_completed_symbols(conn, batch_id: str, timeframe: str, expected_per_symbol: int) -> set[str]:
    """Return symbols that already have a full set of strategy_results rows for this timeframe."""
    if expected_per_symbol <= 0:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symbol, COUNT(*) AS c FROM strategy_results "
            "WHERE batch_id=%s AND timeframe=%s GROUP BY symbol",
            (batch_id, timeframe),
        )
        rows = cur.fetchall()
    done = set()
    for sym, c in rows:
        try:
            if int(c) >= int(expected_per_symbol):
                done.add(sym)
        except Exception:
            continue
    return done


def chunked(items: list[str], n: int) -> list[list[str]]:
    if n is None or n <= 0:
        return [items]
    return [items[i : i + n] for i in range(0, len(items), n)]


def upsert_results(conn, rows: list[dict], selection_rule: dict, batch_id: str, timeframe: str):
    if not rows:
        return

    min_trades = selection_rule["min_trades"]
    thr = min_trades.get(timeframe, 0)

    # best map for this timeframe only
    best_map = {}
    for r in rows:
        if r["timeframe"] != timeframe:
            continue
        if r.get("trades") is None or r["trades"] < thr:
            continue
        key = (r["symbol"], r["timeframe"])
        if key not in best_map or _rank_key(r) > _rank_key(best_map[key]):
            best_map[key] = r

    # fallback (no min_trades)
    if len(best_map) == 0:
        for r in rows:
            if r["timeframe"] != timeframe:
                continue
            key = (r["symbol"], r["timeframe"])
            if key not in best_map or _rank_key(r) > _rank_key(best_map[key]):
                best_map[key] = r

    best_rows = list(best_map.values())

    with conn.cursor() as cur:
        # backtest_runs (idempotent)
        cur.execute(
            "INSERT INTO backtest_runs (batch_id, selection_rule, notes) VALUES (%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE selection_rule=VALUES(selection_rule), notes=VALUES(notes)",
            (batch_id, json.dumps(selection_rule, ensure_ascii=False), f"segmented: {START_DATE}~{END_DATE}"),
        )

        # strategy_results (all rows for this timeframe)
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
            if r["timeframe"] == timeframe
        ]
        if all_vals:
            cur.executemany(sql_all, all_vals)

        # best_selections (this timeframe)
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
        if best_vals:
            cur.executemany(sql_best, best_vals)

        # stock_strategies (deploy mapping) - this timeframe only
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
        if map_vals:
            cur.executemany(sql_map, map_vals)

    conn.commit()


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch-id", default="", help="reuse existing batch_id to resume")
    ap.add_argument("--only", default="", choices=["", "1d", "1h", "5m"], help="run only one timeframe segment")

    # Symbol batching (for safer 5m landing)
    ap.add_argument(
        "--symbols-per-batch",
        type=int,
        default=0,
        help="If >0, split symbols into batches of N (recommended for 5m).",
    )
    ap.add_argument(
        "--symbol-sort",
        default="",
        choices=["", "symbol"],
        help="Sort symbols before batching. Use 'symbol' to sort by ticker.",
    )

    # Strategy batching (to reduce per-task runtime)
    ap.add_argument(
        "--strategies-per-batch",
        type=int,
        default=0,
        help="If >0, split strategies into batches of N for each symbol batch (recommended for 5m).",
    )
    ap.add_argument(
        "--strategy-sort",
        default="",
        choices=["", "name"],
        help="Sort strategy names before batching. Use 'name' to sort alphabetically.",
    )

    # Runtime tuning
    ap.add_argument(
        "--max-workers",
        type=int,
        default=2,
        help="Concurrency for BatchBacktestEngine (lower = more stable).",
    )
    ap.add_argument(
        "--executor-type",
        default="thread",
        choices=["thread", "process"],
        help="Executor type for BatchBacktestEngine. thread is usually more stable on macOS.",
    )
    ap.add_argument(
        "--engine-type",
        default="walkforward",
        choices=["walkforward", "simple", "vectorized"],
        help="Engine type: walkforward (with param optimization), simple, or vectorized (fast).",
    )

    args = ap.parse_args()

    batch_id = args.batch_id.strip() or f"seg_full_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    selection_rule = {
        "min_trades": {"5m": 30, "1h": 20, "1d": 10},
        "score": "sharpe * sqrt(trades)",
        "tie_breakers": ["return_pct desc", "max_dd asc", "trades desc"],
        "start_date": START_DATE,
        "end_date": END_DATE,
        "mode": "segmented",
    }

    print("=" * 70)
    print(f"🚀 Segmented Full Backtest - {batch_id}")
    print("=" * 70)

    symbols = load_symbols()
    registry = get_registry()
    registry.discover()
    strategy_names = [s.name for s in registry.list_strategies()]

    print(f"📈 symbols={len(symbols)}")
    print(f"📊 strategies={len(strategy_names)}")
    print(f"🗓️  range={START_DATE}~{END_DATE}")

    # 依序跑，確保每段都落地
    timeframes = ["1d", "1h", "5m"]
    if args.only:
        timeframes = [args.only]

    conn = pymysql.connect(**DB_CONFIG)
    try:
        for tf in timeframes:
            expected = len(strategy_names) * len(symbols)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM strategy_results WHERE batch_id=%s AND timeframe=%s",
                    (batch_id, tf),
                )
                existing = int(cur.fetchone()[0])

            if existing >= expected:
                print(f"✅ {tf} already complete: {existing}/{expected}")
                continue

            print("\n" + "-" * 60)
            print(f"▶️  segment timeframe={tf} (existing={existing}/{expected})")

            # timeout 設定：5m 整段會非常久；避免「排隊等待」也被算入 timeout
            timeout_by_tf = {
                "1d": 3600,
                "1h": 3 * 3600,
                "5m": 12 * 3600,
            }
            engine = BatchBacktestEngine(
                max_workers=max(1, int(args.max_workers or 1)),
                timeout=timeout_by_tf.get(tf, 12 * 3600),
                executor_type=args.executor_type,
                engine_type=args.engine_type,
                progress_every=50,
            )

            # Optionally split by symbol batches (recommended for 5m)
            tf_symbols = list(symbols)
            if args.symbol_sort == "symbol":
                tf_symbols = sorted(tf_symbols)

            expected_per_symbol = len(strategy_names)
            already_done = get_completed_symbols(conn, batch_id, tf, expected_per_symbol)
            tf_symbols = [s for s in tf_symbols if s not in already_done]

            symbol_batches = chunked(tf_symbols, args.symbols_per_batch)
            print(
                f"🧩 symbol batching: per_batch={args.symbols_per_batch or 'ALL'} batches={len(symbol_batches)} "
                f"(skip_done={len(already_done)})"
            )

            tf_strategies = list(strategy_names)
            if args.strategy_sort == "name":
                tf_strategies = sorted(tf_strategies)
            strategy_batches = chunked(tf_strategies, args.strategies_per_batch)
            print(
                f"🧩 strategy batching: per_batch={args.strategies_per_batch or 'ALL'} batches={len(strategy_batches)}"
            )

            # run each symbol batch and land incrementally
            for bi, sym_batch in enumerate(symbol_batches, 1):
                if not sym_batch:
                    continue
                print(f"\n🧩 symbol batch {bi}/{len(symbol_batches)} symbols={len(sym_batch)}: {','.join(sym_batch)}")

                for si, strat_batch in enumerate(strategy_batches, 1):
                    if not strat_batch:
                        continue
                    print(
                        f"\n   🧩 strategy batch {si}/{len(strategy_batches)} strategies={len(strat_batch)}"
                    )

                    tasks = engine.create_tasks(
                        strategies=strat_batch,
                        symbols=sym_batch,
                        timeframes=[tf],
                        start_date=START_DATE,
                        end_date=END_DATE,
                    )

                    print(
                        f"🔄 tasks={len(tasks)} (expected_batch={len(sym_batch) * len(strat_batch)})"
                    )
                    results = engine.run_batch(tasks, batch_id=batch_id)

                    # collect rows
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

                    # 落地這個 timeframe（incremental)
                    upsert_results(conn, rows, selection_rule, batch_id, tf)

                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM strategy_results WHERE batch_id=%s AND timeframe=%s",
                            (batch_id, tf),
                        )
                        after = int(cur.fetchone()[0])
                    print(f"✅ landed (cumulative) {tf}: {after}/{expected}")

            # end batches

        print("\n✅ segmented backtest finished")
        print(f"- batch_id: {batch_id}")

    finally:
        conn.close()


if __name__ == "__main__":
    run()
