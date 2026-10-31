'use strict';
// Strings, language and the default market come from the server (see server.py render_page).
const boot = JSON.parse(document.getElementById('boot').textContent);
const T = boot.t;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const fmt = (key, vars = {}) => String(T[key] ?? key).replace(/\{(\w+)\}/g, (_, name) => vars[name] ?? '');
const DAY = 86400000;
const query = new URLSearchParams(location.search);
// The server picks the market from the visitor's country. A static host cannot, so the browser
// decides: Korea time zone or Korean page means Korean prices, otherwise US prices.
function pickMarket() {
  if (['KR', 'US'].includes(boot.market)) return boot.market;
  let zone = '';
  try { zone = Intl.DateTimeFormat().resolvedOptions().timeZone; } catch {}
  return zone === 'Asia/Seoul' || boot.lang === 'ko' ? 'KR' : 'US';
}
const base = boot.base || '';
const priceUrl = () => boot.static
  ? `${base}/data/prices-${state.market}${state.demo ? '-demo' : ''}.json`
  : `/api/prices?market=${state.market}${state.demo ? '&demo=1' : ''}`;
const newsUrl = () => boot.static ? `${base}/data/news-${boot.lang}.json` : `/api/news?lang=${boot.lang}`;
const state = {
  page: boot.page,
  market: pickMarket(),
  demo: query.get('demo') === '1',
  period: 30,
  detailPeriod: 90,
  category: 'all',
  sort: null,
  sortDir: 1,
  newsCategory: 'all',
  prices: null,
  news: null,
  selected: null,
};
const locale = boot.lang === 'ko' ? 'ko-KR' : 'en-US';

const money = (value, compact = false) => {
  if (value == null) return '—';
  const krw = state.market === 'KR';
  return new Intl.NumberFormat(locale, {style: 'currency', currency: krw ? 'KRW' : 'USD',
    ...(compact ? {notation: 'compact', maximumFractionDigits: 1}
      : {minimumFractionDigits: krw ? 0 : 2, maximumFractionDigits: krw ? 0 : 2})}).format(value);
};
const direction = value => value == null || Math.abs(value) < 0.05 ? 'flat' : value > 0 ? 'up' : 'down';
const pct = value => value == null ? '—' : `${{up: '▲ ', down: '▼ ', flat: ''}[direction(value)]}${Math.abs(value).toFixed(1)}%`;
const delta = (value, pill = false) => `<span class="delta ${direction(value)}${pill ? ' pill' : ''}">${pct(value)}</span>`;
const when = (value, withTime = true) => value ? new Intl.DateTimeFormat(locale, {month: 'short', day: 'numeric',
  ...(withTime ? {hour: 'numeric', minute: '2-digit'} : {})}).format(new Date(value)) : '—';
const periodPoints = (history, days) => {
  const cutoff = Date.now() - days * DAY;
  return (history || []).filter(p => Date.parse(p.at) >= cutoff && Number.isFinite(p.price));
};
const changeOver = points => points.length > 1 ? (points.at(-1).price / points[0].price - 1) * 100 : null;
const categoryLabel = category => category === 'ram' ? T.catRam : T.catGpu;
const categoryTag = category => category === 'ram' ? T.catRamShort : T.catGpuShort;
const fullName = p => `${p.brand} ${p.name} · ${p.spec}`;
const productHref = p => `${esc(boot.base || '')}/${boot.lang}/${esc(p.id)}/`;
const sourceName = source => ({danawa: T.srcDanawa, bestbuy: T.srcBestbuy, ebay: T.srcEbay}[source] || T.srcFeed);
const bestOffer = p => (p.offers || []).find(o => !o.stale && o.stock !== 'out_of_stock' && o.price);
const offerSource = o => o ? `${sourceName(o.source)}${o.shops ? ` · ${fmt('sellersN', {n: o.shops})}` : ''}` : '';
const safeHref = value => {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? esc(url.href) : null;
  } catch { return null; }
};
const icons = {
  ram: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="2" y="6" width="20" height="10" rx="1"/><path d="M5 16v2m3-2v2m3-2v2m3-2v2m3-2v2m3-2v2M5.5 9h3v4h-3zm5 0h3v4h-3zm5 0h3v4h-3z"/></svg>',
  gpu: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="3" y="5" width="19" height="12" rx="1.5"/><path d="M1 3v17M6 17v2.5h7V17"/><circle cx="9" cy="11" r="3.2"/><circle cx="16.5" cy="11" r="3.2"/></svg>',
};

