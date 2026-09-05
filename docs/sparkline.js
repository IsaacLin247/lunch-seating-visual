// Small two-series line chart (D3 if present, plain SVG fallback) with hover.
export function renderSparkline(el, series, upTo, opts = {}) {
  const n = series[0].values.length;
  const w = el.clientWidth || 400, h = el.clientHeight || 110;
  const m = { l: 30, r: 78, t: 8, b: 20 };
  const iw = w - m.l - m.r, ih = h - m.t - m.b;
  const yMax = opts.yMax || Math.max(1, ...series.flatMap(s => s.values)) * 1.05;
  const x = i => m.l + (i / (n - 1)) * iw;
  const y = v => m.t + ih - (v / yMax) * ih;
  const path = vals => vals.slice(0, upTo + 1).map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const ticks = [0, Math.round(yMax / 2), Math.round(yMax / 1.05)];
  let svg = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${opts.label || ''}">`;
  svg += `<g class="axis">`;
  ticks.forEach(t => { svg += `<line x1="${m.l}" x2="${m.l + iw}" y1="${y(t)}" y2="${y(t)}"/><text x="${m.l - 6}" y="${y(t) + 4}" text-anchor="end">${t}</text>`; });
  [0, 7, 15].forEach(i => { svg += `<text x="${x(i)}" y="${h - 4}" text-anchor="middle">R${i + 1}</text>`; });
  svg += `</g>`;
  series.forEach(s => {
    svg += `<path d="${path(s.values)}" fill="none" stroke="${s.color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>`;
    const last = s.values[upTo];
    svg += `<circle cx="${x(upTo)}" cy="${y(last)}" r="4" fill="${s.color}" stroke="#fffdf8" stroke-width="2"/>`;
  });
  // direct labels, nudged apart if close
  const labels = series.map(s => ({ s, yy: y(s.values[upTo]) })).sort((a, b) => a.yy - b.yy);
  for (let i = 1; i < labels.length; i++) if (labels[i].yy - labels[i - 1].yy < 14) labels[i].yy = labels[i - 1].yy + 14;
  labels.forEach(({ s, yy }) => { svg += `<text class="lbl" x="${x(upTo) + 8}" y="${yy + 4}" fill="${s.color}">${s.name} ${fmt(s.values[upTo])}</text>`; });
  svg += `<line class="cursor" x1="${x(upTo)}" x2="${x(upTo)}" y1="${m.t}" y2="${m.t + ih}"/>`;
  svg += `<rect class="hit" x="${m.l}" y="${m.t}" width="${iw}" height="${ih}" fill="transparent"/>`;
  svg += `</svg>`;
  el.innerHTML = svg;
  const hit = el.querySelector('.hit');
  const tip = document.getElementById('tooltip');
  hit.addEventListener('mousemove', e => {
    const r = hit.getBoundingClientRect();
    const i = Math.max(0, Math.min(upTo, Math.round(((e.clientX - r.left) / r.width) * (n - 1))));
    tip.innerHTML = `<div><b>Rotation ${i + 1}</b><div class="t-sub">${series.map(s => `${s.name}: ${fmt(s.values[i])}`).join(' · ')}</div></div>`;
    tip.hidden = false; tip.style.left = `${e.clientX + 14}px`; tip.style.top = `${e.clientY + 14}px`;
  });
  hit.addEventListener('mouseleave', () => { tip.hidden = true; });
}
const fmt = v => (Math.round(v * 10) / 10).toString();
