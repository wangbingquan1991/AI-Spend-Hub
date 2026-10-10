"""Offline process-level HTTP E2E for invoice review, using synthetic data only.

Run: python3 -m unittest discover -s tests -p 'test_http_review_e2e.py' -v
Runs an actual app.py subprocess on 127.0.0.1 with an isolated temporary SQLite DB.
No third-party connections, paid APIs, credentials, or browser are involved.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = 'synthetic-local-test-token-only-not-a-real-credential'


class ReviewProcessE2ETests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='ai-spend-e2e-')
        self.db_path = Path(self.tmp.name) / 'synthetic.sqlite3'
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.process = None
        self.start_server()

    def tearDown(self):
        self.stop_server()
        self.tmp.cleanup()

    def start_server(self):
        env = os.environ.copy()
        env.update(AI_SPEND_DB=str(self.db_path), AI_SPEND_ACCESS_TOKEN=TOKEN)
        self.process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'app.py'), '--host', '127.0.0.1',
             '--port', str(self.port)], cwd=ROOT, env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                error = self.process.stderr.read().decode('utf-8', errors='replace')
                self.fail('Server exited before ready: ' + error[-1500:])
            try:
                status, body = self.request('GET', '/healthz', authorized=False, timeout=0.3)
                if status == 200 and body == {'status': 'ok'}:
                    return
            except (OSError, http.client.HTTPException):
                time.sleep(0.05)
        self.fail('Timed out waiting for loopback HTTP server')

    def stop_server(self):
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.process.stderr is not None:
            self.process.stderr.close()
        self.process = None

    def request(self, method, path, payload=None, authorized=True, timeout=3):
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = 'Bearer ' + TOKEN
        body = json.dumps(payload).encode('utf-8') if payload is not None else None
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            reply = conn.getresponse()
            data = reply.read()
            return reply.status, json.loads(data.decode('utf-8'))
        finally:
            conn.close()

    @staticmethod
    def receipt(external_id, amount):
        return {'date': '2026-10-09', 'provider': 'Fictional AI Vendor',
                'type': 'subscription', 'amount': amount, 'currency': 'USD',
                'rateToCNY': 7, 'source': 'synthetic-test',
                'externalId': external_id, 'notes': 'Synthetic fixture, not a real invoice'}

    def decide(self, external_id, decision):
        return self.request('POST', '/api/invoices/decision',
                            {'source': 'synthetic-test', 'externalId': external_id,
                             'decision': decision})

    def test_real_http_process_review_lifecycle_and_restart(self):
        """Candidate -> approval/rejection -> ledger/events -> restart persistence."""
        self.assertEqual(self.request('GET', '/api/invoices', authorized=False)[0], 401)
        self.assertEqual(self.request('GET', '/api/state')[1]['revision'], 0)
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 0)

        approved = self.receipt('approved-001', 12.5)
        rejected = self.receipt('rejected-001', 99)
        pending = self.receipt('pending-001', 3)
        self.assertEqual(self.request('POST', '/api/invoices/propose',
                                      {'candidates': [approved, rejected, pending]})[1],
                         {'queued': 3, 'skipped': 0})
        code, queue = self.request('GET', '/api/invoices?status=pending')
        self.assertEqual((code, queue['count']), (200, 3))
        self.assertEqual(self.request('GET', '/api/state')[1]['state']['transactions'], [])
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 0)

        code, outcome = self.decide('approved-001', 'approve')
        self.assertEqual((code, outcome['status'], outcome['revision']), (200, 'approved', 1))
        self.assertEqual(self.decide('approved-001', 'approve')[1]['alreadyReviewed'], True)
        code, reject_outcome = self.decide('rejected-001', 'reject')
        self.assertEqual((code, reject_outcome['status']), (200, 'rejected'))
        self.assertEqual(self.decide('rejected-001', 'reject')[1]['alreadyReviewed'], True)
        self.assertEqual(self.decide('rejected-001', 'approve')[0], 409)

        state = self.request('GET', '/api/state')[1]
        self.assertEqual(state['revision'], 1)
        self.assertEqual(len(state['state']['transactions']), 1)
        tx = state['state']['transactions'][0]
        self.assertEqual((tx['externalId'], tx['source'], tx['amount'], tx['currency']),
                         ('approved-001', 'synthetic-test', 12.5, 'USD'))
        summary = self.request('GET', '/api/summary?month=2026-10')[1]
        self.assertEqual((summary['cashPaidCNY'], summary['transactionCount']), (87.5, 1))
        self.assertEqual(summary['byCategory'], {'subscription': 87.5})

        self.assertEqual(self.request('POST', '/api/invoices/propose',
                                      {'candidates': [approved, rejected, pending]})[1],
                         {'queued': 0, 'skipped': 3})
        altered = {**approved, 'amount': 300}
        self.assertEqual(self.request('POST', '/api/invoices/propose',
                                      {'candidates': [altered]})[0], 409)
        events = self.request('GET', '/api/invoices/events')[1]['events']
        self.assertEqual(sorted(event['event'] for event in events), ['approved', 'rejected'])
        self.assertEqual(self.request('GET', '/api/invoices?status=pending')[1]['count'], 1)

        # Restart the real service process without replacing the temporary DB.
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request('GET', '/api/state')[1]['revision'], 1)
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 87.5)
        self.assertEqual(self.request('GET', '/api/invoices?status=approved')[1]['count'], 1)
        self.assertEqual(self.request('GET', '/api/invoices?status=rejected')[1]['count'], 1)
        self.assertEqual(self.request('GET', '/api/invoices?status=pending')[1]['count'], 1)
        self.assertEqual(self.decide('approved-001', 'approve')[1]['alreadyReviewed'], True)
        self.assertEqual(len(self.request('GET', '/api/invoices/events')[1]['events']), 2)


if __name__ == '__main__':
    unittest.main()
