"""Search-engine content baked into each page: titles and descriptions with today's prices,
canonical and alternate links, Open Graph, JSON-LD, crawlable price rows and product pages."""
import datetime as dt
import html
import json
import os

KST = dt.timezone(dt.timedelta(hours=9))
CATEGORY_NAMES = {'ko': {'ram': '메모리', 'gpu': '그래픽카드'}, 'en': {'ram': 'Memory', 'gpu': 'Graphics cards'}}


def won(value, lang):
    if value is None:
        return '—'
    amount = f'{round(value):,}'
    return f'{amount}원' if lang == 'ko' else f'₩{amount}'


def full_name(p):
    return f"{p['brand']} {p['name']} · {p['spec']}"


def name_of(p, lang):
    return (lang == 'ko' and p.get('shortKo')) or p['short']


def page_path(lang, page, product=None):
    if page == 'product':
        return f'/{lang}/{product}/'
    return f'/{lang}/' if page == 'prices' else f'/{lang}/{page}/'


def best_offer(p):
    return next((o for o in p.get('offers', []) if not o.get('stale') and o.get('stock') != 'out_of_stock' and o.get('price')), None)


def when_text(stamp, lang):
    if not stamp:
        return ''
    at = dt.datetime.fromisoformat(stamp).astimezone(KST)
    return f'{at.month}월 {at.day}일 {at.hour}시' if lang == 'ko' else at.strftime('%b %-d, %H:00 KST')


def json_ld(data):
    # Inside <script type="application/ld+json">; escape "<" so text can never close the tag.
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def seo_context(lang, page, strings, products, base='', site='', product_id=None):
    """Extra template values. `products` are product views for the Korean market (may be empty)."""
    absolute = lambda path: f'{site}{base}{path}'
    path = page_path(lang, page, product_id)
    other = page_path('en' if lang == 'ko' else 'ko', page, product_id)
    alt = {lang: absolute(path), ('en' if lang == 'ko' else 'ko'): absolute(other)}
    by_id = {p['id']: p for p in products}
    priced = [p for p in products if p.get('price') is not None]
    title, desc = strings.get(f'{page}PageTitle', ''), strings.get(f'{page}PageDesc', '')
    graph = [{'@type': 'WebSite', '@id': absolute('/#website'), 'name': strings['brand'], 'url': absolute('/'),
              'inLanguage': lang, 'description': strings['seoPricesDescEmpty']}]
    extra = {'productHeading': '', 'productLead': '', 'productStatic': '', 'relatedLinks': '', 'productCategory': '',
             'prerenderRows': '', 'makerRows': ''}

    if page == 'prices':
        title = strings['seoPricesTitle']
        lead = [p for p in priced if p['id'] in ('samsung-ddr5-32', 'samsung-ddr5-16', 'rtx-5080', 'rtx-5070', 'rtx-5090')]
        desc = (strings['seoPricesDesc'].format(prices=', '.join(f"{name_of(p, lang)} {won(p['price'], lang)}" for p in lead))
                if lead else strings['seoPricesDescEmpty'])
        graph.append({'@type': 'ItemList', 'name': strings['pricesHeading'], 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'item': product_ld(p, lang, absolute)}
            for i, p in enumerate(priced)]})
        extra['prerenderRows'] = ''.join(prerender_row(p, lang, base, strings) for p in products)
        extra['makerRows'] = maker_rows(products, lang, base, strings)

    if page == 'product':
        p = by_id[product_id]
        offer = best_offer(p)
        name, price = name_of(p, lang), won(p.get('price'), lang)
        fmt = {'name': name, 'price': price, 'full': full_name(p), 'shops': (offer or {}).get('shops') or '—',
               'when': when_text(p.get('observed_at'), lang)}
        has_price = p.get('price') is not None
        title = strings['seoProductTitle' if has_price else 'seoProductTitleEmpty'].format(**fmt)
        desc = strings['seoProductDesc' if has_price else 'seoProductDescEmpty'].format(**fmt)
        extra['productHeading'] = strings['productHeading'].format(**fmt)
        extra['productLead'] = strings['productLead' if has_price else 'productLeadEmpty'].format(**fmt)
        extra['productCategory'] = CATEGORY_NAMES[lang][p['category']]
        extra['productStatic'] = product_static(p, lang, strings)
        extra['relatedLinks'] = ''.join(
            f'<li><a href="{html.escape(base)}{page_path(lang, "product", q["id"])}"><span>{html.escape(name_of(q, lang))}</span>'
            f'<b>{html.escape(won(q.get("price"), lang))}</b></a></li>' for q in products if q['id'] != product_id)
        graph.append(product_ld(p, lang, absolute))
        graph.append({'@type': 'BreadcrumbList', 'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': strings['navPrices'], 'item': absolute(f'/{lang}/')},
            {'@type': 'ListItem', 'position': 2, 'name': name, 'item': absolute(path)}]})

    head = []
    for name, env in (('google-site-verification', 'GOOGLE_SITE_VERIFICATION'), ('naver-site-verification', 'NAVER_SITE_VERIFICATION')):
        if os.getenv(env):
            head.append(f'<meta name="{name}" content="{html.escape(os.environ[env])}">')
    return extra | {
        'pageTitle': title, 'pageDesc': desc, 'canonical': alt[lang], 'altKo': alt['ko'], 'altEn': alt['en'],
        'altDefault': absolute('/'), 'ogImage': absolute('/og.png'), 'ogLocale': 'ko_KR' if lang == 'ko' else 'en_US',
        'headExtra': '\n  '.join(head), 'jsonld': json_ld({'@context': 'https://schema.org', '@graph': graph}),
    }


