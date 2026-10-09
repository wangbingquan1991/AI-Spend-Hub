"""v0.3 invoice review safety, durability and HTTP regression tests."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

os.environ['AI_SPEND_ACCESS_TOKEN'] = 'test-secret-token-replace-with-strong-value'
import app


class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def setUp(self):
        app.DB_PATH = Path(self.temp.name) / (self._testMethodName + '.sqlite3')
        app.init_db()

    def request(self, method, path, payload=None, authorized=True):
        headers = {'Content-Type': 'application/json'}
        if authorized:
            headers['Authorization'] = 'Bearer ' + app.TOKEN
        con = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        con.request(method, path, json.dumps(payload).encode() if payload is not None else None, headers)
        result = con.getresponse()
        body = result.read()
        code = result.status
        mime = result.getheader('Content-Type','')
        con.close()
        return code, json.loads(body) if 'application/json' in mime else body

    def invoice(self, reference='receipt-1', amount=20):
        return {'date': '2026-10-09', 'provider': 'Example AI', 'type': 'subscription',
                'amount': amount, 'currency': 'USD', 'source': 'test-extraction',
                'externalId': reference, 'notes': 'Confirmed payment'}

    def propose(self, *rows):
        return self.request('POST', '/api/invoices/propose', {'candidates': list(rows)})

    def decision(self, decision='approve', reference='receipt-1'):
        return self.request('POST', '/api/invoices/decision', {'source': 'test-extraction',
                                                              'externalId': reference, 'decision': decision})

    def test_01_unreviewed_never_enters_ledger(self):
        self.assertEqual(self.propose(self.invoice())[1], {'queued': 1, 'skipped': 0})
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 0)
        code, rows = self.request('GET', '/api/invoices')
        self.assertEqual((code, rows['count'], rows['candidates'][0]['status']), (200, 1, 'pending'))
        self.assertEqual(self.propose(self.invoice())[1], {'queued': 0, 'skipped': 1})
        self.assertEqual(self.request('GET', '/api/state')[1]['revision'], 0)

    def test_02_approve_exactly_once_and_audit(self):
        self.propose(self.invoice())
        code, result = self.decision()
        self.assertEqual((code, result['status'], result['revision']), (200, 'approved', 1))
        self.assertEqual(self.decision()[1]['alreadyReviewed'], True)
        state = self.request('GET', '/api/state')[1]
        self.assertEqual(len(state['state']['transactions']), 1)
        self.assertEqual(state['revision'], 1)
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 140)
        self.assertEqual(len(self.request('GET', '/api/invoices/events')[1]['events']), 1)
        # Re-initialization does not drop reviews.
        app.init_db()
        self.assertEqual(self.request('GET', '/api/invoices?status=approved')[1]['count'], 1)

    def test_03_rejected_never_charges_and_cannot_reverse(self):
        self.propose(self.invoice())
        self.assertEqual(self.decision('reject')[1]['status'], 'rejected')
        self.assertEqual(self.decision('approve')[0], 409)
        self.assertEqual(self.decision('reject')[1]['alreadyReviewed'], True)
        self.assertEqual(self.request('GET', '/api/state')[1]['state']['transactions'], [])
        self.assertEqual(len(self.request('GET', '/api/invoices/events')[1]['events']), 1)

    def test_04_collision_and_invalid_batch_are_atomic(self):
        self.propose(self.invoice())
        code, _ = self.propose(self.invoice('another'), self.invoice(amount=99))
        self.assertEqual(code, 409)
        self.assertEqual(self.request('GET', '/api/invoices?status=all')[1]['count'], 1)
        bad = {**self.invoice('bad'), 'currency': 'XYZ'}
        self.assertEqual(self.propose(self.invoice('new'), bad)[0], 400)
        self.assertEqual(self.request('GET', '/api/invoices')[1]['count'], 1)

    def test_05_existing_transaction_prevents_double_charge(self):
        self.propose(self.invoice())
        row = self.invoice()
        self.assertEqual(self.request('POST', '/api/transactions/import', {'transactions': [row]})[0], 200)
        self.assertEqual(self.decision()[1]['status'], 'duplicate')
        self.assertEqual(self.decision()[1]['alreadyReviewed'], True)
        self.assertEqual(len(self.request('GET', '/api/state')[1]['state']['transactions']), 1)
        self.assertEqual(self.propose(self.invoice())[1]['skipped'], 1)

    def test_06_auth_input_status_limits_and_page(self):
        self.assertEqual(self.request('GET', '/api/invoices', authorized=False)[0], 401)
        self.assertEqual(self.request('POST', '/api/invoices/decision', {}, authorized=False)[0], 401)
        self.assertEqual(self.propose()[0], 400)
        self.assertEqual(self.propose(self.invoice(amount=-4))[0], 400)
        self.assertEqual(self.request('GET', '/api/invoices?status=bogus')[0], 400)
        self.assertEqual(self.request('GET', '/api/invoices?limit=501')[0], 400)
        self.assertEqual(self.request('GET', '/api/invoices/events?limit=0')[0], 400)
        self.assertEqual(self.decision()[0], 404)
        code, html = self.request('GET', '/review', authorized=False)
        self.assertEqual(code, 200)
        self.assertIn(b'<!doctype html>', html)

    def test_07_existing_ledger_upgrade_preserved(self):
        row = self.invoice()
        self.request('POST', '/api/transactions/import', {'transactions': [row]})
        app.init_db()
        self.assertEqual(self.propose(self.invoice())[1], {'queued': 0, 'skipped': 1})
        self.assertEqual(self.request('GET', '/api/state')[1]['revision'], 1)


if __name__ == '__main__':
    unittest.main()
