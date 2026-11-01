"""Daily price sources (Danawa; Coupang, eBay, Best Buy and feeds when configured) and language-specific news headlines."""
import datetime as dt
import base64
import email.utils
import hashlib
import hmac
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from store import PRODUCTS, UTC, now, stamp, parse_time, safe_url, save_quotes, record_run


def fetch(url, headers=None, data=None):
    request = urllib.request.Request(url, data=data, headers={'User-Agent': 'QuiteTerrible-price-reader/0.2 (daily price check)', **(headers or {})})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(4_000_001)
        if len(raw) > 4_000_000:
            raise ValueError('Response too large')
        return raw


def clean_text(value):
    return html.unescape(re.sub(r'<[^>]+>', '', value or '')).strip()


def matches(product, title):
    title = clean_text(title)
    if re.search(r'중고|리퍼|렌탈|대여|refurb|renewed|\bused\b', title, re.I):
        return False
    return all(re.search(p, title, re.I) for p in product['require']) and not any(
        re.search(p, title, re.I) for p in product['reject'])


DANAWA_SEARCH = 'https://search.danawa.com/?'
DANAWA_DELAY = 10  # search.danawa.com robots.txt: Crawl-delay 10
MIN_SHOPS = 3      # one- or two-shop listings are often stale or mispriced
BESTBUY_API = 'https://api.bestbuy.com/v1/products'
EBAY_TOKEN = 'https://api.ebay.com/identity/v1/oauth2/token'
EBAY_SEARCH = 'https://api.ebay.com/buy/browse/v1/item_summary/search?'
# Coupang Partners Open API, products/search, as documented at https://partners.coupang.com/#help/open-api
# (checked 2026-11-01). The docs' Base URL is .../openapi/v1/; one example on the same page leaves out "v1",
# the official deeplink sample keeps it. Search allows at most 50 calls a minute, and reaching a limit
# locks the API for 24 hours. We make one call per product a day, a few seconds apart.
COUPANG_API = 'https://api-gateway.coupang.com'
COUPANG_SEARCH = '/v2/providers/affiliate_open_api/apis/openapi/v1/products/search'
COUPANG_DELAY = 3
COUPANG_COOLDOWN = 3600  # repeated manual runs within an hour leave the Coupang API alone
COUPANG_HOSTS = ('coupang.com', 'coupangcdn.com')
# Pre-built PCs and accessories carry a card's name in their titles too.
COUPANG_GPU_JUNK = re.compile(r'컴퓨터|본체|게이밍\s*pc|미니\s*pc|지지대|브라켓|bracket|라이저|riser|케이블|cable', re.I)
# Box-only, parts and accessory listings are where fake "deals" hide on eBay.
EBAY_JUNK = re.compile(r'box only|empty box|for parts|not working|broken|read desc|bracket|backplate|shroud|'
                       r'cooler|heatsink|water ?block|replacement fan|cable|adapter|riser|repair', re.I)


def rule_for(product, source):
    """Source-specific matching overrides the product's default require/reject patterns."""
    override = product.get(source) if isinstance(product.get(source), dict) else {}
    return {'require': override.get('require', product['require']),
            'reject': override.get('reject', product['reject'])}


def danawa_products(raw):
    """Product list embedded in Danawa's search page (Next.js flight data)."""
    text = raw.decode('utf-8', 'replace') if isinstance(raw, bytes) else raw
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', text, re.S)
    flight = ''.join(json.loads(f'"{chunk}"') for chunk in chunks)
    start = flight.find('"products":[')
    if start < 0:
        raise ValueError('Danawa page layout changed')
    return json.JSONDecoder().raw_decode(flight, start + len('"products":'))[0]


