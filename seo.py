"""Search-engine content baked into each page: titles and descriptions with today's prices,
canonical and alternate links, Open Graph, JSON-LD, crawlable price rows and product pages."""
import datetime as dt
import html
import json
import re
import os
from pathlib import Path

GUIDES = json.loads((Path(__file__).resolve().parent / 'config/guides.json').read_text())

KST = dt.timezone(dt.timedelta(hours=9))
CATEGORY_NAMES = {'ko': {'ram': '메모리', 'gpu': '그래픽카드'}, 'en': {'ram': 'Memory', 'gpu': 'Graphics cards'},
                  'ja': {'ram': 'メモリ', 'gpu': 'グラフィックボード'}, 'de': {'ram': 'Arbeitsspeicher', 'gpu': 'Grafikkarten'}}
LANGS = ('ko', 'en', 'ja', 'de')
OG_LOCALE = {'ko': 'ko_KR', 'en': 'en_US', 'ja': 'ja_JP', 'de': 'de_DE'}


def won(value, lang, currency='KRW'):
    """A price as people write it: 790,970원 / ₩790,970, 79,800円 / ¥79,800, $1,234.56."""
    if value is None:
        return '—'
    if currency == 'USD':
        return f'${value:,.2f}'
    if currency == 'EUR':
        text = f'{value:,.2f}'
        return text.replace(',', ' ').replace('.', ',').replace(' ', '.') + ' €' if lang == 'de' else f'€{text}'
    amount = f'{round(value):,}'
    if currency == 'JPY':
        return f'{amount}円' if lang == 'ja' else f'¥{amount}'
    return f'{amount}원' if lang == 'ko' else f'₩{amount}'


def full_name(p):
    return f"{p['brand']} {p['name']} · {p['spec']}"


def name_of(p, lang):
    return (lang == 'ko' and p.get('shortKo')) or p['short']


PRIVACY = json.loads((Path(__file__).resolve().parent / 'config/privacy.json').read_text())


def privacy_html(lang):
    """The privacy policy body. config/privacy.json is our own text, with links written in as HTML."""
    doc = PRIVACY[lang]
    parts = [f'<p class="privacy-updated">{html.escape(doc["updated"])}</p>']
    for heading, paras in doc['sections']:
        parts.append(f'<h2>{html.escape(heading)}</h2>' + ''.join(f'<p>{p}</p>' for p in paras))
    return ''.join(parts)


def page_path(lang, page, product=None):
    if page == 'product':
        return f'/{lang}/{product}/'
    if page == 'guide':
        return f'/{lang}/guides/{product}/'
    return f'/{lang}/' if page == 'prices' else f'/{lang}/{page}/'


def best_offer(p):
    return next((o for o in p.get('offers', []) if not o.get('stale') and o.get('stock') != 'out_of_stock' and o.get('price')), None)


def when_text(stamp, lang):
    if not stamp:
        return ''
    at = dt.datetime.fromisoformat(stamp).astimezone(KST)
    if lang == 'ko':
        return f'{at.month}월 {at.day}일 {at.hour}시'
    if lang == 'ja':
        return f'{at.month}月{at.day}日 {at.hour}時'
    if lang == 'de':
        return f'{at.day}.{at.month}., {at.hour}:00 Uhr KST'
    return at.strftime('%b %-d, %H:00 KST')


