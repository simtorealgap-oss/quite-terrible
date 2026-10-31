"""Small SQLite store. Amounts are integer minor units (KRW won, USD cents)."""
import contextlib
import datetime as dt
import json
import math
import os
import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PRODUCTS = json.loads((ROOT / 'config/products.json').read_text())
CATALOG = {p['id']: p for p in PRODUCTS}
UTC = dt.timezone.utc
# Prices are checked once each morning, so a quote stays current for 36 hours, not 24.
STALE_SECONDS = 36 * 3600


def now():
    return dt.datetime.now(UTC)


def stamp(value=None):
    return (value or now()).astimezone(UTC).isoformat(timespec='seconds')


def parse_time(value):
    date = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if date.tzinfo is None:
        raise ValueError('Timestamp must contain a timezone')
    return date.astimezone(UTC)


def safe_url(value):
    try:
        parts = urlsplit(value)
        return parts.scheme in ('https', 'http') and bool(parts.hostname) and not parts.username and not parts.password
    except (ValueError, TypeError):
        return False


def connect(path=None):
    path = Path(path or os.getenv('RAMPRICE_DB', ROOT / 'data/ramprice.sqlite3'))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY, product_id TEXT NOT NULL, market TEXT NOT NULL,
            offer_key TEXT NOT NULL, price INTEGER, shipping INTEGER,
            stock TEXT NOT NULL, merchant TEXT NOT NULL, title TEXT NOT NULL,
            url TEXT NOT NULL, affiliate_url TEXT, source TEXT NOT NULL,
            observed_at TEXT NOT NULL, shops INTEGER, image TEXT, rocket INTEGER,
            UNIQUE(product_id, market, source, offer_key, observed_at)
        );
        CREATE INDEX IF NOT EXISTS price_lookup ON prices(product_id, market, observed_at);
        CREATE TABLE IF NOT EXISTS news (
            id TEXT PRIMARY KEY, lang TEXT NOT NULL, category TEXT NOT NULL,
            title TEXT NOT NULL, url TEXT NOT NULL, publisher TEXT NOT NULL,
            published_at TEXT NOT NULL, collected_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            job TEXT PRIMARY KEY, attempted_at TEXT NOT NULL, succeeded_at TEXT,
            state TEXT NOT NULL, message TEXT NOT NULL
        );
    ''')
    columns = {row['name'] for row in db.execute('PRAGMA table_info(prices)')}
    for name, kind in (('shops', 'INTEGER'), ('image', 'TEXT'), ('rocket', 'INTEGER')):
        if name not in columns:
            db.execute(f'ALTER TABLE prices ADD COLUMN {name} {kind}')  # databases created before these columns
    return db


@contextlib.contextmanager
def session(path=None):
    """Commit on success and always close; sqlite3's own context manager never closes."""
    db = connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


def record_run(db, job, state, message):
    at = stamp()
    db.execute('''INSERT INTO runs VALUES(?,?,?,?,?) ON CONFLICT(job) DO UPDATE SET
        attempted_at=excluded.attempted_at,
        succeeded_at=COALESCE(excluded.succeeded_at,runs.succeeded_at),
        state=excluded.state,message=excluded.message''',
        (job, at, at if state == 'ok' else None, state, message))
    db.commit()


def validate_quote(row):
    row = dict(row)
    if row.get('product_id') not in CATALOG or row.get('market') not in ('KR', 'US'):
        raise ValueError('Unknown product or market')
    for key in ('offer_key', 'source', 'merchant', 'title'):
        if not isinstance(row.get(key), str) or not row[key].strip() or len(row[key]) > 500:
            raise ValueError(f'Invalid {key}')
    if row.get('stock') not in ('in_stock', 'out_of_stock', 'unknown'):
        raise ValueError('Invalid stock state')
    for key in ('price', 'shipping', 'shops'):
        value = row.get(key)
        if value is not None and (type(value) is not int or value < 0 or value > 10**10):
            raise ValueError(f'{key} must be a nonnegative integer')
    if row.get('price') == 0 or (row.get('price') is None and row['stock'] != 'out_of_stock'):
        raise ValueError('A listed price must be positive')
    if not safe_url(row.get('url')) or (row.get('affiliate_url') and not safe_url(row['affiliate_url'])):
        raise ValueError('Invalid external link')
    if row.get('image') is not None and not safe_url(row['image']):
        raise ValueError('Invalid image link')
    if row.get('rocket') not in (None, True, False):
        raise ValueError('Invalid rocket delivery flag')
    if parse_time(row['observed_at']) > now() + dt.timedelta(minutes=5):
        raise ValueError('Future observation rejected')
    row['observed_at'] = stamp(parse_time(row['observed_at']))
    return row


def save_quotes(db, rows):
    # Validate the entire batch before inserting any part of it.
    clean = [validate_quote(row) for row in rows]
    keys = ['product_id', 'market', 'offer_key', 'price', 'shipping', 'stock',
            'merchant', 'title', 'url', 'affiliate_url', 'source', 'observed_at', 'shops', 'image', 'rocket']
    before = db.total_changes
    with db:
        db.executemany(f'INSERT OR IGNORE INTO prices({",".join(keys)}) VALUES({",".join("?" for _ in keys)})',
                       [[r.get(k) for k in keys] for r in clean])
    return db.total_changes - before


def minor_to_amount(value, market):
    return value / (100 if market == 'US' else 1) if value is not None else None


def product_view(db, product, market, at=None):
    at = at or now()
    cutoff = at - dt.timedelta(days=90)
    # Coupang's own price sits beside the comparison (coupang_offer); it never enters the lowest price,
    # history or stats.
    rows = [dict(r) for r in db.execute('''SELECT * FROM prices
        WHERE product_id=? AND market=? AND source!='coupang' AND observed_at>=? AND observed_at<=?
        ORDER BY observed_at,id''', (product['id'], market, stamp(cutoff), stamp(at)))]
    latest = {}
    # Each source offer has its own identity; a later sold-out record invalidates its old quote.
    for r in rows:
        latest[(r['source'], r['offer_key'])] = r
    offers = []
    for r in latest.values():
        age = (at - parse_time(r['observed_at'])).total_seconds()
        r['stale'] = age > STALE_SECONDS
        r['amount'] = minor_to_amount(r['price'], market)
        r['shipping_amount'] = minor_to_amount(r['shipping'], market)
        offers.append(r)
    valid = [r for r in offers if not r['stale'] and r['stock'] != 'out_of_stock' and r['price']]
    valid.sort(key=lambda r: r['price'])
    offers.sort(key=lambda r: (r['stale'], r['stock'] == 'out_of_stock', r['price'] or 10**12))
    # A historical point represents the lowest last-seen offer at that observation time.
    # Stale (over 36 hours) and sold-out offers never persist in the history calculation.
    history, seen = [], {}
    groups = {}
    for r in rows:
        groups.setdefault(r['observed_at'], []).append(r)
    for when, batch in groups.items():
        for r in batch:
            seen[(r['source'], r['offer_key'])] = r
        t = parse_time(when)
        candidates = [r['price'] for r in seen.values() if r['price'] and r['stock'] != 'out_of_stock'
                      and (t - parse_time(r['observed_at'])).total_seconds() <= STALE_SECONDS]
        if candidates:
            history.append({'at': when, 'price': minor_to_amount(min(candidates), market)})
    # Preserve daily last observations, plus the latest one. No invented or interpolated prices.
    full_history = history
    daily = {}
    for point in history:
        daily[point['at'][:10]] = point
    history = list(daily.values())
    best = valid[0] if valid else None
    change = None
    if best:
        target = at - dt.timedelta(hours=24)
        prior = [p for p in full_history if target - dt.timedelta(hours=12) <= parse_time(p['at']) <= target]
        if prior:
            change = round((minor_to_amount(best['price'], market) / prior[-1]['price'] - 1) * 100, 1)
    change7 = None
    if best:
        # Compare with the daily close exactly seven days earlier; no close that day means no figure.
        week_ago = (at - dt.timedelta(days=7)).date().isoformat()
        prior = next((p for p in history if p['at'][:10] == week_ago), None)
        if prior:
            change7 = round((minor_to_amount(best['price'], market) / prior['price'] - 1) * 100, 1)
    recent = [p['price'] for p in history if parse_time(p['at']) >= at - dt.timedelta(days=30)]
    return {k: v for k, v in product.items() if k not in ('query', 'require', 'reject', 'demo_us', 'demo_kr')} | {
        'price': best['amount'] if best else None,
        'change': change, 'change7': change7, 'offers': offers, 'history': history,
        'low30': min(recent) if recent else None,
        'high30': max(recent) if recent else None,
        'merchant_count': len(valid),
        'observed_at': max((r['observed_at'] for r in offers), default=None),
    }


def coupang_offer(db, product, at=None):
    """Cheapest listing from the latest Coupang Partners API check, or None.
    The API leaves sold-out items out instead of marking them, so earlier checks are never mixed in."""
    at = at or now()
    latest = db.execute('''SELECT MAX(observed_at) FROM prices
        WHERE product_id=? AND source='coupang' AND observed_at<=?''', (product['id'], stamp(at))).fetchone()[0]
    if not latest or (at - parse_time(latest)).total_seconds() > STALE_SECONDS:
        return None
    row = db.execute('''SELECT * FROM prices WHERE product_id=? AND source='coupang' AND observed_at=?
        AND price>0 AND stock!='out_of_stock' ORDER BY price,id LIMIT 1''', (product['id'], latest)).fetchone()
    if row is None:
        return None
    return {'name': row['title'], 'price': row['price'], 'url': row['affiliate_url'] or row['url'],
            'image': row['image'], 'rocket': bool(row['rocket']), 'free_shipping': row['shipping'] == 0,
            'observed_at': row['observed_at']}


def demo_products(market):
    # Generated ONLY in memory for the explicit demo route; never enters the live database.
    result = []
    for index, product in enumerate(PRODUCTS):
        price = product['demo_us' if market == 'US' else 'demo_kr']
        history = []
        for day in range(90):
            factor = 1 + (89-day) * (0.0015 if index % 3 else -0.0007) + math.sin(day * .5 + index) * .014
            history.append({'at': stamp(now() - dt.timedelta(days=89-day)), 'price': round(price * factor, 2 if market == 'US' else 0)})
        current = history[-1]['price']
        item = {k: v for k, v in product.items() if k not in ('query', 'require', 'reject', 'demo_us', 'demo_kr')}
        result.append(item | {'price': current, 'change': round((current/history[-2]['price']-1)*100, 1),
            'change7': round((current/history[-8]['price']-1)*100, 1),
            'history': history, 'low30': min(p['price'] for p in history[-30:]),
            'high30': max(p['price'] for p in history[-30:]), 'merchant_count': 0,
            'observed_at': None, 'offers': []})
    return result
