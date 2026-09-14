// Canvas room view: 40 tables, 257 students, animated reseating.
import { avatarBitmap } from './avatars.js?v=20260914-minimal-4';

const COLORS = { one: '#2e9e5b', two: '#0f6b3a', none: '#c2bcb1', hero: '#f2b134', coal: '#d64545',
  friend: '#e08a2e', anchor: '#f2b134', table: '#efe6d6', tableLine: '#dccfb8', g11: '#dbe9f6', g12: '#f8e2c8',
  ink: '#2b2723', ink3: '#8b847a', hover: '#2b2723' };

const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2); // cubic in-out
// avatarBitmap caches a single loading bitmap across both rooms. Notify every
// room waiting for that bitmap, even when another room created it first.
const avatarWaiters = new WeakMap();

export class RoomView {
  constructor(canvas, trace, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.opts = Object.assign({ key: 'tables', showAvatars: true, dimOthers: false, coalition: null,
      hero: null, friends: null, link: null, onHover: null, labelGrades: true, duration: 1200,
      portraitProvider: null, onSelectTable: null, showHoverFriends: true }, opts);
    this._portraitCache = new Map();
    this._pendingAvatars = new Set();
    this._portraitGeneration = 0;
    this._destroyed = false;
    this.selectedTable = null;
    this._originalCursor = canvas.style.cursor;
    this._originalAccessibility = Object.fromEntries(['role', 'tabindex', 'aria-label'].map(name => [name, canvas.getAttribute(name)]));
    this.setTrace(trace, false);
    this.rot = 0;
    this.pos = new Map();      // id -> {x,y}
    this.anim = null;
    this.hoverId = null;
    this.tintAlpha = 0;
    this._raf = null;
    this._onMove = e => this._hover(e);
    this._onLeave = () => { if (this.hoverId) { this.hoverId = null; this._emitHover(null); this.requestDraw(); } };
    this._onClick = e => this._selectAt(e);
    this._onKeyDown = e => this._selectWithKeyboard(e);
    canvas.addEventListener('mousemove', this._onMove);
    canvas.addEventListener('mouseleave', this._onLeave);
    canvas.addEventListener('click', this._onClick);
    canvas.addEventListener('keydown', this._onKeyDown);
    this._updateAccessibility();
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(canvas);
    this.resize();
  }

  destroy() {
    this._destroyed = true;
    this._ro.disconnect();
    this.canvas.removeEventListener('mousemove', this._onMove);
    this.canvas.removeEventListener('mouseleave', this._onLeave);
    this.canvas.removeEventListener('click', this._onClick);
    this.canvas.removeEventListener('keydown', this._onKeyDown);
    this.clearPortraitCache();
    for (const bitmap of this._pendingAvatars) avatarWaiters.get(bitmap)?.delete(this);
    this._pendingAvatars.clear();
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = null;
    this.anim = null;
    this._restoreAccessibility();
  }

  setTrace(trace, redraw = true) {
    this.trace = trace;
    this.students = trace.students.map(s => s.id);
    this.grade = new Map(trace.students.map(s => [s.id, s.grade]));
    this.listed = new Map(trace.students.map((s, i) => [s.id, new Set(trace.listed[i])]));
    this.caps = trace.config.tableCapacities;
    this.sameGrade = trace.config.sameGradeTableGrade;
    this._rotCache = new Map();
    if (redraw) { this.snapTo(this.rot); }
  }

  setOpts(o) {
    const portraitChanged = Object.hasOwn(o, 'portraitProvider') && o.portraitProvider !== this.opts.portraitProvider;
    Object.assign(this.opts, o);
    if (portraitChanged) {
      this.clearPortraitCache();
      this.hoverId = null;
      this.selectedTable = null;
      this._emitHover(null);
      // A hidden tab has zero client dimensions, so resize may return early.
      // Erase its backing store synchronously before old object URLs can be
      // revoked, then repaint using the last known logical layout if needed.
      this.ctx.save();
      this.ctx.setTransform(1, 0, 0, 1, 0, 0);
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
      this.ctx.restore();
      this.resize();
      this.draw();
    }
    if (Object.hasOwn(o, 'onSelectTable')) this._updateAccessibility();
    this.requestDraw();
  }

