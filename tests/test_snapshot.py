"""Synthetic-only tests for full backup, WAL, audit history, restore drill and safety."""
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import app
from tools.ledger_snapshot import copy_new, verify


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'live.sqlite3'
        app.DB_PATH = self.source
        app.init_db()
        with app.connect_db() as db:
            app.import_transactions(db, [{'date': '2026-10-09', 'provider': 'Fictional AI',
                                          'type': 'topup', 'amount': 10, 'currency': 'USD',
                                          'source': 'synthetic', 'externalId': 'paid-001'}])
            app.propose_invoices(db, [{'date': '2026-10-09', 'provider': 'Fictional AI',
                                       'type': 'subscription', 'amount': 5, 'currency': 'USD',
                                       'source': 'synthetic', 'externalId': 'review-001'}])
            app.decide_invoice(db, {'source': 'synthetic', 'externalId': 'review-001', 'decision': 'reject'})
            app.propose_invoices(db, [{'date': '2026-10-09', 'provider': 'Fictional AI',
                                       'type': 'subscription', 'amount': 7, 'currency': 'USD',
                                       'source': 'synthetic', 'externalId': 'review-002'}])

    def test_complete_backup_and_restore_drill(self):
        backup = self.folder / 'safe.sqlite3'
        restored = self.folder / 'rehearsal.sqlite3'
        self.assertEqual(copy_new(self.source, backup), verify(self.source))
        self.assertEqual(copy_new(backup, restored), verify(backup))
        with sqlite3.connect(restored) as db:
            self.assertEqual(db.execute('SELECT status FROM invoice_reviews WHERE external_id=?',
                                        ('review-001',)).fetchone()[0], 'rejected')
            self.assertEqual(db.execute('SELECT status FROM invoice_reviews WHERE external_id=?',
                                        ('review-002',)).fetchone()[0], 'pending')
            self.assertEqual(db.execute('SELECT event FROM review_events').fetchone()[0], 'rejected')
            self.assertEqual(len(json.loads(db.execute('SELECT state_json FROM ledger').fetchone()[0])['transactions']), 1)

    def test_refuse_overwrite_and_original_unchanged(self):
        before = verify(self.source)
        with self.assertRaisesRegex(ValueError, 'source and destination'):
            copy_new(self.source, self.source)
        target = self.folder / 'existing.sqlite3'
        target.write_text('not a database')
        with self.assertRaises(FileExistsError):
            copy_new(self.source, target)
        self.assertEqual(target.read_text(), 'not a database')
        self.assertEqual(verify(self.source), before)

    def test_incomplete_or_corrupt_backup_rejected(self):
        corrupt = self.folder / 'bad.sqlite3'
        corrupt.write_bytes(b'not-sqlite')
        with self.assertRaises(sqlite3.DatabaseError):
            verify(corrupt)
        old = self.folder / 'old.sqlite3'
        with sqlite3.connect(old) as db:
            db.execute('CREATE TABLE ledger (id INTEGER PRIMARY KEY, revision INTEGER, state_json TEXT)')
        with self.assertRaisesRegex(ValueError, 'missing tables'):
            verify(old)
        with self.assertRaises(FileNotFoundError):
            verify(self.folder / 'missing.sqlite3')
        self.assertFalse((self.folder / 'missing.sqlite3').exists())

    def test_new_snapshot_permissions_and_cli(self):
        backup = self.folder / 'cmd.sqlite3'
        tool = Path(__file__).resolve().parents[1] / 'tools/ledger_snapshot.py'
        run = subprocess.run([sys.executable, str(tool), 'backup', '--db', str(self.source), '--out', str(backup)],
                             capture_output=True, text=True, check=True)
        response = json.loads(run.stdout)
        self.assertEqual((response['result'], response['tables']['invoice_reviews']), ('ok', 2))
        if os.name == 'posix':
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        again = subprocess.run([sys.executable, str(tool), 'restore', '--file', str(backup), '--out', str(backup)],
                               capture_output=True, text=True)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(verify(backup)['tables']['review_events'], 1)


if __name__ == '__main__':
    unittest.main()
