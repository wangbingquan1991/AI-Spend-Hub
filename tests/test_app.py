"""Run: python3 -m unittest discover -s tests -v"""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest

os.environ['AI_SPEND_ACCESS_TOKEN'] = 'test-secret-token-replace-with-strong-value'
import app


class SpendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        app.DB_PATH = Path(cls.temp.name) / 'db.sqlite3'
        app.init_db()
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

    def request(self, method, path, payload=None, token=True):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + app.TOKEN
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request(method, path, body=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        res = conn.getresponse()
        data = res.read()
        code = res.status
        conn.close()
        return code, json.loads(data) if data and res.getheader('Content-Type','').startswith('application/json') else data

    def test_01_auth_and_health(self):
        self.assertEqual(self.request('GET', '/healthz', token=False)[0], 200)
        self.assertEqual(self.request('GET', '/api/state', token=False)[0], 401)
        self.assertEqual(self.request('POST', '/api/transactions/import', {'transactions': []}, token=False)[0], 401)

    def test_02_state_roundtrip_and_conflict(self):
        code, doc = self.request('GET', '/api/state')
        self.assertEqual(code, 200)
        self.assertEqual(doc['revision'], 0)
        doc['state']['subscriptions'].append({'id':'s1','provider':'Claude','amount':20,'currency':'USD','cycle':'monthly','next':'2026-10-20','active':True,'notes':''})
        code, out = self.request('PUT', '/api/state', doc)
        self.assertEqual((code, out['revision']), (200, 1))
        code, out = self.request('PUT', '/api/state', doc)
        self.assertEqual(code, 409)
        doc2 = self.request('GET', '/api/state')[1]
        self.assertEqual(len(doc2['state']['subscriptions']), 1)
        self.assertEqual(doc2['state']['subscriptions'][0]['provider'], 'Claude')

    def test_03_import_idempotency_and_sum(self):
        row = {'date':'2026-10-09','provider':'OpenAI API','type':'api','amount':12.5,
               'currency':'USD','rateToCNY':7,'source':'invoice','externalId':'inv001'}
        code, out = self.request('POST', '/api/transactions/import', {'transactions':[row,row]})
        self.assertEqual(code, 200)
        self.assertEqual((out['imported'],out['skipped']), (1,1))
        code, out = self.request('POST', '/api/transactions/import', {'transactions':[row]})
        self.assertEqual((out['imported'],out['skipped']), (0,1))
        refund = {**row,'type':'refund','amount':2.5,'externalId':'refund001'}
        topup = {**row,'type':'topup','provider':'Higgsfield','amount':10,'externalId':'topup001'}
        self.assertEqual(self.request('POST', '/api/transactions/import', {'transactions':[refund,topup]})[0], 200)
        code, summary = self.request('GET', '/api/summary?month=2026-10')
        self.assertEqual(code, 200)
        self.assertEqual(summary['cashPaidCNY'], 140.0)
        self.assertEqual(summary['byCategory'], {'api': 87.5, 'refund': -17.5, 'topup': 70.0})
        self.assertEqual(summary['activeSubscriptionMonthlyCNY'], 140.0)

    def test_04_import_invalid_atomic(self):
        valid = {'date':'2026-10-09','provider':'Cursor','type':'subscription',
                 'amount':20,'currency':'USD','source':'email','externalId':'invnew'}
        invalid = {**valid, 'amount':-1, 'externalId':'invbad'}
        before = self.request('GET', '/api/state')[1]['revision']
        code, _ = self.request('POST', '/api/transactions/import', {'transactions':[valid,invalid]})
        self.assertEqual(code, 400)
        after = self.request('GET', '/api/state')[1]
        self.assertEqual(before, after['revision'])
        self.assertFalse(any(x.get('externalId')=='invnew' for x in after['state']['transactions']))
        self.assertEqual(self.request('GET','/api/summary?month=abc')[0], 400)

    def test_05_zero_credit_double_count(self):
        doc = self.request('GET','/api/state')[1]
        doc['state']['wallets'].append({'id':'w1','provider':'Higgsfield','balance':225,'unit':'Credits','updatedAt':'2026-10-09'})
        code, _ = self.request('PUT','/api/state',doc)
        self.assertEqual(code,200)
        summary = self.request('GET','/api/summary?month=2026-10')[1]
        self.assertEqual(summary['cashPaidCNY'],140)
        self.assertEqual(self.request('GET','/')[0],200)

    def test_06_reject_invalid(self):
        doc=self.request('GET','/api/state')[1]
        doc['state']['transactions'].append({'id':'bad','provider':'X','date':'2026-10-09','type':'api',
                                              'amount':float('inf'),'currency':'USD','rateToCNY':7})
        self.assertEqual(self.request('PUT','/api/state',doc)[0],400)
        doc=self.request('GET','/api/state')[1]
        doc['state']['wallets'].append({'id':'bad','provider':'X','balance':'NaN','unit':'积分','updatedAt':'2026-10-09'})
        self.assertEqual(self.request('PUT','/api/state',doc)[0],400)


if __name__=='__main__':
    unittest.main()