def product_ld(p, lang, absolute):
    offers = [o for o in p.get('offers', []) if not o.get('stale') and o.get('price')]
    data = {'@type': 'Product', 'name': name_of(p, lang) if p['category'] == 'ram' else f"{p['brand']} {p['name']}", 'description': full_name(p),
            'brand': {'@type': 'Brand', 'name': p['brand']}, 'category': CATEGORY_NAMES[lang][p['category']],
            'url': absolute(page_path(lang, 'product', p['id'])), 'image': absolute('/og.png')}
    if p.get('price') is not None:
        data['offers'] = {'@type': 'AggregateOffer', 'priceCurrency': 'KRW', 'lowPrice': round(p['price']),
                          'highPrice': round(max(o['amount'] for o in offers)) if offers else round(p['price']),
                          'offerCount': len(offers) or 1, 'availability': 'https://schema.org/InStock'}
    return data


def prerender_row(p, lang, base, strings):
    """Plain rows crawlers can read; app.js replaces them with the interactive table."""
    href = html.escape(f'{base}{page_path(lang, "product", p["id"])}')
    return (f'<tr class="row"><td><div class="prod"><div><a class="prod-name" href="{href}">{html.escape(name_of(p, lang))}</a>'
            f'<span class="prod-spec">{html.escape(full_name(p))}</span></div></div></td>'
            f'<td class="num"><span class="price">{html.escape(won(p.get("price"), lang))}</span></td>'
            '<td class="num">—</td><td class="num hide-sm">—</td><td class="hide-md"></td><td class="hide-sm"></td>'
            f'<td class="num hide-md">{(best_offer(p) or {}).get("shops") or "—"}</td>'
            + '</tr>')


MAKERS = ('samsung', 'hynix', 'micron', 'klevv', 'corsair', 'gskill')


def maker_rows(products, lang, base, strings):
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
            cells.append(f'<td class="num"><a class="mk-cell" href="{href}"><span class="price">{html.escape(won(p.get("price"), lang))}</span></a></td>')
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


def product_static(p, lang, strings):
    """Where to buy, for crawlers and no-JS readers: Coupang first, then the lowest Danawa price.
    app.js swaps in the chart and live detail. A Coupang price only ever comes from the Partners API."""
    rows, offer = [], p.get('coupangOffer')
    if p.get('coupang') and offer:
        checked = strings['coupangChecked'].format(time=when_text(offer['observed_at'], lang))
        meta = f'{strings["coupangRocket"]} · {checked}' if offer.get('rocket') else checked
        rows.append(seller_row(strings['coupangShort'], 'coupang', offer['name'], meta,
                               f'<span class="price">{html.escape(won(offer["price"], lang))}</span>',
                               offer['url'], strings['coupangGo'], True))
    elif p.get('coupang'):
        link = html.escape(p['coupang'])
        rows.append(seller_row(strings['coupangShort'], 'coupang', strings['coupangLine'].format(name=name_of(p, lang)),
                               strings['coupangMeta'],
                               f'<a class="price-link" href="{link}" target="_blank" rel="sponsored noopener noreferrer">'
                               f'{html.escape(strings["coupangPriceCta"])}</a>', p['coupang'], strings['coupangGo'], True))
    best = best_offer(p)
    if best and best.get('url'):
        meta = strings['danawaMeta'].format(shops=best.get('shops') or '—', time=when_text(best['observed_at'], lang))
        rows.append(seller_row(strings['srcDanawa'], 'danawa', best['title'], meta,
                               f'<span class="price">{html.escape(won(best.get("amount"), lang))}</span>',
                               best['url'], strings['danawaGo'], False))
    if not rows:
        return ''
    note = f'<p class="buy-note">{html.escape(strings["coupangDisclosure"])}</p>' if p.get('coupang') else ''
    return f'<h3 class="d-section">{html.escape(strings["buyTitle"])}</h3><ul class="sellers">{"".join(rows)}</ul>{note}'


def sitemap(site, base, products, langs=('ko', 'en'), lastmod=None):
    lastmod = lastmod or dt.date.today().isoformat()
    pages = [('prices', None), ('news', None), ('about', None)] + [('product', p['id']) for p in products]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">']
    for page, pid in pages:
        for lang in langs:
            out.append(f'  <url><loc>{site}{base}{page_path(lang, page, pid)}</loc><lastmod>{lastmod}</lastmod>'
                       f'<changefreq>daily</changefreq>')
            out += [f'    <xhtml:link rel="alternate" hreflang="{alt}" href="{site}{base}{page_path(alt, page, pid)}"/>' for alt in langs]
            out.append('  </url>')
    out.append('</urlset>')
    return '\n'.join(out) + '\n'


def robots(site, base):
    return f'User-agent: *\nAllow: /\n\nSitemap: {site}{base}/sitemap.xml\n'