def json_ld(data):
    # Inside <script type="application/ld+json">; escape "<" so text can never close the tag.
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def seo_context(lang, page, strings, products, base='', site='', product_id=None, currency='KRW', alt_langs=LANGS, news=None):
    """Extra template values. `products` are product views for the page's market, priced in `currency`."""
    absolute = lambda path: f'{site}{base}{path}'
    path = page_path(lang, page, product_id)
    # Only languages where this page exists (a product page exists only where it has a price).
    alt = {code: absolute(page_path(code, page, product_id)) for code in LANGS if code in alt_langs or code == lang}
    money = lambda value: won(value, lang, currency)
    # Products without a price in this market are not shown at all.
    products = [p for p in products if p.get('price') is not None or (page == 'product' and p['id'] == product_id)]
    by_id = {p['id']: p for p in products}
    priced = [p for p in products if p.get('price') is not None]
    title, desc = strings.get(f'{page}PageTitle', ''), strings.get(f'{page}PageDesc', '')
    graph = [{'@type': 'WebSite', '@id': absolute('/#website'), 'name': strings['brand'], 'url': absolute('/'),
              'inLanguage': lang, 'description': strings['seoPricesDescEmpty']}]
    extra = {'productHeading': '', 'productLead': '', 'productStatic': '', 'relatedLinks': '', 'productCategory': '',
             'prerenderRows': '', 'makerRows': '', 'productFacts': '', 'guideList': '', 'guideHtml': ''}

    if page == 'prices':
        title = strings['seoPricesTitle']
        lead = [p for p in priced if p['id'] in ('samsung-ddr5-32', 'rtx-5080', 'rtx-5070')]
        desc = strings['seoPricesDescEmpty']
        while lead:  # keep the description within what search results show (about 160 characters)
            desc = strings['seoPricesDesc'].format(prices=', '.join(f"{name_of(p, lang)} {money(p['price'])}" for p in lead))
            if len(desc) <= 160:
                break
            lead = lead[:-1]
        if len(desc) > 160:
            desc = strings['seoPricesDescEmpty']
        graph.append({'@type': 'ItemList', 'name': strings['pricesHeading'], 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'item': product_ld(p, lang, absolute, currency)}
            for i, p in enumerate(priced)]})
        extra['prerenderRows'] = ''.join(prerender_row(p, lang, base, strings, currency) for p in products)
        extra['makerRows'] = maker_rows(products, lang, base, strings, currency)

    if page == 'guides':
        extra['guideList'] = guide_list(lang, strings, base)

    if page == 'guide':
        title, desc = guide_meta(product_id, lang, strings)
        title = f'{title} | {strings["brand"]}'
        extra['guideHtml'] = guide_body(product_id, lang, strings, products, news, base, money)
        others = [s for s in guide_slugs() if s != product_id]
        extra['guideHtml'] += '{{AD}}'  # replaced with the ad slot by render_page
        extra['guideHtml'] += f'<h2>{html.escape(strings["guideMore"])}</h2><ul class="guide-more">' + ''.join(
            f'<li><a href="{html.escape(base + page_path(lang, "guide", s))}">{html.escape(guide_meta(s, lang, strings)[0])}</a></li>' for s in others) + '</ul>'
        modified = (GUIDES.get(product_id) or {}).get('updated') or dt.date.today().isoformat()
        graph.append({'@type': 'Article', 'headline': guide_meta(product_id, lang, strings)[0], 'description': desc, 'inLanguage': lang,
                      'dateModified': modified, 'datePublished': (GUIDES.get(product_id) or {}).get('updated') or f'{product_id[7:]}-01',
                      'author': {'@type': 'Organization', 'name': strings['brand']}, 'publisher': {'@type': 'Organization', 'name': strings['brand']},
                      'mainEntityOfPage': absolute(path), 'image': absolute('/og.png')})

    if page == 'product':
        p = by_id[product_id]
        offer = best_offer(p)
        name, price = name_of(p, lang), money(p.get('price'))
        fmt = {'name': name, 'price': price, 'full': full_name(p), 'shops': (offer or {}).get('shops') or '—',
               'when': when_text(p.get('observed_at'), lang)}
        has_price = p.get('price') is not None
        title = strings['seoProductTitle' if has_price else 'seoProductTitleEmpty'].format(**fmt)
        desc = strings['seoProductDesc' if has_price else 'seoProductDescEmpty'].format(**fmt)
        extra['productHeading'] = strings['productHeading'].format(**fmt)
        extra['productLead'] = strings['productLead' if has_price else 'productLeadEmpty'].format(**fmt)
        extra['productCategory'] = CATEGORY_NAMES[lang][p['category']]
        extra['productStatic'] = product_static(p, lang, strings, currency)
        extra['productFacts'] = product_facts(p, lang, strings, money) if has_price else ''
        extra['relatedLinks'] = ''.join(
            f'<li><a href="{html.escape(base)}{page_path(lang, "product", q["id"])}"><span>{html.escape(name_of(q, lang))}</span>'
            f'<b>{html.escape(money(q.get("price")))}</b></a></li>' for q in products if q['id'] != product_id)
        graph.append(product_ld(p, lang, absolute, currency))
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': strings['navPrices'], 'item': absolute(f'/{lang}/')},
            {'@type': 'ListItem', 'position': 2, 'name': name, 'item': absolute(path)}]})

    head = []
    for name, env in (('google-site-verification', 'GOOGLE_SITE_VERIFICATION'), ('naver-site-verification', 'NAVER_SITE_VERIFICATION')):
        if os.getenv(env):
            head.append(f'<meta name="{name}" content="{html.escape(os.environ[env])}">')
    return extra | {
        'pageTitle': title, 'pageDesc': desc, 'canonical': alt[lang],
        'alternates': '\n  '.join([f'<link rel="alternate" hreflang="{code}" href="{html.escape(url)}">' for code, url in alt.items()]
                                    + [f'<link rel="alternate" hreflang="x-default" href="{html.escape(absolute("/"))}">']),
        'ogImage': absolute('/og.png'), 'ogLocale': OG_LOCALE[lang],
        'headExtra': '\n  '.join(head), 'jsonld': json_ld({'@context': 'https://schema.org', '@graph': graph}),
    }


