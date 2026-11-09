"""Daily price card for X (@quiteterribleHQ): draw a PNG from today's US prices and post it.

python tools/xpost.py --card out.png          # only draw the card (no keys needed)
python tools/xpost.py --post                  # draw and post (needs X_API_KEY, X_API_SECRET,
                                              # X_ACCESS_TOKEN, X_ACCESS_SECRET; OAuth 1.0a user context)
Posts only to our own account. It never reads, replies to or follows anyone.
"""
import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import prices_payload  # noqa: E402

PICKS = ('crucial-ddr5-32', 'samsung-ddr5-32', 'samsung-ddr5-16', 'rtx-5070', 'rtx-5080', 'rtx-5090')
SITE = 'https://quiteterrible.com/en/'
MEDIA_UPLOAD = 'https://api.x.com/2/media/upload'
CREATE_POST = 'https://api.x.com/2/tweets'


def rows(market='US'):
    """Today's lines for the card: one DDR5 32GB, one DDR5 16GB, three RTX cards, with the 7-day change."""
    payload = prices_payload(market)
    by_id = {p['id']: p for p in payload['products'] if p.get('price') is not None}
    out, seen = [], set()
    for pid in PICKS:
        p = by_id.get(pid)
        if not p:
            continue
        label = f"DDR5 {p['capacity']}GB" if p['category'] == 'ram' else p['short']
        if label in seen:  # one 32GB stick is enough
            continue
        seen.add(label)
        out.append({'label': label, 'price': p['price'], 'change': p.get('change7')})
    return out, payload['currency']


def money(value):
    return f'${value:,.0f}' if float(value).is_integer() else f'${value:,.2f}'


def arrow(change):
    if change is None or abs(change) < 0.05:
        return '—'
    return f"{'▲' if change > 0 else '▼'}{abs(change):.1f}%"


def mood(lines):
    """The boss's face for the day, from the average 7-day change of the lines on the card."""
    changes = [r['change'] for r in lines if r['change'] is not None]
    avg = sum(changes) / len(changes) if changes else 0
    return 'happy' if avg <= -0.5 else 'smirk' if avg < 0.5 else 'sad' if avg < 5 else 'angry'


CLOSERS = {'happy': 'Prices down. Even Sam is smiling.', 'smirk': 'Sam still has the RAM.',
           'sad': 'Prices up. Sam is crying into his RAM pile.', 'angry': 'Prices way up. Sam is furious. So are we.'}


def post_text(lines, day):
    body = '\n'.join(f"{r['label']}  {money(r['price'])}  {arrow(r['change'])}" for r in lines)
    return (f"Quite terrible RAM & GPU prices, {day:%b %-d} (US, lowest new on eBay, vs 7 days ago):\n\n"
            f"{body}\n\n{CLOSERS[mood(lines)]} {SITE}")


def draw_card(lines, day, path):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, str(ROOT / 'tools'))
    W, H = 1200, 675
    img = Image.new('RGB', (W, H), '#f6f1e4')
    d = ImageDraw.Draw(img)
    font = lambda size: ImageFont.load_default(size=size)  # Pillow's bundled scalable font: same everywhere
    d.rectangle([0, 0, W, 112], fill='#e8483c')
    d.text((48, 30), 'QUITE TERRIBLE', font=font(46), fill='#ffffff')
    d.text((W - 48, 44), f'{day:%b %-d, %Y}', font=font(30), fill='#ffffff', anchor='ra')
    d.text((48, 140), 'Lowest new prices in the US today (eBay)', font=font(28), fill='#5c6374')
    y = 196
    for r in lines:
        d.rounded_rectangle([40, y - 8, 760, y + 58], radius=12, fill='#ffffff')
        d.text((64, y + 6), r['label'], font=font(34), fill='#1a1c24')
        d.text((560, y + 6), money(r['price']), font=font(34), fill='#1a1c24', anchor='ra')
        ch = r['change']
        color = '#5c6374' if ch is None or abs(ch) < 0.05 else ('#d23a2f' if ch > 0 else '#2f7de1')
        d.text((740, y + 10), arrow(ch).replace('▲', '+').replace('▼', '-'), font=font(28), fill=color, anchor='ra')
        y += 76
    d.text((48, H - 54), 'vs 7 days ago  ·  quiteterrible.com', font=font(26), fill='#5c6374')
    boss = pixel_boss(scale=9, face=mood(lines))
    img.paste(boss, (W - boss.width - 34, H - boss.height - 36), boss)
    img.save(path)
    return path


