#!/usr/bin/env python3
"""
Trade lifecycle reconciliation report.

交叉比對：
1. trade_lifecycles
2. broker_positions_snapshot
3. account_equity_snapshots

用法：
    python scripts/lifecycle_reconciliation_report.py
    python scripts/lifecycle_reconciliation_report.py --json
    python scripts/lifecycle_reconciliation_report.py --account-type futu_sim --limit 100
"""

from __future__ import annotations

import os
import sys
import json
import math
import argparse
from decimal import Decimal
from datetime import datetime
from typing import Any, Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from config.database import get_db_cursor
except Exception as exc:
    raise SystemExit(f"無法載入資料庫設定: {exc}")

OPEN_STATUSES = ('signal_created', 'order_submitted', 'partially_filled', 'filled_open', 'exit_pending')


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    return str(value)


def _serialize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    serialized: List[Dict[str, Any]] = []
    for row in rows:
        payload: Dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, (datetime, Decimal)):
                payload[key] = _to_str(value) if isinstance(value, datetime) else _to_float(value)
            else:
                payload[key] = value
        serialized.append(payload)
    return serialized


def fetch_one(sql: str, params: tuple = ()) -> Dict[str, Any] | None:
    with get_db_cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchone()


def fetch_all(sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    with get_db_cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall() or []


def build_report(account_type: str = 'futu_sim', limit: int = 200, holding_tolerance_min: int = 5, pnl_tolerance: float = 0.01) -> Dict[str, Any]:
    latest_position_snapshot = fetch_one(
        """
        SELECT snapshot_time, COUNT(*) AS position_count, COALESCE(SUM(qty), 0) AS total_qty
        FROM broker_positions_snapshot
        WHERE account_type = %s
          AND snapshot_time = (
              SELECT MAX(snapshot_time) FROM broker_positions_snapshot WHERE account_type = %s
          )
        GROUP BY snapshot_time
        """,
        (account_type, account_type),
    )

    latest_equity_snapshot = fetch_one(
        """
        SELECT snapshot_time, cash, equity, market_value, realized_pnl, unrealized_pnl, drawdown_pct
        FROM account_equity_snapshots
        WHERE account_type = %s
        ORDER BY snapshot_time DESC
        LIMIT 1
        """,
        (account_type,),
    )

    placeholders = ', '.join(['%s'] * len(OPEN_STATUSES))

    open_without_position = fetch_all(
        f"""
        SELECT
            tl.id,
            tl.signal_id,
            tl.strategy_name,
            tl.symbol,
            tl.direction,
            tl.status,
            tl.position_qty,
            tl.entry_price,
            tl.entry_time,
            tl.updated_at,
            ps.snapshot_time AS latest_position_snapshot_time,
            COALESCE(ps.qty, 0) AS snapshot_qty,
            ps.market_value,
            eq.snapshot_time AS latest_equity_snapshot_time,
            eq.equity,
            eq.market_value AS account_market_value
        FROM trade_lifecycles tl
        LEFT JOIN broker_positions_snapshot ps
            ON ps.account_type = %s
           AND ps.symbol = tl.symbol
           AND ps.snapshot_time = (
               SELECT MAX(p2.snapshot_time)
               FROM broker_positions_snapshot p2
               WHERE p2.account_type = %s AND p2.symbol = tl.symbol
           )
        LEFT JOIN account_equity_snapshots eq
            ON eq.account_type = %s
           AND eq.snapshot_time = (
               SELECT MAX(e2.snapshot_time)
               FROM account_equity_snapshots e2
               WHERE e2.account_type = %s
           )
        WHERE tl.status IN ({placeholders})
          AND COALESCE(ps.qty, 0) <= 0
        ORDER BY tl.updated_at DESC
        LIMIT %s
        """,
        (account_type, account_type, account_type, account_type, *OPEN_STATUSES, limit),
    )

    closed_with_position = fetch_all(
        """
        SELECT
            tl.id,
            tl.signal_id,
            tl.strategy_name,
            tl.symbol,
            tl.direction,
            tl.status,
            tl.position_qty,
            tl.exit_price,
            tl.exit_time,
            tl.updated_at,
            ps.snapshot_time AS latest_position_snapshot_time,
            COALESCE(ps.qty, 0) AS snapshot_qty,
            ps.avg_cost,
            ps.market_price,
            ps.market_value,
            ps.unrealized_pnl,
            eq.snapshot_time AS latest_equity_snapshot_time,
            eq.equity,
            eq.market_value AS account_market_value
        FROM trade_lifecycles tl
        JOIN broker_positions_snapshot ps
            ON ps.account_type = %s
           AND ps.symbol = tl.symbol
           AND ps.snapshot_time = (
               SELECT MAX(p2.snapshot_time)
               FROM broker_positions_snapshot p2
               WHERE p2.account_type = %s AND p2.symbol = tl.symbol
           )
        LEFT JOIN account_equity_snapshots eq
            ON eq.account_type = %s
           AND eq.snapshot_time = (
               SELECT MAX(e2.snapshot_time)
               FROM account_equity_snapshots e2
               WHERE e2.account_type = %s
           )
        WHERE tl.status = 'closed'
          AND COALESCE(ps.qty, 0) > 0
        ORDER BY tl.updated_at DESC
        LIMIT %s
        """,
        (account_type, account_type, account_type, account_type, limit),
    )

    lifecycle_anomalies = fetch_all(
        """
        SELECT
            tl.id,
            tl.signal_id,
            tl.strategy_name,
            tl.symbol,
            tl.direction,
            tl.status,
            tl.position_qty,
            tl.entry_price,
            tl.exit_price,
            tl.entry_time,
            tl.exit_time,
            tl.pnl,
            tl.holding_minutes,
            CASE
                WHEN tl.status = 'closed' AND tl.entry_time IS NOT NULL AND tl.exit_time IS NOT NULL
                    THEN TIMESTAMPDIFF(MINUTE, tl.entry_time, tl.exit_time)
                ELSE NULL
            END AS expected_holding_minutes,
            CASE
                WHEN tl.status = 'closed'
                     AND tl.entry_price IS NOT NULL
                     AND tl.exit_price IS NOT NULL
                     AND tl.position_qty IS NOT NULL
                THEN (
                    CASE
                        WHEN tl.direction = 'long' THEN (tl.exit_price - tl.entry_price) * tl.position_qty
                        ELSE (tl.entry_price - tl.exit_price) * tl.position_qty
                    END
                )
                ELSE NULL
            END AS expected_pnl,
            eq.snapshot_time AS latest_equity_snapshot_time,
            eq.equity,
            eq.market_value AS account_market_value
        FROM trade_lifecycles tl
        LEFT JOIN account_equity_snapshots eq
            ON eq.account_type = %s
           AND eq.snapshot_time = (
               SELECT MAX(e2.snapshot_time)
               FROM account_equity_snapshots e2
               WHERE e2.account_type = %s
           )
        WHERE (
            tl.holding_minutes < 0
            OR (
                tl.status = 'closed'
                AND tl.entry_time IS NOT NULL
                AND tl.exit_time IS NOT NULL
                AND ABS(TIMESTAMPDIFF(MINUTE, tl.entry_time, tl.exit_time) - COALESCE(tl.holding_minutes, 0)) > %s
            )
            OR (
                tl.status = 'closed'
                AND tl.entry_price IS NOT NULL
                AND tl.exit_price IS NOT NULL
                AND tl.position_qty IS NOT NULL
                AND ABS(
                    (
                        CASE
                            WHEN tl.direction = 'long' THEN (tl.exit_price - tl.entry_price) * tl.position_qty
                            ELSE (tl.entry_price - tl.exit_price) * tl.position_qty
                        END
                    ) - COALESCE(tl.pnl, 0)
                ) > %s
            )
        )
        ORDER BY tl.updated_at DESC
        LIMIT %s
        """,
        (account_type, account_type, holding_tolerance_min, pnl_tolerance, limit),
    )

    summary = {
        'account_type': account_type,
        'latest_position_snapshot_time': _to_str(latest_position_snapshot.get('snapshot_time')) if latest_position_snapshot else None,
        'latest_equity_snapshot_time': _to_str(latest_equity_snapshot.get('snapshot_time')) if latest_equity_snapshot else None,
        'latest_equity': _to_float(latest_equity_snapshot.get('equity')) if latest_equity_snapshot else None,
        'latest_account_market_value': _to_float(latest_equity_snapshot.get('market_value')) if latest_equity_snapshot else None,
        'open_without_position_count': len(open_without_position),
        'closed_with_position_count': len(closed_with_position),
        'anomaly_count': len(lifecycle_anomalies),
    }

    return {
        'summary': summary,
        'latest_position_snapshot': _serialize_rows([latest_position_snapshot] if latest_position_snapshot else []),
        'latest_equity_snapshot': _serialize_rows([latest_equity_snapshot] if latest_equity_snapshot else []),
        'open_without_position': _serialize_rows(open_without_position),
        'closed_with_position': _serialize_rows(closed_with_position),
        'lifecycle_anomalies': _serialize_rows(lifecycle_anomalies),
    }


def print_section(title: str, rows: List[Dict[str, Any]]) -> None:
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print("- none")
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, default=str))