def product_ld(p, lang, absolute, currency='KRW'):
    offers = [o for o in p.get('offers', []) if not o.get('stale') and o.get('price')]
    data = {'@type': 'Product', 'name': name_of(p, lang) if p['category'] == 'ram' else f"{p['brand']} {p['name']}", 'description': full_name(p),
            'brand': {'@type': 'Brand', 'name': p['brand']}, 'category': CATEGORY_NAMES[lang][p['category']],
            'url': absolute(page_path(lang, 'product', p['id'])), 'image': absolute('/og.png')}
    if p.get('price') is not None:
        exact = (lambda v: round(v, 2)) if currency in ('USD', 'EUR') else round
        data['offers'] = {'@type': 'AggregateOffer', 'priceCurrency': currency, 'lowPrice': exact(p['price']),
                          'highPrice': exact(max(o['amount'] for o in offers)) if offers else exact(p['price']),
                          'offerCount': len(offers) or 1, 'availability': 'https://schema.org/InStock'}
    return data


def prerender_row(p, lang, base, strings, currency='KRW'):
    """Plain rows crawlers can read; app.js replaces them with the interactive table."""
    href = html.escape(f'{base}{page_path(lang, "product", p["id"])}')
    return (f'<tr class="row"><td><div class="prod"><div><a class="prod-name" href="{href}">{html.escape(name_of(p, lang))}</a>'
            f'<span class="prod-spec">{html.escape(full_name(p))}</span></div></div></td>'
            f'<td class="num"><span class="price">{html.escape(won(p.get("price"), lang, currency))}</span></td>'
            '<td class="num">—</td><td class="num hide-sm">—</td><td class="hide-md"></td><td class="hide-sm"></td>'
            f'<td class="num hide-md">{(best_offer(p) or {}).get("shops") or "—"}</td>'
            + '</tr>')


MAKERS = ('samsung', 'hynix', 'micron', 'klevv', 'corsair', 'gskill')