def face_rows(boss, face):
    """Expressions drawn over the boss sprite's face (eyes at columns 7-8 and 13-14, rows 13-15)."""
    rows = [list(r) for r in boss]

    def put(y, x, ch):
        rows[y][x] = ch
    if face == 'happy':  # eyes closed in ^ ^, mouth open in a grin
        for ex in (7, 13):
            put(13, ex, 'K'); put(13, ex + 1, 'K')
            put(14, ex, 's'); put(14, ex + 1, 's'); put(14, ex - 1, 'K'); put(14, ex + 2, 'K')
            put(15, ex, 's'); put(15, ex + 1, 's')
        for x in (12, 13):
            put(17, x, 's')
        for x in (9, 10, 11):
            put(18, x, 's')
        for x in range(9, 13):
            put(17, x, 'K'); put(18, x, 'm')
    elif face == 'sad':  # brows up in the middle, tears, a frown
        put(12, 7, 's'); put(12, 8, 's'); put(12, 13, 's'); put(12, 14, 's')
        put(11, 8, 'd'); put(12, 9, 'd'); put(11, 13, 'd'); put(12, 12, 'd')
        for y in (16, 17, 18):
            put(y, 7, 'e'); put(y, 14, 'e')
        for x in (12, 13):
            put(17, x, 's')
        for x in (9, 10, 11):
            put(18, x, 's')
        put(17, 10, 'K'); put(17, 11, 'K'); put(18, 9, 'K'); put(18, 12, 'K')
    elif face == 'angry':  # the game's angry face: V brows, wide eyes, shouting mouth
        rows[12] = list('.KdhhTssddssddssshhdK.')
        rows[13] = list('.KdSsssKKssssKKsssSdK.')
        rows[14] = list('.KdSsssKKssssKKsssSdK.')
        rows[16] = list('.KdSssssssssssssssSdK.')
        rows[17] = list('..KdSsssKKKKKKsssSdK..')
        rows[18] = list('...KSSssKmmmmKsSSK....')
    return [''.join(r) for r in rows]


def pixel_boss(scale, face='smirk'):
    """The boss from the site's hero game (static/hero.js), sitting on a pile of RAM sticks."""
    from PIL import Image
    src = (ROOT / 'static/hero.js').read_text()
    grab = lambda name: re.findall(r"'([^']*)'", re.search(r'const %s = \[(.*?)\];' % name, src, re.S).group(1))
    colors = dict(re.findall(r"(\w+): '(#[0-9a-f]{6})'", src[src.index('const C = {'):src.index('};', src.index('const C = {'))]))
    pal_src = src[src.index('const BOSS_PAL = {'):src.index('};', src.index('const BOSS_PAL = {'))]
    boss_pal = dict(re.findall(r"(\w): '(#[0-9a-f]{6})'", pal_src)) | {'K': colors['K']}
    stick_pal = {'K': colors['K'], 'a': colors['pcb2'], 'b': colors['pcb1'], 'c': colors['chip'], 'g': colors['gold']}
    boss, stick = face_rows(grab('BOSS'), face), grab('STICK')
    boss_pal['e'] = '#4db8ff'  # tears
    if face == 'angry':  # red in the face, as in the game
        boss_pal |= {'s': '#f7b49c', 'S': '#e58f74', 'T': '#d98a70', 'm': '#8f2a22'}
    canvas = Image.new('RGBA', (40, 42), (0, 0, 0, 0))

    def put(sprite, x, y, pal):
        for j, row in enumerate(sprite):
            for i, ch in enumerate(row):
                if ch in pal:
                    canvas.putpixel((x + i, y + j), tuple(int(pal[ch][k:k + 2], 16) for k in (1, 3, 5)) + (255,))
    put(boss, 9, 0, boss_pal)
    if face == 'angry':  # the cartoon vein on his forehead
        put(['.r.r.', 'rr.rr', '.....', 'rr.rr', '.r.r.'], 26, 2, {'r': '#e8483c'})
    for r, (sx, n) in enumerate([(0, 3), (3, 2), (7, 1)]):
        for k in range(n):
            put(stick, sx + k * 13, 36 - r * 5, stick_pal)
    return canvas.resize((canvas.width * scale, canvas.height * scale), Image.NEAREST)


