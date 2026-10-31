'use strict';
// Hero: a RAM stick drawn as particles. The cursor melts it; it settles back.
// Plain Canvas 2D, no dependencies. Static (no animation) under reduced motion.
(() => {
  const root = document.getElementById('hero');
  const canvas = document.getElementById('hero-canvas');
  if (!root || root.hidden || !canvas) return;
  const ctx = canvas.getContext('2d');
  const content = document.getElementById('hero-content');
  const hint = document.getElementById('hero-hint');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const coarse = matchMedia('(hover: none), (pointer: coarse)').matches;
  if (coarse && hint) hint.textContent = hint.dataset.touch || hint.textContent;

  // 1. Draw the RAM stick once into an offscreen source image.
  const SW = 1000, SH = 360;
  const PALETTE = ['#1d2027', '#2a2e37', '#e8483c', '#f2efe8', '#3d4350', '#2f6b3a', '#d8a944', '#14161b'];
  function drawSource() {
    const c = document.createElement('canvas');
    c.width = SW; c.height = SH;
    const g = c.getContext('2d');
    const round = (x, y, w, h, r) => { g.beginPath(); g.roundRect(x, y, w, h, r); g.fill(); };
    g.fillStyle = PALETTE[5]; g.fillRect(24, 250, 952, 44);                     // PCB edge
    g.fillStyle = PALETTE[0]; round(16, 20, 968, 246, 16);                      // heat spreader
    g.fillStyle = PALETTE[1];                                                   // brushed stripes
    for (let x = -200; x < SW; x += 46) { g.beginPath(); g.moveTo(x, 266); g.lineTo(x + 120, 54); g.lineTo(x + 138, 54); g.lineTo(x + 18, 266); g.fill(); }
    g.fillStyle = PALETTE[2]; round(16, 20, 968, 34, 16); g.fillRect(16, 38, 968, 16);  // light bar
    g.fillStyle = PALETTE[3]; g.font = '800 128px "Pretendard Variable", "Helvetica Neue", Arial, sans-serif';
    g.textBaseline = 'alphabetic'; g.fillText('DDR5', 64, 212);
    g.fillStyle = PALETTE[4]; g.font = '700 26px "Pretendard Variable", "Helvetica Neue", Arial, sans-serif';
    g.fillText('QUITE TERRIBLE  ·  32GB  ·  6000MT/s', 68, 246);
    g.fillStyle = PALETTE[3]; round(664, 96, 280, 128, 10);                     // spec label
    g.fillStyle = PALETTE[7]; g.font = '800 34px "Pretendard Variable", "Helvetica Neue", Arial, sans-serif';
    g.fillText('CL30', 692, 148);
    g.fillStyle = PALETTE[2]; g.font = '800 30px "Pretendard Variable", "Helvetica Neue", Arial, sans-serif';
    g.fillText('PRICE ↑↑↑', 692, 198);
    g.fillStyle = PALETTE[6];                                                   // gold contacts with the key notch
    for (let x = 36; x < 968; x += 13) if (x < 548 || x > 584) g.fillRect(x, 294, 8, 46);
    return g.getImageData(0, 0, SW, SH).data;
  }

  // 2. One particle per sampled pixel, grouped by palette colour for fast drawing.
  const rgb = PALETTE.map(h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16)));
  const STEP = coarse || (navigator.hardwareConcurrency || 8) <= 4 ? 7 : 5;
  let hx, hy, ox, oy, vx, vy, col, count = 0;
  function build() {
    const data = drawSource();
    const homes = [];
    for (let y = STEP / 2; y < SH; y += STEP) {
      for (let x = STEP / 2; x < SW; x += STEP) {
        const i = ((y | 0) * SW + (x | 0)) * 4;
        if (data[i + 3] < 128) continue;
        let best = 0, bestD = Infinity;
        for (let k = 0; k < rgb.length; k++) {
          const d = (data[i] - rgb[k][0]) ** 2 + (data[i + 1] - rgb[k][1]) ** 2 + (data[i + 2] - rgb[k][2]) ** 2;
          if (d < bestD) { bestD = d; best = k; }
        }
        homes.push([x, y, best]);
      }
    }
    homes.sort((a, b) => a[2] - b[2]);
    count = homes.length;
    hx = new Float32Array(count); hy = new Float32Array(count); col = new Uint8Array(count);
    ox = new Float32Array(count); oy = new Float32Array(count); vx = new Float32Array(count); vy = new Float32Array(count);
    homes.forEach(([x, y, c], i) => { hx[i] = x; hy[i] = y; col[i] = c; });
  }

  // 3. Layout: the stick sits in the band above the copy.
  let W = 1, H = 1, dpr = 1, rect = {x: 0, y: 0, w: 1, h: 1, s: 1};
  function layout() {
    W = root.clientWidth; H = root.clientHeight;
    dpr = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    const bandTop = W < 640 ? 24 : 28;
    const bandBottom = Math.max(bandTop + 120, (content ? content.offsetTop : H) - (W < 640 ? 10 : 30));
    let w = W < 640 ? W * 1.02 : Math.min(W * 0.62, 900);
    if (w / (SW / SH) > bandBottom - bandTop) w = (bandBottom - bandTop) * (SW / SH);
    const h = w * SH / SW;
    rect = {x: (W - w) / 2, y: bandTop + (bandBottom - bandTop - h) / 2, w, h, s: w / SW};
    if (hint) { hint.style.left = `${W / 2}px`; hint.style.top = `${rect.y + h + 14}px`; }
    draw();
  }

  // 4. Simulation.
  const mouse = {x: -1e4, y: -1e4, px: -1e4, py: -1e4, vx: 0, vy: 0, on: false};
  let raf = 0, visible = true, calm = 0;
  function step(dt) {
    const s = rect.s, R = Math.max(70, 150 * Math.min(1.2, Math.max(0.6, rect.w / 1100)));
    const R2 = R * R, k = 0.048, damp = Math.pow(0.9, dt);
    const mx = mouse.x - rect.x, my = mouse.y - rect.y, push = mouse.on ? 1 : 0;
    let energy = 0;
    for (let i = 0; i < count; i++) {
      const px = hx[i] * s + ox[i], py = hy[i] * s + oy[i];
      if (push) {
        const dx = px - mx, dy = py - my, d2 = dx * dx + dy * dy;
        if (d2 < R2) {
          const f = (1 - d2 / R2) ** 2, inv = 1 / Math.sqrt(d2 + 1);
          vx[i] += (dx * inv * 0.65 - dy * inv * 0.4 + mouse.vx * 0.09) * f * dt;  // push out, swirl, drag along
          vy[i] += (dy * inv * 0.65 + dx * inv * 0.4 + mouse.vy * 0.09) * f * dt;
        }
      }
      vx[i] = (vx[i] - ox[i] * k * dt) * damp;
      vy[i] = (vy[i] - oy[i] * k * dt) * damp;
      ox[i] += vx[i] * dt; oy[i] += vy[i] * dt;
      energy += Math.abs(vx[i]) + Math.abs(vy[i]) + (Math.abs(ox[i]) + Math.abs(oy[i])) * 0.02;
    }
    return energy / Math.max(1, count);
  }
  function draw() {
    if (!count) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const s = rect.s, size = Math.max(1.2, STEP * s * 0.92);
    let current = -1;
    for (let i = 0; i < count; i++) {
      if (col[i] !== current) { current = col[i]; ctx.fillStyle = PALETTE[current]; }
      const speed = Math.abs(vx[i]) + Math.abs(vy[i]);
      const stretch = Math.min(1.5, 1 + speed * 0.06);  // fast particles streak like liquid
      ctx.fillRect(rect.x + hx[i] * s + ox[i], rect.y + hy[i] * s + oy[i], size * stretch, size);
    }
  }
  let last = 0;
  function frame(now) {
    const dt = Math.min(2.5, Math.max(0.3, (now - last) / 16.67));
    last = now;
    mouse.vx = (mouse.x - mouse.px) / dt; mouse.vy = (mouse.y - mouse.py) / dt;
    mouse.px = mouse.x; mouse.py = mouse.y;
    const energy = step(dt);
    draw();
    calm = energy < 0.02 && !mouse.on ? calm + 1 : 0;
    if (calm > 20) { ox.fill(0); oy.fill(0); vx.fill(0); vy.fill(0); draw(); raf = 0; return; }  // settled: sleep
    raf = visible ? requestAnimationFrame(frame) : 0;
  }
  function wake() {
    if (raf || reduced || !visible) return;
    last = performance.now(); calm = 0;
    raf = requestAnimationFrame(frame);
  }

  function pointer(event) {
    const b = root.getBoundingClientRect();
    mouse.x = event.clientX - b.left; mouse.y = event.clientY - b.top;
    if (!mouse.on) { mouse.px = mouse.x; mouse.py = mouse.y; }
    mouse.on = true;
    root.dataset.touched = '1';
    wake();
  }
  function leave() { mouse.on = false; wake(); }

  function start() {
    build();
    layout();
    root.addEventListener('pointermove', pointer, {passive: true});
    root.addEventListener('pointerdown', pointer, {passive: true});
    root.addEventListener('pointerleave', leave, {passive: true});
    root.addEventListener('pointerup', event => { if (event.pointerType === 'touch') leave(); }, {passive: true});
    new ResizeObserver(layout).observe(root);
    new IntersectionObserver(entries => {
      visible = entries.some(e => e.isIntersecting);
      if (visible) wake();
    }).observe(root);
  }
  // Wait for the web font so the label text on the stick uses it.
  (document.fonts ? document.fonts.load('800 40px "Pretendard Variable"').catch(() => {}) : Promise.resolve()).then(start, start);
})();