def maker_rows(products, lang, base, strings, currency='KRW'):
    """DDR5 memory by maker and capacity, for crawlers; app.js re-renders it with live data."""
    ram = [p for p in products if p['category'] == 'ram' and p.get('generation') == 'DDR5' and p.get('maker')]
    rows = []
    for maker in MAKERS:
        cells = []
        for size in (16, 32, 64):
            p = next((q for q in ram if q['maker'] == maker and q['capacity'] == size), None)
            if not p:
                cells.append('<td class="num"><span class="muted">—</span></td>')
                continue
            href = html.escape(f'{base}{page_path(lang, "product", p["id"])}')
            cells.append(f'<td class="num"><a class="mk-cell" href="{href}"><span class="price">{html.escape(won(p.get("price"), lang, currency))}</span></a></td>')
        if any('mk-cell' in c for c in cells):
            rows.append(f'<tr><th scope="row">{html.escape(strings["maker_" + maker])}</th>{"".join(cells)}</tr>')
    return ''.join(rows)


def seller_row(mall, kind, name, meta, price, href, cta, sponsored):
    rel = ('sponsored ' if sponsored else '') + 'noopener noreferrer'
    href = html.escape(href)
    return (f'<li class="seller"><span class="mall {kind}">{html.escape(mall)}</span>'
            f'<div class="seller-info"><div><a class="seller-name" href="{href}" target="_blank" rel="{rel}">{html.escape(name)}</a>'
            f'<span class="seller-meta">{html.escape(meta)}</span></div></div>'
            f'<div class="seller-price">{price}</div><a class="go {kind}" href="{href}" target="_blank" rel="{rel}">{html.escape(cta)}</a></li>')


def product_facts(p, lang, strings, money):
    """A plain-text price summary under the chart: real numbers a reader (or a search engine) can quote."""
    best = best_offer(p) or {}
    source = strings[SOURCES.get(best.get('source'), ('srcDanawa',))[0]]
    low, high = p.get('low30') or p['price'], p.get('high30') or p['price']
    change = p.get('change7')
    rows = [(strings['factToday'], money(p['price'])), (strings['factLow30'], money(low)), (strings['factHigh30'], money(high)),
            (strings['factChange7'], '—' if change is None else f'{change:+.1f}%'), (strings['factSellers'], str(best.get('shops') or '—')),
            (strings['factSpec'], full_name(p)), (strings['factSource'], source)]
    items = ''.join(f'<div><dt>{html.escape(k)}</dt><dd>{html.escape(v)}</dd></div>' for k, v in rows)
    text = strings['factSummary'].format(name=name_of(p, lang), low=money(low), high=money(high), source=source)
    return (f'<section class="panel facts"><h2>{html.escape(strings["factsTitle"].format(name=name_of(p, lang)))}</h2>'
            f'<dl class="facts-list">{items}</dl><p class="facts-text">{html.escape(text)}</p></section>')


SOURCES = {'danawa': ('srcDanawa', 'danawaGo'), 'kakaku': ('srcKakaku', 'kakakuGo')}


def product_static(p, lang, strings, currency='KRW'):
    """Where to buy, for crawlers and no-JS readers: on Korean prices Coupang first, then the lowest price
    from the comparison site (Danawa in Korea, Kakaku.com in Japan). app.js swaps in the chart and live
    detail. A Coupang price only ever comes from the Partners API."""
    if currency != 'KRW':
        p = {k: v for k, v in p.items() if k not in ('coupang', 'coupangOffer')}
    rows, offer = [], p.get('coupangOffer')
    if p.get('coupang') and offer:
        checked = strings['coupangChecked'].format(time=when_text(offer['observed_at'], lang))
        meta = f'{strings["coupangRocket"]} · {checked}' if offer.get('rocket') else checked
        rows.append(seller_row(strings['coupangShort'], 'coupang', offer['name'], meta,
                               f'<span class="price">{html.escape(won(offer["price"], lang, currency))}</span>',
                               offer['url'], strings['coupangGo'], True))
    elif p.get('coupang'):
        link = html.escape(p['coupang'])
        rows.append(seller_row(strings['coupangShort'], 'coupang', strings['coupangLine'].format(name=name_of(p, lang)),
                               strings['coupangMeta'],
                               f'<a class="price-link" href="{link}" target="_blank" rel="sponsored noopener noreferrer">'
                               f'{html.escape(strings["coupangPriceCta"])}</a>', p['coupang'], strings['coupangGo'], True))
    best = best_offer(p)
    if best and best.get('url'):
        label, go = SOURCES.get(best.get('source'), ('srcDanawa', 'danawaGo'))
        meta = strings['danawaMeta'].format(shops=best.get('shops') or '—', time=when_text(best['observed_at'], lang))
        rows.append(seller_row(strings[label], best.get('source') or 'danawa', best['title'], meta,
                               f'<span class="price">{html.escape(won(best.get("amount"), lang, currency))}</span>',
                               best['url'], strings[go], False))
    if not rows:
        return ''
    note = f'<p class="buy-note">{html.escape(strings["coupangDisclosure"])}</p>' if p.get('coupang') else ''
    return f'<h3 class="d-section">{html.escape(strings["buyTitle"])}</h3><ul class="sellers">{"".join(rows)}</ul>{note}'


