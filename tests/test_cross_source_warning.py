"""Synthetic-only HTTP tests for advisory cross-source similarity warnings.

No mail account, production credentials, external HTTP or persistent user data.
"""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

os.environ['AI_SPEND_ACCESS_TOKEN'] = 'synthetic-only-test-token-not-an-actual-secret'
import app


class CrossSourceWarningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join(timeout=3)
        cls.folder.cleanup()

    def setUp(self):
        app.DB_PATH = Path(self.folder.name) / (self._testMethodName + '.sqlite3')
        app.init_db()

    def request(self, method, endpoint, data=None, auth=True):
        headers = {'Content-Type': 'application/json'}
        if auth:
            headers['Authorization'] = 'Bearer ' + app.TOKEN
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            conn.request(method, endpoint,
                         json.dumps(data).encode() if data is not None else None, headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def receipt(self, external_id='a', source='mail', provider='Example AI', amount=10,
                currency='USD', date='2026-10-09', tx_type='subscription'):
        return {'date': date, 'provider': provider, 'type': tx_type, 'amount': amount,
                'currency': currency, 'source': source, 'externalId': external_id,
                'notes': 'synthetic only'}

    def propose(self, *receipts):
        return self.request('POST', '/api/invoices/propose', {'candidates': list(receipts)})

    def pending(self):
        status, value = self.request('GET', '/api/invoices?status=pending')
        self.assertEqual(status, 200)
        return {(x['source'], x['externalId']): x for x in value['candidates']}

    def test_cross_source_candidate_flags_both_without_changing_cash(self):
        self.assertEqual(self.propose(self.receipt('a','mail'), self.receipt('b','bank'))[1],
                         {'queued': 2, 'skipped': 0})
        candidates = self.pending()
        self.assertEqual([(x['source'], x['externalId']) for x in
                          candidates['mail','a']['possibleDuplicates']], [('bank', 'b')])
        self.assertEqual([(x['source'], x['externalId']) for x in
                          candidates['bank','b']['possibleDuplicates']], [('mail', 'a')])
        self.assertEqual(self.request('GET', '/api/state')[1]['revision'], 0)
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 0)
        self.assertEqual(self.request('GET', '/api/invoices/events')[1]['events'], [])

    def test_same_money_date_but_different_provider_never_flags(self):
        self.propose(self.receipt('a','mail',provider='Provider Alpha'),
                     self.receipt('b','bank',provider='Provider Beta'))
        for item in self.pending().values():
            self.assertEqual(item['possibleDuplicates'], [])

    def test_date_currency_type_and_amount_must_all_match(self):
        self.propose(self.receipt('a','mail'),
                     self.receipt('date','bank',date='2026-10-10'),
                     self.receipt('currency','card',currency='EUR'),
                     self.receipt('type','invoice',tx_type='api'),
                     self.receipt('amount','csv',amount=10.01))
        for item in self.pending().values():
            self.assertEqual(item['possibleDuplicates'], [])

    def test_same_source_even_distinct_refs_not_flagged(self):
        self.propose(self.receipt('a','mail'), self.receipt('b','mail'))
        for item in self.pending().values():
            self.assertEqual(item['possibleDuplicates'], [])

    def test_approval_still_requires_human_decision_and_rejection_does_not_charge(self):
        self.propose(self.receipt('a','mail'), self.receipt('b','bank'))
        self.assertEqual(self.request('POST', '/api/invoices/decision',
                         {'source':'mail','externalId':'a','decision':'approve'})[1]['status'], 'approved')
        # The second candidate is only WARNED, not auto rejected or auto approved.
        remaining = self.pending()['bank','b']
        self.assertEqual(remaining['status'], 'pending')
        self.assertEqual(len(remaining['possibleDuplicates']), 1)
        self.assertEqual(remaining['possibleDuplicates'][0]['kind'], 'ledger')
        self.assertEqual(remaining['possibleDuplicates'][0]['status'], 'paid')
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 70)
        self.assertEqual(self.request('POST', '/api/invoices/decision',
                         {'source':'bank','externalId':'b','decision':'reject'})[1]['status'], 'rejected')
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 70)
        self.assertEqual(len(self.request('GET', '/api/state')[1]['state']['transactions']), 1)

    def test_warning_never_blocks_manual_approval_or_existing_idempotence(self):
        first, second = self.receipt('a','mail'), self.receipt('b','csv')
        self.propose(first, second)
        self.assertEqual(self.propose(first)[1], {'queued': 0, 'skipped': 1})
        self.assertEqual(self.request('POST', '/api/invoices/decision',
                         {'source':'mail','externalId':'a','decision':'approve'})[0], 200)
        self.assertEqual(self.request('POST', '/api/invoices/decision',
                         {'source':'csv','externalId':'b','decision':'approve'})[0], 200)
        self.assertEqual(self.request('GET', '/api/summary?month=2026-10')[1]['cashPaidCNY'], 140)
        self.assertEqual(len(self.request('GET', '/api/state')[1]['state']['transactions']), 2)
        self.assertEqual(self.request('POST', '/api/invoices/decision',
                         {'source':'csv','externalId':'b','decision':'approve'})[1]['alreadyReviewed'], True)
        self.assertEqual(len(self.request('GET', '/api/state')[1]['state']['transactions']), 2)

    def test_rejected_candidate_ceases_to_be_a_match(self):
        self.propose(self.receipt('a','mail'), self.receipt('b','card'))
        self.assertEqual(self.request('POST', '/api/invoices/decision',
                         {'source':'mail','externalId':'a','decision':'reject'})[1]['status'], 'rejected')
        self.assertEqual(self.pending()['card','b']['possibleDuplicates'], [])
        all_rows = self.request('GET', '/api/invoices?status=all')[1]['candidates']
        self.assertTrue(all(not row['possibleDuplicates'] for row in all_rows))
        self.assertEqual(self.request('GET', '/api/state')[1]['state']['transactions'], [])

    def test_case_whitespace_normalization_only_for_provider_label(self):
        self.propose(self.receipt('a','mail',provider=' Example   AI '),
                     self.receipt('b','csv',provider='example ai'))
        self.assertEqual(len(self.pending()['mail','a']['possibleDuplicates']), 1)
        self.assertEqual(self.request('GET', '/api/invoices',auth=False)[0], 401)


if __name__ == '__main__':
    unittest.main()
