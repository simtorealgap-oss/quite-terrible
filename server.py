#!/usr/bin/env python3
"""Run: python3 server.py --port 8765. No third-party dependencies."""
import argparse
import hashlib
import datetime as dt
import html
import json
import mimetypes
import os
import re
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from store import ROOT, PRODUCTS, MARKETS, CURRENCY, STALE_SECONDS, session, product_view, coupang_offer, demo_products, stamp, now, parse_time
from collectors import update_prices, update_news, import_feed
from seo import seo_context

LANGS = ('ko', 'en', 'ja')
# Each page language shows one market's prices: Korea for Korean, Japan for Japanese, the US for English.
LANG_MARKET = {'ko': 'KR', 'ja': 'JP', 'en': 'US'}
I18N = json.loads((ROOT / 'config/i18n.json').read_text())
PAGES = {f'/{lang}/{path}': (lang, page, None) for lang in LANGS
         for path, page in (('', 'prices'), ('news/', 'news'), ('about/', 'about'))}
PAGES |= {f"/{lang}/{p['id']}/": (lang, 'product', p['id']) for lang in LANGS for p in PRODUCTS}
RAW = {'boot', 'jsonld', 'headExtra', 'alternates', 'prerenderRows', 'makerRows', 'productStatic', 'relatedLinks'}
# Country headers set by common CDNs/hosts. They only pick defaults; visitors can always switch.
COUNTRY_HEADERS = ('CF-IPCountry', 'CloudFront-Viewer-Country', 'X-Vercel-IP-Country', 'X-Country-Code')
PLACEHOLDER = re.compile(r'\{\{(\w+)\}\}')
KST = dt.timezone(dt.timedelta(hours=9))


def load_env():
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def visitor_country(headers):
    for name in COUNTRY_HEADERS:
        value = (headers.get(name) or '').strip().upper()
        if re.fullmatch(r'[A-Z]{2}', value) and value != 'XX':
            return value
    return None


def preferred_lang(accept_language, country=None):
    """Highest-weighted supported language in Accept-Language, else the visitor's country."""
    best = None
    for part in (accept_language or '').split(','):
        tag, _, params = part.strip().partition(';')
        primary = tag.strip().lower().split('-')[0]
        match = re.search(r'q\s*=\s*([0-9.]+)', params)
        try:
            weight = float(match.group(1)) if match else 1.0
        except ValueError:
            weight = 0.0
        if primary in LANGS and weight > 0 and (best is None or weight > best[0]):
            best = (weight, primary)
    if best:
        return best[1]
    return {'KR': 'ko', 'JP': 'ja'}.get(country, 'en')


def default_market(country, lang):
    if country in ('KR', 'JP'):
        return country
    return LANG_MARKET.get(lang, 'US') if not country else 'US'


def has_prices(market):
    with session() as db:
        return db.execute('SELECT 1 FROM prices WHERE market=? AND observed_at>=? LIMIT 1',
            (market, stamp(now() - dt.timedelta(seconds=STALE_SECONDS)))).fetchone() is not None


def prices_due(db, at=None, hour=None):
    """Daily morning check: run once per KST day after the configured hour, at once if never run."""
    at = (at or now()).astimezone(KST)
    hour = int(os.getenv('PRICE_RUN_HOUR_KST', '9')) if hour is None else hour
    row = db.execute("SELECT * FROM runs WHERE job='prices:danawa'").fetchone()
    if row is None:
        return True
    if row['state'] != 'ok' and (at - parse_time(row['attempted_at'])).total_seconds() < 3600:
        return False  # failures retry hourly, not on every tick
    if not row['succeeded_at']:
        return True
    return parse_time(row['succeeded_at']).astimezone(KST).date() < at.date() and at.hour >= hour


def asset_version():
    """Short hash of the scripts and styles, added to their URLs so browsers fetch new versions at once
    (GitHub Pages lets browsers cache files for 10 minutes)."""
    digest = hashlib.sha256()
    for name in ('app.js', 'hero.js', 'styles.css'):
        digest.update((ROOT / 'static' / name).read_bytes())
    return digest.hexdigest()[:10]


def seo_products(lang):
    """Prices baked into a page for search engines: the page language's own market, else Korea's."""
    market = LANG_MARKET[lang]
    if market != 'KR' and not has_prices(market):
        market = 'KR'
    return prices_payload(market)


def render_page(lang, page, market, base='', static=False, site='', product=None, products=None, alt_langs=LANGS):
    strings = I18N[lang]
    if products is None:
        products = seo_products(lang)
    currency = 'KRW'
    if isinstance(products, dict):  # a whole prices payload: its products and their currency
        currency, products = products['currency'], products['products']
    context = strings | {'lang': lang, 'base': base, 'year': str(now().year), 'v': asset_version()}
    context |= seo_context(lang, page, strings, products, base=base, site=site, product_id=product, currency=currency, alt_langs=alt_langs)
    for name in ('prices', 'news', 'about', 'product'):
        context[f'{name}Current'] = 'page' if page == name or (name == 'prices' and page == 'product') else 'false'
        context[f'{name}Hidden'] = '' if page == name else 'hidden'
    # JSON inside <script type="application/json"> is data, not code; escape "<" so it cannot close the tag.
    boot = json.dumps({'lang': lang, 'page': page, 'market': market, 'base': base, 'static': static,
                       'product': product, 't': strings}, ensure_ascii=False).replace('<', '\\u003c')
    context['boot'] = boot

    def fill(match):
        key = match.group(1)
        return context[key] if key in RAW else html.escape(str(context[key]))
    return PLACEHOLDER.sub(fill, (ROOT / 'static/index.html').read_text())


