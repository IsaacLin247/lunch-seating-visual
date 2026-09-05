// Tab 2 — One Student's Year: follow one student through all 16 rotations.
import { RoomView } from './room.js';
import { avatarImg } from './avatars.js';

export function createTab2(ctx) {
  const trace = ctx.traces.honest;
  const $ = id => document.getElementById(id);
  const ids = trace.students.map(s => s.id);
  const grade = new Map(trace.students.map(s => [s.id, s.grade]));
  const listedOf = new Map(trace.students.map((s, i) => [s.id, trace.listed[i]]));
  let hero = trace.hero;
  let lastRot = -1, lastHero = null;

  // picker
  const sel = $('hero-select');
  sel.innerHTML = ids.map(id => `<option value="${id}">${id} · grade ${grade.get(id)}${id === trace.hero ? ' (default)' : ''}</option>`).join('');
  sel.value = hero;
  sel.addEventListener('change', () => setHero(sel.value));
  $('hero-random').addEventListener('click', () => { const id = ids[Math.floor(Math.random() * ids.length)]; sel.value = id; setHero(id); });

  const room = new RoomView($('room-hero'), trace, { key: 'tables', hero, friends: new Set(listedOf.get(hero)), dimOthers: true, onHover: ctx.showTooltip });

  function setHero(id) {
    hero = id;
    room.setOpts({ hero, friends: new Set(listedOf.get(hero)), link: null });
    buildStatic();
    api.render(lastRot >= 0 ? lastRot : 0, false, true);
  }

  function buildStatic() {
    $('hero-avatar').replaceChildren(avatarImg(hero));
    $('hero-id').textContent = hero;
    $('hero-grade').textContent = `Grade ${grade.get(hero)} · listed ${listedOf.get(hero).length} friends`;
    const strip = $('friend-strip');
    strip.innerHTML = '';
    listedOf.get(hero).forEach(f => {
      const d = document.createElement('div'); d.className = 'fs-item'; d.dataset.id = f;
      const av = document.createElement('div'); av.className = 'av'; av.appendChild(avatarImg(f));
      d.appendChild(av);
      d.insertAdjacentHTML('beforeend', `<div class="tick">✓</div><div>${f}</div><div class="uses"></div>`);
      strip.appendChild(d);
    });
  }

  /** Cumulative view of the hero's year up to rotation `rot` (inclusive). */
  function yearUpTo(rot) {
    const met = new Map(), metR = new Map(); // id -> first rotation met
    const anchors = new Map();                // friend -> [rotations]
    let guaranteed = 0, guaranteedR = 0;
    const perRot = [];
    for (let r = 0; r <= rot; r++) {
      const R = trace.rotations[r];
      const tbl = R.tables.find(t => t.includes(hero));
      const tblR = R.tablesRandom.find(t => t.includes(hero));
      const mates = tbl.filter(x => x !== hero), matesR = tblR.filter(x => x !== hero);
      const L = new Set(listedOf.get(hero));
      const a = R.anchors[hero] || null, aR = R.anchorsRandom[hero] || null;
      if (a) { guaranteed++; anchors.set(a, [...(anchors.get(a) || []), r + 1]); }
      if (aR) guaranteedR++;
      const fresh = [];
      mates.forEach(m => { if (!met.has(m)) { met.set(m, r); fresh.push(m); } });
      matesR.forEach(m => { if (!metR.has(m)) metR.set(m, r); });
      perRot.push({ mates, matesR, anchor: a, anchorR: aR, fresh, friendsHere: mates.filter(m => L.has(m)), friendsHereR: matesR.filter(m => L.has(m)) });
    }
    return { met, metR, anchors, guaranteed, guaranteedR, perRot };
  }

  const api = {
    render(rot, animate, force = false) {
      if (!force && rot === lastRot && hero === lastHero) return;
      const anim = animate && lastRot >= 0 && rot !== lastRot && hero === lastHero;
      const Y = yearUpTo(rot);
      const cur = Y.perRot[rot];
      room.setOpts({ link: cur.anchor ? { from: hero, to: cur.anchor } : null });
      room.goTo(rot, anim);

      // strip: used anchors + pulse current
      const L = listedOf.get(hero);
      $('friend-strip').querySelectorAll('.fs-item').forEach(el => {
        const f = el.dataset.id;
        const uses = Y.anchors.get(f);
        el.classList.toggle('used', !!uses);
        el.classList.toggle('active', f === cur.anchor);
        el.querySelector('.uses').textContent = uses ? `R${uses.join(', R')}` : '';
      });
      $('anchor-count').textContent = `${Y.anchors.size} of ${L.length} delivered so far`;
      const others = cur.mates.length - cur.friendsHere.length;
      const freshOthers = cur.fresh.filter(m => !cur.friendsHere.includes(m)).length;
      $('anchor-line').innerHTML = cur.anchor
        ? `Rotation ${rot + 1} (${trace.rotations[rot].state === 'same' ? 'same grade' : 'mixed grades'}): the guarantee seated ${hero} with <b>${cur.anchor}</b>` +
          (cur.friendsHere.length > 1 ? ` (plus ${cur.friendsHere.length - 1} more listed friend${cur.friendsHere.length > 2 ? 's' : ''})` : '') +
          `. The other ${others} tablemates were not on their list — ${freshOthers} of them ${freshOthers === 1 ? 'is' : 'are'} new faces this year.`
        : `Rotation ${rot + 1}: ${hero} listed no friends, so no guarantee applies.`;

      // wall of people met
      const wall = $('avatar-wall');
      wall.innerHTML = '';
      const order = [...Y.met.entries()].sort((a, b) => a[1] - b[1] || a[0].localeCompare(b[0]));
      const Lset = new Set(L);
      order.forEach(([m, r]) => {
        const d = document.createElement('div'); d.className = 'w-av' + (Lset.has(m) ? ' friend' : '');
        if (r !== rot) d.style.animation = 'none';
        d.title = `${m} · first met in rotation ${r + 1}`;
        d.appendChild(avatarImg(m)); wall.appendChild(d);
      });
      $('wall-count').textContent = `${Y.met.size} met`;

      // ghost row (random seating): tablemates per rotation, friends highlighted
      const ghost = $('ghost-row');
      ghost.innerHTML = '';
      Y.perRot.forEach((pr, r) => {
        if (r) { const s = document.createElement('div'); s.className = 'rot-sep'; ghost.appendChild(s); }
        pr.matesR.forEach(m => {
          const d = document.createElement('div'); d.className = 'w-av' + (Lset.has(m) ? ' friend' : '');
          if (r !== rot) d.style.animation = 'none';
          d.title = `${m} · rotation ${r + 1}${Lset.has(m) ? ' · a listed friend!' : ''}`;
          d.appendChild(avatarImg(m)); ghost.appendChild(d);
        });
      });
      $('ghost-count').textContent = `${Y.metR.size} met · friend present ${Y.guaranteedR}/${rot + 1}`;

      // year card
      $('y-guaranteed').textContent = `${Y.guaranteed} / ${rot + 1}`;
      $('y-guaranteed-rand').textContent = `${Y.guaranteedR} / ${rot + 1}`;
      $('y-anchors').textContent = `${Y.anchors.size} of ${L.length}`;
      $('y-met').textContent = `${Y.met.size}`;
      $('y-met-rand').textContent = `${Y.metR.size}`;
      $('year-card').querySelector('h3').textContent = rot === 15 ? 'End-of-year summary' : 'This year so far';
      lastRot = rot; lastHero = hero;
    },
    resize() { room.resize(); },
  };
  buildStatic();
  return api;
}
