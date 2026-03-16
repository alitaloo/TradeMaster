#!/usr/bin/env python3
"""
Passive risk scan for open trade lifecycles.

Stage 2.5 detect-only:
- detect candidate
- persist / dedupe / cooldown candidate state
- no auto-exit orders

Usage:
    python scripts/lifecycle_risk_scan.py
    python scripts/lifecycle_risk_scan.py --json
    python scripts/lifecycle_risk_scan.py --no-persist
    python scripts/lifecycle_risk_scan.py --list-active --json
    python scripts/lifecycle_risk_scan.py --fail-on-candidate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.exit_action_service import ExitActionService
from execution.risk_monitor import LifecycleRiskMonitor


def print_candidates(title: str, rows: List[Dict[str, Any]]) -> None:
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print('- none')
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description='Detect-only lifecycle risk scan with candidate persistence')
    parser.add_argument('--account-type', default='futu_sim')
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--fail-on-candidate', action='store_true')
    parser.add_argument('--no-persist', action='store_true', help='scan only, do not write candidate state')
    parser.add_argument('--list-active', action='store_true', help='list active persisted candidates instead of scanning')
    args = parser.parse_args()

    monitor = LifecycleRiskMonitor()
    if args.list_active:
        report = monitor.list_candidates(status='active', limit=args.limit)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print('=== Active Persisted Exit Candidates ===')
            print(json.dumps({'count': report['count'], 'listed_at': report['listed_at']}, ensure_ascii=False, indent=2, default=str))
            print_candidates('Active Candidates', report['candidates'])
        return 0

    report = monitor.scan(account_type=args.account_type, limit=args.limit, persist=not args.no_persist)
    report['action_layer'] = ExitActionService().generate_proposals(limit=args.limit, persist=not args.no_persist)
    exit_code = 1 if args.fail_on_candidate and report['summary']['candidate_count'] > 0 else 0

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return exit_code

    print('=== Lifecycle Passive Risk Scan Summary ===')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2, default=str))
    print('\n=== Config ===')
    print(json.dumps(report['config'], ensure_ascii=False, indent=2, default=str))
    print('\n=== Stage 3 Handoff ===')
    print(json.dumps(report['stage3_handoff'], ensure_ascii=False, indent=2, default=str))
    if report.get('action_layer') is not None:
        print('\n=== Stage 3 Action Layer ===')
        print(json.dumps(report['action_layer'], ensure_ascii=False, indent=2, default=str))
    print_candidates('Detected / Persisted Candidates', report['candidates'])
    print_candidates('Active Persisted Candidates', report['active_candidates'])
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