/* Charts: SVG with a fixed aspect ratio so pointer math is a simple ratio. */
const charts = new Map();
let chartSeq = 0;

function chartSvg(points, {key = '', w = 320, h = 110, axes = false, label = ''} = {}) {
  const id = `c${++chartSeq}`;
  const padT = 14, padB = axes ? 26 : 6, padR = axes ? 72 : 0;
  const iw = w - padR, ih = h - padT - padB, floor = padT + ih;
  const grid = (axes ? [0, 0.5, 1] : [1]).map(f => {
    const y = (padT + ih * f).toFixed(1);
    return `<line class="grid-line" x1="0" x2="${iw}" y1="${y}" y2="${y}"/>`;
  }).join('');
  if (!points.length) {
    return `<svg class="chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(T.chartEmpty)}">${grid}<text class="empty" x="${iw / 2}" y="${(padT + ih / 2 + 4).toFixed(1)}" text-anchor="middle">${esc(T.chartEmpty)}</text></svg>`;
  }
  const prices = points.map(p => p.price);
  let lo = Math.min(...prices), hi = Math.max(...prices);
  const pad = hi === lo ? Math.max(1, lo * 0.04) : (hi - lo) * 0.15;
  lo -= pad; hi += pad;
  const t0 = Date.parse(points[0].at), t1 = Date.parse(points.at(-1).at);
  const X = t => points.length === 1 ? iw - 8 : 4 + (t - t0) / Math.max(1, t1 - t0) * (iw - 12);
  const Y = v => padT + (hi - v) / (hi - lo) * ih;
  const coords = points.map(p => { const t = Date.parse(p.at); return {t, p, x: X(t), y: Y(p.price)}; });
  // Gaps longer than 36 hours break the line: missing days are never filled in.
  let line = '', segments = 0;
  coords.forEach((c, i) => {
    const gap = i === 0 || c.t - coords[i - 1].t > 36 * 3600000;
    if (gap) segments += 1;
    line += `${gap ? 'M' : 'L'}${c.x.toFixed(1)},${c.y.toFixed(1)}`;
  });
  const last = coords.at(-1);
  const area = segments === 1 && coords.length > 1
    ? `<path d="${line}L${last.x.toFixed(1)},${floor}L${coords[0].x.toFixed(1)},${floor}Z" fill="url(#${id}g)"/>` : '';
  // One observation is drawn as a dashed level with a note, not as a lone dot.
  const single = points.length === 1
    ? `<line class="baseline" x1="0" x2="${last.x.toFixed(1)}" y1="${last.y.toFixed(1)}" y2="${last.y.toFixed(1)}"/>`
      + `<text class="note" x="0" y="${(last.y - 10).toFixed(1)}">${esc(fmt('trackingSince', {date: when(points[0].at, false)}))}</text>` : '';
  let labels = '';
  if (axes) {
    labels = [hi, (hi + lo) / 2, lo].map((v, i) =>
      `<text class="axis-label" x="${w}" y="${(padT + ih * i / 2 + 4).toFixed(1)}" text-anchor="end">${esc(money(v, true))}</text>`).join('');
    labels += points.length > 1
      ? `<text class="axis-label" x="0" y="${h - 6}">${esc(when(points[0].at, false))}</text><text class="axis-label" x="${iw}" y="${h - 6}" text-anchor="end">${esc(when(points.at(-1).at, false))}</text>`
      : `<text class="axis-label" x="${iw}" y="${h - 6}" text-anchor="end">${esc(when(points[0].at, false))}</text>`;
  }
  charts.set(id, {coords, w});
  const summary = `${label} ${when(points[0].at, false)}–${when(points.at(-1).at, false)}: ${money(Math.min(...prices))}–${money(Math.max(...prices))}`;
  return `<svg class="chart ${direction(changeOver(points))}" viewBox="0 0 ${w} ${h}" data-chart="${id}" data-key="${esc(key)}" role="img" aria-label="${esc(summary)}">`
    + `<defs><linearGradient id="${id}g" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".22"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>`
    + `${grid}${labels}${area}${single}<path class="line" d="${line}"/>`
    + `<circle class="last-halo" cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="8"/><circle class="last-dot" cx="${last.x.toFixed(1)}" cy="${last.y.toFixed(1)}" r="3.5"/>`
    + `<g class="cursor" hidden><line class="cursor-line" y1="${padT}" y2="${floor}"/><circle class="cursor-dot" r="4"/></g></svg>`;
}

