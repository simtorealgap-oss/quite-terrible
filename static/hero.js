'use strict';
// Hero: a pixel-art RAM tycoon. A factory makes RAM, a conveyor carries it to an AI data center where
// the hoodie boss keeps almost all of it; now and then he tosses one stick to the people below.
// Click (or tap) a stick on its way to the data center to grab it for the people.
// The caption shows today's real DDR5 32GB price (updated once a day); the game never changes it.
// Plain Canvas 2D, no dependencies. A still frame under reduced motion.
(() => {
  const root = document.getElementById('hero');
  const canvas = document.getElementById('hero-canvas');
  if (!root || root.hidden || !canvas) return;
  const ctx = canvas.getContext('2d');
  const content = document.getElementById('hero-content');
  const hint = document.getElementById('hero-hint');
  if (hint) hint.hidden = true;  // the hint is drawn into the scene's caption instead
  const boot = JSON.parse(document.getElementById('boot')?.textContent || '{}');
  const T = boot.t || {};
  const fmt = (key, vars = {}) => String(T[key] ?? '').replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const coarse = matchMedia('(hover: none), (pointer: coarse)').matches;

  /* Pixel palette and sprites ('.' is transparent). */
  const P = {
    k: '#1d2027', g: '#3d4350', l: '#8b8e94', w: '#f2efe8', r: '#e8483c', R: '#b8352b', G: '#2f6b3a',
    y: '#d8a944', b: '#2563eb', s: '#f1c9a5', h: '#5a3a22', H: '#2a2e37', c: '#9ad0ff', o: '#16a34a',
  };
  const STICK = ['GkGkGkG', 'GGGGGGG', 'y.y.y.y'];
  const BOSS = [
    '...hhhhh...',
    '..hhhhhhh..',
    '..hssssss..',
    '..sksssks..',
    '..ssssss...',
    '...srrss...',
    '....sss....',
    '..HHHHHHH..',
    '.HHHHHHHHH.',
    '.HHHwHwHHH.',
    'HHHHHHHHHHH',
    'HsHHHHHHHsH',
    '.HHHHHHHHH.',
    '.HHHHHHHHH.',
    '..kk...kk..',
    '..kk...kk..',
    '.kkk...kkk.',
  ];
  const SHIRTS = ['#e8483c', '#2563eb', '#16a34a', '#d97706', '#7c3aed', '#0f8a4b', '#db2777'];
  function sprite(c, rows, x, y, pal = P) {
    for (let j = 0; j < rows.length; j++) {
      const row = rows[j];
      for (let i = 0; i < row.length; i++) {
        const ch = row[i];
        if (ch === '.') continue;
        c.fillStyle = pal[ch];
        c.fillRect(x + i, y + j, 1, 1);
      }
    }
  }
  const rect = (c, color, x, y, w, h) => { c.fillStyle = color; c.fillRect(Math.round(x), Math.round(y), w, h); };

  /* Layout: the scene sits in the band above the headline, drawn at low resolution and scaled up. */
  const off = document.createElement('canvas');
  const octx = off.getContext('2d');
  let W = 1, H = 1, dpr = 1, S = 4, LW = 100, LH = 48, y0 = 0;
  let gy, beltY, factoryX, beltStart, bossX, rackX, crowd = [];
  function layout() {
    W = root.clientWidth; H = root.clientHeight;
    dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    S = W < 640 ? 3 : 4;
    const top = content ? content.offsetTop : H;
    LH = Math.max(34, Math.min(60, Math.floor((top - 10) / S)));
    LW = Math.ceil(W / S);
    y0 = Math.max(0, top - 8 - LH * S);
    off.width = LW; off.height = LH;
    gy = LH - 2;
    beltY = gy - 14;
    factoryX = W < 640 ? 2 : Math.max(4, Math.round(LW * 0.08));
    beltStart = factoryX + 25;
    rackX = LW - (W < 640 ? 14 : Math.max(16, Math.round(LW * 0.08)));
    bossX = rackX - 13;
    const left = beltStart + 2, right = bossX - 4;
    const n = Math.max(3, Math.min(10, Math.floor((right - left) / 8)));
    crowd = Array.from({length: n}, (_, i) => crowd[i] || {jump: 0, shirt: SHIRTS[i % SHIRTS.length], holding: 0});
    crowd.forEach((p, i) => { p.x = Math.round(left + (i + 0.5) * (right - left) / n) - 2; });
    draw();
  }

  /* Game state. */
  const state = {ai: 0, people: 0, saved: 0, real: null, change: null, history: [], currency: 'KRW', touched: false};
  // The "why is it going up" board: today's real change with a joke from the boss's world, then real headlines.
  let board = [], boardAt = 0, boardIn = 0;
  let sticks = [], smoke = [], popups = [], spawnIn = 0.6, tossEvery = 11, sinceToss = 0;
  let bubble = null, bubbleIn = 4, grab = 0, time = 0;
  const pick = keys => { const list = keys.map(k => T[k]).filter(Boolean); return list[Math.floor(Math.random() * list.length)]; };
  const IDLE = ['gameLine1', 'gameLine2', 'gameLine3', 'gameLine4'];
  const ANGRY = ['gameAngry1', 'gameAngry2', 'gameAngry3'];
  const TOSS = ['gameToss1', 'gameToss2'];
  function say(keys, seconds, angry = false) {
    const text = pick(keys);
    if (text) { bubble = {text, t: seconds, angry}; bubbleIn = 8 + Math.random() * 6; }
  }

  function arc(s, x1, y1, d, h, then) {
    Object.assign(s, {from: [s.x, s.y], to: [x1, y1], d, h, t: 0, then});
  }
  function landOn(person) {
    person.jump = 0.45; person.holding = 6;
  }
  function toPeople(s, mine) {
    const person = crowd[Math.floor(Math.random() * crowd.length)];
    s.state = 'air';
    arc(s, person.x - 1, gy - 10, mine ? 0.8 : 1.0, mine ? 10 : 16, () => {
      s.dead = true; landOn(person); state.people += 1;
    });
  }
  function rackTop() { return gy - Math.min(LH - 10, 6 + Math.floor(state.ai / 3)); }
  function hoard(s) {
    s.state = 'air';
    grab = 0.3;
    arc(s, rackX + 2, rackTop() - 3, 0.45, 7, () => {
      s.dead = true; state.ai += 1;
    });
  }

  function step(dt) {
    time += dt;
    spawnIn -= dt;
    if (spawnIn <= 0) {
      spawnIn = 1.05 + Math.random() * 0.5;
      sticks.push({x: beltStart - 6, y: beltY - 3, state: 'belt'});
    }
    for (const s of sticks) {
      if (s.state === 'belt') {
        s.x += 13 * dt;
        if (s.x >= bossX - 6) {
          sinceToss += 1;
          if (sinceToss >= tossEvery) {
            sinceToss = 0; tossEvery = 10 + Math.floor(Math.random() * 5);
            toPeople(s, false);
            if (!bubble || !bubble.angry) say(TOSS, 2);
          }
          else hoard(s);
        }
      } else if (s.state === 'air') {
        s.t += dt;
        const p = Math.min(1, s.t / s.d);
        s.x = s.from[0] + (s.to[0] - s.from[0]) * p;
        s.y = s.from[1] + (s.to[1] - s.from[1]) * p - s.h * 4 * p * (1 - p);
        if (p >= 1) s.then();
      }
    }
    sticks = sticks.filter(s => !s.dead);
    if (Math.random() < dt * 3) smoke.push({x: factoryX + 20 + Math.random() * 2, y: gy - 27, t: 0});
    smoke.forEach(p => { p.t += dt; p.y -= 4 * dt; p.x += 2.5 * dt; });
    smoke = smoke.filter(p => p.t < 2.6 && p.y > -4);
    crowd.forEach(p => { p.jump = Math.max(0, p.jump - dt); p.holding = Math.max(0, p.holding - dt); });
    popups.forEach(p => { p.t += dt; });
    popups = popups.filter(p => p.t < 1.1);
    grab = Math.max(0, grab - dt);
    if (board.length && (boardIn -= dt) <= 0) { boardAt = (boardAt + 1) % board.length; boardIn = 6; }
    if (bubble) { bubble.t -= dt; if (bubble.t <= 0) bubble = null; }
    else if ((bubbleIn -= dt) <= 0) say(IDLE, 3);
  }

  /* Drawing. */
  function drawFactory(c) {
    const x = factoryX, top = gy - 22;
    rect(c, P.g, x, top + 7, 24, 22 - 7);
    for (let i = 0; i < 3; i++) for (let r = 0; r < 5; r++) rect(c, P.k, x + i * 8, top + 2 + r, r + 2, 1);  // sawtooth roof
    rect(c, P.k, x, top + 7, 24, 1);
    rect(c, P.k, x + 18, top - 4, 3, 11);               // chimney
    rect(c, P.r, x + 18, top - 2, 3, 1);
    for (let i = 0; i < 4; i++) {                         // windows, blinking
      const on = Math.sin(time * 2 + i * 1.7) > -0.6;
      rect(c, on ? P.c : P.l, x + 2 + i * 4, top + 10, 2, 2);
    }
    rect(c, P.r, x + 2, top + 15, 12, 3);                 // red sign
    rect(c, P.w, x + 3, top + 16, 1, 1); rect(c, P.w, x + 6, top + 16, 1, 1); rect(c, P.w, x + 9, top + 16, 2, 1);
    rect(c, P.k, x + 18, beltY - 4, 6, 5);                // hatch the belt comes out of
    rect(c, P.k, x + 19, gy - 6, 4, 6);                   // door
  }
  function drawBelt(c) {
    rect(c, P.k, beltStart - 1, beltY, bossX - beltStart + 2, 2);
    const shift = Math.floor(time * 13) % 4;
    for (let x = beltStart + shift; x < bossX; x += 4) rect(c, P.l, x, beltY, 1, 1);
    for (const lx of [beltStart + 1, bossX - 2]) rect(c, P.g, lx, beltY + 2, 1, gy - beltY - 2);
  }
  function drawRack(c) {
    const topY = rackTop();
    rect(c, P.k, rackX, topY, 11, gy - topY);
    for (let y = topY + 2; y < gy - 1; y += 3) {
      rect(c, P.g, rackX + 1, y, 9, 2);
      const blink = Math.sin(time * 6 + y) > 0;
      rect(c, blink ? P.o : P.l, rackX + 8, y, 1, 1);
      rect(c, Math.sin(time * 4 + y * 2) > 0.3 ? P.b : P.g, rackX + 6, y, 1, 1);
    }
    rect(c, P.r, rackX, topY - 1, 11, 1);
    sprite(c, STICK, rackX + 2, topY - 4);                 // the latest stick on top of the pile
  }
  function drawBoss(c) {
    const by = gy - BOSS.length;
    sprite(c, BOSS, bossX, by);
    if (grab > 0) rect(c, P.s, bossX - 2, by + 9, 2, 1);  // reaching for the belt
  }
  function drawCrowd(c) {
    for (const p of crowd) {
      const lift = p.jump > 0 ? Math.round(Math.sin((p.jump / 0.45) * Math.PI) * 3) : 0;
      const y = gy - 7 - lift;
      rect(c, P.s, p.x + 1, y, 2, 2);
      rect(c, p.shirt, p.x, y + 2, 4, 3);
      rect(c, P.k, p.x + 1, y + 5, 1, 2 - (lift ? 1 : 0)); rect(c, P.k, p.x + 2, y + 5, 1, 2 - (lift ? 1 : 0));
      if (p.holding > 0) sprite(c, STICK, p.x - 2, y - 4);
    }
  }
  function drawScene() {
    const c = octx;
    c.clearRect(0, 0, LW, LH);
    rect(c, '#d9d6cf', 0, gy, LW, LH - gy);
    for (const p of smoke) {
      c.globalAlpha = Math.max(0, 0.5 - p.t / 6);
      rect(c, P.l, p.x, p.y, 2 + Math.floor(p.t), 2 + Math.floor(p.t));
    }
    c.globalAlpha = 1;
    drawFactory(c);
    drawBelt(c);
    drawRack(c);
    drawBoss(c);
    drawCrowd(c);
    for (const s of sticks) sprite(c, STICK, Math.round(s.x), Math.round(s.y));
  }
  const money = value => value == null ? '…' : new Intl.NumberFormat(boot.lang === 'ko' ? 'ko-KR' : 'en-US',
    {style: 'currency', currency: state.currency, maximumFractionDigits: 0}).format(value);
  function drawText() {
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const cx = W / 2;
    ctx.font = '800 14px "Pretendard Variable", Pretendard, system-ui, sans-serif';
    ctx.fillStyle = '#e8483c';
    const small = W < 640;
    const c = state.change, arrow = c == null || Math.abs(c) < 0.05 ? '' : ` ${c > 0 ? '▲' : '▼'} ${Math.abs(c).toFixed(1)}%`;
    ctx.font = `800 ${small ? 13 : 14}px "Pretendard Variable", Pretendard, system-ui, sans-serif`;
    const priceText = fmt('gamePrice', {price: money(state.real)}) + arrow;
    const hist = state.history, bars = hist.length > 1 ? Math.min(hist.length, 14) : 0;
    const histW = bars ? bars * 4 + 8 : 0, textW = ctx.measureText(priceText).width;
    ctx.fillText(priceText, cx - histW / 2, 12);
    if (bars) {  // price record: one bar per day, today in red
      const pts = hist.slice(-bars), lo = Math.min(...pts), hi = Math.max(...pts);
      const bx = cx - histW / 2 + textW / 2 + 8;
      pts.forEach((v, i) => {
        const h = 4 + (hi === lo ? 6 : Math.round((v - lo) / (hi - lo) * 10));
        ctx.fillStyle = i === pts.length - 1 ? '#e8483c' : '#c9c6bf';
        ctx.fillRect(bx + i * 4, 26 - h, 3, h);
      });
    }
    // Second line: the hint until the first grab, then the reasons board (fading between items).
    ctx.font = '600 12px "Pretendard Variable", Pretendard, system-ui, sans-serif';
    if (!state.touched || !board.length) {
      ctx.fillStyle = '#8b8e94';
      ctx.fillText((coarse ? T.gameHintTouch : T.gameHint) || '', cx, 32);
    } else {
      const item = board[boardAt], fade = Math.min(1, boardIn / 0.4, (6 - boardIn) / 0.4);
      ctx.globalAlpha = Math.max(0, Math.min(1, fade));
      ctx.font = '600 12px "Pretendard Variable", Pretendard, system-ui, sans-serif';
      ctx.fillStyle = item.news ? '#2563eb' : '#141414';
      let text = item.text;
      const max = Math.min(W - 40, small ? W - 24 : W * 0.56);
      while (ctx.measureText(text).width > max && text.length > 8) text = text.slice(0, -2);
      if (text !== item.text) text = text.trimEnd() + '…';
      ctx.fillText(text, cx, 32);
      ctx.globalAlpha = 1;
    }
    // Scoreboard, small, over the data center: what the boss took, what reached people.
    ctx.font = '700 11px "Pretendard Variable", Pretendard, system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillStyle = '#54565c';
    ctx.fillText(fmt('gameCount', {ai: state.ai, people: state.people}), W - 12, y0 + (gy - 14) * S - 34 > 50 ? y0 + 6 : 52);
    ctx.textAlign = 'center';
    // Popups over rescued sticks.
    ctx.font = '800 12px "Pretendard Variable", Pretendard, system-ui, sans-serif';
    for (const p of popups) {
      ctx.globalAlpha = 1 - p.t / 1.1;
      ctx.fillStyle = '#16a34a';
      ctx.fillText(T.gameSavedPop || '+1', p.x * S, y0 + (p.y - p.t * 6) * S - 14);
    }
    ctx.globalAlpha = 1;
    if (bubble) {  // speech bubble left of the boss's head
      ctx.font = `${bubble.angry ? 800 : 700} 12px "Pretendard Variable", Pretendard, system-ui, sans-serif`;
      const pad = 8, w = ctx.measureText(bubble.text).width + pad * 2, h = 24;
      const right = bossX * S - 6, top = y0 + (gy - BOSS.length) * S - 4;
      const left = Math.max(6, right - w);
      ctx.fillStyle = bubble.angry ? '#fff1ef' : '#ffffff'; ctx.strokeStyle = bubble.angry ? '#e8483c' : '#1d2027'; ctx.lineWidth = 2;
      ctx.beginPath(); ctx.roundRect(left, top, w, h, 6); ctx.fill(); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(right - 2, top + 8); ctx.lineTo(right + 6, top + 13); ctx.lineTo(right - 2, top + 17); ctx.fill();
      ctx.fillStyle = bubble.angry ? '#b8352b' : '#1d2027'; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillText(bubble.text, left + pad, top + h / 2 + 1);
    }
  }
  function draw() {
    if (!LW) return;
    drawScene();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, y0, LW * S, LH * S);
    drawText();
  }

  /* Clicking a stick on its way to the data center sends it to the people. */
  function pointer(event) {
    const b = canvas.getBoundingClientRect();
    const lx = (event.clientX - b.left) / S, ly = (event.clientY - b.top - y0) / S;
    const reach = event.pointerType === 'touch' ? 7 : 5;
    let best = null, bestD = Infinity;
    for (const s of sticks) {
      if (s.state === 'air' && s.then && s.to[0] < bossX) continue;  // already going to the people
      const dx = lx - (s.x + 3.5), dy = ly - (s.y + 1.5), d = dx * dx + dy * dy;
      if (Math.abs(dx) <= reach && Math.abs(dy) <= reach && d < bestD) { best = s; bestD = d; }
    }
    if (!best) return;
    state.touched = true;
    state.saved += 1;
    popups.push({x: best.x + 3, y: best.y, t: 0});
    toPeople(best, true);
    say(ANGRY, 2.2, true);  // the boss does not like sharing
    grab = 0.3;
    wake();
  }

  /* Loop: about 30 frames a second, paused when the hero is off screen or the tab is hidden. */
  let raf = 0, last = 0, visible = true;
  function frame(now) {
    const dt = Math.min(0.1, (now - last) / 1000);
    if (dt >= 1 / 32) { last = now; step(dt); draw(); }
    raf = visible && !document.hidden ? requestAnimationFrame(frame) : 0;
  }
  function wake() {
    if (raf || reduced || !visible || document.hidden) { if (reduced) draw(); return; }
    last = performance.now();
    raf = requestAnimationFrame(frame);
  }

  document.addEventListener('qt:prices', event => {
    const data = event.detail || {};
    const p = (data.products || []).find(x => x.id === 'samsung-ddr5-32');
    if (!p || p.price == null) return;
    state.currency = data.currency || 'KRW';
    state.real = p.price;
    state.change = p.change;
    state.history = (p.history || []).map(x => x.price).filter(Number.isFinite);
    buildBoard();
    draw();
  });

  /* Reasons board: the real daily change gets a joke; real headlines follow, marked as news. */
  let headlines = [];
  function buildBoard() {
    const items = [];
    if (state.real != null) {
      const c = state.change, dir = c == null || Math.abs(c) < 0.05 ? 'Flat' : c > 0 ? 'Up' : 'Down';
      const jokes = [1, 2, 3].map(n => T[`gameWhy${dir}${n}`]).filter(Boolean);
      const change = dir === 'Flat' ? T.gameNoChange : fmt('gameChange', {pct: `${c > 0 ? '▲' : '▼'} ${Math.abs(c).toFixed(1)}%`});
      jokes.forEach(j => items.push({text: `${change} · ${j}`}));
    }
    headlines.slice(0, 4).forEach(h => items.push({text: `📰 ${h.title} — ${h.publisher}`, news: true}));
    // Alternate: joke, news, joke, news...
    const jokesOnly = items.filter(i => !i.news), news = items.filter(i => i.news);
    board = [];
    for (let i = 0; i < Math.max(jokesOnly.length, news.length); i++) {
      if (jokesOnly[i]) board.push(jokesOnly[i]);
      if (news[i]) board.push(news[i]);
    }
    boardAt = 0; boardIn = 6;
  }
  const newsUrl = boot.static ? `${boot.base || ''}/data/news-${boot.lang}.json` : `/api/news?lang=${boot.lang}`;
  fetch(newsUrl, {cache: 'no-cache'}).then(r => r.ok ? r.json() : null).then(data => {
    headlines = (data?.news || []).filter(n => n.category === 'ram');
    buildBoard();
  }).catch(() => {});

  function start() {
    layout();
    if (reduced) {  // a still picture: a few sticks on the belt and some already hoarded
      state.ai = 24;
      sticks = [0.2, 0.5, 0.8].map(f => ({x: beltStart + (bossX - beltStart - 8) * f, y: beltY - 3, state: 'belt'}));
      draw();
    }
    canvas.addEventListener('pointerdown', pointer);
    canvas.style.cursor = 'pointer';
    new ResizeObserver(layout).observe(root);
    new IntersectionObserver(entries => {
      visible = entries.some(e => e.isIntersecting);
      if (visible) wake();
    }).observe(root);
    document.addEventListener('visibilitychange', wake);
    wake();
  }
  (document.fonts ? document.fonts.load('800 14px "Pretendard Variable"').catch(() => {}) : Promise.resolve()).then(start, start);
})();
