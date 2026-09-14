// Optional, in-memory presentation layer. Trace records are never changed.
import { loadDirectory } from './portrait-data.js?v=20260914-minimal-4';
import { avatarImg, anonymousAvatarUri, setDirectoryPortraits, clearDirectoryPortraits } from './avatars.js?v=20260914-minimal-4';

const $ = id => document.getElementById(id);

/** Match each synthetic slot once, within its grade. Missing images stay empty. */
export function mapPortraits(simulated, directory) {
  const map = new Map();
  const grades = [...new Set(simulated.map(student => student.grade))];
  for (const grade of grades) {
    const compare = (a, b) => String(a.id).localeCompare(String(b.id), 'en');
    const slots = simulated.filter(student => student.grade === grade).sort(compare);
    const people = directory.filter(student => student.grade === grade).sort(compare);
    slots.forEach((slot, index) => {
      const url = people[index]?.photoUrl;
      if (typeof url === 'string' && url.startsWith('blob:')) map.set(slot.id, url);
    });
  }
  return map;
}

export function createPortraitControls({ trace, tabs, stop, hideTooltip }) {
  // Validate every view before reading any directory or changing shared photos.
  // An older cached view cannot participate in the all-tab portrait layer.
  const portraitTabs = ['room', 'student', 'game', 'math'].map(name => tabs[name]);
  if (portraitTabs.some(tab => typeof tab?.setPortraits !== 'function')) {
    const error = new Error('This page loaded an older version of a view. Reload the page to enable directory portraits in all four tabs.');
    error.code = 'STALE_PORTRAIT_MODULE';
    throw error;
  }
  const roomTab = tabs.room;
  const input = $('portrait-folder');
  const load = $('portrait-load');
  const clear = $('portrait-clear');
  const status = $('portrait-status');
  const controls = $('portrait-controls');
  const zoom = $('portrait-zoom');
  const table = $('portrait-table');
  const source = $('portrait-source');
  const tools = $('portrait-tools');
  const inspection = $('portrait-inspection');
  const seats = $('portrait-seats');
  const frames = [...document.querySelectorAll('.panel .room-frame')];
  const legend = $('room-legend-hint');
  const originalLegend = legend.textContent;
  const grades = new Map(trace.students.map(student => [student.id, student.grade]));
  let urls = new Map();
  let dispose = null;
  let generation = 0;

  for (let index = 0; index < trace.config.tableCapacities.length; index++) {
    const option = document.createElement('option');
    option.value = String(index);
    option.textContent = `Table ${index + 1}`;
    table.append(option);
  }

  function setLoading(loading) {
    load.disabled = loading;
    load.textContent = loading ? 'Loading…' : urls.size ? 'Change directory' : 'Load directory';
    clear.hidden = !loading && !urls.size;
    controls.setAttribute('aria-busy', String(loading));
  }

  function updateTabs(map) {
    if (map.size) setDirectoryPortraits(map);
    else clearDirectoryPortraits();
    portraitTabs.forEach(tab => tab.setPortraits(map));
  }

  function applyZoom() {
    if (!urls.size) return;
    const scale = Number(zoom.value);
    frames.forEach(frame => {
      const height = frame.closest('.stage-layout') ? 350
        : frame.classList.contains('tall') ? Math.max(320, Math.min(620, window.innerHeight - 330))
        : Math.max(280, Math.min(520, window.innerHeight - 385));
      const canvas = frame.querySelector('canvas');
      frame.style.height = `${height + 16}px`;
      canvas.style.width = `${scale * 100}%`;
      canvas.style.height = `${height * scale}px`;
    });
    Object.values(tabs).forEach(tab => tab.resize());
  }

  function inspect(info) {
    seats.replaceChildren();
    if (!info || !urls.size) {
      inspection.hidden = true;
      table.value = '';
      return;
    }
    stop();
    source.value = info.key;
    table.value = String(info.table);
    const baseline = info.key === 'tablesRandom' ? 'Random baseline' : 'Proposed solver';
    $('portrait-table-heading').textContent = `${baseline} · Table ${info.table + 1}`;
    $('portrait-table-description').textContent = `Rotation ${info.index + 1} · ${info.ids.length} seats`;
    for (const id of info.ids) {
      const card = document.createElement('div');
      card.className = 'portrait-seat';
      const url = urls.get(id);
      const img = url ? new Image() : avatarImg(id);
      if (url) img.src = url;
      img.alt = url ? `Illustrative portrait for simulated student ${id}` : `Anonymous avatar for simulated student ${id}`;
      img.width = 80; img.height = 80;
      img.addEventListener('error', () => {
        const fallback = new Image(); fallback.src = anonymousAvatarUri(id);
        fallback.alt = `Anonymous avatar for simulated student ${id}`;
        fallback.width = 80; fallback.height = 80;
        img.replaceWith(fallback);
      }, { once: true });
      const label = document.createElement('strong'); label.textContent = id;
      const grade = document.createElement('span'); grade.textContent = `Grade ${grades.get(id)}`;
      card.append(img, label, grade);
      if (!url) {
        const caption = document.createElement('small'); caption.textContent = 'No photo';
        card.append(caption);
      }
      seats.append(card);
    }
    inspection.hidden = false;
  }

  function showNotes(notes) {
    $('portrait-warnings').open = false;
    const list = $('portrait-warning-list');
    list.replaceChildren();
    for (const note of notes) {
      const item = document.createElement('li'); item.textContent = note; list.append(item);
    }
    $('portrait-warnings').hidden = !notes.length;
  }

  function removePhotos() {
    generation++;
    stop(); hideTooltip();
    urls = new Map();
    updateTabs(urls);
    inspect(null);
    dispose?.(); dispose = null;
    document.body.classList.remove('portrait-mode');
    tools.hidden = true;
    $('portrait-zoom-control').hidden = true;
    frames.forEach(frame => {
      frame.style.removeProperty('height');
      const canvas = frame.querySelector('canvas');
      canvas.style.removeProperty('width'); canvas.style.removeProperty('height');
      frame.scrollTo(0, 0);
    });
    Object.values(tabs).forEach(tab => tab.resize());
    legend.textContent = originalLegend;
    input.value = '';
    showNotes([]);
    status.textContent = 'Photos removed';
    status.classList.remove('error');
    setLoading(false);
  }

  load.addEventListener('click', () => input.click());
  input.addEventListener('change', async () => {
    const files = [...input.files];
    input.value = '';
    if (!files.length) return;
    const current = ++generation;
    stop(); hideTooltip();
    setLoading(true);
    status.classList.remove('error');
    status.textContent = 'Reading directory…';
    let result = null;
    try {
      result = await loadDirectory(files, { onProgress(progress) {
        if (current !== generation) return;
        const action = progress.phase === 'photos' ? 'Preparing portraits' : 'Reading grade files';
        status.textContent = `${action}: ${progress.completed} / ${progress.total}`;
      } });
      if (current !== generation) { result.dispose(); return; }
      const mapped = mapPortraits(trace.students, result.students);
      if (!mapped.size) throw new Error('No usable photos matched this demo’s grades. Choose a directory folder containing grades 11 and 12 and their saved image folders.');
      const previousDispose = dispose;
      try { updateTabs(mapped); }
      catch (error) { updateTabs(urls); throw error; }
      urls = mapped;
      dispose = result.dispose;
      previousDispose?.();
      showNotes(result.warnings);
      status.textContent = `${urls.size} photos · ${trace.students.length - urls.size} missing`;
      document.body.classList.add('portrait-mode');
      tools.hidden = false;
      $('portrait-zoom-control').hidden = false;
      legend.textContent = 'Select a table to enlarge';
      zoom.value = '1';
      applyZoom();
    } catch (error) {
      result?.dispose();
      if (current !== generation) return;
      status.textContent = `${error.message || 'The directory could not be read.'}${urls.size ? ' Your previous portrait view is still loaded.' : ''}`;
      status.classList.add('error');
    } finally {
      if (current === generation) setLoading(false);
    }
  });
  clear.addEventListener('click', removePhotos);
  $('portrait-inspection-close').addEventListener('click', () => inspect(null));
  zoom.addEventListener('change', () => { stop(); applyZoom(); });
  table.addEventListener('change', () => {
    stop();
    if (table.value === '') inspect(null);
    else roomTab.selectTable(Number(table.value), source.value);
  });
  source.addEventListener('change', () => {
    stop();
    if (table.value !== '') roomTab.selectTable(Number(table.value), source.value);
  });
  window.addEventListener('resize', applyZoom);
  window.addEventListener('pagehide', removePhotos);
  setLoading(false);
  return { inspect, clear: removePhotos, resize: applyZoom };
}
