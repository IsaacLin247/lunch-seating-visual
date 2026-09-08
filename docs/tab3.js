// Tab 3, Trying to Game It: a six-student coalition under four defense levels.
import { RoomView } from './room.js';
import { avatarUri } from './avatars.js';

const MODES = {
  coalition_none: {
    explainer: 'With no rules, six friends each list just one name (the next in a loop), and the hard guarantee has no choice but to seat the whole loop at one table, every rotation.',
    wiringNote: 'Each arrow = "I listed you". One name each, in a loop: the only way to satisfy all six is one table.',
  },
  coalition_min4: {
    explainer: 'With four names each the six can never force a shared table, but the strongest wiring we found (nobody lists member one) still keeps them in threes: the rule caps the damage, it does not erase it.',
    wiringNote: 'Min-4 rule, best wiring found by exhaustive search over all 4-of-5 wirings: nobody lists the first member, so no seating can put them in pairs; two triples is the least cohesion any solver can grant.',
  },
  coalition_stratified: {
    explainer: 'Five members list the next two around a cycle plus two seniors each; in same-grade rotations the seniors vanish from the lists that count, and the guarantee has to seat all six together, eight rotations a year.',
    wiringNote: 'Every list has four names and two same-grade names. Green stubs are names outside the group (seniors). In same-grade rotations those names are not usable anchors, the five-cycle cannot be split, and the sixth member, who lists four of the five, is dragged along.',
  },
  coalition_screened: {
    explainer: 'Checked on each rotation state’s own lists, the same-grade attack is caught before the first lunch; the strongest wiring that still passes cannot capture a table.',
    wiringNote: 'Flagged wiring (left) was returned: on the same-grade lists the five-cycle admits no closed split. The group resubmits the strongest wiring that passes (right, the 4-of-5 star), which forces triples but never a table.',
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

  function wiring(members, lists, opts = {}) {
    const H = 215, cx = opts.cx || 150, cy = 98, R = 62, r = 15;
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
    // outside names as green stubs, one per name not in the group
    pos.forEach(p => {
      const out = lists.get(p.m).filter(b => !mset.has(b)).length;
      if (!out) return;
      const ax = p.x - cx, ay = p.y - cy, d = Math.hypot(ax, ay), base = Math.atan2(ay / d, ax / d);
      for (let k = 0; k < out; k++) {
        const ang = base + (k - (out - 1) / 2) * 0.38;
        const x1 = p.x + Math.cos(ang) * (r + 2), y1 = p.y + Math.sin(ang) * (r + 2);
        s += `<line x1="${x1}" y1="${y1}" x2="${x1 + Math.cos(ang) * 16}" y2="${y1 + Math.sin(ang) * 16}" stroke="#2e9e5b" stroke-width="1.5" marker-end="url(#ahg)"/>`;
      }
    });
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
        wiring(members, init, { cx: 150, id: 'a', stamp: 'RETURNED', caption: 'as submitted · flagged on same-grade lists' }) +
        `<text x="300" y="104" text-anchor="middle" font-size="26" fill="#8b847a">→</text>` +
        wiring(members, lists, { cx: 450, id: 'b', color: '#c98b8b', caption: 'resubmitted · strongest wiring that passes' }) + `</svg>`;
    } else {
      inner = `<svg viewBox="0 0 300 215">${defs}${wiring(members, lists, {})}</svg>`;
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
      const sofar = trace.rotations.slice(0, rot + 1);
      const intactSoFar = sofar.filter(x => x.coalition.intact).length;
      const intactSame = sofar.filter(x => x.coalition.intact && x.state === 'same').length;
      const sameSoFar = sofar.filter(x => x.state === 'same').length;
      $('g-avg').textContent = c.avgCluster.toFixed(1);
      $('g-max').textContent = `${c.maxCluster}`;
      $('g-intact').textContent = `${intactSoFar} / ${rot + 1}`;
      $('g-intact-sub').textContent = mode === 'coalition_stratified'
        ? `all six at one table · ${intactSame} of ${sameSoFar} same-grade rotations`
        : 'all six at one table';
      const members = trace.config.coalition;
      const ids = trace.students.map(s => s.id);
      const lists = new Map(ids.map((id, i) => [id, new Set(trace.listed[i])]));
      const ge1 = members.filter(m => { const t = R.tables.find(t => t.includes(m)); return t.some(x => x !== m && lists.get(m).has(x)); }).length;
      $('g-ge1').textContent = `${ge1} of ${members.length}`;
      const banner = $('intact-banner');
      if (c.intact) {
        banner.className = 'banner-intact';
        banner.textContent = `group intact ${intactSoFar}/${rot + 1}: one table captured` + (R.state === 'same' ? ' (same-grade rotation)' : '');
      } else {
        banner.className = 'banner-intact split';
        banner.textContent = `group split ${c.pattern} across ${c.clusters.length} tables, intact ${intactSoFar}/${rot + 1}`;
      }
      $('mode-explainer').textContent = MODES[mode].explainer;
      const sb = $('screen-banner');
      if (mode === 'coalition_screened') {
        const scr = trace.config.screen;
        const same = scr.perState.same;
        const core = same.flags.map(f => `{${f.members.join(', ')}}`).join(' and ');
        sb.hidden = false;
        sb.innerHTML = `⚠ Submission screen flagged this group (insular lists), returned for diversification before rotation 1` +
          `<small>On the mixed-rotation lists nothing is flagged: the seniors they named are valid anchors there. On the same-grade lists the seniors drop out and ${core} admits no split into two closed parts, so the guarantee would have to seat it as a block. ` +
          `${scr.nReturned} students returned, ${scr.honestFlagged.length} honest students affected. ` +
          `Resubmission: ${scr.resubmission}; after it, ${scr.afterResubmission.nFlagged} flagged.</small>`;
      } else sb.hidden = true;
      if (mode !== lastMode) drawWiring();
      lastRot = rot; lastMode = mode;
    },
    resize() { room.resize(); },
  };
  return api;
}
