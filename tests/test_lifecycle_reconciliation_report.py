#!/usr/bin/env python3
import io
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts import lifecycle_reconciliation_report as report_script


class LifecycleReconciliationReportTest(unittest.TestCase):
    def test_fail_on_anomaly_returns_non_zero_but_keeps_json_output(self):
        report = {
            'summary': {
                'account_type': 'futu_sim',
                'open_without_position_count': 1,
                'closed_with_position_count': 0,
                'anomaly_count': 0,
            },
            'latest_position_snapshot': [],
            'latest_equity_snapshot': [],
            'open_without_position': [],
            'closed_with_position': [],
            'lifecycle_anomalies': [],
        }
        buf = io.StringIO()
        with patch.object(report_script, 'build_report', return_value=report), \
             patch.object(sys, 'argv', ['lifecycle_reconciliation_report.py', '--json', '--fail-on-anomaly']), \
             redirect_stdout(buf):
            exit_code = report_script.main()

        self.assertEqual(exit_code, 1)
        self.assertIn('"open_without_position_count": 1', buf.getvalue())

    def test_fail_on_anomaly_returns_zero_when_clean(self):
        report = {
            'summary': {
                'account_type': 'futu_sim',
                'open_without_position_count': 0,
                'closed_with_position_count': 0,
                'anomaly_count': 0,
            },
            'latest_position_snapshot': [],
            'latest_equity_snapshot': [],
            'open_without_position': [],
            'closed_with_position': [],
            'lifecycle_anomalies': [],
        }
        buf = io.StringIO()
        with patch.object(report_script, 'build_report', return_value=report), \
             patch.object(sys, 'argv', ['lifecycle_reconciliation_report.py', '--fail-on-anomaly']), \
             redirect_stdout(buf):
            exit_code = report_script.main()

        self.assertEqual(exit_code, 0)
        self.assertIn('Lifecycle Reconciliation Summary', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
