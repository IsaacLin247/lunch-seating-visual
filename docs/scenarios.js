// Explanatory annotations. Membership, counts, charts, and outcomes come from traces.
export const SCENARIO_NAMES = ['honest', 'coalition_none', 'coalition_min4', 'coalition_stratified', 'coalition_shared_anchor', 'coalition_screened'];

export const EXPLANATIONS = {
  coalition_none: {
    proof: 'With a single successor on each list, following the directed cycle forces all members onto one table in every feasible seating. This violates the four-name rule.',
    note: 'Each arrow means “I listed you.” The list constraint follows the cycle all the way around.',
  },
  coalition_min4: {
    proof: 'For this six-member omission star, the possible coalition patterns are 3+3, 4+2, and 6. The member-weighted mean cluster is at least 3. A shared table is allowed but cannot be forced solely by these lists.',
    note: 'Each member names four of the other five. Nobody names the first member. Exhaustive search establishes the best structural lower bound within this internal four-of-five family; it does not cover all attacks.',
  },
  coalition_stratified: {
    proof: 'In same-grade rounds, the five-member step-two cycle has no closed split. The sixth member lists only that core, so all six must share a table. Cross-grade names provide extra eligible choices only in mixed rounds.',
    note: 'Dashed gray names remain on the submitted list but cannot satisfy a same-grade guarantee. The revised screens test both effective graphs.',
  },
  coalition_shared_anchor: {
    proof: 'Seven cycle members also name one shared outside junior. At capacity seven, the seven plus their anchor cannot share a table. A member seated without that anchor needs their successor, forcing all seven together in every same-grade chart.',
    note: 'The shared anchor is drawn separately because many outside arrows meet the same student. This attack defeated closure-only screening; the revised detector checks this targeted core while retaining every outside option. Enforcement is disabled here to display its consequences.',
  },
  coalition_screened: {
    proof: 'The submitted same-grade attack is detected and returned. The experiment then specifies an omission-star resubmission: allowed patterns are 3+3, 4+2, and 6. This is one chosen response, not proof that all strategic responses are safe.',
    note: 'The initial and resubmitted lists are saved in this trace. Their diagrams show which names are eligible in the selected rotation. A passing resubmission does not establish general collusion resistance.',
  },
};

export function coalitionModes(traces) {
  return Object.entries(traces).filter(([name, trace]) => name !== 'honest' && trace.config.coalition?.length);
}

export function observation(trace) {
  const rows = trace.rotations;
  const patterns = new Map();
  for (const row of rows) patterns.set(row.coalition.pattern, (patterns.get(row.coalition.pattern) || 0) + 1);
  const intact = rows.filter(row => row.coalition.intact).length;
  const same = rows.filter(row => row.state === 'same');
  const sameIntact = same.filter(row => row.coalition.intact).length;
  const mean = rows.reduce((sum, row) => sum + row.coalition.avgCluster, 0) / rows.length;
  return `${rows.length} saved rotations: ${[...patterns].map(([pattern, n]) => `${pattern} (${n})`).join(', ')}. All members shared one table in ${intact}/${rows.length} rounds, including ${sameIntact}/${same.length} same-grade rounds. Mean cluster: ${mean.toFixed(2)}.`;
}
