'use strict';
// Hero: a 16-bit style RAM tycoon. A brick factory makes RAM, a conveyor carries it to the AI boss's
// data center where he keeps almost all of it; now and then he grudgingly tosses one to the people.
// Click (or tap) a stick on its way to the data center to grab it for the people.
// The caption shows today's real DDR5 32GB price (updated once a day); the game never changes it.
// Plain Canvas 2D, no dependencies. A still frame under reduced motion.
(() => {
  const root = document.getElementById('hero');
  const canvas = document.getElementById('hero-canvas');
  if (!root || root.hidden || !canvas) return;
  const ctx = canvas.getContext('2d');
  const content = document.getElementById('hero-content');
  const boot = JSON.parse(document.getElementById('boot')?.textContent || '{}');
  const T = boot.t || {};
  const fmt = (key, vars = {}) => String(T[key] ?? '').replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? '');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const coarse = matchMedia('(hover: none), (pointer: coarse)').matches;
  const FONT = '"Pretendard Variable", Pretendard, system-ui, sans-serif';

  /* Palette: a warm 16-bit console look, every sprite outlined in near-black. */
  const C = {
    K: '#1a1c24',
    sky1: '#9fd3f2', sky2: '#c3e5f7', sky3: '#e3f2f8', sky4: '#f6f1e4',
    far1: '#b9cfe0', far2: '#a6bfd4', farWin: '#d9e7f2',
    grass1: '#79b84a', grass2: '#5a9636', dirt1: '#d9c49b', dirt2: '#c6ad7f', dirt3: '#e6d6b3',
    brick1: '#7a3529', brick2: '#a44a35', brick3: '#c86a4c', mortar: '#5e2a21',
    roof1: '#2f3747', roof2: '#495468', roof3: '#6c7a92', glass1: '#7ec4e6', glass2: '#b9e3f5',
    win1: '#f7b84a', win2: '#ffe08a', winOff: '#4d5668',
    steel1: '#3d4250', steel2: '#5c6374', steel3: '#868ea0',
    dc1: '#1f2b45', dc2: '#2e3f63', dc3: '#45598a', neon: '#ff4d5e', neon2: '#ffb3ba',
    led1: '#39e07a', led2: '#4db8ff', led3: '#ff6b5e',
    pcb1: '#2c7a3c', pcb2: '#49a85a', chip: '#23262e', gold: '#e8b84a',
    skin1: '#f4cba3', skin2: '#d9a27a', white: '#ffffff', smoke1: '#e9e9ef', smoke2: '#c7c9d3',
  };

  /* Sprites: rows of palette keys ('.' is transparent). */
  const STICK = ['KKKKKKKKK', 'KacbcbcaK', 'KbbbbbbbK', 'KgKgKgKgK'];
  const STICK_PAL = {K: C.K, a: C.pcb2, b: C.pcb1, c: C.chip, g: C.gold};
  // The boss: a caricature in the spirit of the 'quite terrible' quote. Tousled light-brown hair with a
  // side part, fair skin, big round eyes, a pleased little smile, a plain gray crewneck sweater.
  const BOSS = [
    '.....KKKKKK.....',
    '....KdhhHHhK....',
    '...KdhhHHHhhK...',
    '..KdhhhhHhhhdK..',
    '..KdhsssshhhdK..',
    '..KdssssssshdK..',
    '..KsbbssssbbsK..',
    '..KswesssswesK..',
    '..KswesssswesK..',
    '..KSssssSssmSK..',
    '...KSsmmmssSK...',
    '....KSSssSSK....',
    '.....KKSSKK.....',
    '...KK222222KK...',
    '..K2233333322K..',
    '.K223333333322K.',
    '.K22K3333333K2K.',
    '.KssK3322223KsK.',
    '..KKK2222222KKK.',
    '....KjjjjjjjK...',
    '....KjjK.KjjK...',
    '....KjjK.KjjK...',
    '...KOOOK.KOOOK..',
    '...KKKKK.KKKKK..',
  ];
  const BOSS_ANGRY = BOSS.slice();
  BOSS_ANGRY[5] = '..KdbssssssbdK..';
  BOSS_ANGRY[6] = '..KssbbssbbssK..';
  BOSS_ANGRY[7] = '..KsKesssseKsK..';
  BOSS_ANGRY[8] = '..KssssssssssK..';
  BOSS_ANGRY[9] = '..KSssssSsssSK..';
  BOSS_ANGRY[10] = '...KSsKKKKsSK...';
  BOSS_ANGRY[11] = '....KSmmmmSK....';
  const ANGER_MARK = ['.r.r.', 'rr.rr', '.....', 'rr.rr', '.r.r.'];  // the cartoon "vein pop"
  const BOSS_PAL = {K: C.K, d: '#5c3a26', h: '#8a5a3c', H: '#a8754f', s: '#f6d3b8', S: '#e3b394', b: '#5c3a26',
    w: '#ffffff', e: '#2b3a55', m: '#c4675c', 1: '#5f6878', 2: '#7d8696', 3: '#9aa2b1', j: '#34436a', J: '#25304d', O: '#e9e9e9'};
  const PERSON = [
    '..KKKK..',
    '.KhhhhK.',
    '.KhsssK.',
    '.KsKsKK.',
    '..KssK..',
    '.KKccKK.',
    'KccccCCK',
    'KscccCsK',
    '.KccCCK.',
    '.KppppK.',
    '.KpKKpK.',
    '.KK..KK.',
  ];
  const CHEER = PERSON.slice();
  CHEER[5] = 'sKKccKKs'; CHEER[6] = 'KccccCCK'; CHEER[7] = '.KcccCK.';
  const HAIR = ['#4a3324', '#1a1c24', '#8a5a2b', '#c98a3a', '#6b6f7a'];
  const SKIN = [[C.skin1, C.skin2], ['#d9a27a', '#b9805a'], ['#a8704a', '#87553a']];
  const SHIRT = [['#e8483c', '#b8352b'], ['#3d7be0', '#2a5bb0'], ['#3faa5a', '#2c7e42'], ['#f0a03a', '#c27a20'],
    ['#8a5ad6', '#6a3fb0'], ['#e05a9a', '#b03f78'], ['#2fb3b0', '#20837f']];
  const FONT3 = {  // 3x5 pixel letters for signs
    R: ['11.', '1.1', '11.', '1.1', '1.1'], A: ['.1.', '1.1', '111', '1.1', '1.1'], M: ['1.1', '111', '111', '1.1', '1.1'],
    I: ['111', '.1.', '.1.', '.1.', '111'],
  };
  function sprite(c, rows, x, y, pal, flip = false) {
    for (let j = 0; j < rows.length; j++) {
      const row = rows[j];
      for (let i = 0; i < row.length; i++) {
        const ch = row[flip ? row.length - 1 - i : i];
        if (ch === '.') continue;
        c.fillStyle = pal[ch];
        c.fillRect(x + i, y + j, 1, 1);
      }
    }
  }
  const px = (c, color, x, y, w = 1, h = 1) => { c.fillStyle = color; c.fillRect(Math.round(x), Math.round(y), w, h); };
  function word(c, text, x, y, color, scale = 1) {
    for (const ch of text) {
      const glyph = FONT3[ch];
      if (glyph) glyph.forEach((row, j) => [...row].forEach((v, i) => { if (v === '1') px(c, color, x + i * scale, y + j * scale, scale, scale); }));
      x += 4 * scale;
    }
  }

  /* Layout: the scene fills the band above the headline, drawn at low resolution and scaled up. */
  const off = document.createElement('canvas');
  const octx = off.getContext('2d');
  let W = 1, H = 1, dpr = 1, S = 3, LW = 100, LH = 60, y0 = 0;
  let gy, beltY, fx, beltStart, dcX, bossX, crowd = [], skyline = [], clouds = [];
  function layout() {
    W = root.clientWidth; H = root.clientHeight;
    dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    S = W < 640 ? 2 : 3;
    const top = content ? content.offsetTop : H;
    LH = Math.max(52, Math.min(86, Math.floor((top - 6) / S)));
    LW = Math.ceil(W / S);
    y0 = Math.max(0, top - 6 - LH * S);
    off.width = LW; off.height = LH;
    gy = LH - 5;                                   // top of the ground
    beltY = gy - 19;
    fx = W < 640 ? 2 : Math.max(6, Math.round(LW * 0.06));
    beltStart = fx + 44;
    dcX = LW - 38 - (W < 640 ? 2 : Math.max(6, Math.round(LW * 0.06)));
    bossX = dcX - 17;
    const left = beltStart + 3, right = bossX - 2;
    const n = Math.max(2, Math.min(8, Math.floor((right - left) / (W < 640 ? 18 : 24))));  // fewer people on narrow screens
    crowd = Array.from({length: n}, (_, i) => crowd[i] || {
      jump: 0, holding: 0, hair: HAIR[(i * 3) % HAIR.length], skin: SKIN[(i * 2) % SKIN.length],
      shirt: SHIRT[i % SHIRT.length], phase: Math.random() * 6,
    });
    crowd.forEach((p, i) => { p.x = Math.round(left + (i + 0.5) * (right - left) / n) - 4; });
    // Distant city: fixed per width so it does not flicker on resize.
    skyline = [];
    let seed = 7;
    const rand = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
    for (const far of [true, false]) {  // far row (taller, paler), then near row
      for (let x = -4 - Math.floor(rand() * 6); x < LW;) {
        const w = 12 + Math.floor(rand() * 12);
        const h = Math.round((far ? LH * 0.36 : LH * 0.22) * (0.65 + rand() * 0.5));
        skyline.push({x, w, h, far, kind: Math.floor(rand() * 4), seed: Math.floor(rand() * 100)});
        x += w + (far ? 1 : 2 + Math.floor(rand() * 4));
      }
    }
    if (!clouds.length) clouds = [0.12, 0.45, 0.78].map((f, i) => ({x: f * LW, y: 4 + i * 5 % 12, speed: 1.2 + i * 0.5}));
    draw();
  }

  /* Game state. */
  const state = {ai: 0, people: 0, saved: 0, real: null, change: null, history: [], currency: 'KRW', touched: false};
  // Clicker record: how many sticks this visitor has ever grabbed, kept in this browser only.
  const RECORD = 'qt-rescued';
  let record = 0;
  try { record = Math.max(0, parseInt(localStorage.getItem(RECORD), 10) || 0); } catch {}
  function saveRecord() { try { localStorage.setItem(RECORD, String(record)); } catch {} }
  // Worldwide total: a public counter shared by every visitor (Abacus, no key; +1 per grab).
  // Grabs are sent one at a time, a little apart, to stay well under its rate limit.
  const COUNTER = 'https://abacus.jasoncameron.dev';
  const COUNTER_KEY = 'quiteterrible/ram-saved-world';
  let world = null, pending = 0, sending = false;
  function readWorld() {
    fetch(`${COUNTER}/get/${COUNTER_KEY}`, {cache: 'no-store'})
      .then(r => r.status === 404 ? {value: 0} : r.ok ? r.json() : null)
      .then(d => { if (d && Number.isFinite(d.value)) { world = d.value; draw(); } })
      .catch(() => {});
  }
  function sendGrabs() {
    if (sending || !pending) return;
    sending = true;
    fetch(`${COUNTER}/hit/${COUNTER_KEY}`, {cache: 'no-store'})
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d && Number.isFinite(d.value)) { pending -= 1; world = d.value; } })
      .catch(() => {})
      .finally(() => { sending = false; if (pending) setTimeout(sendGrabs, 400); });
  }
  readWorld();
  setInterval(() => { if (visible && !document.hidden && !pending) readWorld(); }, 30000);
  let board = [], boardAt = 0, boardIn = 0;  // the real daily change, with a joke from the boss's world
  let sticks = [], smoke = [], popups = [], spawnIn = 0.6, tossEvery = 11, sinceToss = 0;
  let bubble = null, bubbleIn = 4, grab = 0, time = 0;
  const pick = keys => { const list = keys.map(k => T[k]).filter(Boolean); return list[Math.floor(Math.random() * list.length)]; };
  // Every gameLineN / gameAngryN / gameTossN string in config/i18n.json is used; add lines there.
  const linesFor = prefix => Object.keys(T).filter(k => new RegExp(`^${prefix}\\d+$`).test(k));
  const IDLE = linesFor('gameLine'), ANGRY = linesFor('gameAngry'), TOSS = linesFor('gameToss');
  function say(keys, seconds, angry = false) {
    const text = pick(keys);
    if (text) { bubble = {text, t: seconds, angry, at: time}; bubbleIn = 8 + Math.random() * 6; }
  }
  function arc(s, x1, y1, d, h, then) { Object.assign(s, {from: [s.x, s.y], to: [x1, y1], d, h, t: 0, then}); }
  function toPeople(s, mine) {
    const person = crowd[Math.floor(Math.random() * crowd.length)];
    s.state = 'air'; s.toPeople = true;
    arc(s, person.x - 1, gy - 17, mine ? 0.8 : 1.0, mine ? 12 : 18, () => {
      s.dead = true; person.jump = 0.5; person.holding = 6; state.people += 1;
    });
  }
  const pileTop = () => gy - 31 - Math.min(14, Math.floor(state.ai / 4));
  function hoard(s) {
    s.state = 'air'; grab = 0.3;
    arc(s, dcX + 14 + (state.ai % 3) * 3 - 3, pileTop() - 2, 0.5, 9, () => { s.dead = true; state.ai += 1; });
  }

  function step(dt) {
    time += dt;
    if ((spawnIn -= dt) <= 0) {
      spawnIn = 1.0 + Math.random() * 0.5;
      sticks.push({x: beltStart - 8, y: beltY - 4, state: 'belt'});
    }
    for (const s of sticks) {
      if (s.state === 'belt') {
        s.x += 15 * dt;
        if (s.x >= bossX - 7) {
          if (++sinceToss >= tossEvery) {
            sinceToss = 0; tossEvery = 10 + Math.floor(Math.random() * 5);
            toPeople(s, false);
            if (!bubble || !bubble.angry) say(TOSS, 2);
          } else hoard(s);
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
    if (Math.random() < dt * 4) smoke.push({x: fx + 33 + Math.random() * 3, y: gy - 40, t: 0, r: 1 + Math.random()});
    smoke.forEach(p => { p.t += dt; p.y -= 5 * dt; p.x += 3 * dt; });
    smoke = smoke.filter(p => p.t < 3 && p.y > -6);
    clouds.forEach(cl => { cl.x += cl.speed * dt; if (cl.x > LW + 20) cl.x = -24; });
    crowd.forEach(p => { p.jump = Math.max(0, p.jump - dt); p.holding = Math.max(0, p.holding - dt); });
    popups.forEach(p => { p.t += dt; });
    popups = popups.filter(p => p.t < 1.1);
    grab = Math.max(0, grab - dt);
    if (board.length && (boardIn -= dt) <= 0) { boardAt = (boardAt + 1) % board.length; boardIn = 6; }
    if (bubble) { bubble.t -= dt; if (bubble.t <= 0) bubble = null; }
    else if ((bubbleIn -= dt) <= 0) say(IDLE, 3);
  }

  /* Drawing, back to front. */
  function drawSun(c) {
    const sx = Math.round(LW * 0.2), sy = 9, r = 5;
    for (let j = -r; j <= r; j++) for (let i = -r; i <= r; i++) {
      const d = i * i + j * j;
      if (d <= r * r) px(c, d <= (r - 2) * (r - 2) ? '#ffe9a3' : '#ffd166', sx + i, sy + j);
    }
    const ray = Math.floor(time * 2) % 2;  // rays twinkle
    for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0], [1, 1], [-1, -1], [1, -1], [-1, 1]]) {
      const len = dx && dy ? 7 + ray : 8 + (1 - ray);
      px(c, '#ffd166', sx + dx * len, sy + dy * len);
    }
  }
  function drawBirds(c) {
    for (let i = 0; i < 3; i++) {
      const x = ((time * (6 + i * 2) + i * LW * 0.37) % (LW + 30)) - 15, y = 6 + i * 4 + Math.sin(time * 2 + i) * 1.5;
      const flap = Math.floor(time * 6 + i) % 2;
      px(c, C.K, x, y + flap, 1, 1); px(c, C.K, x + 1, y + 1, 1, 1); px(c, C.K, x + 2, y + flap, 1, 1);
    }
  }
  function drawBushes(c) {
    const spots = [fx - 6, fx + 46, dcX - 24, dcX + 38];
    for (const bx of spots) {
      if (bx < -6 || bx > LW) continue;
      px(c, C.K, bx, gy - 4, 8, 4); px(c, '#4f9a3e', bx + 1, gy - 4, 6, 4); px(c, '#6cbb53', bx + 2, gy - 4, 3, 1);
      px(c, '#e8483c', bx + 5, gy - 3); // a berry
    }
    for (const lx of [Math.round(LW * 0.33), Math.round(LW * 0.62)]) {  // street lamps
      if (lx < beltStart + 2 || lx > bossX - 4) continue;
      px(c, C.K, lx, gy - 22, 1, 22); px(c, C.K, lx - 1, gy - 23, 4, 2); px(c, '#ffe08a', lx, gy - 22, 2, 1);
    }
  }
  // A horizon packed with data centers: server halls, cooling towers, blinking racks, "AI" signs.
  function drawServerHall(c, b) {
    const top = gy - b.h, x = b.x, w = b.w;
    const body = b.far ? '#9fb2c8' : '#6f84a3', dark = b.far ? '#8ea2ba' : '#5a6d8c', edge = b.far ? '#b7c7d8' : '#8aa0bf';
    const ledOn = b.far ? ['#d6f5e0', '#d4ecff'] : [C.led1, C.led2];
    px(c, body, x, top, w, b.h);
    px(c, edge, x, top, w, 1);
    for (let i = 3; i < w - 1; i += 6) px(c, dark, x + i, top + 2, 1, b.h - 2);  // panel seams
    // Rows of rack lights; a few blink.
    for (let y = top + 3; y < gy - 2; y += 3) for (let i = x + 1; i < x + w - 1; i += 2) {
      const k = (i * 7 + y * 13 + b.seed) % 11;
      if (k > 3) continue;
      const blink = k === 0 ? Math.sin(time * 4 + i + y) > 0 : true;
      px(c, blink ? ledOn[k % 2] : dark, i, y);
    }
    // Roof gear by building kind: cooling fans, a cooling tower, an antenna, or an "AI" sign.
    if (b.kind === 0) {
      for (let i = x + 2; i < x + w - 4; i += 6) { px(c, dark, i, top - 2, 4, 2); px(c, edge, i + (Math.floor(time * 8) % 2) * 2, top - 2, 2, 1); }
    } else if (b.kind === 1) {
      const tw = Math.min(8, w - 4), tx = x + 2;
      for (let r = 0; r < 7; r++) { const inset = r < 3 ? 2 - r : r > 4 ? r - 4 : 0; px(c, b.far ? '#c7d4e2' : '#a9b9cf', tx + inset, top - 7 + r, tw - inset * 2, 1); }
      px(c, C.smoke1, tx + 2, top - 9 - (Math.floor(time * 2) % 2), tw - 4, 2);  // vapor
    } else if (b.kind === 2) {
      px(c, dark, x + w - 4, top - 8, 1, 8); px(c, Math.sin(time * 3 + b.seed) > 0 ? C.led3 : dark, x + w - 4, top - 9);
    } else if (!b.far && w >= 14) {
      px(c, '#2a1a2e', x + 2, top - 6, 11, 6);
      c.globalAlpha = 0.7 + Math.sin(time * 4 + b.seed) * 0.3;
      word(c, 'AI', x + 4, top - 6, C.neon);
      c.globalAlpha = 1;
    }
  }
  function drawBackdrop(c) {
    drawSun(c);
    for (const b of skyline) drawServerHall(c, b);
    for (const cl of clouds) {
      const x = Math.round(cl.x), y = cl.y;
      px(c, C.white, x + 3, y, 8, 1); px(c, C.white, x + 1, y + 1, 14, 2); px(c, C.white, x, y + 3, 18, 2);
      px(c, C.smoke1, x + 1, y + 5, 16, 1);
    }
    drawBirds(c);
  }
  function drawGround(c) {
    px(c, C.grass1, 0, gy, LW, 1); px(c, C.grass2, 0, gy + 1, LW, 1);
    px(c, C.dirt1, 0, gy + 2, LW, LH - gy - 2);
    for (let x = (Math.floor(time * 0) % 4); x < LW; x += 4) px(c, C.dirt3, x, gy + 3);
    for (let x = 2; x < LW; x += 7) px(c, C.dirt2, x, gy + 4);
  }
  function brickWall(c, x, y, w, h) {
    px(c, C.brick2, x, y, w, h);
    for (let j = 0; j < h; j++) {
      if (j % 3 === 2) { px(c, C.mortar, x, y + j, w, 1); continue; }
      const offset = Math.floor(j / 3) % 2 ? 2 : 0;
      for (let i = offset; i < w; i += 5) px(c, C.mortar, x + i, y + j);
      if (j % 3 === 0) for (let i = offset + 1; i < w; i += 5) px(c, C.brick3, x + i, y + j, 3, 1);
    }
  }
  function drawFactory(c) {
    const x = fx, top = gy - 26;
    // Smokestack.
    brickWall(c, x + 32, gy - 40, 6, 14);
    px(c, C.K, x + 31, gy - 41, 8, 2); px(c, C.steel2, x + 32, gy - 41, 6, 1);
    px(c, C.white, x + 32, gy - 36, 6, 1); px(c, C.white, x + 32, gy - 33, 6, 1);
    px(c, C.K, x + 31, gy - 40, 1, 14); px(c, C.K, x + 38, gy - 40, 1, 14);
    // Sawtooth roof with skylights.
    for (let t = 0; t < 4; t++) {
      const tx = x + t * 11;
      for (let r = 0; r < 7; r++) {
        px(c, r === 0 ? C.roof3 : C.roof2, tx, top - r, 10 - Math.floor(r * 1.4), 1);
        px(c, C.K, tx + 10 - Math.floor(r * 1.4), top - r, 1, 1);
      }
      px(c, C.glass1, tx + 9, top - 6, 1, 6); px(c, C.glass2, tx + 10, top - 5, 1, 5);
      px(c, C.K, tx, top - 7, 2, 1);
    }
    px(c, C.roof1, x, top, 44, 2); px(c, C.K, x - 1, top + 2, 46, 1);
    // Brick hall.
    brickWall(c, x, top + 3, 44, gy - top - 3);
    px(c, C.brick3, x, top + 3, 1, gy - top - 3); px(c, C.brick1, x + 43, top + 3, 1, gy - top - 3);
    px(c, C.K, x - 1, top + 2, 1, gy - top - 2); px(c, C.K, x + 44, top + 2, 1, gy - top - 2);
    // Windows with flickering light.
    for (let i = 0; i < 4; i++) {
      const wx = x + 3 + i * 7, wy = top + 6, on = Math.sin(time * 1.7 + i * 2.1) > -0.7;
      px(c, C.K, wx - 1, wy - 1, 6, 6);
      px(c, on ? C.win1 : C.winOff, wx, wy, 4, 4);
      if (on) px(c, C.win2, wx, wy, 2, 2);
      px(c, C.K, wx + 2, wy, 1, 4); px(c, C.K, wx, wy + 2, 4, 1);
    }
    // Sign plate "RAM".
    px(c, C.K, x + 3, gy - 13, 17, 9); px(c, '#d23b30', x + 4, gy - 12, 15, 7); px(c, '#f05a4a', x + 4, gy - 12, 15, 1);
    word(c, 'RAM', x + 6, gy - 11, C.white);
    // Shutter door.
    px(c, C.K, x + 22, gy - 12, 10, 12); px(c, C.steel2, x + 23, gy - 11, 8, 11);
    for (let y = gy - 10; y < gy; y += 2) px(c, C.steel1, x + 23, y, 8, 1);
    px(c, C.steel3, x + 23, gy - 11, 8, 1);
    // Hatch the belt comes out of, with a warning stripe.
    px(c, C.K, x + 37, beltY - 6, 8, 8); px(c, '#14161c', x + 38, beltY - 5, 6, 6);
    for (let i = 0; i < 6; i += 2) { px(c, '#f2c230', x + 38 + i, beltY - 6, 1, 1); }
    // Pipe.
    px(c, C.steel2, x + 41, top + 3, 2, beltY - top - 9); px(c, C.steel3, x + 41, top + 3, 1, beltY - top - 9);
  }
  function drawBelt(c) {
    const len = bossX - beltStart + 2;
    px(c, C.K, beltStart - 1, beltY - 1, len + 1, 5);
    px(c, C.steel2, beltStart, beltY, len - 1, 3);
    px(c, C.steel3, beltStart, beltY, len - 1, 1);
    const shift = Math.floor(time * 15) % 6;
    for (let x = beltStart + shift; x < beltStart + len - 2; x += 6) px(c, C.steel1, x, beltY + 1, 2, 1);
    // Rollers and legs.
    for (let x = beltStart + 3; x < beltStart + len - 3; x += 9) {
      px(c, C.K, x - 1, beltY + 3, 4, 2); px(c, C.steel3, x, beltY + 3, 2, 1);
    }
    for (const lx of [beltStart + 2, beltStart + len - 5]) {
      px(c, C.K, lx - 1, beltY + 4, 4, gy - beltY - 4); px(c, C.steel2, lx, beltY + 4, 2, gy - beltY - 4);
      px(c, C.steel3, lx, beltY + 4, 1, gy - beltY - 4);
    }
  }
  function drawDataCenter(c) {
    const x = dcX, top = gy - 30, w = 36;
    // Hoard pile on the roof: it grows as the boss takes more.
    const pile = Math.min(14, Math.floor(state.ai / 4));
    for (let r = 0; r <= pile; r++) {
      const rowW = Math.max(9, 26 - r * 2), rx = x + Math.floor((w - rowW) / 2);
      for (let i = rx; i + 9 <= rx + rowW + 1; i += 8) sprite(c, STICK, i, top - 4 - r * 2, STICK_PAL);
    }
    // Body.
    px(c, C.K, x - 1, top - 1, w + 2, gy - top + 1);
    px(c, C.dc2, x, top, w, gy - top);
    for (let i = 4; i < w; i += 8) px(c, C.dc1, x + i, top + 1, 1, gy - top - 1);
    px(c, C.dc3, x, top, w, 1); px(c, C.dc3, x, top, 1, gy - top);
    // Rooftop fans.
    for (const fxo of [3, w - 9]) {
      px(c, C.K, x + fxo, top - 3, 6, 3); px(c, C.steel2, x + fxo + 1, top - 2, 4, 1);
      const spin = Math.floor(time * 10) % 2;
      px(c, C.steel3, x + fxo + 1 + spin * 2, top - 3, 2, 1);
    }
    // Neon "AI" sign.
    const glow = 0.75 + Math.sin(time * 5) * 0.25;
    c.globalAlpha = glow;
    px(c, C.K, x + 10, top + 3, 16, 11); px(c, '#3a1020', x + 11, top + 4, 14, 9);
    word(c, 'AI', x + 13, top + 5, C.neon, 1);
    word(c, 'AI', x + 13, top + 5, C.neon2, 1);
    px(c, C.neon, x + 12, top + 11, 12, 1);
    c.globalAlpha = 1;
    // Server windows with blinking LEDs.
    for (let row = 0; row < 2; row++) for (let col = 0; col < 4; col++) {
      const wx = x + 3 + col * 8, wy = top + 16 + row * 6;
      px(c, C.K, wx - 1, wy - 1, 7, 5); px(c, C.dc1, wx, wy, 5, 3);
      const k = row * 4 + col;
      px(c, Math.sin(time * 7 + k) > 0 ? C.led1 : C.dc3, wx + 1, wy + 1);
      px(c, Math.sin(time * 5 + k * 2) > 0.2 ? C.led2 : C.dc3, wx + 3, wy + 1);
      if (k % 3 === 0) px(c, Math.sin(time * 3 + k) > 0.6 ? C.led3 : C.dc3, wx + 2, wy + 2);
    }
    // Door the boss guards.
    px(c, C.K, x + 1, gy - 10, 9, 10); px(c, '#0f1524', x + 2, gy - 9, 7, 9); px(c, C.led2, x + 7, gy - 5);
  }
  const ANGRY_PAL = {...BOSS_PAL, s: '#f7b49c', S: '#e58f74', m: '#8f2a22'};
  function drawBoss(c) {
    const angry = bubble?.angry;
    const since = angry ? time - bubble.at : 1;
    const shake = since < 0.24 ? (Math.floor(since * 25) % 2 ? 1 : -1) : 0;  // one quick jolt, then still
    const by = gy - BOSS.length, bx = bossX + shake;
    sprite(c, angry ? BOSS_ANGRY : BOSS, bx, by, angry ? ANGRY_PAL : BOSS_PAL);
    if (angry) {
      sprite(c, ANGER_MARK, bx + 12, by - 2, {r: '#e8483c'});
    }
    if (grab > 0) {  // reaching for the belt
      px(c, C.K, bossX - 3, by + 13, 4, 3); px(c, C.skin1, bossX - 2, by + 14, 2, 1);
    }
  }
  function drawCrowd(c) {
    for (const p of crowd) {
      const jump = p.jump > 0 ? Math.round(Math.sin((p.jump / 0.5) * Math.PI) * 4) : 0;
      const idle = Math.sin(time * 2 + p.phase) > 0.95 ? 1 : 0;
      const y = gy - PERSON.length - jump - idle;
      const pal = {K: C.K, h: p.hair, s: p.skin[0], c: p.shirt[0], C: p.shirt[1], p: '#3a4566'};
      sprite(c, p.jump > 0 || p.holding > 0 ? CHEER : PERSON, p.x, y, pal);
      if (p.holding > 0) sprite(c, STICK, p.x - 1, y - 5, STICK_PAL);
    }
  }
  function drawScene() {
    const c = octx;
    c.clearRect(0, 0, LW, LH);
    drawBackdrop(c);
    for (const p of smoke) {
      const size = Math.round(2 + p.t * 1.6 + p.r);
      c.globalAlpha = Math.max(0, 0.85 - p.t / 3.2);
      px(c, C.smoke2, p.x, p.y + 1, size, size);
      px(c, C.smoke1, p.x, p.y, size, size - 1);
    }
    c.globalAlpha = 1;
    drawGround(c);
    drawBushes(c);
    drawFactory(c);
    drawDataCenter(c);
    drawBelt(c);
    drawBoss(c);
    drawCrowd(c);
    for (const s of sticks) sprite(c, STICK, Math.round(s.x), Math.round(s.y), STICK_PAL);
  }

  /* Sky behind everything, in 16-bit bands; text drawn crisp over the pixels. */
  function drawSky() {
    const bands = [C.sky1, C.sky2, C.sky3, C.sky4];
    const bottom = y0 + gy * S, step = Math.ceil(bottom / bands.length);
    bands.forEach((color, i) => { ctx.fillStyle = color; ctx.fillRect(0, i * step, W, step + 1); });
    ctx.fillStyle = C.dirt1;
    ctx.fillRect(0, y0 + LH * S - 1, W, H - (y0 + LH * S) + 1);
  }
  const money = value => value == null ? '…' : new Intl.NumberFormat(boot.lang === 'ko' ? 'ko-KR' : 'en-US',
    {style: 'currency', currency: state.currency, maximumFractionDigits: 0}).format(value);
  function outlined(text, x, y, fill) {
    ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineJoin = 'round';
    ctx.strokeText(text, x, y);
    ctx.fillStyle = fill; ctx.fillText(text, x, y);
  }
  function drawText() {
    const small = W < 640, cx = W / 2;
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const c = state.change, arrow = c == null || Math.abs(c) < 0.05 ? '' : ` ${c > 0 ? '▲' : '▼'} ${Math.abs(c).toFixed(1)}%`;
    ctx.font = `800 ${small ? 13 : 15}px ${FONT}`;
    const priceText = fmt('gamePrice', {price: money(state.real)}) + arrow;
    const hist = state.history, bars = hist.length >= 5 ? Math.min(hist.length, 14) : 0;  // only once it means something
    const label = bars ? fmt('gameDays', {n: bars}) : '';
    ctx.font = `700 10px ${FONT}`;
    const labelW = bars ? ctx.measureText(label).width + 6 : 0;
    ctx.font = `800 ${small ? 13 : 15}px ${FONT}`;
    const histW = bars ? bars * 4 + 8 + labelW : 0, textW = ctx.measureText(priceText).width;
    outlined(priceText, cx - histW / 2, 12, '#c8352a');
    if (bars) {  // price record: one bar per recorded day, today in red
      const pts = hist.slice(-bars), lo = Math.min(...pts), hi = Math.max(...pts);
      const bx = cx - histW / 2 + textW / 2 + 8;
      pts.forEach((v, i) => {
        const h = 4 + (hi === lo ? 6 : Math.round((v - lo) / (hi - lo) * 10));
        ctx.fillStyle = C.K; ctx.fillRect(bx + i * 4 - 1, 27 - h, 5, h + 1);
        ctx.fillStyle = i === pts.length - 1 ? '#e8483c' : '#ffffff';
        ctx.fillRect(bx + i * 4, 28 - h, 3, h - 1);
      });
      ctx.font = `700 10px ${FONT}`; ctx.textAlign = 'left';
      outlined(label, bx + bars * 4 + 4, 16, '#54565c');
      ctx.textAlign = 'center';
    }
    // Second line: the hint until the first grab, then the reasons board.
    ctx.font = `700 12px ${FONT}`;
    if (!state.touched || !board.length) {
      outlined((coarse ? T.gameHintTouch : T.gameHint) || '', cx, 34, '#3d4350');
    } else {
      const item = board[boardAt], fade = Math.min(1, boardIn / 0.4, (6 - boardIn) / 0.4);
      ctx.globalAlpha = Math.max(0, Math.min(1, fade));
      outlined(item.text, cx, 34, '#1a1c24');
      ctx.globalAlpha = 1;
    }
    // Scoreboard over the data center.
    ctx.font = `800 11px ${FONT}`; ctx.textAlign = 'right';
    const num = n => n.toLocaleString(boot.lang === 'ko' ? 'ko-KR' : 'en-US');
    outlined(fmt('gameRecord', {n: num(record)}), W - 12, small ? 54 : 14, '#16a34a');
    outlined(fmt('gameWorld', {n: world == null ? '…' : num(world + pending)}), W - 12, small ? 70 : 30, '#2e3f63');
    ctx.textAlign = 'center';
    ctx.font = `800 12px ${FONT}`;
    for (const p of popups) {
      ctx.globalAlpha = 1 - p.t / 1.1;
      outlined(T.gameSavedPop || '+1', p.x * S, y0 + (p.y - p.t * 6) * S - 14, '#16a34a');
    }
    ctx.globalAlpha = 1;
    if (bubble) {  // 16-bit dialogue box left of the boss's head
      ctx.font = `${bubble.angry ? 900 : 700} ${bubble.angry ? 14 : 12}px ${FONT}`;
      const pad = 8, w = Math.ceil(ctx.measureText(bubble.text).width) + pad * 2, h = bubble.angry ? 28 : 24;
      const jolt = bubble.angry && time - bubble.at < 0.24 ? (Math.floor((time - bubble.at) * 25) % 2 ? 1 : -1) : 0;
      const headX = (bossX + 8) * S, headTop = y0 + (gy - BOSS.length) * S;
      let top = headTop - h - 16, left = Math.min(W - w - 8, headX - w + 18), tail = 'down';
      if (top < 54) { top = headTop + 2; left = Math.max(6, bossX * S - 10 - w); tail = 'right'; }
      left = Math.max(6, left) + jolt;
      ctx.fillStyle = C.K; ctx.fillRect(left - 2, top - 2, w + 4, h + 4);
      ctx.fillStyle = bubble.angry ? '#fff1ef' : '#ffffff'; ctx.fillRect(left, top, w, h);
      ctx.fillStyle = bubble.angry ? '#ffd2cc' : '#e8eef6'; ctx.fillRect(left, top + h - 3, w, 3);
      ctx.fillStyle = C.K;
      if (tail === 'down') { ctx.fillRect(headX - 4, top + h + 2, 4, 4); ctx.fillRect(headX - 1, top + h + 7, 3, 3); }
      else { ctx.fillRect(left + w + 2, top + 8, 4, 4); ctx.fillRect(left + w + 6, top + 11, 3, 3); }
      ctx.fillStyle = bubble.angry ? '#c8352a' : C.K; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
      ctx.fillText(bubble.text, left + pad, top + h / 2);
    }
  }
  function draw() {
    if (!LW || gy == null) return;  // not laid out yet
    drawScene();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    drawSky();
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(off, 0, y0, LW * S, LH * S);
    drawText();
  }

  /* 16-bit style sound: square-wave blips made on the fly. Plays only after a click or tap. */
  let audio = null;
  function tone(freq, start, length, type = 'square', volume = 0.05, slide = 0) {
    const osc = audio.createOscillator(), gain = audio.createGain(), t = audio.currentTime + start;
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (slide) osc.frequency.linearRampToValueAtTime(freq + slide, t + length);
    gain.gain.setValueAtTime(volume, t);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + length);
    osc.connect(gain).connect(audio.destination);
    osc.start(t); osc.stop(t + length + 0.02);
  }
  function sound(kind) {
    try {
      audio = audio || new (window.AudioContext || window.webkitAudioContext)();
      if (audio.state === 'suspended') audio.resume();
      if (kind === 'grab') { tone(988, 0, 0.07); tone(1319, 0.07, 0.16); }          // coin: B5 then E6
      if (kind === 'angry') { tone(196, 0.12, 0.12, 'square', 0.035, -40); tone(147, 0.25, 0.18, 'square', 0.035, -30); }
    } catch {}
  }

  /* Clicking a stick on its way to the data center sends it to the people. */
  function pointer(event) {
    const b = canvas.getBoundingClientRect();
    const lx = (event.clientX - b.left) / S, ly = (event.clientY - b.top - y0) / S;
    const reach = (event.pointerType === 'touch' ? 24 : 16) / S;
    let best = null, bestD = Infinity;
    for (const s of sticks) {
      if (s.toPeople) continue;
      const dx = lx - (s.x + 4.5), dy = ly - (s.y + 2), d = dx * dx + dy * dy;
      if (Math.abs(dx) <= reach && Math.abs(dy) <= reach && d < bestD) { best = s; bestD = d; }
    }
    if (!best) return;
    state.touched = true;
    state.saved += 1;
    record += 1;
    saveRecord();
    pending += 1;
    sendGrabs();
    popups.push({x: best.x + 4, y: best.y, t: 0});
    toPeople(best, true);
    sound('grab');
    if (!bubble || !bubble.angry) sound('angry');
    say(ANGRY, 2.8, true);  // the boss does not like sharing
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

  /* Reasons board: the real daily change, each time with a different joke. */
  function buildBoard() {
    board = [];
    if (state.real == null) return;
    const c = state.change, dir = c == null || Math.abs(c) < 0.05 ? 'Flat' : c > 0 ? 'Up' : 'Down';
    const change = dir === 'Flat' ? T.gameNoChange : fmt('gameChange', {pct: `${c > 0 ? '▲' : '▼'} ${Math.abs(c).toFixed(1)}%`});
    [1, 2, 3].map(n => T[`gameWhy${dir}${n}`]).filter(Boolean).forEach(j => board.push({text: `${change} · ${j}`}));
    boardAt = 0; boardIn = 6;
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

  function start() {
    layout();
    if (reduced) {  // a still picture: a few sticks on the belt and a hoard on the roof
      state.ai = 32;
      sticks = [0.2, 0.5, 0.8].map(f => ({x: beltStart + (bossX - beltStart - 10) * f, y: beltY - 4, state: 'belt'}));
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
  (document.fonts ? document.fonts.load(`800 14px "Pretendard Variable"`).catch(() => {}) : Promise.resolve()).then(start, start);
})();