def has_reconciliation_anomaly(report: Dict[str, Any]) -> bool:
    summary = report.get('summary', {})
    return any(
        int(summary.get(key, 0) or 0) > 0
        for key in ('open_without_position_count', 'closed_with_position_count', 'anomaly_count')
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='trade_lifecycles 對帳報告')
    parser.add_argument('--account-type', default='futu_sim')
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--holding-tolerance-min', type=int, default=5)
    parser.add_argument('--pnl-tolerance', type=float, default=0.01)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--fail-on-anomaly', action='store_true', help='若對帳檢測到異常則以非 0 exit code 結束')
    args = parser.parse_args()

    report = build_report(
        account_type=args.account_type,
        limit=args.limit,
        holding_tolerance_min=args.holding_tolerance_min,
        pnl_tolerance=args.pnl_tolerance,
    )
    exit_code = 1 if args.fail_on_anomaly and has_reconciliation_anomaly(report) else 0

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return exit_code

    print("=== Lifecycle Reconciliation Summary ===")
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2, default=str))
    print_section('Latest Position Snapshot', report['latest_position_snapshot'])
    print_section('Latest Equity Snapshot', report['latest_equity_snapshot'])
    print_section('Open lifecycles but no latest position snapshot qty', report['open_without_position'])
    print_section('Closed lifecycles but latest snapshot still has qty', report['closed_with_position'])
    print_section('PnL / holding_minutes anomalies', report['lifecycle_anomalies'])
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