def sitemap(site, base, products, langs=LANGS, lastmod=None, available=None):
    lastmod = lastmod or dt.date.today().isoformat()
    pages = ([('prices', None), ('news', None), ('about', None), ('guides', None), ('privacy', None)] + [('guide', s) for s in guide_slugs()]
             + [('product', p['id']) for p in products])
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for page, pid in pages:
        # A product page exists only in the languages whose market has a price for it.
        here = [lang for lang in langs if page != 'product' or available is None or pid in available.get(lang, ())]
        for lang in here:
            out.append(f'  <url><loc>{site}{base}{page_path(lang, page, pid)}</loc><lastmod>{lastmod}</lastmod>'
                       f'<changefreq>daily</changefreq>')
            out += [f'    <xhtml:link rel="alternate" hreflang="{alt}" href="{site}{base}{page_path(alt, page, pid)}"/>' for alt in here]
            out.append('  </url>')
    out.append('</urlset>')
    return '\n'.join(out) + '\n'


MONTHS_EN = ('January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December')
MONTHS_DE = ('Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember')


def report_slug(at=None):
    at = (at or dt.datetime.now(KST)).astimezone(KST)
    return f'report-{at:%Y-%m}'


def guide_slugs(at=None):
    return list(GUIDES) + [report_slug(at)]


def guide_meta(slug, lang, strings):
    """Title and description of a guide (the monthly report's come from its year and month)."""
    if slug.startswith('report-'):
        year, month = slug.split('-')[1:]
        vars = {'year': year, 'month': int(month), 'monthName': (MONTHS_DE if lang == 'de' else MONTHS_EN)[int(month) - 1]}
        return strings['reportTitle'].format(**vars), strings['reportDesc'].format(**vars)
    g = GUIDES[slug][lang]
    return g['title'], g['desc']


def guide_list(lang, strings, base):
    rows = []
    for slug in guide_slugs():
        title, desc = guide_meta(slug, lang, strings)
        href = html.escape(f'{base}{page_path(lang, "guide", slug)}')
        rows.append(f'<li class="guide-card"><a href="{href}"><h2>{html.escape(title)}</h2><p>{html.escape(desc)}</p>'
                    f'<span class="guide-read">{html.escape(strings["guideRead"])} →</span></a></li>')
    return ''.join(rows)