def danawa_quotes(product, items, at=None, limit=10):
    config, rule, rows = product['danawa'], rule_for(product, 'danawa'), {}
    for item in items:
        code = str(item.get('productSeq', ''))
        # Catalog entries only (open-market listings have non-numeric ids), in the right category.
        if not code.isdigit() or item.get('categorySeq3') not in config['category']:
            continue
        try:
            amount, shops = int(item.get('minPrice') or 0), int(item.get('shopCount') or 0)
        except (TypeError, ValueError):
            continue
        name = clean_text(item.get('productName'))
        title = f"{name} {clean_text(item.get('bundleName'))}".strip()
        if amount <= 0 or shops < MIN_SHOPS or item.get('priceCompareStatusType') != '가격비교':
            continue
        if not matches(rule, title):
            continue
        rows[code] = {'product_id': product['id'], 'market': 'KR', 'offer_key': code,
            'price': amount, 'shipping': None, 'stock': 'unknown', 'merchant': title[:200],
            'title': title, 'shops': shops, 'url': f'https://prod.danawa.com/info/?pcode={code}',
            'source': 'danawa', 'observed_at': at or stamp()}
    return sorted(rows.values(), key=lambda r: r['price'])[:limit]


def bestbuy_quotes(product, data, at=None, limit=10):
    rule, rows = rule_for(product, 'bestbuy'), {}
    for item in data.get('products', []):
        title = clean_text(item.get('name'))
        price = item.get('salePrice')
        if not isinstance(price, (int, float)) or price <= 0 or not item.get('sku') or not matches(rule, title):
            continue
        if not safe_url(item.get('url')):
            continue
        rows[str(item['sku'])] = {'product_id': product['id'], 'market': 'US', 'offer_key': str(item['sku']),
            'price': round(price * 100), 'shipping': None,
            'stock': 'in_stock' if item.get('onlineAvailability') else 'out_of_stock',
            'merchant': 'Best Buy', 'title': title[:200], 'url': item['url'],
            'source': 'bestbuy', 'observed_at': at or stamp()}
    return sorted(rows.values(), key=lambda r: r['price'])[:limit]


def ebay_token(client_id, secret):
    """Application access token (client credentials grant), valid for about two hours."""
    auth = base64.b64encode(f'{client_id}:{secret}'.encode()).decode()
    body = urllib.parse.urlencode({'grant_type': 'client_credentials',
                                   'scope': 'https://api.ebay.com/oauth/api_scope'}).encode()
    data = json.loads(fetch(EBAY_TOKEN, {'Authorization': f'Basic {auth}',
                                         'Content-Type': 'application/x-www-form-urlencoded'}, body))
    return data['access_token']


def ebay_params(product):
    config = product['ebay']
    return {'q': config['q'], 'category_ids': config['category'], 'sort': 'price', 'limit': 50,
            'filter': f"conditionIds:{{1000}},buyingOptions:{{FIXED_PRICE}},itemLocationCountry:US,"
                      f"deliveryCountry:US,price:[{config['min']}..],priceCurrency:USD"}


def ebay_quotes(product, data, at=None, limit=10):
    config, rule, rows = product['ebay'], rule_for(product, 'ebay'), {}
    for item in data.get('itemSummaries', []):
        title, price, seller = clean_text(item.get('title')), item.get('price') or {}, item.get('seller') or {}
        try:
            amount = round(float(price.get('value')) * 100)
            score, percent = int(seller.get('feedbackScore') or 0), float(seller.get('feedbackPercentage') or 0)
        except (TypeError, ValueError):
            continue
        if price.get('currency') != 'USD' or amount < config['min'] * 100 or str(item.get('conditionId')) != '1000':
            continue
        if score < 100 or percent < 98 or EBAY_JUNK.search(title) or not matches(rule, title):
            continue
        if not item.get('itemId') or not safe_url(item.get('itemWebUrl')):
            continue
        cost = next((o.get('shippingCost') for o in item.get('shippingOptions') or [] if o.get('shippingCost')), None)
        try:
            shipping = round(float(cost['value']) * 100) if cost and cost.get('currency') == 'USD' else None
        except (TypeError, ValueError):
            shipping = None
        affiliate = item.get('itemAffiliateWebUrl')
        # Seller names are eBay user data; they are not stored.
        rows[item['itemId']] = {'product_id': product['id'], 'market': 'US', 'offer_key': item['itemId'],
            'price': amount, 'shipping': shipping, 'stock': 'in_stock', 'merchant': 'eBay',
            'title': title[:200], 'url': item['itemWebUrl'], 'affiliate_url': affiliate if safe_url(affiliate) else None,
            'source': 'ebay', 'observed_at': at or stamp()}
    return sorted(rows.values(), key=lambda r: r['price'])[:limit]


