// Tab 3 — Trying to Game It: a six-student coalition under three defense levels.
import { RoomView } from './room.js';
import { avatarUri } from './avatars.js';

const MODES = {
  coalition_none: {
    explainer: 'With no rules, six friends each list just one name — the next in a loop — and the hard guarantee has no choice but to seat the whole loop at one table, every rotation.',
    wiringNote: 'Each arrow = "I listed you". One name each, in a loop: the only way to satisfy all six is one table.',
  },
  coalition_min4: {
    explainer: 'The guarantee still gives each of them one familiar face — it just can’t be weaponized into a private table.',
    wiringNote: 'Min-4 rule: each lists 4 of the 5 others (wired so penalty-free triples exist). The solver, which wants exactly one familiar face per student, splits them into pairs.',
  },
  coalition_screened: {
    explainer: 'Lists that only point inward are caught before anyone is seated; once the group adds real outside names, the year plays out like everyone else’s.',
    wiringNote: 'Flagged wiring (left) was returned. Resubmitted lists (right) name the five friends plus three people outside the group — enough outward names to pass both screens.',
  },
};

export function createTab3(ctx) {
  const $ = id => document.getElementById(id);
  let mode = 'coalition_none';
  let trace = ctx.traces[mode];
  let lastRot = -1, lastMode = null;
  const room = new RoomView($('room-game'), trace, { key: 'tables', coalition: new Set(trace.config.coalition), onHover: ctx.showTooltip });

  document.querySelectorAll('.seg').forEach(b => b.addEventListener('click', () => {
    document.querySelectorAll('.seg').forEach(x => x.classList.toggle('is-active', x === b));
    setMode(b.dataset.mode);
  }));

  function setMode(m) {
    mode = m; trace = ctx.traces[m];
    room.setTrace(trace, false);
    room.setOpts({ coalition: new Set(trace.config.coalition) });
    room.snapTo(lastRot >= 0 ? lastRot : 0);
    api.render(lastRot >= 0 ? lastRot : 0, false, true);
  }

  function wiring(el, members, lists, opts = {}) {
    const W = 300, H = 215, cx = opts.cx || 150, cy = 98, R = 62, r = 15;
    const pos = members.map((m, i) => { const a = -Math.PI / 2 + (i / members.length) * Math.PI * 2; return { m, x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R }; });
    const P = new Map(pos.map(p => [p.m, p]));
    let s = '';
    const mset = new Set(members);
    const seen = new Set();
    members.forEach(a => lists.get(a).forEach(b => {
      if (!mset.has(b)) return;
      const key = a < b ? `${a}|${b}` : `${b}|${a}`;
      const mutual = lists.get(b).includes(a);
      if (mutual && seen.has(key)) return;
      seen.add(key);
      const pa = P.get(a), pb = P.get(b);
      const dx = pb.x - pa.x, dy = pb.y - pa.y, d = Math.hypot(dx, dy);
      const ux = dx / d, uy = dy / d;
      const x1 = pa.x + ux * (r + 2), y1 = pa.y + uy * (r + 2), x2 = pb.x - ux * (r + 4), y2 = pb.y - uy * (r + 4);
      s += `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${opts.color || '#d64545'}" stroke-width="${mutual ? 2 : 1.5}" marker-end="url(#ah)" ${mutual ? 'marker-start="url(#ahs)"' : ''} opacity=".85"/>`;
    }));
    if (opts.outward) {
      pos.forEach(p => {
        const ax = p.x - cx, ay = p.y - cy, d = Math.hypot(ax, ay), ux = ax / d, uy = ay / d;
        for (let k = -1; k <= 1; k++) {
          const ang = Math.atan2(uy, ux) + k * 0.38;
          const x1 = p.x + Math.cos(ang) * (r + 2), y1 = p.y + Math.sin(ang) * (r + 2);
          s += `<line x1="${x1}" y1="${y1}" x2="${x1 + Math.cos(ang) * 16}" y2="${y1 + Math.sin(ang) * 16}" stroke="#2e9e5b" stroke-width="1.5" marker-end="url(#ahg)"/>`;
        }
      });
    }
    pos.forEach(p => {
      s += `<clipPath id="c${opts.id || ''}${p.m}"><circle cx="${p.x}" cy="${p.y}" r="${r}"/></clipPath>` +
        `<image href="${avatarUri(p.m)}" x="${p.x - r}" y="${p.y - r}" width="${2 * r}" height="${2 * r}" clip-path="url(#c${opts.id || ''}${p.m})"/>` +
        `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="none" stroke="#d64545" stroke-width="2.5"/>`;
    });
    if (opts.stamp) s += `<text x="${cx}" y="${cy + 4}" text-anchor="middle" font-size="13" font-weight="800" fill="#c23b3b" transform="rotate(-18 ${cx} ${cy})" style="letter-spacing:.08em">${opts.stamp}</text>`;
    if (opts.caption) s += `<text x="${cx}" y="${H - 4}" text-anchor="middle" font-size="11" fill="#8b847a">${opts.caption}</text>`;
    return s;
  }

  function drawWiring() {
    const members = trace.config.coalition;
    const ids = trace.students.map(s => s.id);
    const lists = new Map(ids.map((id, i) => [id, trace.listed[i]]));
    const defs = `<defs>
      <marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="#d64545"/></marker>
      <marker id="ahs" viewBox="0 0 10 10" refX="2" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M10,1 L1,5 L10,9 z" fill="#d64545"/></marker>
      <marker id="ahg" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="#2e9e5b"/></marker></defs>`;
    let inner;
    if (mode === 'coalition_screened' && trace.listedInitial) {
      const init = new Map(ids.map((id, i) => [id, trace.listedInitial[i]]));
      inner = `<svg viewBox="0 0 600 215">${defs}` +
        wiring(null, members, init, { cx: 150, id: 'a', stamp: 'RETURNED', caption: 'as submitted · flagged' }) +
        `<text x="300" y="104" text-anchor="middle" font-size="26" fill="#8b847a">→</text>` +
        wiring(null, members, lists, { cx: 450, id: 'b', outward: true, color: '#c98b8b', caption: 'resubmitted · + outside names' }) + `</svg>`;
    } else {
      inner = `<svg viewBox="0 0 300 215">${defs}${wiring(null, members, lists, {})}</svg>`;
    }
    $('wiring').innerHTML = inner;
    $('wiring-note').textContent = MODES[mode].wiringNote;
  }

  const api = {
    render(rot, animate, force = false) {
      if (!force && rot === lastRot && mode === lastMode) return;
      const anim = animate && lastRot >= 0 && rot !== lastRot && mode === lastMode;
      room.goTo(rot, anim);
      const R = trace.rotations[rot];
      const c = R.coalition;
      const intactSoFar = trace.rotations.slice(0, rot + 1).filter(x => x.coalition.intact).length;
      $('g-avg').textContent = c.avgCluster.toFixed(1);
      $('g-max').textContent = `${c.maxCluster}`;
      $('g-intact').textContent = `${intactSoFar} / ${rot + 1}`;
      const members = trace.config.coalition;
      const ids = trace.students.map(s => s.id);
      const lists = new Map(ids.map((id, i) => [id, new Set(trace.listed[i])]));
      const ge1 = members.filter(m => { const t = R.tables.find(t => t.includes(m)); return t.some(x => x !== m && lists.get(m).has(x)); }).length;
      $('g-ge1').textContent = `${ge1} of ${members.length}`;
      const banner = $('intact-banner');
      if (c.intact) { banner.className = 'banner-intact'; banner.textContent = `group intact ${intactSoFar}/${rot + 1} — one table captured`; }
      else { banner.className = 'banner-intact split'; banner.textContent = `group scattered into ${c.clusters.length} tables — intact ${intactSoFar}/${rot + 1}`; }
      $('mode-explainer').textContent = MODES[mode].explainer;
      const sb = $('screen-banner');
      if (mode === 'coalition_screened') {
        const scr = trace.config.screen;
        sb.hidden = false;
        sb.innerHTML = `⚠ Submission screen flagged this group (insular lists) — returned for diversification before rotation 1` +
          `<small>Insularity screen: their six lists close on themselves (closure size ${scr.flags.find(f => f.screen === 'insularity')?.kernel?.length ?? 6}, limit 12). ` +
          `Boundary screen: heavy pairwise overlap with ≤3 outward names. ${scr.nFlagged} students flagged, ${scr.honestFlagged.length} of them honest. ` +
          `After resubmission: ${scr.afterResubmission.nFlagged} flagged.</small>`;
      } else sb.hidden = true;
      if (mode !== lastMode) drawWiring();
      lastRot = rot; lastMode = mode;
    },
    resize() { room.resize(); },
  };
  return api;
}