def price_table(products, lang, strings, base, money, cols):
    """A small table of products with links; `cols` picks the columns."""
    head = {'today': strings['colToday'], 'low30': strings['col30Low'], 'high30': strings['col30High'],
            'mlow': strings['colMonthLow'], 'mhigh': strings['colMonthHigh'], 'mchange': strings['colMonthChange']}
    rows = []
    for p in products:
        href = html.escape(f'{base}{page_path(lang, "product", p["id"])}')
        cells = []
        for c in cols:
            v = p.get({'today': 'price'}.get(c, c))
            cells.append(f'<td class="num">{html.escape("—" if v is None else (f"{v:+.1f}%" if c == "mchange" else money(v)))}</td>')
        rows.append(f'<tr><td><a href="{href}">{html.escape(name_of(p, lang))}</a></td>{"".join(cells)}</tr>')
    th = ''.join(f'<th class="num">{html.escape(head[c])}</th>' for c in cols)
    return f'<div class="table-wrap"><table class="grid guide-table"><thead><tr><th>{html.escape(strings["colProduct"])}</th>{th}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def month_stats(p, slug):
    """Low, high and change within the report's month, from the daily history (real records only)."""
    month = slug.removeprefix('report-')
    pts = [x for x in p.get('history', []) if x['at'][:7] == month and x.get('price') is not None]
    if not pts:
        return None
    prices = [x['price'] for x in pts]
    change = (prices[-1] / prices[0] - 1) * 100 if len(prices) > 1 else None
    return p | {'mlow': min(prices), 'mhigh': max(prices), 'mchange': change, 'first': pts[0]['at'], 'last': pts[-1]['at']}


