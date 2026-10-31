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
             'prerenderRows': ''}

    if page == 'prices':
        title = strings['seoPricesTitle']
        lead = [p for p in priced if p['id'] in ('samsung-ddr5-32', 'samsung-ddr5-16', 'rtx-5080', 'rtx-5070', 'rtx-5090')]
        desc = (strings['seoPricesDesc'].format(prices=', '.join(f"{p['short']} {won(p['price'], lang)}" for p in lead))
                if lead else strings['seoPricesDescEmpty'])
        graph.append({'@type': 'ItemList', 'name': strings['pricesHeading'], 'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'item': product_ld(p, lang, absolute)}
            for i, p in enumerate(priced)]})
        extra['prerenderRows'] = ''.join(prerender_row(p, lang, base, strings) for p in products)

    if page == 'product':
        p = by_id[product_id]
        offer = best_offer(p)
        name, price = p['short'], won(p.get('price'), lang)
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
            f'<li><a href="{html.escape(base)}{page_path(lang, "product", q["id"])}"><span>{html.escape(q["short"])}</span>'
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
    data = {'@type': 'Product', 'name': f"{p['brand']} {p['name']} {p['short']}".strip(), 'description': full_name(p),
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
    return (f'<tr class="row"><td><div class="prod"><div><a class="prod-name" href="{href}">{html.escape(p["short"])}</a>'
            f'<span class="prod-spec">{html.escape(full_name(p))}</span></div></div></td>'
            f'<td class="num"><span class="price">{html.escape(won(p.get("price"), lang))}</span></td>'
            '<td class="num">—</td><td class="num hide-sm">—</td><td class="hide-md"></td><td class="hide-sm"></td>'
            f'<td class="num hide-md">{(best_offer(p) or {}).get("shops") or "—"}</td>'
            + '</tr>')


def product_static(p, lang, strings):
    """Model list for crawlers and no-JS readers; app.js swaps in the chart and live detail."""
    rows = ''.join(
        f'<tr><td><span class="offer-name">{html.escape(o["merchant"])}</span>'
        f'<span class="offer-meta">{html.escape(strings["srcDanawa"])} · {o.get("shops") or "—"}</span></td>'
        f'<td class="num"><span class="price">{html.escape(won(o.get("amount"), lang))}</span></td>'
        f'<td class="num"><a class="buy secondary" href="{html.escape(o["url"])}" rel="noopener noreferrer" target="_blank">{html.escape(strings["visitSeller"])}</a></td></tr>'
        for o in p.get('offers', [])[:3] if o.get('url'))
    coupang = ''
    if p.get('coupang'):
        frame = (f'<iframe class="coupang-frame" src="{html.escape(p["coupangBanner"])}" width="120" height="240" frameborder="0" '
                 f'scrolling="no" referrerpolicy="unsafe-url" loading="lazy" title="{html.escape(strings["coupangHead"])}"></iframe>') if p.get('coupangBanner') else ''
        coupang = (f'<section class="coupang-box">{frame}<div class="coupang-copy"><h3>{html.escape(strings["coupangHead"])}</h3>'
                   f'<p>{html.escape(strings["coupangBody"])}</p><a class="coupang-btn" href="{html.escape(p["coupang"])}" target="_blank" '
                   f'rel="sponsored noopener noreferrer">{html.escape(strings["coupangCta"].format(name=p["short"]))}</a>'
                   f'<p class="coupang-note">{html.escape(strings["coupangDisclosure"])}</p></div></section>')
    table = f'<h3 class="d-section">{html.escape(strings["modelsTitle"])}</h3><table class="offers"><tbody>{rows}</tbody></table>' if rows else ''
    return coupang + table


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
