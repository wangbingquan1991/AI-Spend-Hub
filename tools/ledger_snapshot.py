"""Safely snapshot the complete AI Spend Hub SQLite DB; never overwrite files.

Examples:
  python3 tools/ledger_snapshot.py backup --db /data/spend.sqlite3 --out /backups/2026-10-09.sqlite3
  python3 tools/ledger_snapshot.py verify --file /backups/2026-10-09.sqlite3
  python3 tools/ledger_snapshot.py restore --file /backups/2026-10-09.sqlite3 --out /tmp/rehearsal.sqlite3
"""
from __future__ import annotations

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys

REQUIRED = ('ledger', 'invoice_reviews', 'review_events')


def read_only(path: Path):
    """Open without creating a missing database."""
    return sqlite3.connect(path.resolve(strict=True).as_uri() + '?mode=ro', uri=True)


def verify(path: Path):
    """Check SQLite integrity and all v0.3 ledger/review tables (no PII output)."""
    with closing(read_only(path)) as db:
        check = db.execute('PRAGMA integrity_check').fetchone()
        if check != ('ok',):
            raise ValueError('database integrity check failed')
        existing = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = set(REQUIRED) - existing
        if missing:
            raise ValueError('missing tables: ' + ', '.join(sorted(missing)))
        row = db.execute('SELECT revision,state_json FROM ledger WHERE id=1').fetchone()
        if row is None or not isinstance(row[0], int):
            raise ValueError('missing ledger state or revision')
        state = json.loads(row[1])
        if not isinstance(state, dict) or not all(key in state for key in ('subscriptions', 'transactions', 'wallets')):
            raise ValueError('invalid ledger state')
        return {'revision': row[0], 'tables': {name: db.execute('SELECT count(*) FROM "' + name + '"').fetchone()[0]
                                               for name in REQUIRED}}


def copy_new(source: Path, destination: Path):
    """SQLite online backup including committed WAL; refuses existing destinations."""
    source = source.resolve(strict=True)
    destination = destination.absolute()
    if destination.resolve() == source:
        raise ValueError('source and destination must differ')
    if not destination.parent.is_dir():
        raise ValueError('destination directory does not exist')
    verify(source)
    # O_EXCL prevents accidentally clobbering a live database or following an existing symlink.
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    try:
        with closing(read_only(source)) as original, closing(sqlite3.connect(destination)) as target:
            original.backup(target)
            target.commit()
        return verify(destination)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local-only full SQLite backup and restore drill')
    commands = parser.add_subparsers(dest='command', required=True)
    backup = commands.add_parser('backup', help='snapshot live DB to a NEW path')
    backup.add_argument('--db', type=Path, required=True)
    backup.add_argument('--out', type=Path, required=True)
    check = commands.add_parser('verify', help='check an existing backup without modifying it')
    check.add_argument('--file', type=Path, required=True)
    restore = commands.add_parser('restore', help='restore backup to NEW path, NEVER replace live DB')
    restore.add_argument('--file', type=Path, required=True)
    restore.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        details = (verify(args.file) if args.command == 'verify' else
                   copy_new(args.db if args.command == 'backup' else args.file, args.out))
    except (OSError, ValueError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        parser.exit(1, f'Error: {exc}\n')
    print(json.dumps({'result': 'ok', 'operation': args.command, **details}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