def coupang_authorization(method, path, query, access_key, secret_key, at=None):
    """Authorization header from the Partners API guide: HMAC-SHA256 (hex) of
    signed-date (yyMMdd'T'HHmmss'Z', GMT) + method + path + query string (without "?")."""
    signed = (at or now()).astimezone(UTC).strftime('%y%m%dT%H%M%SZ')
    signature = hmac.new(secret_key.encode(), (signed + method + path + query).encode(), hashlib.sha256).hexdigest()
    return f'CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={signed}, signature={signature}'


def coupang_search(product, access_key, secret_key):
    query = urllib.parse.urlencode({'keyword': product['coupangSearch']['keyword'], 'limit': 10},
                                   quote_via=urllib.parse.quote)
    headers = {'Authorization': coupang_authorization('GET', COUPANG_SEARCH, query, access_key, secret_key),
               'Content-Type': 'application/json;charset=UTF-8'}
    return json.loads(fetch(f'{COUPANG_API}{COUPANG_SEARCH}?{query}', headers))


def coupang_link(value):
    """Links and images must point at Coupang's own domains."""
    host = urllib.parse.urlsplit(value).hostname if safe_url(value) else None
    return bool(host) and any(host == h or host.endswith('.' + h) for h in COUPANG_HOSTS)


def coupang_quotes(product, data, at=None, limit=10):
    """products/search response: {"rCode": "0", "data": {"productData": [{productId, productName,
    productPrice, productImage, productUrl, isRocket, isFreeShipping, ...}]}}. Sold-out items are not returned."""
    if not isinstance(data, dict) or str(data.get('rCode')) != '0' or not isinstance(data.get('data'), dict):
        raise ValueError('Coupang API returned no results')
    config, rule, rows = product['coupangSearch'], rule_for(product, 'coupangSearch'), {}
    for item in data['data'].get('productData') or []:
        title, url, image = clean_text(item.get('productName')), item.get('productUrl'), item.get('productImage')
        try:
            amount = round(float(item.get('productPrice')))
        except (TypeError, ValueError, OverflowError):
            continue
        if amount < config.get('min', 1) or not item.get('productId') or not coupang_link(url) or not matches(rule, title):
            continue
        if product['category'] == 'gpu' and COUPANG_GPU_JUNK.search(title):
            continue
        rows[str(item['productId'])] = {'product_id': product['id'], 'market': 'KR', 'offer_key': str(item['productId']),
            'price': amount, 'shipping': 0 if item.get('isFreeShipping') is True else None, 'stock': 'in_stock',
            'merchant': 'Coupang', 'title': title[:200], 'url': url, 'affiliate_url': url,
            'image': image if coupang_link(image) else None, 'rocket': item.get('isRocket') is True,
            'source': 'coupang', 'observed_at': at or stamp()}
    return sorted(rows.values(), key=lambda r: r['price'])[:limit]


def coupang_due(db):
    row = db.execute("SELECT attempted_at FROM runs WHERE job='prices:coupang'").fetchone()
    return row is None or (now() - parse_time(row['attempted_at'])).total_seconds() >= COUPANG_COOLDOWN


def error_name(exc):
    # Never log request URLs/headers: providers may put credentials in them.
    return f'HTTPError {exc.code}' if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__


def collect(db, source, products, request, parse, sleep, delay):
    """Fetch every product from one source; a failing product does not stop the rest."""
    at, count, matched, failed = stamp(), 0, {}, []
    for index, product in enumerate(products):
        if index and delay:
            sleep(delay)
        try:
            quotes = parse(product, request(product), at)
            matched[product['id']] = len(quotes)
            count += save_quotes(db, quotes)
        except Exception as exc:
            failed.append(f"{product['id']}: {error_name(exc)}")
    ok = not failed and any(matched.values())
    message = f'{count} observations' if ok else '; '.join(failed) or 'No matching products'
    record_run(db, f'prices:{source}', 'ok' if ok else 'error', message[:500])
    return {'source': source, 'count': count, 'matched': matched, **({} if ok else {'error': message})}


