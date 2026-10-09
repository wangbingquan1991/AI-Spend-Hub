"""AI Spend Hub: single-user, LAN-only ledger. Python standard library only."""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import hmac
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get('AI_SPEND_DB', '/data/spend.sqlite3'))
TOKEN = os.environ.get('AI_SPEND_ACCESS_TOKEN', '')
CURRENCIES = {'CNY', 'USD', 'JPY', 'EUR', 'HKD'}
TYPES = {'subscription', 'api', 'topup', 'oneoff', 'refund'}
CYCLES = {'weekly', 'monthly', 'quarterly', 'yearly'}
MAX_BODY = 8 * 1024 * 1024
MAX_REVIEW_CANDIDATES = 10000


class DecisionConflictError(ValueError):
    """The candidate has already received a different final decision."""


def date_ok(value):
    try:
        return isinstance(value, str) and dt.date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def clean_text(v, n=300):
    return str(v if v is not None else '').strip()[:n]


def nonnegative(v, field='amount'):
    if isinstance(v, bool):
        raise ValueError(f'{field} should be a number')
    try:
        number = float(v)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'invalid {field}') from None
    if not math.isfinite(number) or number < 0 or number > 1e12:
        raise ValueError(f'invalid {field}')
    return number


def signed_balance(v):
    if isinstance(v, bool):
        raise ValueError('invalid balance')
    try:
        number = float(v)
    except (ValueError, TypeError, OverflowError):
        raise ValueError('invalid balance') from None
    if not math.isfinite(number) or abs(number) > 1e12:
        raise ValueError('invalid balance')
    return number


def positive(v, field='rateToCNY'):
    number = nonnegative(v, field)
    if number == 0:
        raise ValueError(f'{field} must be positive')
    return number