function sparkSvg(points) {
  if (points.length < 2) return '<span class="muted">—</span>';
  const w = 100, h = 30, prices = points.map(p => p.price);
  const lo = Math.min(...prices), hi = Math.max(...prices), span = hi - lo || 1;
  const t0 = Date.parse(points[0].at), t1 = Date.parse(points.at(-1).at);
  let line = '';
  points.forEach((p, i) => {
    const t = Date.parse(p.at);
    const gap = i === 0 || t - Date.parse(points[i - 1].at) > 36 * 3600000;
    const x = 2 + (t - t0) / Math.max(1, t1 - t0) * (w - 4);
    const y = hi === lo ? h / 2 : 3 + (hi - p.price) / span * (h - 6);
    line += `${gap ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `<svg class="spark ${direction(changeOver(points))}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path class="line" d="${line}"/></svg>`;
}

// Hovering a chart shows that day's price in the quote above it, like a market terminal.
let hovered = null;
function setReadout(key, point) {
  const el = document.querySelector(`[data-readout="${CSS.escape(key)}"]`);
  if (!el) return;
  if (el.dataset.original === undefined) el.dataset.original = el.innerHTML;
  el.innerHTML = point
    ? `<span class="quote-price">${money(point.price)}</span><span class="quote-when">${esc(when(point.at, false))}</span>`
    : el.dataset.original;
}
function clearCursor() {
  if (!hovered) return;
  hovered.querySelector('.cursor')?.setAttribute('hidden', '');
  setReadout(hovered.dataset.key, null);
  hovered = null;
}
document.addEventListener('pointermove', event => {
  const svg = event.target instanceof Element ? event.target.closest('svg[data-chart]') : null;
  if (svg !== hovered) clearCursor();
  const info = svg && charts.get(svg.dataset.chart);
  if (!info) return;
  hovered = svg;
  const box = svg.getBoundingClientRect();
  const x = (event.clientX - box.left) / box.width * info.w;
  const nearest = info.coords.reduce((best, c) => Math.abs(c.x - x) < Math.abs(best.x - x) ? c : best);
  const cursor = svg.querySelector('.cursor');
  cursor.removeAttribute('hidden');
  const line = cursor.querySelector('line');
  line.setAttribute('x1', nearest.x); line.setAttribute('x2', nearest.x);
  const dot = cursor.querySelector('circle');
  dot.setAttribute('cx', nearest.x); dot.setAttribute('cy', nearest.y);
  setReadout(svg.dataset.key, nearest.p);
});
document.documentElement.addEventListener('pointerleave', clearCursor);

/* Prices page */
function quoteHtml(p, extra) {
  if (p.price == null) return `<span class="quote-price muted">${esc(p.observed_at ? T.stale : T.awaiting)}</span>`;
  return `<span class="quote-price">${money(p.price)}</span>${extra}`;
}

// Charts are drawn at their on-screen width so axis text stays at its real size on every screen.
function columnWidth(selector, columns, inset, gap = 16) {
  const box = $(selector)?.clientWidth || 0;
  const count = columns.find(([query]) => matchMedia(query).matches)?.[1] ?? columns.at(-1)[1];
  return Math.max(220, Math.floor((box - gap * (count - 1)) / count) - inset);
}
const layout = {spot: 640, card: 300, detail: 580};
function measureCharts() {
  layout.spot = columnWidth('#spotlight', [['(max-width: 860px)', 1], ['all', 2]], innerWidth <= 640 ? 34 : 42);
  layout.card = columnWidth('#cards', [['(max-width: 640px)', 1], ['(max-width: 1100px)', 2], ['all', 4]], 34);
  const body = $('#drawer-body');
  const inset = innerWidth <= 640 ? 32 : 44;
  layout.detail = Math.max(240, (body?.clientWidth || Math.min(620, innerWidth)) - inset);
}

const rangeOf = points => {
  const prices = points.map(x => x.price);
  return prices.length ? [Math.min(...prices), Math.max(...prices)] : [null, null];
};

// The two parts most people buy first get large charts with axes.
function spotHtml(p) {
  const points = periodPoints(p.history, state.period);
  const [low, high] = rangeOf(points);
  const key = `spot:${p.id}`;
  return `<article class="spot" data-product="${esc(p.id)}">
    <div class="spot-kicker"><span class="tag ${p.category}">${esc(categoryTag(p.category))}</span><span class="spec">${esc(fullName(p))}</span></div>
    <h2 class="spot-title"><a class="card-title" href="${productHref(p)}" data-product="${esc(p.id)}">${esc(p.short)}</a></h2>
    <div class="quote" data-readout="${key}">${quoteHtml(p, `<span class="quote-when">${esc(state.demo ? T.statusDemo : offerSource(bestOffer(p)))}</span>`)}</div>
    <div class="spot-changes"><span>${esc(T.change24)} ${delta(p.change, true)}</span><span>${esc(T.change7)} ${delta(p.change7, true)}</span><span>${esc(T['p' + state.period])} ${delta(changeOver(points), true)}</span></div>
    ${chartSvg(points, {key, w: layout.spot, h: 240, axes: true, label: p.short})}
    <div class="spot-foot"><span>${esc(T.low)} <b>${money(low)}</b></span><span>${esc(T.high)} <b>${money(high)}</b></span><span class="src">${esc(T.daysObserved)} <b>${esc(fmt('daysN', {n: p.history.length}))}</b></span></div>
  </article>`;
}

function cardHtml(p) {
  const points = periodPoints(p.history, state.period);
  const [low, high] = rangeOf(points);
  const key = `card:${p.id}`;
  return `<article class="card" data-product="${esc(p.id)}">
    <div class="card-top"><a class="card-title card-name" href="${productHref(p)}" data-product="${esc(p.id)}">${esc(p.short)}</a><span class="tag ${p.category}">${esc(categoryTag(p.category))}</span></div>
    <p class="card-spec">${esc(fullName(p))}</p>
    <div class="quote" data-readout="${key}">${quoteHtml(p, delta(changeOver(points), true))}</div>
    ${chartSvg(points, {key, w: layout.card, h: 92, label: p.short})}
    <div class="card-foot"><span>${esc(T.low)} <b>${money(low)}</b></span><span>${esc(T.high)} <b>${money(high)}</b></span></div>
  </article>`;
}

function rangeHtml(p) {
  if (p.price == null || p.low30 == null || p.high30 == null) return '<span class="muted">—</span>';
  const pos = p.high30 === p.low30 ? 0.5 : Math.min(1, Math.max(0, (p.price - p.low30) / (p.high30 - p.low30)));
  return `<div class="range" data-pos="${pos.toFixed(3)}"><div class="range-track"><span class="range-dot"></span></div><div class="range-labels"><span>${money(p.low30, true)}</span><span>${money(p.high30, true)}</span></div></div>`;
}

function rowHtml(p) {
  const price = p.price == null ? `<span class="muted">${esc(p.observed_at ? T.stale : T.awaiting)}</span>` : `<span class="price">${money(p.price)}</span>`;
  return `<tr class="row" data-product="${esc(p.id)}">
    <td><div class="prod"><span class="prod-icon ${p.category}">${icons[p.category]}</span><div><a class="prod-name" href="${productHref(p)}" data-product="${esc(p.id)}">${esc(p.short)}</a><span class="prod-spec">${esc(fullName(p))}</span></div></div></td>
    <td class="num">${price}</td>
    <td class="num">${delta(p.change)}</td>
    <td class="num hide-sm">${delta(p.change7)}</td>
    <td class="hide-md">${rangeHtml(p)}</td>
    <td class="hide-sm">${sparkSvg(periodPoints(p.history, 30))}</td>
    <td class="num hide-md">${bestOffer(p)?.shops ?? '<span class="muted">—</span>'}</td>
  </tr>`;
}

function renderStatus() {
  const data = state.prices;
  const priced = data.products.filter(p => p.price != null).length;
  const last = data.products.map(p => p.observed_at).filter(Boolean).sort().at(-1);
  const lastOk = data.runs.map(r => r.succeeded_at).filter(Boolean).sort().at(-1);
  const failed = data.runs.some(r => r.state === 'error');
  let kind = 'idle', label = T.statusOffline;
  if (data.demo) [kind, label] = ['demo', T.statusDemo];
  else if (failed) [kind, label] = ['error', fmt('statusError', {time: when(lastOk)})];
  else if (priced) [kind, label] = ['live', fmt('statusLive', {time: when(last)})];
  label += ` · ${state.market === 'KR' ? T.marketKR : T.marketUS}`;
  $('#price-status').dataset.state = kind;
  $('#price-status-text').textContent = label;
  const banner = $('#banner');
  banner.hidden = !data.demo && priced > 0;
  banner.dataset.kind = data.demo ? 'demo' : 'idle';
  banner.innerHTML = data.demo
    ? `<span>${esc(T.demoBanner)}</span><button type="button" data-action="live">${esc(T.viewLive)}</button>`
    : `<span>${esc(T.offlineBanner)}</span><button type="button" data-action="demo">${esc(T.viewDemo)}</button>`;
}

function renderCards() {
  measureCharts();
  const featured = state.prices.products.filter(p => p.featured).sort((a, b) => a.featured - b.featured);
  const spot = ['ram', 'gpu'].map(c => featured.find(p => p.category === c)).filter(Boolean);
  $('#spotlight').innerHTML = spot.map(spotHtml).join('');
  $('#cards').innerHTML = featured.filter(p => !spot.includes(p)).map(cardHtml).join('');
  $$('#period button').forEach(b => b.setAttribute('aria-pressed', String(Number(b.dataset.period) === state.period)));
}

function renderSide() {
  $('#side-prices').innerHTML = state.prices.products.map(p => `<li><a href="${esc(base)}/${boot.lang}/"><span class="side-name">${esc(p.short)}</span><span class="side-price">${money(p.price)}</span>${delta(p.change)}</a></li>`).join('');
}

function renderTable() {
  let list = state.prices.products.filter(p => state.category === 'all' || p.category === state.category);
  if (state.sort) {
    list = [...list].sort((a, b) => {
      const x = a[state.sort], y = b[state.sort];
      if (x == null || y == null) return x == null ? (y == null ? 0 : 1) : -1;
      return (x - y) * state.sortDir;
    });
  }
  const grouped = !state.sort && state.category === 'all';
  $('#rows').innerHTML = grouped
    ? ['ram', 'gpu'].map(c => `<tr class="group"><td colspan="7">${esc(categoryLabel(c))}</td></tr>${list.filter(p => p.category === c).map(rowHtml).join('')}`).join('')
    : list.map(rowHtml).join('');
  // CSP forbids inline style attributes, so marker positions are set through the CSSOM.
  $$('.range[data-pos]').forEach(el => el.style.setProperty('--pos', `${Number(el.dataset.pos) * 100}%`));
  $$('#category button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.category === state.category)));
  $$('.th-sort').forEach(b => b.closest('th').setAttribute('aria-sort',
    state.sort === b.dataset.sort ? (state.sortDir > 0 ? 'ascending' : 'descending') : 'none'));
}

function renderPrices() {
  charts.clear();
  renderStatus();
  renderCards();
  renderTable();
}

async function fetchPrices() {
  const response = await fetch(priceUrl(), {cache: 'no-cache', signal: AbortSignal.timeout(15000)});
  if (!response.ok) throw new Error(String(response.status));
  const data = await response.json();
  if (!data.demo && data.market === 'US' && !data.products.some(p => p.price != null)) {
    state.market = 'KR';  // no US source connected yet: show real Korean prices instead of an empty page
    return fetchPrices();
  }
  return data;
}

let priceRequest = 0;
async function loadPrices() {
  const id = ++priceRequest;
  if (!state.prices) {
    $('#spotlight').innerHTML = '<div class="spot skeleton"></div>'.repeat(2);
    $('#cards').innerHTML = '<div class="card skeleton"></div>'.repeat(4);
  }
  try {
    const data = await fetchPrices();
    if (id !== priceRequest) return;
    state.prices = data;
    $('#table-msg').hidden = true;
    renderPrices();
  } catch {
    if (id !== priceRequest) return;
    $('#price-status').dataset.state = 'error';
    $('#price-status-text').textContent = T.loadError;
    $('#spotlight').innerHTML = '';
    $('#cards').innerHTML = '';
    $('#rows').innerHTML = '';
    $('#table-msg').hidden = false;
    $('#table-msg').innerHTML = `${esc(T.loadError)}<button type="button" data-action="retry">${esc(T.retry)}</button>`;
  }
}

function offerHtml(o) {
  const stock = o.stale ? T.stale : {in_stock: T.stockYes, out_of_stock: T.soldOut}[o.stock];
  const shipping = o.shipping_amount == null ? T.shippingUnknown : o.shipping_amount === 0 ? T.freeShipping : fmt('shippingN', {v: money(o.shipping_amount)});
  const href = safeHref(o.affiliate_url || o.url);
  return `<tr class="${o.stale || o.stock === 'out_of_stock' ? 'muted-row' : ''}">
    <td><span class="offer-name" title="${esc(o.title)}">${esc(o.merchant)}</span>${o.affiliate_url ? ` <span class="tag aff">${esc(T.affiliate)}</span>` : ''}<span class="offer-meta">${esc([offerSource(o), stock, fmt('checkedAt', {time: when(o.observed_at)})].filter(Boolean).join(' · '))}</span></td>
    <td class="num"><span class="price">${money(o.amount)}</span><span class="offer-meta">${esc(shipping)}</span></td>
    <td class="num">${href ? `<a class="buy" href="${href}" target="_blank" rel="noopener noreferrer${o.affiliate_url ? ' sponsored' : ''}">${esc(T.visitSeller)}</a>` : ''}</td>
  </tr>`;
}

function renderDetail(target = '#drawer-body') {
  const p = state.prices?.products.find(x => x.id === state.selected);
  if (!p) return;
  measureCharts();
  if (target !== '#drawer-body') layout.detail = Math.max(240, $(target).clientWidth - (innerWidth <= 640 ? 32 : 44));
  const points = periodPoints(p.history, state.detailPeriod);
  const prices = points.map(x => x.price);
  const key = `detail:${p.id}`;
  const checked = state.demo ? T.statusDemo : fmt('checkedAt', {time: when(p.observed_at)});
  if (target === '#drawer-body') $('#drawer-kicker').textContent = `${categoryLabel(p.category)} · ${state.prices.currency}`;
  $(target).innerHTML = `
    <div class="d-title"><div><h2 ${target === '#drawer-body' ? 'id="drawer-title"' : ''}>${esc(p.short)}</h2><p>${esc(fullName(p))}</p></div><span class="tag ${p.category}">${esc(categoryTag(p.category))}</span></div>
    <div class="quote d-quote" data-readout="${key}">${quoteHtml(p, `<span class="quote-when">${esc(checked)}</span>`)}</div>
    <div class="d-changes"><span>${esc(T.change24)}${delta(p.change)}</span><span>${esc(T.change7)}${delta(p.change7)}</span><span>${esc(T['p' + state.detailPeriod])}${delta(changeOver(points))}</span></div>
    <div class="segmented" role="group" aria-label="${esc(T.period)}">${[7, 30, 90].map(n => `<button type="button" data-detail-period="${n}" aria-pressed="${state.detailPeriod === n}">${esc(T['p' + n])}</button>`).join('')}</div>
    <div class="d-chart">${chartSvg(points, {key, w: layout.detail, h: 240, axes: true, label: p.short})}</div>
    <dl class="d-stats">
      <div><dt>${esc(T.low)}</dt><dd>${money(prices.length ? Math.min(...prices) : null)}</dd></div>
      <div><dt>${esc(T.high)}</dt><dd>${money(prices.length ? Math.max(...prices) : null)}</dd></div>
      <div><dt>${esc(T.daysObserved)}</dt><dd>${esc(fmt('daysN', {n: p.history.length}))}</dd></div>
      <div><dt>${esc(T.colSellers)}</dt><dd>${bestOffer(p)?.shops ?? '—'}</dd></div>
    </dl>
    <h3 class="d-section">${esc(T.offersTitle)}</h3>
    ${p.offers.length ? `<table class="offers"><tbody>${p.offers.slice(0, 10).map(offerHtml).join('')}</tbody></table>` : `<p class="d-empty">${esc(state.demo ? T.demoOffers : T.noOffers)}</p>`}
    <p class="d-note">${esc(p.category === 'gpu' ? T.gpuNote : T.ramNote)}</p>`;
}

let resizeTimer = 0;
addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    if (!state.prices) return;
    charts.clear();
    if (state.page === 'product') { renderDetail('#product-detail'); return; }
    if (state.page !== 'prices') return;
    renderCards();
    if ($('#drawer').open) renderDetail();
  }, 150);
});

