// Tab 1, The Whole Room: random status quo vs. proposed system, side by side.
import { RoomView, COLORS } from './room.js?v=20260915-served-directory-1';
import { renderSparkline } from './sparkline.js?v=20260915-served-directory-1';

export function createTab1(ctx) {
  const trace = ctx.traces.honest;
  const $ = id => document.getElementById(id);
  const roomRandom = new RoomView($('room-random'), trace, { key: 'tablesRandom', showAvatars: false, onHover: ctx.showTooltip });
  const roomProposed = new RoomView($('room-proposed'), trace, { key: 'tables', showAvatars: false, onHover: ctx.showTooltip });
  const met = trace.rotations.map(r => r.stats.meanDistinctMet);
  const metR = trace.rotations.map(r => r.stats.meanDistinctMetRandom);
  const yMax = Math.max(...met, ...metR) * 1.08;
  let lastRot = -1;
  let portraits = new Map();

  function inspect(info) {
    if (!portraits.size) return;
    if (info?.key === 'tablesRandom') roomProposed.clearSelection();
    if (info?.key === 'tables') roomRandom.clearSelection();
    ctx.onPortraitTable?.(info);
  }

  function setPortraits(map) {
    // The caller owns the object URLs and may revoke them after this returns.
    // Clone the mapping so replacing or clearing an import cannot mutate an
    // image provider that is still being used by a previous animation frame.
    portraits = new Map(map || []);
    const enabled = portraits.size > 0;
    const opts = {
      portraitProvider: enabled ? id => portraits.get(id) || null : null,
      showAvatars: enabled,
      onSelectTable: enabled ? inspect : null,
      onHover: enabled ? null : ctx.showTooltip,
      showHoverFriends: !enabled,
    };
    ctx.showTooltip(null);
    roomRandom.setOpts(opts);
    roomProposed.setOpts(opts);
    ctx.onPortraitTable?.(null);
  }

  function stats(rot) {
    const s = trace.rotations[rot].stats;
    $('s-rand-ge1').textContent = pct(s.pctGe1Random);
    $('s-rand-ex1').textContent = pct(s.pctExactly1Random);
    $('s-rand-met').textContent = num(s.meanDistinctMetRandom);
    $('s-prop-ge1').textContent = pct(s.pctGe1);
    $('s-prop-ex1').textContent = pct(s.pctExactly1);
    $('s-prop-met').textContent = num(s.meanDistinctMet);
    const r = trace.rotations[rot];
    const release = s.status ? ` · release: ${s.status}${s.optimalityProven ? ' (CP-SAT optimality proof)' : ''}` : '';
    $('solver-status').textContent = `Saved rotation ${r.idx}: ${s.cost?.violations ?? 0} guarantee violations · accepted stage: ${s.acceptedPhase}${release} · CP-SAT status: ${s.cpsatStatus} · ${s.solveTime}s solving time. Random baseline follows the same grade schedule.`;
    renderSparkline($('spark-met'), [
      { name: 'Proposed', values: met, color: COLORS.two },
      { name: 'Random', values: metR, color: '#9a948a' },
    ], rot, { yMax, label: 'Distinct schoolmates met, cumulative' });
  }

  return {
    render(rot, animate) {
      const anim = animate && lastRot >= 0 && rot !== lastRot;
      if (portraits.size && rot !== lastRot) {
        roomRandom.clearSelection(); roomProposed.clearSelection();
        ctx.onPortraitTable?.(null);
      }
      roomRandom.goTo(rot, anim);
      roomProposed.goTo(rot, anim);
      stats(rot);
      lastRot = rot;
    },
    resize() { roomRandom.resize(); roomProposed.resize(); },
    setPortraits,
    clearPortraits() { setPortraits(new Map()); },
    selectTable(table, key = 'tables') {
      if (!portraits.size || !['tables', 'tablesRandom'].includes(key)) return false;
      return (key === 'tablesRandom' ? roomRandom : roomProposed).selectTable(table);
    },
    destroy() {
      roomRandom.destroy(); roomProposed.destroy();
      portraits.clear();
      ctx.onPortraitTable?.(null);
    },
  };
}

const pct = v => `${v.toFixed(1)}%`;
const num = v => `${v.toFixed(1)}`;