  /** Drop decoded photos without revoking caller-owned object URLs. */
  clearPortraitCache() {
    this._portraitGeneration++;
    for (const entry of this._portraitCache.values()) {
      entry.image.onload = null;
      entry.image.onerror = null;
      entry.image.removeAttribute('src');
    }
    this._portraitCache.clear();
  }

  _portrait(id) {
    const url = this.opts.portraitProvider?.(id);
    // Real portraits may come only from files explicitly chosen in this tab.
    if (typeof url !== 'string' || !url.startsWith('blob:')) return null;
    let entry = this._portraitCache.get(url);
    if (!entry) {
      const generation = this._portraitGeneration;
      const image = new Image();
      image.decoding = 'async';
      entry = { image, ready: false };
      this._portraitCache.set(url, entry);
      image.onload = () => {
        if (this._destroyed || generation !== this._portraitGeneration) return;
        entry.ready = image.naturalWidth > 0 && image.naturalHeight > 0;
        this.requestDraw();
      };
      image.onerror = () => {
        if (this._destroyed || generation !== this._portraitGeneration) return;
        entry.ready = false;
        this.requestDraw();
      };
      image.src = url;
    }
    return entry.ready ? entry.image : null;
  }

  _avatar(id, px) {
    const bitmap = avatarBitmap(id, px, () => {
      const waiting = avatarWaiters.get(bitmap);
      if (!waiting) return;
      for (const room of waiting) {
        room._pendingAvatars.delete(bitmap);
        room.requestDraw();
      }
      avatarWaiters.delete(bitmap);
    });
    if (bitmap.dataset.ready !== '1') {
      let waiting = avatarWaiters.get(bitmap);
      if (!waiting) { waiting = new Set(); avatarWaiters.set(bitmap, waiting); }
      waiting.add(this);
      this._pendingAvatars.add(bitmap);
    }
    return bitmap;
  }