function openDetail(id) {
  state.selected = id;
  state.detailPeriod = 90;
  // Open first so the chart can be drawn at the drawer's real width.
  if (!$('#drawer').open) $('#drawer').showModal();
  renderDetail();
}

/* News page */
function renderNews() {
  const {news, runs} = state.news;
  const lastOk = runs.map(r => r.succeeded_at).filter(Boolean).sort().at(-1);
  const failed = runs.some(r => r.state === 'error');
  $('#news-status').dataset.state = failed ? 'error' : lastOk ? 'live' : 'idle';
  $('#news-status-text').textContent = failed ? fmt('newsDelayed', {time: when(lastOk)}) : lastOk ? fmt('newsUpdated', {time: when(lastOk)}) : T.newsPending;
  $$('#news-category button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.newsCategory === state.newsCategory)));
  const items = news.filter(n => state.newsCategory === 'all' || n.category === state.newsCategory);
  if (!items.length) {
    $('#news-list').innerHTML = `<p class="news-empty">${esc(lastOk ? T.newsEmpty : T.newsPending)}</p>`;
    return;
  }
  const dayKey = date => `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  const today = dayKey(new Date()), yesterday = dayKey(new Date(Date.now() - DAY));
  const groups = new Map();
  for (const item of items) {
    const key = dayKey(new Date(item.published_at));
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const dayLabel = new Intl.DateTimeFormat(locale, {month: 'long', day: 'numeric', weekday: 'short'});
  const timeLabel = new Intl.DateTimeFormat(locale, {hour: 'numeric', minute: '2-digit'});
  $('#news-list').innerHTML = [...groups].map(([key, list]) => {
    const date = new Date(list[0].published_at);
    const prefix = key === today ? `${T.today} · ` : key === yesterday ? `${T.yesterday} · ` : '';
    return `<section class="news-day"><h3>${esc(prefix + dayLabel.format(date))}</h3><ol class="news-items">${list.map(n => {
      const href = safeHref(n.url);
      return `<li class="news-item"><time class="news-time" datetime="${esc(n.published_at)}">${esc(timeLabel.format(new Date(n.published_at)))}</time><div class="news-body">${href ? `<a class="news-title" href="${href}" target="_blank" rel="noopener noreferrer">${esc(n.title)}<span class="news-out" aria-hidden="true"> ↗</span></a>` : `<span class="news-title">${esc(n.title)}</span>`}<div class="news-meta"><span class="tag ${n.category}">${esc(categoryTag(n.category))}</span><span>${esc(n.publisher)}</span></div></div></li>`;
    }).join('')}</ol></section>`;
  }).join('');
}

async function loadNews() {
  try {
    const response = await fetch(newsUrl(), {cache: 'no-cache', signal: AbortSignal.timeout(15000)});
    if (!response.ok) throw new Error(String(response.status));
    state.news = await response.json();
    renderNews();
  } catch {
    $('#news-status').dataset.state = 'error';
    $('#news-status-text').textContent = T.loadError;
    $('#news-list').innerHTML = `<p class="news-empty">${esc(T.loadError)}<button type="button" data-action="retry">${esc(T.retry)}</button></p>`;
  }
}

/* Events */
document.addEventListener('click', event => {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  const pick = selector => target.closest(selector);
  let el;
  if ((el = pick('[data-period]'))) { state.period = Number(el.dataset.period); charts.clear(); renderCards(); renderTable(); return; }
  if ((el = pick('[data-detail-period]'))) {
    state.detailPeriod = Number(el.dataset.detailPeriod);
    renderDetail(state.page === 'product' ? '#product-detail' : '#drawer-body');
    $(`[data-detail-period="${state.detailPeriod}"]`)?.focus();
    return;
  }
  if ((el = pick('[data-category]'))) { state.category = el.dataset.category; renderTable(); return; }
  if ((el = pick('[data-news-category]'))) { state.newsCategory = el.dataset.newsCategory; renderNews(); return; }
  if ((el = pick('[data-sort]'))) {
    const key = el.dataset.sort;
    if (state.sort !== key) [state.sort, state.sortDir] = [key, 1];
    else if (state.sortDir === 1) state.sortDir = -1;
    else state.sort = null;
    renderTable();
    return;
  }
  const action = pick('[data-action]')?.dataset.action;
  if (action === 'retry') { state.page === 'news' ? loadNews() : loadPrices(); return; }
  if (action === 'demo' || action === 'live') {
    state.demo = action === 'demo';
    const url = new URL(location.href);
    if (state.demo) url.searchParams.set('demo', '1'); else url.searchParams.delete('demo');
    history.replaceState(null, '', url);
    loadPrices();
    return;
  }
  const link = pick('a');
  if (link && !(link.dataset.product && state.page === 'prices' && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey)) return;
  if ((el = pick('[data-product]')) && state.prices && state.page === 'prices') {
    event.preventDefault();
    openDetail(el.dataset.product);
  }
});

$('#drawer-close').addEventListener('click', () => $('#drawer').close());
$('#drawer').addEventListener('click', event => {
  const box = event.currentTarget.getBoundingClientRect();
  if (event.target === event.currentTarget && (event.clientX < box.left || event.clientX > box.right)) event.currentTarget.close();
});

if (state.page === 'product') {
  state.selected = boot.product;
  state.detailPeriod = 90;
  fetchPrices().then(data => { state.prices = data; renderDetail('#product-detail'); }).catch(() => {});
} else if (state.page === 'news') {
  loadNews();
  // The news page shows today's prices beside the headlines.
  fetchPrices().then(data => { state.prices = data; renderSide(); }).catch(() => {});
} else if (state.page === 'prices') {
  loadPrices();
}
