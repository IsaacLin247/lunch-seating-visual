// Entry point: load traces, wire the shared timeline, tabs, keyboard and tooltip.
import { initAvatars, avatarImg } from './avatars.js';
import { createTab1 } from './tab1.js';
import { createTab2 } from './tab2.js';
import { createTab3 } from './tab3.js';
import { createTab4 } from './tab4.js';

const $ = id => document.getElementById(id);
const SCENARIOS = ['honest', 'coalition_none', 'coalition_min4', 'coalition_screened'];
const N_ROT = 16;
const PLAY_MS = 2400;

async function loadTraces() {
  const out = {};
  await Promise.all(SCENARIOS.map(async name => {
    const res = await fetch(`data/${name}.json`, { cache: 'no-cache' });
    if (!res.ok) throw new Error(`missing data/${name}.json (${res.status})`);
    out[name] = await res.json();
  }));
  return out;
}

const tooltip = $('tooltip');
function showTooltip(info) {
  if (!info) { tooltip.hidden = true; return; }
  const listedHere = info.listedHere.length ? info.listedHere.join(', ') : 'none';
  tooltip.innerHTML = '';
  const av = document.createElement('div'); av.className = 't-av'; av.appendChild(avatarImg(info.id));
  const txt = document.createElement('div');
  txt.innerHTML = `<b>${info.id}</b> · grade ${info.grade}<div class="t-sub">table ${info.table + 1} · listed friends here: ${listedHere}</div>` +
    `<div class="t-sub">listed ${info.listed.length}: ${info.listed.join(', ') || 'none'}</div>`;
  tooltip.append(av, txt);
  tooltip.hidden = false;
  const x = Math.min(window.innerWidth - 280, info.x + 16), y = Math.min(window.innerHeight - 90, info.y + 16);
  tooltip.style.left = `${x}px`; tooltip.style.top = `${y}px`;
}

async function main() {
  const [traces] = await Promise.all([loadTraces(), initAvatars()]);
  $('loading').hidden = true;

  const ctx = { traces, showTooltip };
  const tabs = { room: createTab1(ctx), student: createTab2(ctx), game: createTab3(ctx), math: createTab4(ctx) };
  let active = 'room';
  let rot = 0;
  let playing = false, timer = null;

  // ticks under the scrubber
  const first = traces.honest.config.firstState;
  $('ticks').innerHTML = traces.honest.rotations.map(r => `<span class="${r.state}">${r.idx}</span>`).join('');

  function badge() {
    const r = traces.honest.rotations[rot];
    $('rot-num').textContent = r.idx;
    const pill = $('state-pill');
    pill.textContent = r.state === 'same' ? 'SAME GRADE' : 'MIXED GRADES';
    pill.classList.toggle('same', r.state === 'same');
    $('rot-weeks').textContent = `weeks ${rot * 2 + 1}–${rot * 2 + 2}`;
    $('scrub').value = rot + 1;
  }

  function setRotation(i, animate = true) {
    i = Math.max(0, Math.min(N_ROT - 1, i));
    rot = i;
    badge();
    tabs[active].render(rot, animate);
  }

  function stop() { playing = false; $('btn-play').textContent = '▶'; $('btn-play').setAttribute('aria-label', 'Play'); if (timer) clearTimeout(timer); timer = null; }
  function play() {
    if (rot >= N_ROT - 1) setRotation(0, false);
    playing = true; $('btn-play').textContent = '❚❚'; $('btn-play').setAttribute('aria-label', 'Pause');
    const step = () => {
      if (!playing) return;
      if (rot >= N_ROT - 1) { stop(); return; }
      setRotation(rot + 1, true);
      timer = setTimeout(step, PLAY_MS);
    };
    timer = setTimeout(step, 600);
  }

  $('btn-play').addEventListener('click', () => (playing ? stop() : play()));
  $('btn-prev').addEventListener('click', () => { stop(); setRotation(rot - 1); });
  $('btn-next').addEventListener('click', () => { stop(); setRotation(rot + 1); });
  $('btn-first').addEventListener('click', () => { stop(); setRotation(0); });
  $('btn-last').addEventListener('click', () => { stop(); setRotation(N_ROT - 1); });
  $('scrub').addEventListener('input', e => { stop(); setRotation(+e.target.value - 1, true); });

  document.querySelectorAll('.tab').forEach(btn => btn.addEventListener('click', () => switchTab(btn.dataset.tab)));
  function switchTab(name) {
    if (name === active) return;
    document.querySelectorAll('.tab').forEach(b => { const on = b.dataset.tab === name; b.classList.toggle('is-active', on); b.setAttribute('aria-selected', on); });
    document.querySelectorAll('.panel').forEach(p => { const on = p.id === `tab-${name}`; p.classList.toggle('is-active', on); p.hidden = !on; });
    active = name;
    showTooltip(null);
    document.querySelector('.timeline').classList.toggle('is-hidden', name === 'math');
    tabs[active].resize();
    tabs[active].render(rot, false);
  }

  window.addEventListener('keydown', e => {
    if (e.target.tagName === 'SELECT' || e.target.tagName === 'INPUT') return;
    if (e.key === 'ArrowRight') { stop(); setRotation(rot + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { stop(); setRotation(rot - 1); e.preventDefault(); }
    else if (e.key === ' ') { playing ? stop() : play(); e.preventDefault(); }
    else if (e.key === 'Home') { stop(); setRotation(0); e.preventDefault(); }
    else if (e.key === 'End') { stop(); setRotation(N_ROT - 1); e.preventDefault(); }
    else if (e.key === '1') switchTab('room');
    else if (e.key === '2') switchTab('student');
    else if (e.key === '3') switchTab('game');
    else if (e.key === '4') switchTab('math');
  });

  setRotation(0, false);
}

main().catch(err => {
  console.error(err);
  $('loading').textContent = `Could not load the simulation data: ${err.message}. Run "python sim/export_traces.py" and serve the docs/ folder.`;
});
