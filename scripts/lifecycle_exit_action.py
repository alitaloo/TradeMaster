#!/usr/bin/env python3
"""
Stage 3 dry-run exit action proposal generator.

This script never submits broker orders.
It only evaluates active exit candidates and persists/prints dry-run proposals.

Usage:
    python scripts/lifecycle_exit_action.py
    python scripts/lifecycle_exit_action.py --json
    python scripts/lifecycle_exit_action.py --no-persist
    python scripts/lifecycle_exit_action.py --list-proposals --json
    python scripts/lifecycle_exit_action.py --statuses proposed blocked stale
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
from execution.exit_submit_service import ExitSubmitService


def print_rows(title: str, rows: List[Dict[str, Any]]) -> None:
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print('- none')
        return
    for row in rows:
        print(json.dumps(row, ensure_ascii=False, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description='Stage 3 dry-run lifecycle exit action proposals')
    parser.add_argument('--limit', type=int, default=200)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--no-persist', action='store_true')
    parser.add_argument('--list-proposals', action='store_true')
    parser.add_argument('--statuses', nargs='*', default=None, help='filter persisted proposal statuses when using --list-proposals / --inspect-submit-state')
    parser.add_argument('--submit-dry-run', action='store_true', help='acquire lease and simulate pre-live submit attempts for proposed rows')
    parser.add_argument('--inspect-submit-state', action='store_true', help='show pre-live submit state / lease / correlation view')
    parser.add_argument('--list-attempts', action='store_true', help='list persisted submit attempts')
    parser.add_argument('--lease-owner', default='cli', help='lease owner id used by --submit-dry-run')
    parser.add_argument('--lease-seconds', type=int, default=120, help='lease ttl seconds used by --submit-dry-run')
    args = parser.parse_args()

    service = ExitActionService()
    submit_service = ExitSubmitService()
    if args.list_proposals:
        report = service.list_proposals(limit=args.limit, statuses=args.statuses)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print('=== Persisted Exit Action Proposals ===')
            print(json.dumps({'count': report['count'], 'listed_at': report['listed_at'], 'statuses': report['statuses']}, ensure_ascii=False, indent=2, default=str))
            print_rows('Proposals', report['proposals'])
        return 0

    if args.inspect_submit_state:
        report = submit_service.inspect_state(limit=args.limit, statuses=args.statuses)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print('=== Pre-Live Submit State ===')
            print(json.dumps({'count': report['count'], 'inspected_at': report['inspected_at']}, ensure_ascii=False, indent=2, default=str))
            print_rows('State', report['items'])
        return 0

    if args.list_attempts:
        report = {
            'listed_at': submit_service.now.isoformat(sep=' '),
            'attempts': submit_service.attempt_repository.list_attempts(statuses=args.statuses, limit=args.limit),
        }
        report['count'] = len(report['attempts'])
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print('=== Persisted Submit Attempts ===')
            print(json.dumps({'count': report['count'], 'listed_at': report['listed_at']}, ensure_ascii=False, indent=2, default=str))
            print_rows('Attempts', report['attempts'])
        return 0

    if args.submit_dry_run:
        report = submit_service.process_dry_run_submissions(limit=args.limit, lease_owner=args.lease_owner, lease_seconds=args.lease_seconds)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        else:
            print('=== Stage 3.5 Pre-Live Submit Simulation ===')
            print(json.dumps(report['summary'], ensure_ascii=False, indent=2, default=str))
            print_rows('Submit Results', report['results'])
        return 0

    report = service.generate_proposals(limit=args.limit, persist=not args.no_persist)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    print('=== Lifecycle Exit Action Dry-Run Summary ===')
    print(json.dumps(report['summary'], ensure_ascii=False, indent=2, default=str))
    print('\n=== Config ===')
    print(json.dumps(report['config'], ensure_ascii=False, indent=2, default=str))
    print('\n=== Gate ===')
    print(json.dumps(report['gate'], ensure_ascii=False, indent=2, default=str))
    print_rows('Dry-Run Proposals', report.get('proposals', []))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