  // ---------- layout ----------
  resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.w = w; this.h = h;
    this.canvas.width = Math.round(w * dpr); this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._layout();
    // Cached targets use canvas coordinates. They and in-flight coordinates
    // must be rebuilt after resizing, including when the room is zoomed.
    this._rotCache.clear();
    this.anim = null;
    this._snapPositions();
    this.requestDraw();
  }

  _layout() {
    const cols = 8, rows = 5, aisle = Math.max(10, this.w * 0.03);
    const padX = 8, padTop = 26, padBot = 8;
    const cw = (this.w - 2 * padX - aisle) / cols, ch = (this.h - padTop - padBot) / rows;
    this.cell = { cw, ch };
    const portraits = Boolean(this.opts.portraitProvider);
    this.dotR = Math.max(5, Math.min(portraits ? 28 : 12, Math.min(cw, ch) * (portraits ? 0.13 : 0.085)));
    this.tableR = Math.min(cw, ch) * (portraits ? 0.23 : 0.30);
    this.orbit = this.tableR + this.dotR * 0.95;
    // junior tables (in same-grade rotations) fill the left block, seniors the right
    const left = [], right = [];
    this.sameGrade.forEach((g, t) => (g === 11 ? left : right).push(t));
    this.tableXY = new Array(this.caps.length);
    const place = (list, colOffset, xShift) => list.forEach((t, k) => {
      const c = k % 4, r = Math.floor(k / 4);
      this.tableXY[t] = { x: padX + xShift + (c + colOffset) * cw + cw / 2, y: padTop + r * ch + ch / 2 };
    });
    place(left, 0, 0); place(right, 4, aisle);
    this.halves = { left: { x0: padX, x1: padX + 4 * cw }, right: { x0: padX + 4 * cw + aisle, x1: this.w - padX } };
    this.padTop = padTop;
  }

  seatXY(t, k, n) {
    const c = this.tableXY[t];
    const a = -Math.PI / 2 + (k / n) * Math.PI * 2;
    return { x: c.x + Math.cos(a) * this.orbit, y: c.y + Math.sin(a) * this.orbit };
  }

  // ---------- rotation data ----------
  rotInfo(idx) {
    const key = `${this.opts.key}:${idx}`;
    let info = this._rotCache.get(key);
    if (info) return info;
    const rot = this.trace.rotations[idx];
    const tables = rot[this.opts.key];
    const tableOf = new Map(), seat = new Map(), count = new Map(), target = new Map();
    tables.forEach((tbl, t) => tbl.forEach((id, k) => {
      tableOf.set(id, t); seat.set(id, k);
      target.set(id, this.seatXY(t, k, tbl.length));
    }));
    tables.forEach(tbl => {
      const set = new Set(tbl);
      tbl.forEach(id => {
        let c = 0;
        for (const f of this.listed.get(id)) if (set.has(f)) c++;
        count.set(id, c);
      });
    });
    info = { rot, tables, tableOf, seat, count, target, state: rot.state };
    this._rotCache.set(key, info);
    return info;
  }

  _snapPositions() {
    if (!this.tableXY) return;
    const info = this.rotInfo(this.rot);
    this.students.forEach(id => { const p = info.target.get(id); this.pos.set(id, { x: p.x, y: p.y }); });
    this.tintAlpha = info.state === 'same' ? 1 : 0;
  }

  snapTo(idx) {
    this.rot = idx;
    this.anim = null;
    this._rotCache.clear();
    this._snapPositions();
    this.requestDraw();
  }

  /** Animate students flying to their seats in rotation idx. */
  goTo(idx, animate = true) {
    if (!animate || window.matchMedia('(prefers-reduced-motion: reduce)').matches || idx === this.rot && !this.anim) { if (idx !== this.rot) this.snapTo(idx); else this.requestDraw(); return; }
    const fromInfo = this.rotInfo(this.rot);
    const toInfo = this.rotInfo(idx);
    const from = new Map(), to = new Map(), delay = new Map();
    this.students.forEach(id => {
      const p = this.pos.get(id);
      from.set(id, { x: p.x, y: p.y });
      to.set(id, toInfo.target.get(id));
      // stagger by origin table so tables "release" one after another
      const t = fromInfo.tableOf.get(id);
      delay.set(id, (0.35 * ((t * 7) % 40)) / 40);
    });
    this.anim = { from, to, delay, t0: performance.now(), dur: this.opts.duration,
      tintFrom: this.tintAlpha, tintTo: toInfo.state === 'same' ? 1 : 0, fromRot: this.rot };
    this.rot = idx;
    this.hoverId = null;
    this._emitHover(null);
    this._tick();
  }

  _tick() {
    if (this._raf) cancelAnimationFrame(this._raf);
    this._raf = requestAnimationFrame(() => {
      this._raf = null;
      const a = this.anim;
      if (!a) { this.draw(); return; }
      const u = Math.min(1, (performance.now() - a.t0) / a.dur);
      this.students.forEach(id => {
        const d = a.delay.get(id);
        const p = Math.max(0, Math.min(1, (u - d) / 0.65));
        const e = ease(p);
        const f = a.from.get(id), t = a.to.get(id);
        const dx = t.x - f.x, dy = t.y - f.y;
        const dist = Math.hypot(dx, dy);
        // gentle arc perpendicular to the flight path
        const bulge = Math.min(40, dist * 0.18) * Math.sin(Math.PI * e) * ((id.charCodeAt(3) % 2) ? 1 : -1);
        const nx = dist ? -dy / dist : 0, ny = dist ? dx / dist : 0;
        const cur = this.pos.get(id);
        cur.x = f.x + dx * e + nx * bulge;
        cur.y = f.y + dy * e + ny * bulge;
        cur.p = e;
      });
      this.tintAlpha = a.tintFrom + (a.tintTo - a.tintFrom) * ease(u);
      this.draw(u);
      if (u < 1) this._tick();
      else { this.anim = null; this.students.forEach(id => { const c = this.pos.get(id); c.p = 1; }); this.draw(); }
    });
  }

  requestDraw() { if (!this._destroyed && !this.anim) this._tick(); }

  // ---------- drawing ----------
  colorFor(count, id) {
    if (!this.listed.get(id).size) return COLORS.none;
    return count >= 2 ? COLORS.two : count === 1 ? COLORS.one : COLORS.none;
  }

  draw(u = 1) {
    const ctx = this.ctx, w = this.w, h = this.h;
    if (!w) return;
    const info = this.rotInfo(this.rot);
    const prev = this.anim ? this.rotInfo(this.anim.fromRot) : null;
    ctx.clearRect(0, 0, w, h);
    // grade halves tint (same-grade rotations)
    if (this.tintAlpha > 0.01) {
      ctx.save();
      ctx.globalAlpha = this.tintAlpha;
      const draw = (hx, color, label) => {
        ctx.fillStyle = color;
        roundRect(ctx, hx.x0, 4, hx.x1 - hx.x0, h - 8, 16); ctx.fill();
        if (this.opts.labelGrades) {
          ctx.fillStyle = COLORS.ink3; ctx.font = '600 12px Avenir Next, Segoe UI, Arial, sans-serif';
          ctx.textAlign = 'center'; ctx.textBaseline = 'top';
          ctx.fillText(label, (hx.x0 + hx.x1) / 2, 9);
        }
      };
      draw(this.halves.left, COLORS.g11, 'GRADE 11 · juniors');
      draw(this.halves.right, COLORS.g12, 'GRADE 12 · seniors');
      ctx.restore();
    }
    // tables
    const heroTable = this.opts.hero ? info.tableOf.get(this.opts.hero) : -1;
    for (let t = 0; t < this.caps.length; t++) {
      const c = this.tableXY[t];
      ctx.beginPath(); ctx.arc(c.x, c.y, this.tableR, 0, Math.PI * 2);
      ctx.fillStyle = t === heroTable ? '#fff3cf' : COLORS.table;
      ctx.fill();
      ctx.lineWidth = t === heroTable ? 3 : 1.5;
      ctx.strokeStyle = t === heroTable ? COLORS.hero : COLORS.tableLine;
      ctx.stroke();
      if (t === this.selectedTable && this.opts.onSelectTable) {
        ctx.beginPath(); ctx.arc(c.x, c.y, this.tableR + 3, 0, Math.PI * 2);
        ctx.lineWidth = 2.5; ctx.strokeStyle = COLORS.hover; ctx.stroke();
      }
      if (this.tableR > 20) {
        ctx.fillStyle = COLORS.ink3; ctx.font = `${Math.round(this.tableR * 0.42)}px Avenir Next, Segoe UI, Arial, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(this.opts.portraitProvider ? String(t + 1) : String(this.caps[t]), c.x, c.y);
      }
    }
    // anchor link
    if (this.opts.link && !this.anim) {
      const a = this.pos.get(this.opts.link.from), b = this.pos.get(this.opts.link.to);
      if (a && b) {
        ctx.save();
        ctx.strokeStyle = COLORS.anchor; ctx.lineWidth = 4; ctx.lineCap = 'round';
        ctx.shadowColor = 'rgba(242,177,52,.6)'; ctx.shadowBlur = 10;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        ctx.restore();
      }
    }
    // hover: friend rings
    const hoverFriends = this.hoverId && this.opts.showHoverFriends ? this.listed.get(this.hoverId) : null;
    const friends = this.opts.friends;
    const coal = this.opts.coalition;
    const r = this.dotR;
    const px = Math.round(r * 2 * (window.devicePixelRatio || 1));
    const dim = this.opts.dimOthers && this.opts.hero;
    const heroFriendsAndTable = dim ? new Set([...(friends || []), ...(info.tables[heroTable] || [])]) : null;
    // dots
    for (const id of this.students) {
      const p = this.pos.get(id);
      const cnt = info.count.get(id);
      let color = this.colorFor(cnt, id);
      if (prev && p.p < 0.5) color = this.colorFor(prev.count.get(id), id);
      const isHero = id === this.opts.hero;
      const dimmed = dim && !isHero && !heroFriendsAndTable.has(id) && (!hoverFriends || !hoverFriends.has(id)) && id !== this.hoverId;
      ctx.save();
      if (dimmed) ctx.globalAlpha = 0.35;
      // avatar or plain dot
      let drewAvatar = false;
      if (this.opts.showAvatars && r >= 5) {
        const portrait = this._portrait(id);
        if (portrait) {
          const side = Math.min(portrait.naturalWidth, portrait.naturalHeight);
          ctx.save();
          ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.clip();
          ctx.drawImage(portrait, (portrait.naturalWidth - side) / 2, (portrait.naturalHeight - side) / 2,
            side, side, p.x - r, p.y - r, r * 2, r * 2);
          ctx.restore();
          drewAvatar = true;
        } else {
          const bm = this._avatar(id, px);
          if (bm.dataset.ready === '1') { ctx.drawImage(bm, p.x - r, p.y - r, r * 2, r * 2); drewAvatar = true; }
        }
      }
      if (!drewAvatar) { ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); }
      // outcome ring
      ctx.beginPath(); ctx.arc(p.x, p.y, r + 0.5, 0, Math.PI * 2);
      ctx.lineWidth = drewAvatar ? Math.max(2.2, r * 0.32) : 1;
      ctx.strokeStyle = drewAvatar ? color : 'rgba(255,255,255,.7)';
      ctx.stroke();
      // overlays
      if (coal && coal.has(id)) { ctx.beginPath(); ctx.arc(p.x, p.y, r + 3.5, 0, Math.PI * 2); ctx.lineWidth = 3.5; ctx.strokeStyle = COLORS.coal; ctx.stroke(); }
      if (friends && friends.has(id) && !isHero) { ctx.beginPath(); ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2); ctx.lineWidth = 2; ctx.setLineDash([3, 3]); ctx.strokeStyle = COLORS.friend; ctx.stroke(); ctx.setLineDash([]); }
      if (hoverFriends && hoverFriends.has(id)) { ctx.beginPath(); ctx.arc(p.x, p.y, r + 3.5, 0, Math.PI * 2); ctx.lineWidth = 2.5; ctx.strokeStyle = COLORS.hover; ctx.stroke(); }
      if (isHero) { ctx.beginPath(); ctx.arc(p.x, p.y, r + 4, 0, Math.PI * 2); ctx.lineWidth = 4; ctx.strokeStyle = COLORS.hero; ctx.stroke(); }
      if (this.opts.link && !this.anim && id === this.opts.link.to) { ctx.beginPath(); ctx.arc(p.x, p.y, r + 4, 0, Math.PI * 2); ctx.lineWidth = 3; ctx.strokeStyle = COLORS.anchor; ctx.stroke(); }
      if (id === this.hoverId) { ctx.beginPath(); ctx.arc(p.x, p.y, r + 5, 0, Math.PI * 2); ctx.lineWidth = 2; ctx.strokeStyle = COLORS.hover; ctx.stroke(); }
      ctx.restore();
    }
  }

  // ---------- hover ----------
  _pointerPosition(e) {
    const rect = this.canvas.getBoundingClientRect();
    return { x: (e.clientX - rect.left) * this.w / rect.width,
      y: (e.clientY - rect.top) * this.h / rect.height };
  }

  _hover(e) {
    if (this.anim) return;
    const { x, y } = this._pointerPosition(e);
    let best = null, bd = (this.dotR + 4) ** 2;
    for (const id of this.students) {
      const p = this.pos.get(id);
      const d = (p.x - x) ** 2 + (p.y - y) ** 2;
      if (d < bd) { bd = d; best = id; }
    }
    if (best !== this.hoverId) {
      this.hoverId = best;
      this._emitHover(best, e);
      this.requestDraw();
    } else if (best) this._emitHover(best, e);
  }

  // ---------- table inspection (click, touch-generated click, keyboard) ----------
  _restoreAccessibility() {
    this.canvas.style.cursor = this._originalCursor;
    for (const [name, value] of Object.entries(this._originalAccessibility)) {
      if (value === null) this.canvas.removeAttribute(name);
      else this.canvas.setAttribute(name, value);
    }
  }

  _updateAccessibility() {
    if (!this.opts.onSelectTable) { this._restoreAccessibility(); return; }
    const label = this.opts.key === 'tablesRandom' ? 'Random seating room' : 'Proposed seating room';
    const selection = this.selectedTable === null ? '' : ` Table ${this.selectedTable + 1} selected.`;
    this.canvas.setAttribute('role', 'button');
    this.canvas.setAttribute('tabindex', '0');
    this.canvas.style.cursor = 'pointer';
    this.canvas.setAttribute('aria-label', `${label}.${selection} Click a table to inspect its simulated seating. Use arrow keys to choose a table and Enter to inspect it.`);
  }

  selectTable(table) {
    if (!this.opts.onSelectTable || !Number.isInteger(table) || table < 0 || table >= this.caps.length) return false;
    this.selectedTable = table;
    this._updateAccessibility();
    const info = this.rotInfo(this.rot);
    this.opts.onSelectTable({ table, index: this.rot, ids: [...info.tables[table]], key: this.opts.key });
    this.requestDraw();
    return true;
  }

  clearSelection() {
    this.selectedTable = null;
    this._updateAccessibility();
    this.requestDraw();
  }

  _selectAt(e) {
    if (!this.opts.onSelectTable || this.anim) return;
    const { x, y } = this._pointerPosition(e);
    let best = null, distance = Infinity;
    // Clicking a face inspects the table it currently belongs to.
    for (const id of this.students) {
      const p = this.pos.get(id);
      const d = (p.x - x) ** 2 + (p.y - y) ** 2;
      if (d <= (this.dotR + 5) ** 2 && d < distance) {
        best = this.rotInfo(this.rot).tableOf.get(id); distance = d;
      }
    }
    if (best === null) {
      for (let table = 0; table < this.tableXY.length; table++) {
        const p = this.tableXY[table], d = (p.x - x) ** 2 + (p.y - y) ** 2;
        if (d <= (this.tableR + 6) ** 2 && d < distance) { best = table; distance = d; }
      }
    }
    if (best !== null) this.selectTable(best);
  }

  _selectWithKeyboard(e) {
    if (!this.opts.onSelectTable || this.anim) return;
    const arrows = { ArrowRight: 1, ArrowLeft: -1, ArrowDown: 4, ArrowUp: -4 };
    if (Object.hasOwn(arrows, e.key)) {
      e.preventDefault(); e.stopPropagation();
      this.selectedTable = ((this.selectedTable ?? 0) + arrows[e.key] + this.caps.length) % this.caps.length;
      this._updateAccessibility();
      this.requestDraw();
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault(); e.stopPropagation();
      this.selectTable(this.selectedTable ?? 0);
    } else if (e.key === 'Escape') {
      e.preventDefault(); e.stopPropagation();
      this.selectedTable = null;
      this._updateAccessibility();
      this.opts.onSelectTable(null);
      this.requestDraw();
    }
  }

  _emitHover(id, e) {
    if (!this.opts.onHover) return;
    if (!id) { this.opts.onHover(null); return; }
    const info = this.rotInfo(this.rot);
    const t = info.tableOf.get(id);
    const mates = info.tables[t].filter(x => x !== id);
    const listedHere = mates.filter(m => this.listed.get(id).has(m));
    this.opts.onHover({ id, table: t, mates, listedHere, listed: [...this.listed.get(id)], count: info.count.get(id),
      grade: this.grade.get(id), x: e ? e.clientX : 0, y: e ? e.clientY : 0 });
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

export { COLORS };