def update_prices(db, sleep=time.sleep, market=None):
    """market='KR' (Danawa, Coupang) or 'US' (eBay, Best Buy); None runs every source."""
    korea, us = market in (None, 'KR'), market in (None, 'US')
    outcomes = []
    if korea:
        outcomes.append(collect(db, 'danawa', PRODUCTS,
            lambda p: danawa_products(fetch(DANAWA_SEARCH + urllib.parse.urlencode({'query': p['danawa']['query']}))),
            lambda p, items, at: danawa_quotes(p, items, at), sleep, DANAWA_DELAY))
    # Coupang prices come only from the Partners API (final approval required); without keys nothing is called.
    coupang_key, coupang_secret = os.getenv('COUPANG_ACCESS_KEY'), os.getenv('COUPANG_SECRET_KEY')
    if korea and coupang_key and coupang_secret and coupang_due(db):
        outcomes.append(collect(db, 'coupang', [p for p in PRODUCTS if p.get('coupangSearch')],
            lambda p: coupang_search(p, coupang_key, coupang_secret),
            lambda p, data, at: coupang_quotes(p, data, at), sleep, COUPANG_DELAY))
    ebay_id, ebay_secret = os.getenv('EBAY_CLIENT_ID'), os.getenv('EBAY_CLIENT_SECRET')
    if us and ebay_id and ebay_secret:
        try:
            token = ebay_token(ebay_id, ebay_secret)
        except Exception as exc:
            record_run(db, 'prices:ebay', 'error', error_name(exc))
            outcomes.append({'source': 'ebay', 'error': error_name(exc)})
        else:
            headers = {'Authorization': f'Bearer {token}', 'X-EBAY-C-MARKETPLACE-ID': 'EBAY_US'}
            if os.getenv('EBAY_CAMPAIGN_ID'):  # eBay Partner Network: returns affiliate item links
                headers['X-EBAY-C-ENDUSERCTX'] = f"affiliateCampaignId={os.environ['EBAY_CAMPAIGN_ID']}"
            outcomes.append(collect(db, 'ebay', [p for p in PRODUCTS if p.get('ebay')],
                lambda p: json.loads(fetch(EBAY_SEARCH + urllib.parse.urlencode(ebay_params(p)), headers)),
                lambda p, data, at: ebay_quotes(p, data, at), sleep, 1))
    key = os.getenv('BESTBUY_API_KEY')
    if us and key:
        params = urllib.parse.urlencode({'apiKey': key, 'format': 'json', 'pageSize': 50, 'sort': 'salePrice.asc',
            'show': 'sku,name,salePrice,onlineAvailability,url'})
        outcomes.append(collect(db, 'bestbuy', [p for p in PRODUCTS if p.get('bestbuy')],
            lambda p: json.loads(fetch(f"{BESTBUY_API}({p['bestbuy']})?{params}")),
            lambda p, data, at: bestbuy_quotes(p, data, at), sleep, 1))
    feed = os.getenv('PRICE_FEED_URL')
    if market is None and feed:
        try:
            if not feed.startswith('https://'):
                raise ValueError('Price feed must use HTTPS')
            data = json.loads(fetch(feed))
            count = import_feed(db, data)
            record_run(db, 'prices:feed', 'ok', f'{count} observations')
            outcomes.append({'source': 'feed', 'count': count})
        except Exception as exc:
            record_run(db, 'prices:feed', 'error', error_name(exc))
            outcomes.append({'source': 'feed', 'error': error_name(exc)})
    return outcomes


def import_feed(db, data):
    if not isinstance(data, dict) or not isinstance(data.get('observations'), list):
        raise ValueError('Expected an observations array')
    if len(data['observations']) > 10000:
        raise ValueError('Feed too large')
    if any(isinstance(row, dict) and row.get('source') == 'coupang' for row in data['observations']):
        raise ValueError('Coupang prices come only from the Coupang Partners API')
    return save_quotes(db, data['observations'])


