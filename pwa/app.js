/* app.js — PWA Loterie (Lucky Six + Maxa Šestka).
 * Veškerá logika je přenesena z Pythonu (loterie_simulator.py, maxa_sestka.py, main.py).
 * Offline, bez reálných peněz.
 */
'use strict';

/* =========================================================================
 * 1) KONSTANTY — Lucky Six (oficiální Herní plán Fortuna ČR, čl. 6.7/6.8)
 * ========================================================================= */
const L6 = {
  TOTAL: 48, PICK: 6, DRAWN: 35,
  MIN: 20, MAX: 500, DEFAULT: 20,
  KOLO_MIN: 3.5,              // 3,5 min → 24 h = 411 kol
  RTP_DOC: 0.7587,            // čl. 6.8
  // výherní násobek podle pořadí posledního (6.) trefeného čísla
  MULT: {
    6: 10000, 7: 7500, 8: 5000, 9: 2000, 10: 1000,
    11: 500, 12: 200, 13: 100, 14: 70, 15: 50,
    16: 40, 17: 30, 18: 25, 19: 20, 20: 17,
    21: 15, 22: 14, 23: 13, 24: 12, 25: 11,
    26: 10, 27: 9, 28: 8, 29: 7, 30: 6,
    31: 5, 32: 4, 33: 3, 34: 2, 35: 1,
  },
  BARVY: {
    'Červená':  [1, 9, 17, 25, 33, 41],
    'Zelená':   [2, 10, 18, 26, 34, 42],
    'Modrá':    [3, 11, 19, 27, 35, 43],
    'Fialová':  [4, 12, 20, 28, 36, 44],
    'Hnědá':    [5, 13, 21, 29, 37, 45],
    'Žlutá':    [6, 14, 22, 30, 38, 46],
    'Oranžová': [7, 15, 23, 31, 39, 47],
    'Šedá':     [8, 16, 24, 32, 40, 48],
  },
  SYSTEM_MULT: { 6: 1.0, 7: 0.1429, 8: 0.0357, 9: 0.0119, 10: 0.0048 },
};

/* barva čísla → název skupiny */
const L6_GROUP_OF = (() => {
  const m = new Map();
  for (const [name, nums] of Object.entries(L6.BARVY))
    for (const n of nums) m.set(n, name);
  return m;
})();
const GROUP_COLOR = {
  'Červená': '#ef4444', 'Zelená': '#22c55e', 'Modrá': '#3b82f6',
  'Fialová': '#a855f7', 'Hnědá': '#a16207', 'Žlutá': '#eab308',
  'Oranžová': '#f97316', 'Šedá': '#94a3b8',
};

/* =========================================================================
 * 2) KONSTANTY — Maxa Šestka (maxa.cz / encyklopediehazardu.cz)
 * ========================================================================= */
const MX = {
  TOTAL: 49, PICK: 6, DRAWN: 6,
  STAKE: 35,                  // základní tiket; 70 = dvojnásobné výhry
  LOSOVANI_DENNE: 2,
  // pevné výhry pro tiket 35 Kč
  VYHRY: { 6: 5_000_000, 5: 250_000, 4: 2_500, 3: 500, 2: 35, 1: 0, 0: 0 },
};
MX.MULT = Object.fromEntries(Object.entries(MX.VYHRY).map(([k, v]) => [k, v / MX.STAKE]));

/* =========================================================================
 * 3) MATEMATIKA
 * ========================================================================= */
function comb(n, k) {
  if (k < 0 || k > n) return 0;
  k = Math.min(k, n - k);
  let r = 1;
  for (let i = 0; i < k; i++) r = (r * (n - i)) / (i + 1);
  return r;
}

/* Lucky Six — přesná pravděpodobnost trefy všech 6 = C(42,13)/C(48,13) */
function l6HitProb() { return comb(42, 13) / comb(48, 13); }

/* Lucky Six — rozdělení pořadí 6. trefy, p = 6..35 */
function l6PosDist() {
  const d = {};
  for (let p = 6; p <= 35; p++) {
    const num = comb(6, 5) * comb(42, p - 6);
    const den = comb(48, p - 1);
    d[p] = (num / den) * (1 / (48 - (p - 1)));
  }
  return d;
}

/* Lucky Six — analytické EV a RTP */
function l6EV() {
  const dist = l6PosDist();
  let ev = 0;
  for (const p in dist) ev += dist[p] * L6.MULT[p];
  return ev;
}

/* Maxa — rozdělení přesně k tref: C(6,k)*C(43,6-k)/C(49,6) */
function mxDist() {
  const d = {};
  for (let k = 0; k <= 6; k++) d[k] = comb(6, k) * comb(43, 6 - k) / comb(49, 6);
  return d;
}
function mxRTP() {
  const d = mxDist();
  let ev = 0;
  for (let k = 0; k <= 6; k++) ev += d[k] * MX.VYHRY[k];
  return ev / MX.STAKE;
}
function mxJackpotProb() { return 1 / comb(49, 6); }

/* =========================================================================
 * 4) NÁHODNÝ GENERÁTOR (seedovatelný — mulberry32)
 * ========================================================================= */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
let RNG = Math.random;
function setSeed(seed) {
  RNG = (seed === null || seed === undefined || Number.isNaN(seed))
    ? Math.random : mulberry32(seed >>> 0);
}

/* vylosuj n unikátních čísel z 1..total (v pořadí) */
function drawN(total, n) {
  const pool = new Array(total);
  for (let i = 0; i < total; i++) pool[i] = i + 1;
  for (let i = 0; i < n; i++) {
    const j = i + Math.floor(RNG() * (total - i));
    const t = pool[i]; pool[i] = pool[j]; pool[j] = t;
  }
  return pool.slice(0, n);
}

/* =========================================================================
 * 5) POMOCNÉ UI
 * ========================================================================= */
const $ = (sel) => document.querySelector(sel);
const app = () => document.getElementById('app');

