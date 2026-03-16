#!/usr/bin/env python3
"""Rebuild / reconcile paper_positions from filled paper_orders."""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from paper_position_reconciliation import reconcile_paper_positions


def main() -> int:
    parser = argparse.ArgumentParser(description='重建 / 對帳 paper_positions')
    parser.add_argument('--apply', action='store_true', help='套用重建結果到 paper_positions')
    parser.add_argument('--json', action='store_true', help='輸出 JSON')
    args = parser.parse_args()

    report = reconcile_paper_positions(apply=args.apply)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        mode = 'APPLY' if args.apply else 'DRY-RUN'
        print(f'=== paper_positions rebuild ({mode}) ===')
        print(f"mismatch_count: {report['mismatch_count']}")
        for item in report['mismatches']:
            print(f"- {item['symbol']}")
            for field, diff in item['diff'].items():
                print(f"    {field}: {diff['current']} -> {diff['rebuilt']}")
        print('assets:', report['assets'])

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
