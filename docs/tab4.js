// Tab 4, The Algorithm: recorded stages and explanations typeset with local KaTeX.
import { RoomView } from './room.js?v=20260915-served-directory-1';

export function createTab4(ctx) {
  const trace = ctx.traces.honest;
  const leakage = trace.leakage;
  if (leakage) {
    document.getElementById('leakage-summary').textContent = `Across ${leakage.rotationsObserved} honest-trace charts, the exact inference probe forces ${leakage.forcedEdges} directed list entries affecting ${leakage.studentsWithForcedEdge} students, under a public cap of ${leakage.kMax} names. Confidential collection does not prevent inference from outputs.`;
  }
  const exposure = leakage?.coseatingExposure;
  if (exposure) {
    const current = leakage.currentOnlyDistribution;
    document.getElementById('exposure-summary').textContent = `Distributing one chart at a time forces ${current ? current.forcedEdges : 0} entries logically, but the most frequent tablemate of an obligated student is a listed peer for ${(100 * exposure.proposed.top1ListedRate).toFixed(0)}% of students under the proposed charts (${(100 * exposure.random.top1ListedRate).toFixed(0)}% under random seating). Counting co-seatings needs no list cap and no complete archive.`;
  }
  const statuses = trace.summary?.releaseStatuses;
  if (statuses) {
    const proven = trace.summary.optimalityProvenRotations?.length ?? 0;
    document.getElementById('trace-statuses').textContent = `Release statuses in this honest year: ${Object.entries(statuses).map(([k, v]) => `${k} ${v}`).join(', ')}. Rotations with a CP-SAT optimality proof under the exact objective: ${proven}. Scheduling outcome: ${trace.config.schedulingStatus || 'scheduled'}.`;
  }
  const config = trace.config, versions = config.versions || {}, source = config.provenance || versions;
  const identity = source.effectiveSourceHash || source.sourceHash || source.sourceFingerprint || source.sourceTreeHash || source.sourceSha256;
  document.getElementById('trace-provenance').textContent = `Population seed ${source.populationSeed ?? config.populationSeed ?? config.network?.seed ?? config.seed}; solver seed ${source.solverSeed ?? config.solverSeed ?? config.seed}. ${config.solver.annealIters.toLocaleString()} annealing iterations, CP-SAT budget ${config.solver.cpsatTime} ${config.solver.deterministic ? 'deterministic-time' : 'wall-clock'} units, ${config.solver.workers} workers. Python ${versions.python || 'unrecorded'}, OR-Tools ${versions.ortools || 'unrecorded'}. Commit ${versions.gitCommit || source.gitCommit || 'unrecorded'}${identity ? `; effective-source hash ${identity}` : '; see the downloaded trace for effective-source provenance'}. Generated ${config.generatedAt || 'at an unrecorded time'}.`;
  const $ = id => document.getElementById(id);
  const labels = { construction: 'Construction', repair: 'Repair', annealing: 'Annealing', final: 'Accepted chart' };
  const descriptions = {
    construction: 'Greedy pods packed into grade-compatible tables. The initial chart may still strand submitters.',
    repair: 'Guarded rescue swaps preserve previously satisfied students. Unresolved violations can remain.',
    annealing: 'Recorded annealing candidate after the fixed iteration budget, before CP-SAT polishing and final selection.',
    final: 'Accepted chart after bounded polishing, the full-history guard, and any fallback. This is the chart exported for this rotation.',
  };
  let activeRotation = 0, activeStage = 0, stageTimer = null;
  let stageRoom = null;
  let portraits = new Map();
  const portraitOptions = () => ({
    portraitProvider: portraits.size ? id => portraits.get(id) || null : null,
    showAvatars: portraits.size > 0,
  });
  function stopStages() { if (stageTimer) clearTimeout(stageTimer); stageTimer = null; $('stage-replay').textContent = 'Replay stages'; }
  function renderStage(animate = false) {
    const rotation = trace.rotations[activeRotation], stages = rotation.pipeline;
    const available = Array.isArray(stages) && stages.length > 0;
    $('stage-controls').hidden = !available;
    $('room-stage').closest('.room-frame').hidden = !available;
    $('stage-replay').disabled = !available;
    if (!available) { $('stage-description').textContent = 'This older trace has no recorded stage snapshots. Regenerate it with the current exporter to inspect the pipeline.'; return; }
    activeStage = Math.min(activeStage, stages.length - 1);
    const snapshot = stages[activeStage];
    const stageTrace = { ...trace, rotations: stages.map(stage => ({ ...rotation, tables: stage.tables })) };
    if (!stageRoom) stageRoom = new RoomView($('room-stage'), stageTrace, { ...portraitOptions(), onHover: ctx.showTooltip });
    if (stageRoom.originalRotation !== activeRotation) {
      stageRoom.setTrace(stageTrace, false); stageRoom.originalRotation = activeRotation; stageRoom.snapTo(activeStage); stageRoom.resize();
    } else stageRoom.goTo(activeStage, animate);
    $('stage-controls').replaceChildren();
    stages.forEach((stage, idx) => {
      const button = document.createElement('button'); button.className = `seg${idx === activeStage ? ' is-active' : ''}`;
      button.textContent = `${idx + 1} · ${labels[stage.name] || stage.name}`;
      button.dataset.stage = stage.name;
      button.setAttribute('aria-pressed', String(idx === activeStage));
      button.addEventListener('click', () => { stopStages(); activeStage = idx; renderStage(true); $('stage-controls').querySelector(`[data-stage="${stage.name}"]`).focus(); });
      $('stage-controls').appendChild(button);
    });
    $('stage-description').textContent = `Rotation ${rotation.idx}, ${rotation.state === 'same' ? 'same grade' : 'mixed grades'}. ${descriptions[snapshot.name] || snapshot.name}`;
    $('stage-violations').textContent = snapshot.cost.violations;
    $('stage-extra').textContent = snapshot.cost.extraPeers;
    $('stage-energy').textContent = (snapshot.cost.total / 10).toFixed(1);
    $('stage-seconds').textContent = `${snapshot.seconds.toFixed(2)} s`;
    $('stage-validity').textContent = snapshot.name === 'final' ? 'Validated published chart.' : snapshot.cost.violations ? 'Intermediate candidate: friend guarantee not yet satisfied.' : 'This intermediate candidate satisfies the friend guarantee; final validation follows.';
    $('stage-validity').className = snapshot.cost.violations ? 'stage-invalid' : 'stage-valid';
  }
  $('stage-replay').addEventListener('click', () => {
    if (stageTimer) { stopStages(); return; }
    activeStage = 0; renderStage(false); $('stage-replay').textContent = 'Stop replay';
    function step() {
      if (activeStage >= trace.rotations[activeRotation].pipeline.length - 1) { stopStages(); return; }
      activeStage += 1; renderStage(true); stageTimer = setTimeout(step, 1900);
    }
    stageTimer = setTimeout(step, 1900);
  });
  const el = document.getElementById('tab-math');
  let rendered = false;
  function typeset() {
    if (rendered) return;
    if (typeof window.renderMathInElement !== 'function') return; // KaTeX still loading or offline
    window.renderMathInElement(el, {
      delimiters: [
        { left: '\\[', right: '\\]', display: true },
        { left: '\\(', right: '\\)', display: false },
      ],
      throwOnError: false,
    });
    rendered = true;
  }
  // KaTeX scripts are deferred; typeset once they are in, or on first view.
  if (document.readyState === 'complete') typeset();
  else window.addEventListener('load', typeset, { once: true });
  const api = {
    render(rotation) { typeset(); if (rotation !== activeRotation) { stopStages(); activeRotation = rotation; } renderStage(false); },
    resize() { stageRoom?.resize(); },
    pause() { stopStages(); },
    setPortraits(map) {
      portraits = new Map(map || []);
      stageRoom?.setOpts(portraitOptions());
      // A photo import is a display change. Preserve the inspected stage,
      // rotation, and saved numerical evidence while refreshing its canvas.
      renderStage(false);
      stageRoom?.draw();
    },
    clearPortraits() { api.setPortraits(new Map()); },
  };
  return api;
}
