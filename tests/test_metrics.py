import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/deployment_metrics.py'


class MetricsTests(unittest.TestCase):
    def test_cross_job_timestamp_outputs_and_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            metrics = root / 'metrics.json'
            outputs = root / 'outputs.txt'
            summary = root / 'summary.md'
            env = os.environ | {'GITHUB_OUTPUT': str(outputs), 'GITHUB_STEP_SUMMARY': str(summary)}
            subprocess.run([sys.executable, str(SCRIPT), 'start', '--file', str(metrics), '--started-at', '1234567890'], check=True, env=env)
            subprocess.run([sys.executable, str(SCRIPT), 'finish', '--file', str(metrics), '--outcome', 'success/success', '--url', 'https://example.org/'], check=True, env=env)
            data = json.loads(metrics.read_text())
            self.assertEqual(data['started_unix'], 1234567890)
            self.assertGreater(data['delivery_seconds'], 0)
            self.assertEqual(data['outcome'], 'success/success')
            self.assertIn('delivery_started=1234567890.0', outputs.read_text())
            self.assertIn('delivery_seconds', summary.read_text())

    def test_failed_before_start_does_not_invent_duration(self):
        with tempfile.TemporaryDirectory() as temporary:
            metrics = Path(temporary) / 'metrics.json'
            env = {key: value for key, value in os.environ.items() if key not in {'GITHUB_OUTPUT', 'GITHUB_STEP_SUMMARY'}}
            subprocess.run([sys.executable, str(SCRIPT), 'finish', '--file', str(metrics), '--outcome', 'skipped/skipped'], check=True, env=env)
            self.assertNotIn('delivery_seconds', json.loads(metrics.read_text()))


if __name__ == '__main__':
    unittest.main()
