// Tab 1, The Whole Room: random status quo vs. proposed system, side by side.
import { RoomView, COLORS } from './room.js';
import { renderSparkline } from './sparkline.js';

export function createTab1(ctx) {
  const trace = ctx.traces.honest;
  const $ = id => document.getElementById(id);
  const roomRandom = new RoomView($('room-random'), trace, { key: 'tablesRandom', showAvatars: false, onHover: ctx.showTooltip });
  const roomProposed = new RoomView($('room-proposed'), trace, { key: 'tables', showAvatars: false, onHover: ctx.showTooltip });
  const met = trace.rotations.map(r => r.stats.meanDistinctMet);
  const metR = trace.rotations.map(r => r.stats.meanDistinctMetRandom);
  const yMax = Math.max(...met, ...metR) * 1.08;
  let lastRot = -1;

  function stats(rot) {
    const s = trace.rotations[rot].stats;
    $('s-rand-ge1').textContent = pct(s.pctGe1Random);
    $('s-rand-ex1').textContent = pct(s.pctExactly1Random);
    $('s-rand-met').textContent = num(s.meanDistinctMetRandom);
    $('s-prop-ge1').textContent = pct(s.pctGe1);
    $('s-prop-ex1').textContent = pct(s.pctExactly1);
    $('s-prop-met').textContent = num(s.meanDistinctMet);
    const r = trace.rotations[rot];
    $('solver-status').textContent = `Saved rotation ${r.idx}: ${s.cost?.violations ?? 0} guarantee violations · accepted stage: ${s.acceptedPhase} · CP-SAT status: ${s.cpsatStatus} · ${s.solveTime}s solving time. Random baseline follows the same grade schedule.`;
    renderSparkline($('spark-met'), [
      { name: 'Proposed', values: met, color: COLORS.two },
      { name: 'Random', values: metR, color: '#9a948a' },
    ], rot, { yMax, label: 'Distinct schoolmates met, cumulative' });
  }

  return {
    render(rot, animate) {
      const anim = animate && lastRot >= 0 && rot !== lastRot;
      roomRandom.goTo(rot, anim);
      roomProposed.goTo(rot, anim);
      stats(rot);
      lastRot = rot;
    },
    resize() { roomRandom.resize(); roomProposed.resize(); },
  };
}

const pct = v => `${v.toFixed(1)}%`;
const num = v => `${v.toFixed(1)}`;
