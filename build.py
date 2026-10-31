#!/usr/bin/env python3
"""Static export for free hosting (GitHub Pages).

    python3 build.py --base /quite-terrible   # site served from https://<user>.github.io/quite-terrible/
    python3 build.py                          # site served from a domain root
"""
import argparse
import json
import shutil
from pathlib import Path
from store import ROOT
from server import LANGS, render_page, prices_payload, news_payload

PAGES = (('prices', ''), ('news', 'news/'), ('about', 'about/'))

# A static host cannot read Accept-Language, so "/" lets the browser pick: its language, then its time zone.
LANG_JS = """(function () {
  var base = document.currentScript.getAttribute('data-base') || '';
  var langs = navigator.languages || [navigator.language || ''];
  var lang = null;
  for (var i = 0; i < langs.length && !lang; i++) {
    var primary = String(langs[i]).toLowerCase().split('-')[0];
    if (primary === 'ko' || primary === 'en') lang = primary;
  }
  if (!lang) {
    var zone = '';
    try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch (e) {}
    lang = zone === 'Asia/Seoul' ? 'ko' : 'en';
  }
  location.replace(base + '/' + lang + '/' + location.search);
})();
"""

ROOT_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Quite Terrible · RAM &amp; GPU prices</title>
  <link rel="icon" href="{base}/favicon.svg" type="image/svg+xml">
  <link rel="alternate" hreflang="ko" href="{base}/ko/">
  <link rel="alternate" hreflang="en" href="{base}/en/">
  <script src="{base}/lang.js" data-base="{base}"></script>
</head>
<body><p><a href="{base}/ko/">한국어</a> · <a href="{base}/en/">English</a></p></body>
</html>
"""


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(',', ':')))


def build(out, base=''):
    base = base.rstrip('/')
    if out.exists():
        shutil.rmtree(out)
    for lang in LANGS:
        for page, path in PAGES:
            target = out / lang / path / 'index.html'
            target.parent.mkdir(parents=True, exist_ok=True)
            # market=None: the browser picks the market (see pickMarket in app.js).
            target.write_text(render_page(lang, page, None, base=base, static=True))
    data = out / 'data'
    data.mkdir()
    for market in ('KR', 'US'):
        write_json(data / f'prices-{market}.json', prices_payload(market))
        write_json(data / f'prices-{market}-demo.json', prices_payload(market, demo=True))
    for lang in LANGS:
        write_json(data / f'news-{lang}.json', news_payload(lang))
    for name in ('app.js', 'styles.css', 'favicon.svg'):
        shutil.copy(ROOT / 'static' / name, out / name)
    (out / 'lang.js').write_text(LANG_JS)
    (out / 'index.html').write_text(ROOT_PAGE.format(base=base))
    (out / '404.html').write_text(ROOT_PAGE.format(base=base))
    (out / '.nojekyll').write_text('')  # serve files as-is, no Jekyll processing
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='', help='URL path prefix, e.g. /quite-terrible')
    parser.add_argument('--out', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(build(args.out, args.base))


if __name__ == '__main__':
    main()