def default_state():
    return {
        'version': 2, 'subscriptions': [], 'transactions': [], 'wallets': [],
        'settings': {'budget': 500, 'rates': {'CNY': 1, 'USD': 7, 'JPY': .05, 'EUR': 7.5, 'HKD': .9}},
        'createdAt': dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def ensure_dict(data):
    if not isinstance(data, dict):
        raise ValueError('JSON object required')
    return data


def normalize_state(data):
    data = ensure_dict(data)
    out = default_state()
    settings = ensure_dict(data.get('settings', {}))
    out['settings']['budget'] = nonnegative(settings.get('budget', 500), 'budget')
    rates = ensure_dict(settings.get('rates', {}))
    for cur in CURRENCIES - {'CNY'}:
        out['settings']['rates'][cur] = positive(rates.get(cur, out['settings']['rates'][cur]), 'rate')
    if isinstance(data.get('createdAt'), str):
        out['createdAt'] = data['createdAt'][:45]
    for key, limit in [('subscriptions', 2000), ('transactions', 30000), ('wallets', 2000)]:
        rows = data.get(key)
        if not isinstance(rows, list) or len(rows) > limit:
            raise ValueError(f'bad {key} array')
        seen = set()
        for record in rows:
            a = ensure_dict(record)
            rid = clean_text(a.get('id'), 100)
            if not rid or rid in seen:
                raise ValueError(f'missing or duplicate id in {key}')
            seen.add(rid)
            provider = clean_text(a.get('provider'), 100)
            if not provider:
                raise ValueError(f'missing provider in {key}')
            item = {'id': rid, 'provider': provider}
            if key == 'subscriptions':
                if a.get('currency') not in CURRENCIES or a.get('cycle') not in CYCLES or not date_ok(a.get('next')):
                    raise ValueError('invalid subscription')
                if not isinstance(a.get('active'), bool):
                    raise ValueError('active must be boolean')
                item.update(amount=nonnegative(a.get('amount')), currency=a['currency'],
                            cycle=a['cycle'], next=a['next'], active=a['active'], notes=clean_text(a.get('notes')))
            elif key == 'transactions':
                if a.get('type') not in TYPES or a.get('currency') not in CURRENCIES or not date_ok(a.get('date')):
                    raise ValueError('invalid transaction')
                item.update(date=a['date'], type=a['type'], amount=nonnegative(a.get('amount')),
                            currency=a['currency'], rateToCNY=positive(a.get('rateToCNY')),
                            notes=clean_text(a.get('notes')))
                # Keep import provenance across UI edits and backups.
                if a.get('source') is not None:
                    item['source'] = clean_text(a['source'], 80)
                if a.get('externalId') is not None:
                    item['externalId'] = clean_text(a['externalId'], 200)
            else:
                item.update(balance=signed_balance(a.get('balance')),
                            unit=clean_text(a.get('unit', '积分'), 32),
                            updatedAt=a.get('updatedAt'))
                if not date_ok(item['updatedAt']):
                    raise ValueError('invalid wallet date')
            out[key].append(item)
    external_seen = set()
    for item in out['transactions']:
        if item.get('externalId'):
            key = (item.get('source', ''), item['externalId'])
            if key in external_seen:
                raise ValueError('duplicate external invoice reference')
            external_seen.add(key)
    return out


def connect_db():
    db = sqlite3.connect(str(DB_PATH), timeout=10)
    db.execute('PRAGMA busy_timeout=10000')
    return db


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS ledger (id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, state_json TEXT NOT NULL, updated_at TEXT NOT NULL)')
        db.execute('INSERT OR IGNORE INTO ledger(id,revision,state_json,updated_at) VALUES(1,0,?,?)',
                   (json.dumps(default_state(), ensure_ascii=False), dt.datetime.now(dt.timezone.utc).isoformat()))
        db.execute('''CREATE TABLE IF NOT EXISTS invoice_reviews (
            source TEXT NOT NULL, external_id TEXT NOT NULL,
            candidate_json TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL, reviewed_at TEXT,
            PRIMARY KEY(source, external_id))''')
        db.execute('''CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
            external_id TEXT NOT NULL, event TEXT NOT NULL,
            recorded_at TEXT NOT NULL)''')


def load(db):
    row = db.execute('SELECT revision,state_json FROM ledger WHERE id=1').fetchone()
    return row[0], json.loads(row[1])


def commit_state(db, revision, state):
    db.execute('UPDATE ledger SET revision=?,state_json=?,updated_at=? WHERE id=1',
               (revision + 1, json.dumps(state, ensure_ascii=False, allow_nan=False, separators=(',', ':')),
                dt.datetime.now(dt.timezone.utc).isoformat()))


def add_cycle(day, cycle):
    if cycle == 'weekly':
        return day + dt.timedelta(days=7)
    months = {'monthly': 1, 'quarterly': 3, 'yearly': 12}[cycle]
    year, month = divmod(day.year * 12 + (day.month - 1) + months, 12)
    month += 1
    return dt.date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def summary(state, month=None, today=None):
    today = today or dt.date.today()
    if month is None:
        month = today.strftime('%Y-%m')
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', month):
        raise ValueError('month should be YYYY-MM')
    spend = 0.0
    categories = {}
    providers = {}
    for t in state['transactions']:
        if t['date'][:7] != month:
            continue
        cost = t['amount'] * t['rateToCNY'] * (-1 if t['type'] == 'refund' else 1)
        spend += cost
        categories[t['type']] = categories.get(t['type'], 0) + cost
        providers[t['provider']] = providers.get(t['provider'], 0) + cost
    monthly = 0.0
    due = []
    horizon = today + dt.timedelta(days=30)
    for s in state['subscriptions']:
        if not s['active']:
            continue
        cost = s['amount'] * state['settings']['rates'][s['currency']]
        monthly += cost * {'weekly': 52 / 12, 'monthly': 1, 'quarterly': 1 / 3, 'yearly': 1 / 12}[s['cycle']]
        day = dt.date.fromisoformat(s['next'])
        for _ in range(2000):
            if day > horizon:
                break
            if today <= day <= horizon:
                due.append({'provider': s['provider'], 'date': day.isoformat(), 'amountCNY': round(cost, 2)})
            day = add_cycle(day, s['cycle'])
    return {
        'month': month, 'currency': 'CNY', 'cashPaidCNY': round(spend, 2),
        'budgetCNY': round(state['settings']['budget'], 2),
        'budgetRemainingCNY': round(state['settings']['budget'] - spend, 2),
        'activeSubscriptionMonthlyCNY': round(monthly, 2),
        'next30DaysCNY': round(sum(a['amountCNY'] for a in due), 2),
        'renewals': sorted(due, key=lambda x: x['date']),
        'byCategory': {k: round(v, 2) for k, v in categories.items()},
        'byProvider': dict(sorted(((k, round(v, 2)) for k, v in providers.items()), key=lambda x: -x[1])),
        'transactionCount': sum(t['date'][:7] == month for t in state['transactions']),
        'asOf': today.isoformat(),
    }


def normalize_import_row(a, rates):
    a = ensure_dict(a)
    if not date_ok(a.get('date')) or a.get('type') not in TYPES or a.get('currency') not in CURRENCIES:
        raise ValueError('invalid date, type or currency')
    provider = clean_text(a.get('provider'), 100)
    source = clean_text(a.get('source'), 80)
    external_id = clean_text(a.get('externalId'), 200)
    if not provider or not source or not external_id:
        raise ValueError('provider, source and externalId are required')
    rate = a.get('rateToCNY')
    rate = positive(rate, 'rateToCNY') if rate is not None else rates[a['currency']]
    return {
        'id': str(uuid.uuid4()), 'date': a['date'], 'provider': provider,
        'type': a['type'], 'amount': nonnegative(a.get('amount')),
        'currency': a['currency'], 'rateToCNY': rate,
        'notes': clean_text(a.get('notes')), 'source': source, 'externalId': external_id,
    }


def import_transactions(db, rows):
    if not isinstance(rows, list) or len(rows) > 1000 or not rows:
        raise ValueError('transactions must be a non-empty array (max 1000)')
    db.execute('BEGIN IMMEDIATE')
    try:
        rev, state = load(db)
        existing = {(t.get('source'), t.get('externalId')) for t in state['transactions'] if t.get('externalId')}
        normalized = [normalize_import_row(x, state['settings']['rates']) for x in rows]
        added = skipped = 0
        for row in normalized:
            key = (row['source'], row['externalId'])
            if key in existing:
                skipped += 1
                continue
            existing.add(key)
            state['transactions'].append(row)
            added += 1
        if len(state['transactions']) > 30000:
            raise ValueError('ledger transaction limit reached')
        if added:
            commit_state(db, rev, state)
            rev += 1
        db.commit()
        return {'imported': added, 'skipped': skipped, 'revision': rev}
    except Exception:
        db.rollback()
        raise


def review_time():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def propose_invoices(db, candidates):
    """Store minimal invoice fields, never raw email content or payment credentials."""
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 500:
        raise ValueError('candidates must be a non-empty array (max 500)')
    db.execute('BEGIN IMMEDIATE')
    try:
        _, state = load(db)
        # Validate entire batch before making any changes.
        rows = [normalize_import_row(x, state['settings']['rates']) for x in candidates]
        new, skipped = 0, 0
        now = review_time()
        existing_refs = {(t.get('source'), t.get('externalId')) for t in state['transactions'] if t.get('externalId')}
        for row in rows:
            key = (row['source'], row['externalId'])
            existing = db.execute('SELECT candidate_json FROM invoice_reviews WHERE source=? AND external_id=?', key).fetchone()
            # A repeated upstream ID must never silently replace its contents.
            proposed = {k: v for k, v in row.items() if k != 'id'}
            if existing:
                old = json.loads(existing[0])
                if old != proposed:
                    raise DecisionConflictError('same invoice reference has different content')
                skipped += 1
                continue
            if key in existing_refs:
                skipped += 1
                continue
            if db.execute('SELECT COUNT(*) FROM invoice_reviews').fetchone()[0] >= MAX_REVIEW_CANDIDATES:
                raise ValueError('invoice review storage limit reached')
            db.execute('''INSERT INTO invoice_reviews(source,external_id,candidate_json,status,created_at)
                          VALUES(?,?,?,'pending',?)''',
                       (key[0], key[1], json.dumps(proposed, ensure_ascii=False, allow_nan=False), now))
            new += 1
        db.commit()
        return {'queued': new, 'skipped': skipped}
    except Exception:
        db.rollback()
        raise


def list_invoices(db, status='pending', limit=100):
    if status not in {'pending', 'approved', 'rejected', 'duplicate', 'all'}:
        raise ValueError('status must be pending, approved, rejected, duplicate or all')
    if not isinstance(limit, int) or limit < 1 or limit > 500:
        raise ValueError('limit must be 1..500')
    if status == 'all':
        rows = db.execute('''SELECT source,external_id,candidate_json,status,created_at,reviewed_at
                             FROM invoice_reviews ORDER BY created_at DESC,source,external_id LIMIT ?''', (limit,)).fetchall()
    else:
        rows = db.execute('''SELECT source,external_id,candidate_json,status,created_at,reviewed_at
                             FROM invoice_reviews WHERE status=? ORDER BY created_at DESC,source,external_id LIMIT ?''',
                          (status, limit)).fetchall()
    return {'candidates': [{**json.loads(row[2]), 'status': row[3], 'createdAt': row[4],
                            'reviewedAt': row[5]} for row in rows],
            'count': len(rows)}


def decide_invoice(db, data):
    data = ensure_dict(data)
    source, external_id = clean_text(data.get('source'), 80), clean_text(data.get('externalId'), 200)
    decision = data.get('decision')
    if not source or not external_id or decision not in {'approve', 'reject'}:
        raise ValueError('source, externalId and decision (approve or reject) required')
    db.execute('BEGIN IMMEDIATE')
    try:
        row = db.execute('SELECT candidate_json,status FROM invoice_reviews WHERE source=? AND external_id=?',
                         (source, external_id)).fetchone()
        if not row:
            db.rollback()
            return None
        payload, status = json.loads(row[0]), row[1]
        final = 'approved' if decision == 'approve' else 'rejected'
        if status != 'pending':
            if status == final or (status == 'duplicate' and decision == 'approve'):
                db.rollback()
                return {'status': status, 'alreadyReviewed': True}
            raise DecisionConflictError('invoice already reviewed; cannot reverse decision')
        if decision == 'reject':
            final = 'rejected'
            revision = None
        else:
            revision, state = load(db)
            key = (source, external_id)
            duplicates = {(t.get('source'), t.get('externalId')) for t in state['transactions'] if t.get('externalId')}
            if key in duplicates:
                final = 'duplicate'
            else:
                if len(state['transactions']) >= 30000:
                    raise ValueError('ledger transaction limit reached')
                state['transactions'].append({'id': str(uuid.uuid4()), **payload})
                commit_state(db, revision, state)
                revision += 1
        now = review_time()
        db.execute('UPDATE invoice_reviews SET status=?,reviewed_at=? WHERE source=? AND external_id=?',
                   (final, now, source, external_id))
        db.execute('INSERT INTO review_events(source,external_id,event,recorded_at) VALUES(?,?,?,?)',
                   (source, external_id, final, now))
        db.commit()
        return {'status': final, 'alreadyReviewed': False, 'revision': revision}
    except Exception:
        db.rollback()
        raise


def list_review_events(db, limit=100):
    if not 1 <= limit <= 500:
        raise ValueError('limit must be 1..500')
    rows = db.execute('''SELECT source,external_id,event,recorded_at
                         FROM review_events ORDER BY id DESC LIMIT ?''', (limit,)).fetchall()
    return {'events': [{'source': r[0], 'externalId': r[1], 'event': r[2], 'recordedAt': r[3]} for r in rows]}


class Handler(BaseHTTPRequestHandler):
    server_version = 'AISpendHub/0.3-dev'

    def log_message(self, fmt, *args):
        # Avoid accidentally logging authorization material or full URLs with tokens.
        print('%s [%s] %s' % (self.address_string(), self.log_date_time_string(), fmt % args), flush=True)

    def respond(self, status, data):
        raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        supplied = self.headers.get('Authorization', '')
        return len(TOKEN) >= 20 and hmac.compare_digest(supplied, 'Bearer ' + TOKEN)

    def require_auth(self):
        if not self.authorized():
            self.respond(401, {'error': 'Unauthorized. Provide Bearer access token.'})
            return False
        return True

    def read_json(self):
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise ValueError('invalid Content-Length') from None
        if size < 0 or size > MAX_BODY:
            raise ValueError('request body exceeds 8 MB or missing Content-Length')
        return json.loads(self.rfile.read(size).decode('utf-8'))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in {'/', '/index.html', '/review'}:
            content = (ROOT / ('web/review.html' if path == '/review' else 'web/index.html')).read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(content)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; object-src 'none'; frame-ancestors 'none'")
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(content)
        elif path == '/healthz':
            self.respond(200, {'status': 'ok'})
        elif path == '/api/state':
            if not self.require_auth():
                return
            with connect_db() as db:
                rev, state = load(db)
            self.respond(200, {'revision': rev, 'state': state})
        elif path == '/api/summary':
            if not self.require_auth():
                return
            try:
                params = parse_qs(urlparse(self.path).query)
                with connect_db() as db:
                    _, state = load(db)
                self.respond(200, summary(state, params.get('month', [None])[0]))
            except ValueError as e:
                self.respond(400, {'error': str(e)})
        elif path in {'/api/invoices', '/api/invoices/events'}:
            if not self.require_auth():
                return
            try:
                params = parse_qs(urlparse(self.path).query)
                limit = int(params.get('limit', ['100'])[0])
                with connect_db() as db:
                    output = (list_review_events(db, limit) if path.endswith('/events')
                              else list_invoices(db, params.get('status', ['pending'])[0], limit))
                self.respond(200, output)
            except ValueError as e:
                self.respond(400, {'error': str(e)})
        else:
            self.respond(404, {'error': 'not found'})

    def do_PUT(self):
        if urlparse(self.path).path != '/api/state':
            return self.respond(404, {'error': 'not found'})
        if not self.require_auth():
            return
        try:
            a = ensure_dict(self.read_json())
            revision = a.get('revision')
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                raise ValueError('revision required')
            state = normalize_state(a.get('state'))
            with connect_db() as db:
                db.execute('BEGIN IMMEDIATE')
                current, _ = load(db)
                if current != revision:
                    db.rollback()
                    return self.respond(409, {'error': 'Version conflict: reload before saving', 'revision': current})
                commit_state(db, current, state)
                db.commit()
            self.respond(200, {'revision': current + 1})
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
            self.respond(400, {'error': str(e)})

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {'/api/transactions/import', '/api/invoices/propose', '/api/invoices/decision'}:
            return self.respond(404, {'error': 'not found'})
        if not self.require_auth():
            return
        try:
            a = ensure_dict(self.read_json())
            with connect_db() as db:
                if path == '/api/transactions/import':
                    result = import_transactions(db, a.get('transactions'))
                elif path == '/api/invoices/propose':
                    result = propose_invoices(db, a.get('candidates'))
                else:
                    result = decide_invoice(db, a)
            self.respond(404 if result is None else 200, {'error': 'invoice not found'} if result is None else result)
        except DecisionConflictError as e:
            self.respond(409, {'error': str(e)})
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as e:
            self.respond(400, {'error': str(e)})


def main():
    if len(TOKEN) < 20 or TOKEN.startswith('replace-with'):
        raise SystemExit('Set AI_SPEND_ACCESS_TOKEN to a strong random value (20+ chars) before starting.')
    parser = argparse.ArgumentParser(description='AI Spend Hub')
    parser.add_argument('--host', default=os.environ.get('AI_SPEND_HOST', '0.0.0.0'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('AI_SPEND_PORT', '8765')))
    args = parser.parse_args()
    if os.environ.get('TZ') and hasattr(time, 'tzset'):
        time.tzset()
    init_db()
    print(f'AI Spend Hub serving at http://{args.host}:{args.port} (DB {DB_PATH})', flush=True)
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