/* české formátování peněz */
function kc(x, dec = 2) {
  const neg = x < 0;
  let s = Math.abs(x).toFixed(dec);
  let [i, d] = s.split('.');
  i = i.replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
  let out = dec > 0 ? `${i},${d} Kč` : `${i} Kč`;
  return (neg ? '−' : '') + out;
}
function num(x, dec = 0) {
  return x.toLocaleString('cs-CZ', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
function pct(x, dec = 2) { return (x * 100).toFixed(dec) + ' %'; }

/* vytvoření elementu z HTML stringu */
function h(html) {
  const t = document.createElement('template');
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}
function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/* =========================================================================
 * 6) ROUTER / OBRAZOVKY
 * ========================================================================= */
const NAV = { stack: [] };
function go(screen, params) {
  NAV.stack.push(screen);
  render(screen, params);
}
function back() {
  if (NAV.stack.length > 1) {
    NAV.stack.pop();
    const s = NAV.stack[NAV.stack.length - 1];
    render(s.name || s, s.params);
  }
}
function setTitle(t) { document.getElementById('scr-title').textContent = t; }
function showBack(v) { document.getElementById('back').hidden = !v; }

/* =========================================================================
 * 7) HLAVNÍ MENU
 * ========================================================================= */
function screenMenu() {
  setTitle('Loterie'); showBack(false);
  const el = h(`<div>
    <div class="card">
      <h2>Loterie — simulátor</h2>
      <p class="dim small">Lucky Six (Fortuna, 35 z 48, RTP <b>75,87 %</b>) a
      Maxa Šestka (6 z 49, RTP <b>59,57 %</b>). Vše offline, bez reálných peněz.</p>
    </div>
    <div class="menu">
      <button class="mbtn group">🎟  Lucky Six — Fortuna</button>
      <button class="mbtn" data-go="l6-solo"><span class="em">🎟</span><span>Hlavní sázka (6 čísel)<span class="sub">vybereš 6, vyhraješ když padnou všechny</span></span></button>
      <button class="mbtn" data-go="l6-system"><span class="em">🧩</span><span>Systémová sázka (6/7 – 6/10)<span class="sub">víc čísel = víc kombinací</span></span></button>
      <button class="mbtn" data-go="l6-special"><span class="em">🌈</span><span>Vedlejší hry<span class="sub">Barva · Prvních 5 · Barva prvního čísla</span></span></button>
      <button class="mbtn" data-go="l6-day"><span class="em">⚡</span><span>Rychlá simulace dne<span class="sub">24 h / 3:30 = 411 kol + bank</span></span></button>
      <button class="mbtn" data-go="l6-stats"><span class="em">📊</span><span>Statistiky &amp; RTP</span></button>
      <button class="mbtn group">🍀  Maxa Šestka</button>
      <button class="mbtn" data-go="mx-solo"><span class="em">🍀</span><span>Simulace do hlavní výhry<span class="sub">1 z 13 983 816 · jackpot 5 000 000 Kč</span></span></button>
      <button class="mbtn" data-go="mx-stats"><span class="em">📊</span><span>Statistiky &amp; RTP</span></button>
    </div>
  </div>`);
  el.querySelectorAll('[data-go]').forEach((b) =>
    b.addEventListener('click', () => { const g = b.dataset.go; go(SCREENS[g].name, SCREENS[g]); }));
  return el;
}

/* =========================================================================
 * 8) VÝBĚR ČÍSEL — komponenta
 * ========================================================================= */
function numberPicker({ total, need, max = need, groups = null, initial = [] }) {
  const wrap = h('<div></div>');
  const chosen = new Set(initial);
  const grid = h(`<div class="grid${total === 49 ? ' g7' : ''}"></div>`);
  const counter = h('<div class="small dim" style="margin-top:8px"></div>');

  function refresh() {
    grid.querySelectorAll('.num').forEach((n) => {
      const v = +n.dataset.v;
      n.classList.toggle('on', chosen.has(v));
    });
    counter.textContent = `Vybráno ${chosen.size} / ${need}`
      + (max !== need ? ` (max ${max})` : '');
  }
  for (let v = 1; v <= total; v++) {
    const b = h(`<button class="num" data-v="${v}">${v}</button>`);
    if (groups) {
      const g = L6_GROUP_OF.get(v);
      if (g) b.style.borderColor = GROUP_COLOR[g] + '99';
    }
    b.addEventListener('click', () => {
      if (chosen.has(v)) chosen.delete(v);
      else {
        if (chosen.size >= max) return;
        chosen.add(v);
      }
      refresh();
    });
    grid.appendChild(b);
  }
  refresh();
  wrap.appendChild(grid);
  wrap.appendChild(counter);
  const rnd = h('<button class="btn ghost small">🎲 Náhodný výběr</button>');
  rnd.style.marginTop = '8px';
  rnd.addEventListener('click', () => {
    chosen.clear();
    drawN(total, need).forEach((n) => chosen.add(n));
    refresh();
  });
  wrap.appendChild(rnd);
  wrap.getValue = () => [...chosen].sort((a, b) => a - b);
  wrap.setValue = (arr) => { chosen.clear(); arr.forEach((x) => chosen.add(x)); refresh(); };
  return wrap;
}

/* =========================================================================
 * 9) LUCKY SIX — HLAVNÍ SÁZKA
 * ========================================================================= */
function screenL6Solo() {
  setTitle('Lucky Six — hlavní sázka'); showBack(true);
  const picker = numberPicker({ total: 48, need: 6, groups: true });
  const stakeIn = h(`<input type="number" min="${L6.MIN}" max="${L6.MAX}" step="1" value="${L6.DEFAULT}">`);
  const out = h('<div></div>');

  const el = h(`<div>
    <div class="card">
      <h3>1 · Vyber 6 čísel</h3>
      <div class="slot-picker"></div>
    </div>
    <div class="card">
      <h3>2 · Vklad</h3>
      <label class="field"><span>Vklad na kolo (Kč, ${L6.MIN}–${L6.MAX})</span></label>
      <div class="slot-stake"></div>
      <div class="row" style="margin-top:12px">
        <button class="btn primary" data-act="play">▶ Odehrát kolo</button>
      </div>
    </div>
    <div class="slot-out"></div>
  </div>`);
  el.querySelector('.slot-picker').appendChild(picker);
  el.querySelector('.slot-stake').appendChild(stakeIn);
  el.querySelector('.slot-out').appendChild(out);

  el.querySelector('[data-act="play"]').addEventListener('click', () => {
    const mine = picker.getValue();
    const stake = +stakeIn.value || 0;
    if (mine.length !== 6) { toast(out, 'Vyber přesně 6 čísel.', 'warn'); return; }
    if (stake < L6.MIN || stake > L6.MAX) { toast(out, `Vklad musí být ${L6.MIN}–${L6.MAX} Kč.`, 'warn'); return; }
    const draw = drawN(48, 35);
    const posMap = new Map();
    draw.forEach((n, i) => posMap.set(n, i + 1));
    // pořadí 6. trefy
    let seen = 0, pos6 = null;
    for (let i = 0; i < draw.length; i++) {
      if (mine.includes(draw[i])) { seen++; if (seen === 6) { pos6 = i + 1; break; } }
    }
    renderL6Round(out, mine, draw, posMap, pos6, seen, stake);
  });
  return el;
}

function numberRow(mine, posMap) {
  // barevný výpis čísel: zeleně trefeno + pozice, šedě netrefeno
  return mine.map((n) => {
    const p = posMap.get(n);
    const g = L6_GROUP_OF.get(n);
    const dot = `<span class="dotc" style="background:${GROUP_COLOR[g] || '#888'}"></span>`;
    if (p) return `<span class="mono g">${dot}${n}<small class="dim2">(${p})</small></span>`;
    return `<span class="mono d">${dot}${n}<small class="dim2">(–)</small></span>`;
  }).join('  ');
}

function renderL6Round(out, mine, draw, posMap, pos6, seen, stake) {
  const win = pos6 ? stake * L6.MULT[pos6] : 0;
  const zisk = win - stake;
  out.innerHTML = '';
  const card = h(`<div class="card">
    <h3>Výsledek</h3>
    <p style="font-size:16px;line-height:1.9">${numberRow(mine, posMap)}</p>
    <div class="stat"><span class="k">Trefeno z 6</span><span class="v">${seen}</span></div>
    ${pos6
      ? `<div class="stat"><span class="k">6. trefa padla na pozici</span><span class="v">${pos6}. → ${L6.MULT[pos6]}×</span></div>
         <div class="stat"><span class="k">Výhra</span><span class="v pos">${kc(win)}</span></div>
         <div class="stat"><span class="k">Zisk</span><span class="v ${zisk >= 0 ? 'pos' : 'neg'}">${kc(zisk)}</span></div>`
      : `<div class="stat"><span class="k">Výsledek</span><span class="v neg">Nevyhráváš (netrefeno všech 6)</span></div>
         <div class="stat"><span class="k">Ztráta</span><span class="v neg">${kc(-stake)}</span></div>`}
    <div class="dim small" style="margin-top:8px">
      Legenda: <span class="pos">zeleně</span> = padlo (v závorce pořadí losování),
      <span class="dim2">šedě</span> = nepadlo. Pořadí 1 = první koule, 35 = poslední.
    </div>
  </div>`);
  out.appendChild(card);
}

/* =========================================================================
 * 10) LUCKY SIX — SYSTÉMOVÁ SÁZKA (6/7 – 6/10)
 * ========================================================================= */
function combos(arr, k) {
  const res = [];
  (function rec(start, cur) {
    if (cur.length === k) { res.push(cur.slice()); return; }
    for (let i = start; i < arr.length; i++) { cur.push(arr[i]); rec(i + 1, cur); cur.pop(); }
  })(0, []);
  return res;
}

function screenL6System() {
  setTitle('Lucky Six — systém'); showBack(true);
  let n = 7;
  const picker = numberPicker({ total: 48, need: 7, max: 10, groups: true });
  const stakeIn = h(`<input type="number" min="${L6.MIN}" max="${L6.MAX}" step="1" value="${L6.DEFAULT}">`);
  const out = h('<div></div>');

  const el = h(`<div>
    <div class="card">
      <h3>Systém</h3>
      <div class="chips slot-sys"></div>
      <p class="dim small" style="margin-top:8px">Vybereš 7–10 čísel → vznikne C(n,6) kombinací.
      Každá se hodnotí samostatně; celkový vklad na tiket se dělí počtem kombinací.</p>
    </div>
    <div class="card">
      <h3>Čísla</h3>
      <div class="slot-picker"></div>
    </div>
    <div class="card">
      <h3>Celkový vklad na tiket (Kč, ${L6.MIN}–${L6.MAX})</h3>
      <div class="slot-stake"></div>
      <div class="row" style="margin-top:12px"><button class="btn primary" data-act="play">▶ Odehrát</button></div>
    </div>
    <div class="slot-out"></div>
  </div>`);
  el.querySelector('.slot-picker').appendChild(picker);
  el.querySelector('.slot-stake').appendChild(stakeIn);
  el.querySelector('.slot-out').appendChild(out);

  const sysWrap = el.querySelector('.slot-sys');
  function renderSys() {
    sysWrap.innerHTML = '';
    [7, 8, 9, 10].forEach((k) => {
      const c = h(`<button class="chip ${k === n ? 'on' : ''}">6/${k} · ${comb(k, 6)} komb.</button>`);
      c.addEventListener('click', () => {
        n = k; picker.setValue([]);
        const need = k;
        // přegeneruj picker s novým počtem
        const np = numberPicker({ total: 48, need, max: need, groups: true, initial: picker.getValue() });
        el.querySelector('.slot-picker').replaceChild(np, picker);
        // nahradit referenci
        Object.assign(picker, np);
        renderSys();
      });
      sysWrap.appendChild(c);
    });
  }
  renderSys();

  el.querySelector('[data-act="play"]').addEventListener('click', () => {
    const mine = picker.getValue();
    const stake = +stakeIn.value || 0;
    if (mine.length !== n) { toast(out, `Vyber přesně ${n} čísel (máš ${mine.length}).`, 'warn'); return; }
    if (stake < L6.MIN || stake > L6.MAX) { toast(out, `Vklad ${L6.MIN}–${L6.MAX} Kč.`, 'warn'); return; }
    const cs = combos(mine, 6);
    const perCombo = stake * L6.SYSTEM_MULT[n];
    const draw = drawN(48, 35);
    const dset = new Set(draw);
    const posMap = new Map(); draw.forEach((x, i) => posMap.set(x, i + 1));
    let vyhry = 0, hitCombos = 0;
    const lines = [];
    for (const c of cs) {
      let seen = 0, pos6 = null;
      for (let i = 0; i < draw.length; i++) {
        if (c.includes(draw[i])) { seen++; if (seen === 6) { pos6 = i + 1; break; } }
      }
      if (pos6) {
        const w = perCombo * L6.MULT[pos6];
        vyhry += w; hitCombos++;
        lines.push(`<div class="mono g">✔ ${c.join(' ')} → 6. trefa ${pos6}. → ${L6.MULT[pos6]}× = ${kc(w)}</div>`);
      }
    }
    const zisk = vyhry - stake;
    out.innerHTML = '';
    out.appendChild(h(`<div class="card">
      <h3>Systém 6/${n}</h3>
      <p class="mono" style="margin:6px 0">Tvá čísla: ${mine.map((x) => `<span class="g">${x}</span>`).join(' ')}</p>
      <div class="stat"><span class="k">Kombinací</span><span class="v">${cs.length}</span></div>
      <div class="stat"><span class="k">Vklad / kombinace</span><span class="v">${kc(perCombo)}</span></div>
      <div class="stat"><span class="k">Celkem vsazeno</span><span class="v">${kc(stake)}</span></div>
      <div class="stat"><span class="k">Vyhraných kombinací</span><span class="v">${hitCombos}/${cs.length}</span></div>
      <div class="stat"><span class="k">Vráceno</span><span class="v">${kc(vyhry)}</span></div>
      <div class="stat"><span class="k">Zisk</span><span class="v ${zisk >= 0 ? 'pos' : 'neg'}">${kc(zisk)}</span></div>
      <div class="log" style="margin-top:10px">${lines.join('') || '<div class="dim">Žádná kombinace netrefila všech 6.</div>'}</div>
    </div>`));
  });
  return el;
}

/* =========================================================================
 * 11) LUCKY SIX — VEDLEJŠÍ HRY (Barva, Prvních 5, Barva prvního čísla)
 * ========================================================================= */
function screenL6Special() {
  setTitle('Lucky Six — vedlejší hry'); showBack(true);
  const out = h('<div></div>');
  const el = h(`<div>
    <div class="card">
      <h3>Vyber hru</h3>
      <div class="chips slot-game"></div>
      <div class="slot-body" style="margin-top:12px"></div>
    </div>
    <div class="slot-out"></div>
  </div>`);
  el.querySelector('.slot-out').appendChild(out);
  const games = [
    ['barva', '🌈 Barva (6 čísel jedné barvy)'],
    ['prvnich5', '🖐 Prvních 5'],
    ['barva1', '🎨 Barva prvního čísla'],
  ];
  let cur = 'barva';
  const chips = el.querySelector('.slot-game');
  const body = el.querySelector('.slot-body');

  function renderChips() {
    chips.innerHTML = '';
    games.forEach(([k, label]) => {
      const c = h(`<button class="chip ${k === cur ? 'on' : ''}">${label}</button>`);
      c.addEventListener('click', () => { cur = k; renderChips(); renderBody(); });
      chips.appendChild(c);
    });
  }

  function renderBody() {
    body.innerHTML = '';
    if (cur === 'barva') {
      const sel = h('<div class="chips"></div>');
      let barva = Object.keys(L6.BARVY)[0];
      Object.keys(L6.BARVY).forEach((b) => {
        const c = h(`<button class="chip ${b === barva ? 'on' : ''}">
          <span class="dotc" style="background:${GROUP_COLOR[b]}"></span>${b}</button>`);
        c.addEventListener('click', () => { barva = b; renderBody(); });
        sel.appendChild(c);
      });
      const stake = stakeInput();
      const btn = h('<button class="btn primary" style="margin-top:10px">▶ Odehrát</button>');
      btn.addEventListener('click', () => {
        const mine = L6.BARVY[barva].slice();
        const draw = drawN(48, 35);
        const posMap = new Map(); draw.forEach((n, i) => posMap.set(n, i + 1));
        let seen = 0, pos6 = null;
        for (let i = 0; i < draw.length; i++) if (mine.includes(draw[i])) { seen++; if (seen === 6) { pos6 = i + 1; break; } }
        const s = +stake.value || 0;
        out.innerHTML = '';
        out.appendChild(h(`<div class="card">
          <h3>Číselná loterie „Barva“ — ${barva}</h3>
          <p class="mono" style="margin:6px 0">${numberRow(mine, posMap)}</p>
          <div class="stat"><span class="k">Trefeno</span><span class="v">${seen}/6</span></div>
          ${pos6
            ? `<div class="stat"><span class="k">6. trefa na pozici</span><span class="v">${pos6}. → ${L6.MULT[pos6]}×</span></div>
               <div class="stat"><span class="k">Výhra</span><span class="v pos">${kc(s * L6.MULT[pos6])}</span></div>`
            : `<div class="stat"><span class="k">Výsledek</span><span class="v neg">Nevyhráváš</span></div>`}
          <div class="dim small" style="margin-top:6px">RTP 75,87 % · stejné násobky jako hlavní hra.</div>
        </div>`));
      });
      body.appendChild(sel); body.appendChild(stake); body.appendChild(btn);
    }
    if (cur === 'prvnich5') {
      const numIn = h(`<input type="number" min="1" max="48" value="13">`);
      const stake = stakeInput();
      const btn = h('<button class="btn primary" style="margin-top:10px">▶ Odehrát</button>');
      const f1 = h('<label class="field"><span>Tipované číslo (1–48)</span></label>');
      f1.appendChild(numIn);
      btn.addEventListener('click', () => {
        const cislo = +numIn.value || 0;
        const s = +stake.value || 0;
        const draw = drawN(48, 35);
        const first5 = draw.slice(0, 5);
        const win = first5.includes(cislo);
        out.innerHTML = '';
        out.appendChild(h(`<div class="card">
          <h3>Číselná loterie „Prvních 5“</h3>
          <div class="stat"><span class="k">Tvůj tip</span><span class="v">${cislo}</span></div>
          <div class="stat"><span class="k">Prvních 5</span><span class="v mono">${first5.join(' ')}</span></div>
          <div class="stat"><span class="k">Výsledek</span><span class="v ${win ? 'pos' : 'neg'}">${win ? `Výhra ${kc(s * 7.2)}` : 'Nevyhráváš'}</span></div>
          <div class="dim small" style="margin-top:6px">Pevný násobek 7,2× · RTP 75 %.</div>
        </div>`));
      });
      body.appendChild(f1); body.appendChild(stake); body.appendChild(btn);
    }
    if (cur === 'barva1') {
      let pocet = 1;
      const pc = h('<div class="chips"></div>');
      [[1, '1 skupina · 6,0×'], [2, '2 skupiny · 3,0×'], [4, '4 skupiny · 1,5×']].forEach(([k, l]) => {
        const c = h(`<button class="chip ${k === pocet ? 'on' : ''}">${l}</button>`);
        c.addEventListener('click', () => { pocet = k; renderBody(); });
        pc.appendChild(c);
      });
      const sel = h('<div class="chips" style="margin-top:8px"></div>');
      const chosen = new Set();
      Object.keys(L6.BARVY).forEach((b) => {
        const c = h(`<button class="chip"><span class="dotc" style="background:${GROUP_COLOR[b]}"></span>${b}</button>`);
        c.addEventListener('click', () => {
          if (chosen.has(b)) chosen.delete(b);
          else { if (chosen.size >= pocet) return; chosen.add(b); }
          c.classList.toggle('on', chosen.has(b));
        });
        sel.appendChild(c);
      });
      const stake = stakeInput();
      const btn = h('<button class="btn primary" style="margin-top:10px">▶ Odehrát</button>');
      btn.addEventListener('click', () => {
        if (chosen.size !== pocet) { toast(out, `Vyber přesně ${pocet} skupin.`, 'warn'); return; }
        const mnoz = new Set();
        chosen.forEach((b) => L6.BARVY[b].forEach((n) => mnoz.add(n)));
        const draw = drawN(48, 35);
        const first = draw[0];
        const win = mnoz.has(first);
        const mult = { 1: 6.0, 2: 3.0, 4: 1.5 }[pocet];
        const s = +stake.value || 0;
        out.innerHTML = '';
        out.appendChild(h(`<div class="card">
          <h3>Číselná loterie „Barva prvního čísla“</h3>
          <div class="stat"><span class="k">Skupiny</span><span class="v">${[...chosen].join(', ')}</span></div>
          <div class="stat"><span class="k">První číslo</span><span class="v">${first} → ${L6_GROUP_OF.get(first)}</span></div>
          <div class="stat"><span class="k">Výsledek</span><span class="v ${win ? 'pos' : 'neg'}">${win ? `Výhra ${kc(s * mult)}` : 'Nevyhráváš'}</span></div>
          <div class="dim small" style="margin-top:6px">Násobek ${mult}× · RTP 75 %.</div>
        </div>`));
      });
      body.appendChild(pc); body.appendChild(sel); body.appendChild(stake); body.appendChild(btn);
    }
  }

  function stakeInput() {
    const w = h('<label class="field"><span>Vklad (Kč, 20–500)</span></label>');
    w.appendChild(h(`<input type="number" min="20" max="500" value="20">`));
    return w;
  }

  renderChips(); renderBody();
  return el;
}

/* =========================================================================
 * 12) LUCKY SIX — RYCHLÁ SIMULACE DNE
 * ========================================================================= */
function screenL6Day() {
  setTitle('Lucky Six — simulace dne'); showBack(true);
  const picker = numberPicker({ total: 48, need: 6, max: 10, groups: true });
  const stakeIn = h(`<input type="number" min="${L6.MIN}" max="${L6.MAX}" value="${L6.DEFAULT}">`);
  const bankIn = h('<input type="number" min="1" step="1" value="5000">');
  const hoursIn = h('<input type="number" min="1" max="72" step="1" value="24">');
  const out = h('<div></div>');

  const el = h(`<div>
    <div class="card">
      <h3>Čísla (6 = sólo, 7–10 = systém)</h3>
      <div class="slot-picker"></div>
    </div>
    <div class="card">
      <h3>Parametry</h3>
      <label class="field"><span>Vklad na kolo / tiket (Kč)</span></label><div class="s1"></div>
      <label class="field"><span>Počáteční bank (Kč)</span></label><div class="s2"></div>
      <label class="field"><span>Kolik hodin simulovat (kolo = 3:30)</span></label><div class="s3"></div>
      <div class="row" style="margin-top:10px">
        <button class="btn primary" data-act="run">⚡ Spustit</button>
      </div>
      <div class="dim small" style="margin-top:8px">24 h = 411 kol. Log ukazuje každé tvé číslo s pořadím
      losování (zeleně = padlo, šedě = nepadlo) a stav banku po každém kole.</div>
    </div>
    <div class="slot-out"></div>
  </div>`);
  el.querySelector('.slot-picker').appendChild(picker);
  el.querySelector('.s1').appendChild(stakeIn);
  el.querySelector('.s2').appendChild(bankIn);
  el.querySelector('.s3').appendChild(hoursIn);
  el.querySelector('.slot-out').appendChild(out);

  el.querySelector('[data-act="run"]').addEventListener('click', () => {
    const mine = picker.getValue();
    const stake = +stakeIn.value || 0;
    const bank0 = +bankIn.value || 0;
    const hours = +hoursIn.value || 24;
    if (mine.length < 6 || mine.length > 10) { toast(out, 'Vyber 6–10 čísel.', 'warn'); return; }
    if (stake < L6.MIN || stake > L6.MAX) { toast(out, `Vklad ${L6.MIN}–${L6.MAX} Kč.`, 'warn'); return; }
    runDay(out, mine, stake, bank0, hours);
  });
  return el;
}

function runDay(out, mine, stake, bank0, hours) {
  const rounds = Math.floor(hours * 60 / L6.KOLO_MIN);
  const n = mine.length;
  const isSystem = n > 6;
  const cs = isSystem ? combos(mine, 6) : [mine.slice()];
  const perCombo = isSystem ? stake * L6.SYSTEM_MULT[n] : stake;

  let bank = bank0, minB = bank0, maxB = bank0, minK = 0, maxK = 0;
  let staked = 0, returned = 0, winRounds = 0;
  const lines = [];
  let bustedAt = null;
  let k = 0;

  for (k = 1; k <= rounds; k++) {
    if (bank < stake) { bustedAt = k; break; }
    const draw = drawN(48, 35);
    const posMap = new Map(); draw.forEach((x, i) => posMap.set(x, i + 1));
    let vyhra = 0;
    for (const c of cs) {
      let seen = 0, pos6 = null;
      for (let i = 0; i < draw.length; i++) if (c.includes(draw[i])) { seen++; if (seen === 6) { pos6 = i + 1; break; } }
      if (pos6) vyhra += perCombo * L6.MULT[pos6];
    }
    staked += stake; returned += vyhra;
    if (vyhra > 0) winRounds++;
    bank += vyhra - stake;
    if (bank < minB) { minB = bank; minK = k; }
    if (bank > maxB) { maxB = bank; maxK = k; }
    // log řádek
    const cells = mine.map((num) => {
      const p = posMap.get(num);
      const g = L6_GROUP_OF.get(num);
      const dot = `<span class="dotc" style="background:${GROUP_COLOR[g] || '#888'}"></span>`;
      return p ? `<span class="mono g">${dot}${num}<small class="dim2">(${p})</small></span>`
               : `<span class="mono d">${dot}${num}<small class="dim2">(–)</small></span>`;
    }).join(' ');
    const delta = vyhra - stake;
    const bcls = bank >= bank0 ? 'w' : 'z';
    lines.push(`<div class="l"><span class="p">${String(k).padStart(3, ' ')}.</span>${cells} <span class="${delta >= 0 ? 'g' : 'z'}">${delta >= 0 ? '+' : '−'}${Math.abs(delta).toFixed(0)}</span> <span class="${bcls}">[${num(bank, 0)}]</span></div>`);
  }

  const odehrano = bustedAt ? k - 1 : rounds;
  const zisk = returned - staked;
  const rtp = staked > 0 ? returned / staked : 0;

  out.innerHTML = '';
  const card = h(`<div class="card">
    <h3>Souhrn za ${num(odehrano)} kol (${(odehrano * L6.KOLO_MIN / 60).toFixed(1)} h)</h3>
    <div class="stat"><span class="k">Počáteční bank</span><span class="v">${kc(bank0)}</span></div>
    <div class="stat"><span class="k">Konečný bank</span><span class="v ${bank >= bank0 ? 'pos' : 'neg'}">${kc(bank)} (${bank - bank0 >= 0 ? '+' : ''}${num(bank - bank0, 0)})</span></div>
    <div class="stat"><span class="k">Vsazeno</span><span class="v">${kc(staked)}</span></div>
    <div class="stat"><span class="k">Vráceno</span><span class="v">${kc(returned)}</span></div>
    <div class="stat"><span class="k">Zisk</span><span class="v ${zisk >= 0 ? 'pos' : 'neg'}">${kc(zisk)}</span></div>
    <div class="stat"><span class="k">RTP (skutečné)</span><span class="v">${pct(rtp)}</span></div>
    <div class="stat"><span class="k">Výherních kol</span><span class="v">${num(winRounds)}/${num(odehrano)} (${pct(odehrano ? winRounds / odehrano : 0)})</span></div>
    <div class="stat"><span class="k">Min / max bank</span><span class="v">${kc(minB)} (${minK}.) / ${kc(maxB)} (${maxK}.)</span></div>
    <div class="stat"><span class="k">Přežil</span><span class="v ${bustedAt ? 'neg' : 'pos'}">${bustedAt ? 'BANKROT v ' + bustedAt + '. kole' : 'ano, celou simulaci'}</span></div>
    <h3 style="margin-top:14px">Kompletní log (${num(lines.length)} kol)</h3>
    <div class="log" id="daylog"></div>
    <div class="row end" style="margin-top:10px">
      <button class="btn ghost" id="exp">⤓ Export CSV</button>
    </div>
  </div>`);
  out.appendChild(card);
  const logEl = card.querySelector('#daylog');
  logEl.innerHTML = lines.join('');
  logEl.scrollTop = logEl.scrollHeight;

  card.querySelector('#exp').addEventListener('click', () => {
    const header = 'kolo;' + mine.map((x) => 'c' + x).join(';') + ';delta;bank';
    const rows = [];
    // rekonstrukce z DOM není přesná → exportujeme jen souhrn + délku
    const csv = header + '\n' + `# ${odehrano} kol, vklad ${stake} Kc, bank ${bank0} -> ${bank.toFixed(2)}`;
    download('lucky6-den.csv', csv);
  });
}

/* =========================================================================
 * 13) LUCKY SIX — STATISTIKY
 * ========================================================================= */
function screenL6Stats() {
  setTitle('Lucky Six — statistiky'); showBack(true);
  const p = l6HitProb();
  const dist = l6PosDist();
  const ev = l6EV();
  let rows = '';
  for (let pos = 6; pos <= 35; pos++) {
    rows += `<tr><td>${pos}.</td><td class="r">${L6.MULT[pos]}×</td>
      <td class="r mono">${(dist[pos] * 100).toFixed(6)} %</td>
      <td class="r mono">${((dist[pos] / p) * 100).toFixed(3)} %</td></tr>`;
  }
  const el = h(`<div>
    <div class="card">
      <h3>Základní údaje</h3>
      <div class="stat"><span class="k">Losování</span><span class="v">35 z 48</span></div>
      <div class="stat"><span class="k">Tipuje se</span><span class="v">6 čísel</span></div>
      <div class="stat"><span class="k">Frekvence</span><span class="v">3,5 min → 411 kol / 24 h</span></div>
      <div class="stat"><span class="k">Vklad</span><span class="v">${L6.MIN}–${L6.MAX} Kč</span></div>
      <div class="stat"><span class="k">RTP (oficiální, čl. 6.8)</span><span class="v pos">${pct(L6.RTP_DOC)}</span></div>
    </div>
    <div class="card">
      <h3>Pravděpodobnost trefy všech 6</h3>
      <p class="big center pos">${(p * 100).toFixed(5)} %</p>
      <p class="center dim">= 1 z ${num(1 / p, 1)} kol · tedy průměrně každé ~${Math.round(1 / p)}. kolo</p>
    </div>
    <div class="card">
      <h3>Analytické RTP</h3>
      <div class="stat"><span class="k">E[násobek vkladu]</span><span class="v">${ev.toFixed(5)}×</span></div>
      <div class="stat"><span class="k">RTP</span><span class="v pos">${pct(ev)}</span></div>
      <p class="dim small" style="margin-top:8px">Spočítáno z výplatní tabulky (Herní plán, čl. 6.7).
      Sedí na oficiální RTP ${pct(L6.RTP_DOC)} z čl. 6.8.</p>
    </div>
    <div class="card">
      <h3>Výplatní tabulka + rozdělení 6. trefy</h3>
      <table><thead><tr><th>Pořadí</th><th class="r">Násobek</th>
      <th class="r">P(pořadí)</th><th class="r">podíl z tref</th></tr></thead>
      <tbody>${rows}</tbody></table>
    </div>
  </div>`);
  return el;
}

/* =========================================================================
 * 14) MAXA ŠESTKA — SIMULACE DO JACKPOTU
 * ========================================================================= */
function screenMxSolo() {
  setTitle('Maxa Šestka — jackpot'); showBack(true);
  const picker = numberPicker({ total: 49, need: 6, max: 6 });
  const stakeIn = h(`<input type="number" min="35" max="70" step="35" value="35">`);
  const seedIn = h('<input type="number" placeholder="prázdné = náhodný">');
  const out = h('<div></div>');
  const el = h(`<div>
    <div class="card">
      <h3>1 · Vyber 6 čísel (z 49)</h3>
      <div class="slot-picker"></div>
    </div>
    <div class="card">
      <h3>2 · Parametry</h3>
      <label class="field"><span>Vklad na tiket (35 nebo 70 Kč)</span></label><div class="s1"></div>
      <label class="field"><span>Seed (nepovinné, pro reprodukci)</span></label><div class="s2"></div>
      <div class="row" style="margin-top:10px">
        <button class="btn primary" data-act="run">🍀 Hrát do jackpotu</button>
      </div>
      <div class="dim small" style="margin-top:8px">Hraje se, dokud netrefíš všech 6 (5 000 000 Kč).
      Průměrně to je 1 z ${num(1 / mxJackpotProb(), 0)} kol ≈ ${num(1 / mxJackpotProb() / 2 / 365, 0)} let
      (2 losování denně).</div>
    </div>
    <div class="slot-out"></div>
  </div>`);
  el.querySelector('.slot-picker').appendChild(picker);
  el.querySelector('.s1').appendChild(stakeIn);
  el.querySelector('.s2').appendChild(seedIn);
  el.querySelector('.slot-out').appendChild(out);

  el.querySelector('[data-act="run"]').addEventListener('click', () => {
    const mine = picker.getValue();
    const stake = +stakeIn.value || 35;
    const seedTxt = seedIn.value.trim();
    if (mine.length !== 6) { toast(out, 'Vyber přesně 6 čísel.', 'warn'); return; }
    setSeed(seedTxt === '' ? null : +seedTxt);
    runMx(out, mine, stake);
  });
  return el;
}

/* Simulace do jackpotu — běží po chuncích, aby nezamrzla UI */
function runMx(out, mine, stake) {
  const mySet = new Uint8Array(50);
  mine.forEach((n) => mySet[n] = 1);
  const base = new Uint8Array(49);
  for (let i = 0; i < 49; i++) base[i] = i + 1;
  const pool = new Uint8Array(49);

  const CHUNK = 300000;
  const MAX = 200_000_000;

  let rounds = 0, staked = 0, returned = 0;
  const tiers = { 2: 0, 3: 0, 4: 0, 5: 0 };
  let jackpotRound = null;

  out.innerHTML = '';
  const card = h(`<div class="card">
    <h3>Simulace běží…</h3>
    <div class="bar"><i id="mxbar"></i></div>
    <div class="stat"><span class="k">Odehráno kol</span><span class="v mono" id="mxr">0</span></div>
    <div class="stat"><span class="k">Vsazeno</span><span class="v mono" id="mxs">0</span></div>
    <div class="stat"><span class="k">Vráceno</span><span class="v mono" id="mxv">0</span></div>
    <div class="stat"><span class="k">Bank</span><span class="v mono" id="mxb">0</span></div>
    <div id="mxres" style="margin-top:10px"></div>
    <div class="row end" style="margin-top:10px"><button class="btn danger" id="mxstop">■ Zastavit</button></div>
  </div>`);
  out.appendChild(card);
  let stop = false;
  card.querySelector('#mxstop').addEventListener('click', () => { stop = true; });

  const barEl = card.querySelector('#mxbar');
  const rEl = card.querySelector('#mxr'), sEl = card.querySelector('#mxs'),
        vEl = card.querySelector('#mxv'), bEl = card.querySelector('#mxb');

  function finish(hit) {
    const zisk = returned - staked;
    const rtp = staked > 0 ? returned / staked : 0;
    card.querySelector('h3').textContent = 'Výsledek';
    card.querySelector('#mxres').innerHTML = `
      <p class="big ${hit ? 'pos' : 'warn'}">${hit ? '★ JACKPOT! Trefeno všech 6' : 'Zastaveno bez jackpotu'}</p>
      <div class="stat"><span class="k">Odehráno kol</span><span class="v mono">${num(rounds)}</span></div>
      <div class="stat"><span class="k">= dnů / let hraní</span><span class="v mono">${num(rounds / 2)} dní = ${num(rounds / 2 / 365, 1)} let</span></div>
      <div class="stat"><span class="k">Vsazeno</span><span class="v">${kc(staked)}</span></div>
      <div class="stat"><span class="k">Vráceno</span><span class="v">${kc(returned)}</span></div>
      <div class="stat"><span class="k">Zisk / bank</span><span class="v ${zisk >= 0 ? 'pos' : 'neg'}">${kc(zisk)}</span></div>
      <div class="stat"><span class="k">Výhry dle tref</span><span class="v mono">2→${num(tiers[2])} · 3→${num(tiers[3])} · 4→${num(tiers[4])} · 5→${num(tiers[5])}</span></div>
      ${hit ? `<div class="stat"><span class="k">Jackpot (kolo)</span><span class="v pos">${num(jackpotRound)} → ${kc(stake * MX.MULT[6])}</span></div>` : ''}
      <div class="stat"><span class="k">Reálné RTP</span><span class="v">${pct(rtp)}</span></div>
      <div class="dim small" style="margin-top:6px">Srov. teoretické RTP ${pct(mxRTP())}.
      Jackpot padne v průměru 1 z ${num(1 / mxJackpotProb(), 0)} kol.</div>`;
    card.querySelector('#mxstop').remove();
  }

  function step() {
    if (stop) { finish(false); return; }
    const end = Math.min(rounds + CHUNK, MAX);
    while (rounds < end) {
      pool.set(base);
      for (let i = 0; i < 6; i++) {
        const j = i + Math.floor(RNG() * (49 - i));
        const t = pool[i]; pool[i] = pool[j]; pool[j] = t;
      }
      let m = 0;
      for (let i = 0; i < 6; i++) if (mySet[pool[i]]) m++;
      rounds++; staked += stake;
      if (m === 6) {
        returned += stake * MX.MULT[6];
        jackpotRound = rounds;
        barEl.style.width = '100%';
        rEl.textContent = num(rounds); sEl.textContent = kc(staked);
        vEl.textContent = kc(returned); bEl.textContent = kc(returned - staked);
        finish(true);
        return;
      }
      if (m >= 2) { tiers[m]++; returned += stake * MX.MULT[m]; }
    }
    const prog = Math.min(1, rounds / (1 / mxJackpotProb()));
    barEl.style.width = (prog * 100).toFixed(2) + '%';
    rEl.textContent = num(rounds); sEl.textContent = kc(staked);
    vEl.textContent = kc(returned); bEl.textContent = kc(returned - staked);
    if (rounds >= MAX) { finish(false); return; }
    setTimeout(step, 0);
  }
  setTimeout(step, 0);
}

/* =========================================================================
 * 15) MAXA ŠESTKA — STATISTIKY
 * ========================================================================= */
function screenMxStats() {
  setTitle('Maxa Šestka — statistiky'); showBack(true);
  const dist = mxDist();
  const rtp = mxRTP();
  const pj = mxJackpotProb();
  let rows = '';
  for (let k = 6; k >= 0; k--) {
    rows += `<tr><td>${k}</td><td class="r mono">${(dist[k] * 100).toFixed(6)} %</td>
      <td class="r mono">1 z ${num(1 / dist[k], 1)}</td>
      <td class="r">${num(MX.VYHRY[k])} Kč</td></tr>`;
  }
  return h(`<div>
    <div class="card">
      <h3>Základní údaje</h3>
      <div class="stat"><span class="k">Losování</span><span class="v">6 z 49</span></div>
      <div class="stat"><span class="k">Frekvence</span><span class="v">2× denně (14:10, 18:10)</span></div>
      <div class="stat"><span class="k">Vklad</span><span class="v">35 Kč (70 = dvojnásobné výhry)</span></div>
      <div class="stat"><span class="k">Výhry</span><span class="v">pevné, nedělí se</span></div>
      <div class="stat"><span class="k">RTP (spočítané)</span><span class="v warn">${pct(rtp)}</span></div>
    </div>
    <div class="card">
      <h3>Pravděpodobnost hlavní výhry (6/6)</h3>
      <p class="big center warn">${(pj * 100).toFixed(8)} %</p>
      <p class="center dim">= 1 z ${num(1 / pj)} · při 2 losováních denně ≈
      ${num(1 / pj / 2 / 365, 0)} let hraní</p>
    </div>
    <div class="card">
      <h3>Výherní tabulka</h3>
      <table><thead><tr><th>Trefy</th><th class="r">P</th><th class="r">1 z</th>
      <th class="r">Výhra (35 Kč)</th></tr></thead><tbody>${rows}</tbody></table>
    </div>
    <div class="card">
      <h3>Srovnání</h3>
      <table><thead><tr><th></th><th class="r">Lucky Six</th><th class="r">Maxa Šestka</th></tr></thead>
      <tbody>
        <tr><td>Losování</td><td class="r">35 z 48</td><td class="r">6 z 49</td></tr>
        <tr><td>Frekvence</td><td class="r">3,5 min</td><td class="r">2× denně</td></tr>
        <tr><td>RTP</td><td class="r pos">75,87 %</td><td class="r warn">59,57 %</td></tr>
        <tr><td>Výplata dle</td><td class="r">pořadí 6. trefy</td><td class="r">počtu tref</td></tr>
      </tbody></table>
      <p class="dim small" style="margin-top:8px">Lucky Six je hráčsky výrazně přívětivější —
      i když Maxa láká na 5 000 000 Kč.</p>
    </div>
  </div>`);
}

/* =========================================================================
 * 16) POMOCNÉ
 * ========================================================================= */
function toast(container, msg, cls) {
  container.innerHTML = `<div class="card"><span class="badge ${cls || 'yl'}">${esc(msg)}</span></div>`;
}
function download(name, text) {
  const b = new Blob([text], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(b); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/* =========================================================================
 * 17) REGISTR OBRAZOVEK + START
 * ========================================================================= */
const SCREENS = {
  'menu': { name: 'menu', fn: screenMenu },
  'l6-solo': { name: 'l6-solo', fn: screenL6Solo },
  'l6-system': { name: 'l6-system', fn: screenL6System },
  'l6-special': { name: 'l6-special', fn: screenL6Special },
  'l6-day': { name: 'l6-day', fn: screenL6Day },
  'l6-stats': { name: 'l6-stats', fn: screenL6Stats },
  'mx-solo': { name: 'mx-solo', fn: screenMxSolo },
  'mx-stats': { name: 'mx-stats', fn: screenMxStats },
};

function render(screenName) {
  const s = SCREENS[screenName];
  if (!s) return;
  app().innerHTML = '';
  app().appendChild(s.fn());
  window.scrollTo(0, 0);
}

document.getElementById('back').addEventListener('click', () => {
  if (NAV.stack.length > 1) {
    NAV.stack.pop();
    render(NAV.stack[NAV.stack.length - 1]);
  }
});

/* start */
NAV.stack = ['menu'];
render('menu');

/* service worker */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(() => {});
  });
}

/* online/offline indikátor */
function netUpdate() {
  const dot = document.getElementById('netdot');
  const txt = document.getElementById('nettext');
  const on = navigator.onLine;
  dot.classList.toggle('ok', on);
  txt.textContent = on ? 'online' : 'offline';
}
window.addEventListener('online', netUpdate);
window.addEventListener('offline', netUpdate);
netUpdate();

/* install prompt (Android/Chrome) */
let deferredPrompt = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  deferredPrompt = e;
  const b = document.getElementById('install');
  b.hidden = false;
  b.addEventListener('click', async () => {
    b.hidden = true;
    deferredPrompt.prompt();
    await deferredPrompt.userChoice;
    deferredPrompt = null;
  });
});