def oauth_header(method, url, keys):
    """OAuth 1.0a header (HMAC-SHA1). Multipart and JSON bodies are not part of the signature."""
    oauth = {'oauth_consumer_key': keys['X_API_KEY'], 'oauth_nonce': secrets.token_hex(16),
             'oauth_signature_method': 'HMAC-SHA1', 'oauth_timestamp': str(int(time.time())),
             'oauth_token': keys['X_ACCESS_TOKEN'], 'oauth_version': '1.0'}
    quote = lambda s: urllib.parse.quote(str(s), safe='~')
    params = '&'.join(f'{quote(k)}={quote(v)}' for k, v in sorted(oauth.items()))
    base = '&'.join([method, quote(url), quote(params)])
    key = f"{quote(keys['X_API_SECRET'])}&{quote(keys['X_ACCESS_SECRET'])}"
    oauth['oauth_signature'] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return 'OAuth ' + ', '.join(f'{quote(k)}="{quote(v)}"' for k, v in sorted(oauth.items()))


def request(url, keys, data, content_type):
    req = urllib.request.Request(url, data=data, method='POST', headers={
        'Authorization': oauth_header('POST', url, keys), 'Content-Type': content_type})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read() or b'{}')
    except urllib.error.HTTPError as exc:
        # Show X's error text (never our keys) so a failed post is easy to diagnose.
        raise SystemExit(f'X API {exc.code}: {exc.read()[:500].decode("utf-8", "replace")}')


def upload(path, keys):
    boundary = uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="media_category"\r\n\r\ntweet_image\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="card.png"\r\n'
            f'Content-Type: image/png\r\n\r\n').encode() + Path(path).read_bytes() + f'\r\n--{boundary}--\r\n'.encode()
    data = request(MEDIA_UPLOAD, keys, body, f'multipart/form-data; boundary={boundary}')
    return (data.get('data') or {}).get('id') or data.get('media_id_string')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--card', type=Path, default=ROOT / 'build-x-card.png')
    parser.add_argument('--post', action='store_true')
    args = parser.parse_args()
    day = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5))).date()  # the US morning run's date
    lines, currency = rows()
    if currency != 'USD' or len(lines) < 3:
        print('Not enough US prices today; nothing to post.')
        return
    draw_card(lines, day, args.card)
    text = post_text(lines, day)
    print(text)
    if not args.post:
        return
    keys = {k: os.getenv(k, '') for k in ('X_API_KEY', 'X_API_SECRET', 'X_ACCESS_TOKEN', 'X_ACCESS_SECRET')}
    if not all(keys.values()):
        print('X keys are not set; skipped posting.')
        return
    media = upload(args.card, keys)
    result = request(CREATE_POST, keys, json.dumps({'text': text, 'media': {'media_ids': [media]}}).encode(), 'application/json')
    print('posted', (result.get('data') or {}).get('id'))


if __name__ == '__main__':
    main()