NEWS_QUERIES = {
    'en': {'ram': ['(DDR5 OR DDR4) (RAM OR memory) (price OR supply OR shortage) when:7d',
                   '(DRAM OR HBM) (Samsung OR "SK hynix" OR Micron) (price OR supply) when:7d'],
           'gpu': ['(GeForce OR "RTX 50") (price OR availability OR stock) when:7d',
                   '("graphics card" OR GPU) NVIDIA price when:7d']},
    'ko': {'ram': ['(DDR5 OR DDR4) (램 OR 메모리) (가격 OR 공급 OR 품귀) when:7d',
                   '(D램 OR HBM) (삼성전자 OR SK하이닉스 OR 마이크론) (가격 OR 공급) when:7d'],
           'gpu': ['(지포스 OR "RTX 50" OR "RTX 5070" OR "RTX 5080" OR "RTX 5090") (가격 OR 공급 OR 출시) when:7d',
                   '(그래픽카드 OR 엔비디아) 가격 when:7d']}
}
NEWS_PER_QUERY = 15


def parse_news(raw, lang, category, at=None):
    at = at or now()
    items = []
    for item in ET.fromstring(raw).findall('./channel/item'):
        source = clean_text(item.findtext('source'))
        title = clean_text(item.findtext('title'))
        if source and title.endswith(' - ' + source):
            title = title[:-len(source)-3]
        link = item.findtext('link') or ''
        if not title or not safe_url(link):
            continue
        relevant = (r'\bDDR[45]\b|\bDRAM\b|\bHBM\d?\b|\bRAM\b|메모리|램|D램|디램' if category == 'ram'
                    else r'\bRTX\s*\d|GeForce|지포스|그래픽\s*카드|graphics card|\bGPU\b')
        if not re.search(relevant, title, re.I):
            continue
        try:
            date = email.utils.parsedate_to_datetime(item.findtext('pubDate')).astimezone(UTC)
        except (TypeError, ValueError, AttributeError):
            continue
        if not at - dt.timedelta(days=7) <= date <= at + dt.timedelta(minutes=10):
            continue
        uid = hashlib.sha256((lang + '|' + title.casefold()).encode()).hexdigest()[:24]
        items.append((uid, lang, category, title, link, source or 'Google News', stamp(date), stamp(at)))
    return sorted(items, key=lambda row: row[6], reverse=True)[:NEWS_PER_QUERY]


def update_news(db, force=False, langs=None):
    results = []
    for lang, categories in NEWS_QUERIES.items():
        if langs and lang not in langs:
            continue
        for category, queries in categories.items():
            job = f'news:{lang}:{category}'
            old = db.execute('SELECT * FROM runs WHERE job=?', (job,)).fetchone()
            if old and not force:
                # The daily job runs each morning; a run in the last 12 hours (e.g. a manual one the night
                # before) must not make the morning run skip. Failures retry after one hour.
                cooldown = 12 * 3600 if old['state'] == 'ok' else 3600
                if (now() - parse_time(old['attempted_at'])).total_seconds() < cooldown:
                    continue
            try:
                rows = []
                for query in ([queries] if isinstance(queries, str) else queries):
                    params = urllib.parse.urlencode({'q': query, 'hl': 'ko' if lang == 'ko' else 'en-US',
                        'gl': 'KR' if lang == 'ko' else 'US', 'ceid': 'KR:ko' if lang == 'ko' else 'US:en'})
                    rows += parse_news(fetch('https://news.google.com/rss/search?' + params), lang, category)
                with db:
                    db.executemany('INSERT OR IGNORE INTO news VALUES(?,?,?,?,?,?,?,?)', rows)
                    db.execute('DELETE FROM news WHERE published_at<?', (stamp(now()-dt.timedelta(days=30)),))
                record_run(db, job, 'ok', f'{len(rows)} headlines')
                results.append({'feed': job, 'count': len(rows)})
            except Exception as exc:
                record_run(db, job, 'error', error_name(exc))
                results.append({'feed': job, 'error': error_name(exc)})
    return results
