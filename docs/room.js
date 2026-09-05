// Canvas room view: 40 tables, 257 students, animated reseating.
import { avatarBitmap } from './avatars.js';

const COLORS = { one: '#2e9e5b', two: '#0f6b3a', none: '#c2bcb1', hero: '#f2b134', coal: '#d64545',
  friend: '#e08a2e', anchor: '#f2b134', table: '#efe6d6', tableLine: '#dccfb8', g11: '#dbe9f6', g12: '#f8e2c8',
  ink: '#2b2723', ink3: '#8b847a', hover: '#2b2723' };

const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2); // cubic in-out

export class RoomView {
  constructor(canvas, trace, opts = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.opts = Object.assign({ key: 'tables', showAvatars: true, dimOthers: false, coalition: null,
      hero: null, friends: null, link: null, onHover: null, labelGrades: true, duration: 1200 }, opts);
    this.setTrace(trace, false);
    this.rot = 0;
    this.pos = new Map();      // id -> {x,y}
    this.anim = null;
    this.hoverId = null;
    this.tintAlpha = 0;
    this._raf = null;
    this._onMove = e => this._hover(e);
    this._onLeave = () => { if (this.hoverId) { this.hoverId = null; this._emitHover(null); this.requestDraw(); } };
    canvas.addEventListener('mousemove', this._onMove);
    canvas.addEventListener('mouseleave', this._onLeave);
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(canvas);
    this.resize();
  }

  destroy() {
    this._ro.disconnect();
    this.canvas.removeEventListener('mousemove', this._onMove);
    this.canvas.removeEventListener('mouseleave', this._onLeave);
    if (this._raf) cancelAnimationFrame(this._raf);
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

  setOpts(o) { Object.assign(this.opts, o); this.requestDraw(); }

  // ---------- layout ----------
  resize() {
    const dpr = window.devicePixelRatio || 1;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.w = w; this.h = h;
    this.canvas.width = Math.round(w * dpr); this.canvas.height = Math.round(h * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this._layout();
    this._snapPositions();
    this.requestDraw();
  }

  _layout() {
    const cols = 8, rows = 5, aisle = Math.max(10, this.w * 0.03);
    const padX = 8, padTop = 26, padBot = 8;
    const cw = (this.w - 2 * padX - aisle) / cols, ch = (this.h - padTop - padBot) / rows;
    this.cell = { cw, ch };
    this.dotR = Math.max(5, Math.min(12, Math.min(cw, ch) * 0.085));
    this.tableR = Math.min(cw, ch) * 0.30;
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
    if (!animate || idx === this.rot && !this.anim) { if (idx !== this.rot) this.snapTo(idx); else this.requestDraw(); return; }
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

  requestDraw() { if (!this.anim) this._tick(); }

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
      if (this.tableR > 20) {
        ctx.fillStyle = COLORS.ink3; ctx.font = `${Math.round(this.tableR * 0.42)}px Avenir Next, Segoe UI, Arial, sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillText(String(this.caps[t]), c.x, c.y);
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
    const hoverFriends = this.hoverId ? this.listed.get(this.hoverId) : null;
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
        const bm = avatarBitmap(id, px, () => this.requestDraw());
        if (bm.dataset.ready === '1') { ctx.drawImage(bm, p.x - r, p.y - r, r * 2, r * 2); drewAvatar = true; }
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
  _hover(e) {
    if (this.anim) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
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
