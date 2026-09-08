// Coalition playback: graph annotations are structural; all outcomes are trace data.
import { RoomView } from './room.js';
import { avatarUri } from './avatars.js';
import { coalitionModes, EXPLANATIONS, observation } from './scenarios.js';

const esc = value => String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));

export function createTab3(ctx) {
  const $ = id => document.getElementById(id);
  const modes = coalitionModes(ctx.traces);
  let [mode, trace] = modes[0];
  let lastRot = -1, lastMode = null;
  const room = new RoomView($('room-game'), trace, { key: 'tables', coalition: new Set(trace.config.coalition), onHover: ctx.showTooltip });
  const container = $('scenario-modes');
  for (const [name, data] of modes) {
    const button = document.createElement('button');
    button.className = `seg${name === mode ? ' is-active' : ''}`;
    button.dataset.mode = name;
    button.textContent = data.config.short || data.config.title || name;
    button.setAttribute('aria-pressed', String(name === mode));
    button.addEventListener('click', () => {
      mode = name; trace = data;
      for (const item of container.children) {
        item.classList.toggle('is-active', item === button);
        item.setAttribute('aria-pressed', String(item === button));
      }
      ctx.showTooltip(null);
      room.setTrace(trace, false);
      room.setOpts({ coalition: new Set(trace.config.coalition) });
      room.snapTo(Math.max(lastRot, 0));
      api.render(Math.max(lastRot, 0), false, true);
    });
    container.appendChild(button);
  }

  function graph(lists, state, suffix, caption) {
    const members = trace.config.coalition;
    const grade = new Map(trace.students.map(s => [s.id, s.grade]));
    const mset = new Set(members);
    const outside = [...new Set(members.flatMap(id => lists.get(id)).filter(id => !mset.has(id)))].sort((a, b) => grade.get(a) - grade.get(b) || a.localeCompare(b));
    const cx = outside.length ? 140 : 225, cy = 145, radius = 84;
    const positions = new Map(members.map((id, i) => {
      const angle = -Math.PI / 2 + i / members.length * Math.PI * 2;
      return [id, {x: cx + Math.cos(angle) * radius, y: cy + Math.sin(angle) * radius}];
    }));
    outside.forEach((id, i) => positions.set(id, {x: 350, y: outside.length === 1 ? cy : 25 + i * 245 / (outside.length - 1)}));
    let paths = '';
    for (const a of members) for (const b of lists.get(a)) {
      const p = positions.get(a), q = positions.get(b);
      if (!p || !q || a === b) continue;
      const eligible = state !== 'same' || grade.get(a) === grade.get(b);
      const color = !eligible ? '#a49e96' : mset.has(b) ? '#c53d45' : '#217a55';
      const marker = !eligible ? 'inactive' : mset.has(b) ? 'internal' : 'external';
      const d = Math.hypot(q.x - p.x, q.y - p.y), ux = (q.x - p.x) / d, uy = (q.y - p.y) / d;
      paths += `<line x1="${p.x + ux * 18}" y1="${p.y + uy * 18}" x2="${q.x - ux * 21}" y2="${q.y - uy * 21}" stroke="${color}" stroke-width="1.6" ${eligible ? '' : 'stroke-dasharray="4 4"'} marker-end="url(#${marker}-${suffix})" opacity=".7"><title>${esc(a)} lists ${esc(b)}: ${eligible ? 'eligible' : 'ineligible this rotation'}</title></line>`;
    }
    let nodes = '';
    for (const [id, p] of positions) {
      const member = mset.has(id), clip = `avatar-${suffix}-${id}`;
      nodes += `<clipPath id="${clip}"><circle cx="${p.x}" cy="${p.y}" r="15"/></clipPath>` +
        `<image href="${avatarUri(id)}" x="${p.x - 15}" y="${p.y - 15}" width="30" height="30" clip-path="url(#${clip})"/>` +
        `<circle cx="${p.x}" cy="${p.y}" r="16" fill="none" stroke="${member ? '#c53d45' : '#217a55'}" stroke-width="2"/>` +
        `<text x="${member ? p.x : p.x + 23}" y="${member ? p.y + 29 : p.y + 4}" text-anchor="${member ? 'middle' : 'start'}" font-size="10" fill="#605a52">${esc(id)}${member ? '' : ` · G${grade.get(id)}`}</text>`;
    }
    const markers = [['internal', '#c53d45'], ['external', '#217a55'], ['inactive', '#a49e96']].map(([id, color]) => `<marker id="${id}-${suffix}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="${color}"/></marker>`).join('');
    return `<svg viewBox="0 0 465 315" role="img" aria-label="${esc(caption)}: directed submitted names, with ineligible cross-grade edges dashed"><defs>${markers}</defs>${paths}${nodes}<text x="232" y="307" text-anchor="middle" font-size="12" font-weight="600" fill="#605a52">${esc(caption)}</text></svg>`;
  }

  function drawWiring(state) {
    const ids = trace.students.map(s => s.id);
    const lists = new Map(ids.map((id, i) => [id, trace.listed[i]]));
    const initial = trace.listedInitial && new Map(ids.map((id, i) => [id, trace.listedInitial[i]]));
    $('wiring').classList.toggle('wiring-pair', !!initial);
    $('wiring').innerHTML = initial
      ? graph(initial, state, 'initial', 'Submitted lists · returned') + graph(lists, state, 'final', 'Chosen resubmission · used in charts')
      : graph(lists, state, 'current', `${trace.config.coalition.length} coalition members · ${state === 'same' ? 'same-grade eligibility' : 'mixed-grade eligibility'}`);
    $('wiring-note').textContent = EXPLANATIONS[mode]?.note || 'Arrows show the submitted lists saved with this trace.';
  }

  function screenNotice() {
    const report = trace.config.screen || trace.config.diagnosticScreen;
    const banner = $('screen-banner');
    if (!report) { banner.hidden = true; return; }
    banner.hidden = false;
    const diagnostic = !trace.config.rules?.screens;
    const statements = [];
    for (const [state, row] of Object.entries(report.perState || {})) {
      const coercion = (row.flags || []).length;
      const demand = (row.demandFlags || []).length;
      const unresolved = (row.unresolved || row.unresolvedCandidates || []).length;
      statements.push(`${state === 'same' ? 'Same-grade' : 'Mixed'}: ${coercion} coercion flags, ${demand} demand flags${unresolved ? `, ${unresolved} unresolved candidates` : ''}`);
    }
    const returned = report.nReturned ?? report.returnedStudents?.length ?? 0;
    const honest = report.honestFlagged?.length ?? 0;
    const after = report.afterResubmission;
    const unresolvedChecks = report.unresolvedChecks?.length || 0;
    banner.replaceChildren();
    const title = document.createElement('div');
    title.textContent = diagnostic ? 'Diagnostic only: screening is disabled in this seating experiment.' : 'Submission screening before the first rotation';
    const detail = document.createElement('small');
    detail.textContent = `${statements.join('. ')}. ${returned} students ${diagnostic ? 'would be' : 'were'} returned; ${honest} outside the designated coalition. ` +
      (after ? `A specified adversarial omission-star resubmission was used. After resubmission: ${after.nReturned ?? after.returnedStudents?.length ?? 0} returns. ` : '') +
      (unresolvedChecks ? `${unresolvedChecks} additional checks are unresolved and require review. ` : '') +
      'These are results for the checked candidates; a pass is not a complete safety guarantee.';
    banner.append(title, detail);
  }

  const api = {
    render(rot, animate, force = false) {
      if (!force && rot === lastRot && mode === lastMode) return;
      room.goTo(rot, animate && lastRot >= 0 && rot !== lastRot && mode === lastMode);
      const row = trace.rotations[rot], coalition = row.coalition, members = trace.config.coalition;
      const past = trace.rotations.slice(0, rot + 1);
      const intact = past.filter(r => r.coalition.intact).length;
      $('g-avg').textContent = coalition.avgCluster.toFixed(2);
      $('g-max').textContent = coalition.maxCluster;
      $('g-size').textContent = `of ${members.length} coalition members`;
      $('coalition-count').textContent = `${members.length} coalition members`;
      $('g-intact').textContent = `${intact} / ${rot + 1}`;
      $('g-intact-sub').textContent = `all ${members.length} members at one table`;
      const lists = new Map(trace.students.map((s, i) => [s.id, new Set(trace.listed[i])]));
      const ge1 = members.filter(id => row.tables.find(table => table.includes(id)).some(other => other !== id && lists.get(id).has(other))).length;
      $('g-ge1').textContent = `${ge1} of ${members.length}`;
      const banner = $('intact-banner');
      banner.className = `banner-intact${coalition.intact ? '' : ' split'}`;
      const table = coalition.intact ? row.tables.find(t => t.includes(members[0])) : null;
      banner.textContent = coalition.intact
        ? `Observed: all ${members.length} together${table.length === members.length ? ' · full table' : ` · ${table.length - members.length} other tablemate${table.length - members.length === 1 ? '' : 's'}`}`
        : `Observed split: ${coalition.pattern} across ${coalition.clusters.length} tables`;
      $('mode-explainer').textContent = trace.config.description;
      $('game-proof').textContent = EXPLANATIONS[mode]?.proof || 'No general forcing theorem is asserted for this scenario.';
      $('game-observed').textContent = observation(trace);
      screenNotice();
      drawWiring(row.state);
      lastRot = rot; lastMode = mode;
    },
    resize() { room.resize(); },
  };
  return api;
}
