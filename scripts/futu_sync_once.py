#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from execution.futu_sync_service import FutuSyncService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run one Futu SIM -> MySQL sync cycle')
    parser.add_argument('--pretty', action='store_true', help='Pretty-print JSON output')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    service = FutuSyncService()
    result = service.run_once()
    if args.pretty:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(json.dumps(result, ensure_ascii=False, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