def prices_payload(market, demo=False):
    with session() as db:
        products = demo_products(market) if demo else [product_view(db, p, market) for p in PRODUCTS]
        for item, p in zip(products, PRODUCTS):
            # Coupang's own price from its Partners API, shown beside (never inside) the price comparison.
            item['coupangOffer'] = coupang_offer(db, p) if market == 'KR' and not demo else None
        runs = [dict(r) for r in db.execute("SELECT * FROM runs WHERE job LIKE 'prices:%' AND job!='prices:coupang'")]
    return {'market': market, 'currency': CURRENCY[market], 'demo': demo,
            'generated_at': stamp(), 'products': products, 'runs': runs}


NEWS_PER_PUBLISHER_DAY = 2


def news_payload(lang):
    with session() as db:
        # Each language has its own feed; headlines are never machine-translated.
        news = [dict(r) for r in db.execute('''SELECT * FROM news WHERE lang=? AND published_at>=?
            ORDER BY published_at DESC LIMIT 200''', (lang, stamp(now() - dt.timedelta(days=14))))]
        runs = [dict(r) for r in db.execute('SELECT * FROM runs WHERE job LIKE ?', (f'news:{lang}:%',))]
    # At most two headlines per publisher per day, so one prolific outlet cannot fill the page.
    seen, kept = {}, []
    for item in news:
        key = (item['publisher'], item['published_at'][:10])
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= NEWS_PER_PUBLISHER_DAY:
            kept.append(item)
    return {'lang': lang, 'news': kept[:80], 'runs': runs}


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, content_type, headers=None):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' https://cdn.jsdelivr.net; font-src https://cdn.jsdelivr.net; script-src 'self'; img-src 'self' data: https://thumb.wikimedia.org https://upload.wikimedia.org https://*.coupang.com https://*.coupangcdn.com; connect-src 'self' https://abacus.jasoncameron.dev; frame-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def redirect(self, code, target):
        self.send(code, b'', 'text/plain', {'Location': target, 'Vary': 'Accept-Language'})

    def send_json(self, data):
        self.send(200, json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        keep = '?demo=1' if query.get('demo') == ['1'] else ''
        if path == '/health':
            self.send(200, b'{"ok":true}', 'application/json')
            return
        country = visitor_country(self.headers)
        if path == '/':
            # No language or market switcher: both follow the browser language and the visitor's country.
            lang = preferred_lang(self.headers.get('Accept-Language'), country)
            self.redirect(302, f'/{lang}/{keep}')
            return
        if path + '/' in PAGES:
            self.redirect(301, f'{path}/{keep}')
            return
        if path in PAGES:
            lang, page, product = PAGES[path]
            market = default_market(country, lang)
            if market != 'KR' and not has_prices(market):
                market = 'KR'  # no source for that market yet: show real Korean prices instead of an empty page
            self.send(200, render_page(lang, page, market, product=product).encode(), 'text/html; charset=utf-8')
            return
        if path in ('/api/prices', '/api/news'):
            market, lang = query.get('market', ['KR'])[0], query.get('lang', ['ko'])[0]
            if market not in MARKETS or lang not in LANGS:
                self.send(400, b'{"error":"Invalid market or language"}', 'application/json')
                return
            try:
                self.send_json(prices_payload(market, query.get('demo') == ['1']) if path == '/api/prices' else news_payload(lang))
            except Exception:
                self.send(500, b'{"error":"Data temporarily unavailable"}', 'application/json')
            return
        # Explicit static allowlist: never serve .env, config, SQLite, tests or Python source.
        name = path.removeprefix('/')
        if name not in ('app.js', 'hero.js', 'styles.css', 'favicon.svg', 'og.png'):
            self.send(404, b'Not found', 'text/plain')
            return
        self.send(200, (ROOT / 'static' / name).read_bytes(), mimetypes.guess_type(name)[0] or 'application/octet-stream')

    def log_message(self, fmt, *args):
        # Paths may include user-provided query strings; keep logs minimal.
        print(f'HTTP {args[1] if len(args) > 1 else "request"}', flush=True)


def worker(stop):
    while not stop.is_set():
        try:
            with session() as db:
                update_news(db)
                if prices_due(db):
                    update_prices(db, sleep=stop.wait)
        except Exception as exc:
            print(f'worker error: {type(exc).__name__}', flush=True)
        stop.wait(600)


def main():
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-worker', action='store_true')
    parser.add_argument('--update', choices=['all', 'news', 'prices'])
    parser.add_argument('--force-news', action='store_true')
    parser.add_argument('--region', choices=['kr', 'us'],
                        help="'kr': Korea and Japan (both 9:00 local at 00:00 UTC) prices and news; 'us': US prices and English news")
    parser.add_argument('--import-feed', type=Path)
    args = parser.parse_args()
    with session() as db:
        if args.import_feed:
            print(json.dumps({'inserted': import_feed(db, json.loads(args.import_feed.read_text()))}))
            return
        if args.update:
            results = {}
            markets = {'kr': ['KR', 'JP'], 'us': ['US']}.get(args.region, [None])
            langs = {'kr': ['ko', 'ja'], 'us': ['en']}.get(args.region)
            if args.update in ('all', 'news'):
                results['news'] = update_news(db, force=args.force_news, langs=langs)
            if args.update in ('all', 'prices'):
                results['prices'] = [o for m in markets for o in update_prices(db, market=m)]
            print(json.dumps(results, ensure_ascii=False))
            if any('error' in item for items in results.values() for item in items):
                raise SystemExit(1)
            return
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    stop = threading.Event()
    if not args.no_worker:
        threading.Thread(target=worker, args=(stop,), daemon=True).start()
    print(f'Quite Terrible → http://{args.host}:{args.port}/', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