def guide_body(slug, lang, strings, products, news, base, money):
    """The article: written text plus blocks filled from today's real data."""
    priced = [p for p in products if p.get('price') is not None]
    by_id = {p['id']: p for p in priced}
    out = []
    if slug.startswith('report-'):
        title, _ = guide_meta(slug, lang, strings)
        rows = [r for r in (month_stats(p, slug) for p in priced) if r]
        out.append(f'<h1>{html.escape(title)}</h1>')
        if rows:
            first = min(r['first'] for r in rows); last = max(r['last'] for r in rows)
            out.append(f'<p class="guide-lead">{html.escape(strings["reportLead"].format(first=when_text(first, lang), last=when_text(last, lang)))}</p>')
            if first[:10] == last[:10]:
                out.append(f'<p class="guide-note">{html.escape(strings["reportFew"])}</p>')
            for cat in ('ram', 'gpu'):
                part = [r for r in rows if r['category'] == cat]
                if part:
                    out.append(f'<h2>{html.escape(CATEGORY_NAMES[lang][cat])}</h2>')
                    out.append(price_table(part, lang, strings, base, money, ('today', 'mlow', 'mhigh', 'mchange')))
        return ''.join(out)
    g = GUIDES[slug][lang]
    out.append(f'<h1>{html.escape(g["title"])}</h1>')
    out.append(f'<p class="guide-meta">{html.escape(strings["guideUpdated"].format(date=GUIDES[slug]["updated"]))}</p>')
    out.append(f'<p class="guide-lead">{html.escape(g["lead"])}</p>')
    for sec in g['sections']:
        out.append(f'<h2>{html.escape(sec["h"])}</h2>' + ''.join(f'<p>{html.escape(x)}</p>' for x in sec['p']))
    if slug == 'ddr5-vs-ddr4':
        a, b = by_id.get('samsung-ddr4-16'), by_id.get('samsung-ddr5-16')
        pair = [x for x in (a, b) if x]
        if pair:
            out.append(f'<h2>{html.escape(strings["guideCompare"])}</h2>')
            if a and b:
                out.append(f'<p>{html.escape(strings["compareSentence"].format(a=name_of(a, lang), pa=money(a["price"]), b=name_of(b, lang), pb=money(b["price"])))}</p>')
            out.append(price_table(pair, lang, strings, base, money, ('today', 'low30', 'high30')))
    fill = g.get('fill', {})
    if slug == 'rtx-5090-worth' and by_id.get('rtx-5090'):
        big = by_id['rtx-5090']['price']
        items = []
        for pid in ('rtx-5060', 'rtx-5070', 'samsung-ddr5-32', 'samsung-ddr5-16', 'crucial-ddr5-64'):
            q = by_id.get(pid)
            if q and q['price']:
                items.append(fill['item'].format(name=name_of(q, lang), n=int(big // q['price']), each=money(q['price'])))
        out.append(f'<h2>{html.escape(fill["h"].format(price=money(big)))}</h2><ul class="guide-facts">'
                   + ''.join(f'<li>{html.escape(x)}</li>' for x in items) + '</ul>')
    if slug == 'rtx-50-lineup':
        gpus = sorted((q for q in priced if q['category'] == 'gpu'), key=lambda q: q['price'] / q['capacity'])
        if gpus:
            rows = ''.join(f'<tr><td><a href="{html.escape(base + page_path(lang, "product", q["id"]))}">{html.escape(name_of(q, lang))}</a></td>'
                           f'<td class="num">{q["capacity"]}GB</td><td class="num">{html.escape(money(q["price"]))}</td>'
                           f'<td class="num">{html.escape(money(q["price"] / q["capacity"]))}</td></tr>' for q in gpus)
            out.append(f'<h2>{html.escape(fill["h"])}</h2><div class="table-wrap"><table class="grid guide-table"><thead><tr>'
                       f'<th>{html.escape(strings["colProduct"])}</th><th class="num">{html.escape(fill["vram"])}</th>'
                       f'<th class="num">{html.escape(strings["colToday"])}</th><th class="num">{html.escape(fill["perGb"])}</th>'
                       f'</tr></thead><tbody>{rows}</tbody></table></div>')
    ddr5 = sorted((q for q in priced if q['category'] == 'ram' and q.get('generation') == 'DDR5'), key=lambda q: q['price'] / q['capacity'])
    if slug == 'ram-price-per-gb' and ddr5:
        rows = ''.join(f'<tr><td>{i + 1}</td><td><a href="{html.escape(base + page_path(lang, "product", q["id"]))}">{html.escape(name_of(q, lang))}</a></td>'
                       f'<td class="num">{q["capacity"]}GB</td><td class="num">{html.escape(money(q["price"]))}</td>'
                       f'<td class="num">{html.escape(money(q["price"] / q["capacity"]))}</td></tr>' for i, q in enumerate(ddr5))
        out.append(f'<h2>{html.escape(fill["h"])}</h2><div class="table-wrap"><table class="grid guide-table"><thead><tr><th>#</th>'
                   f'<th>{html.escape(strings["colProduct"])}</th><th class="num">{html.escape(fill["cap"])}</th>'
                   f'<th class="num">{html.escape(strings["colToday"])}</th><th class="num">{html.escape(fill["perGb"])}</th>'
                   f'</tr></thead><tbody>{rows}</tbody></table></div>')
    if slug == 'chrome-tabs-ram' and ddr5:
        cheap = ddr5[0]
        per = cheap['price'] / cheap['capacity']
        gb = round(87 * 0.15, 1)
        out.append(f'<h2>{html.escape(fill["h"])}</h2><ul class="guide-facts">'
                   f'<li><b>{html.escape(fill["tab"])}</b>: {html.escape(money(per * 0.15))}</li>'
                   f'<li><b>{html.escape(fill["tabs"].format(gb=gb))}</b>: {html.escape(money(per * gb))}</li></ul>'
                   f'<p class="guide-note">{html.escape(fill["basis"].format(per=money(per), name=name_of(cheap, lang)))}</p>')
    if slug in ('why-ram-prices-rise', 'ram-altman'):
        ram = [p for p in priced if p['category'] == 'ram' and p.get('generation') == 'DDR5']
        if ram:
            out.append(f'<h2>{html.escape(strings["guidePricesNow"])}</h2>')
            out.append(price_table(ram, lang, strings, base, money, ('today', 'low30', 'high30')))
        items = [n for n in (news or []) if n.get('category') == 'ram' and str(n.get('url', '')).startswith('http')]
        if slug == 'ram-altman':  # headlines about him first
            items.sort(key=lambda n: not re.search(r'altman|올트먼|올트만|アルトマン', n['title'], re.I))
        items = items[:6]
        if items:
            out.append(f'<h2>{html.escape(strings["guideRelatedNews"])}</h2><ul class="guide-news">' + ''.join(
                f'<li><a href="{html.escape(n["url"])}" target="_blank" rel="noopener noreferrer">{html.escape(n["title"])}</a>'
                f' <span>{html.escape(n.get("publisher", ""))} · {html.escape(when_text(n["published_at"], lang))}</span></li>' for n in items) + '</ul>')
    sources = GUIDES[slug].get('sources')
    if sources:
        out.append(f'<h2>{html.escape(strings["guideSources"])}</h2><ul class="guide-news">' + ''.join(
            f'<li><a href="{html.escape(s["url"])}" target="_blank" rel="noopener noreferrer">{html.escape(s["name"])}</a></li>'
            for s in sources) + '</ul>')
    return ''.join(out)


def news_rows(news, lang, strings):
    """Latest headlines as plain HTML for crawlers that do not run JavaScript; app.js re-renders them."""
    items = []
    for n in (news or [])[:20]:
        if not str(n.get('url', '')).startswith(('https://', 'http://')):
            continue
        at = dt.datetime.fromisoformat(n['published_at']).astimezone(KST)
        tag = strings['catRamShort'] if n.get('category') == 'ram' else strings['catGpuShort']
        items.append(f'<li class="news-item"><time class="news-time" datetime="{html.escape(n["published_at"])}">{at:%m-%d %H:%M}</time>'
                     f'<div class="news-body"><a class="news-title" href="{html.escape(n["url"])}" target="_blank" rel="noopener noreferrer">'
                     f'{html.escape(n["title"])}</a><div class="news-meta"><span class="tag {html.escape(n.get("category", ""))}">{html.escape(tag)}</span>'
                     f'<span>{html.escape(n.get("publisher", ""))}</span></div></div></li>')
    return f'<section class="news-day"><ol class="news-items">{"".join(items)}</ol></section>' if items else ''


def llms_txt(site, base, by_lang):
    """/llms.txt: a plain summary for AI search and answer engines, with today's prices per market."""
    lines = ['# Quite Terrible', '',
             '> Daily RAM (DDR4/DDR5) and NVIDIA GeForce RTX graphics card prices in Korea and Japan, with price history.',
             '> Korean prices are the lowest new-item prices on Danawa; Japanese prices come from Kakaku.com. Checked every morning at 09:00 KST/JST.',
             '', '## Pages', '',
             f'- [Korean prices (원)]({site}{base}/ko/): 램 가격·그래픽카드 가격 오늘 시세',
             f'- [Japanese prices (円)]({site}{base}/ja/): メモリ価格・グラボ価格 今日の相場',
             f'- [English]({site}{base}/en/): RAM & GPU prices today',
             f'- [German]({site}{base}/de/): RAM- und Grafikkarten-Preise heute',
             f'- [About]({site}{base}/en/about/): why this site exists', '', '## Guides', '']
    strings_en = {'reportTitle': 'RAM & GPU prices: {monthName} {year} report', 'reportDesc': ''}
    lines += [f"- [{guide_meta(s, 'en', strings_en)[0]}]({site}{base}{page_path('en', 'guide', s)})" for s in guide_slugs()]
    lines.append('')
    for lang, title in (('ko', 'Korea, KRW'), ('ja', 'Japan, JPY')):
        payload = by_lang[lang]
        priced = [p for p in payload['products'] if p.get('price') is not None]
        if not priced:
            continue
        lines += [f'## Today\'s lowest prices ({title})', '']
        lines += [f"- [{name_of(p, lang)}]({site}{base}{page_path(lang, 'product', p['id'])}): {won(p['price'], 'en', payload['currency'])}"
                  for p in priced]
        lines.append('')
    return '\n'.join(lines)


def robots(site, base):
    return f'User-agent: *\nAllow: /\n\nSitemap: {site}{base}/sitemap.xml\n'
