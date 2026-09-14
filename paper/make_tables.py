#!/usr/bin/env python
"""Build primary-study numbers from the finalized, verified experiment ledger.
Bench-prefixed macros are separately identified exploratory summary-only evidence.

There is deliberately no fallback to historical summary-only results or old
website traces. Run assemble_evidence.py first after all attempts terminate.
"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper.assemble_evidence import REFERENCES, verify_attempt
from sim.attacks import best_four_of_five_wiring

LABEL = dict(zip(REFERENCES, ('Honest', 'One-name cycle', 'Omission star',
    'Stratified attack', 'Shared-anchor attack', 'Screened resubmission')))
OUTS = (ROOT / 'article', ROOT / 'paper')


def esc(value):
    return str(value).replace('&', r'\&').replace('%', r'\%').replace('_', r'\_').replace('#', r'\#')


def table(name, caption, header, rows, spec):
    return '\n'.join((r'\begin{table}[tb]\centering\small',
        r'\caption{' + caption + r'}\label{tab:' + name + '}',
        r'\begin{tabular}{@{}' + spec + r'@{}}\toprule',
        ' & '.join(header) + r' \\ \midrule',
        *(' & '.join(map(str, row)) + r' \\' for row in rows),
        r'\bottomrule\end{tabular}\end{table}', ''))


def main(manifest=None):
    path = Path(manifest) if manifest else ROOT / 'results/revised_experiments.json'
    data = json.loads(path.read_text())
    if data['assembly']['partial'] or any(a['status'] == 'running' for a in data['attempts']):
        raise SystemExit('Finalize evidence assembly before generating publication tables.')
    attempts = {a['id']: a for a in data['attempts']}
    for a in attempts.values():
        verify_attempt(a, path, retained_source=True)
    refs = {}
    for name in REFERENCES:
        matches = [r for r in data['seeds'] if r['scenario'] == name and r['populationSeed'] == 7
                   and r['rotations'] == 16 and r['annealIters'] == 300000 and r['cpsatTime'] == 3.5]
        if len(matches) != 1:
            raise ValueError(f'Need exactly one verified seed7 reference for {name}, got {len(matches)}')
        refs[name] = json.loads((path.parent / matches[0]['traceEvidence']['path']).read_text())
    honest = sorted((r for r in data['seeds'] if r['scenario'] == 'honest'), key=lambda r: r['populationSeed'])
    stars = {r['populationSeed']: r for r in data['seeds'] if r['scenario'] == 'coalition_min4'}
    if [r['populationSeed'] for r in honest] != list(range(1, 11)) or set(stars) != set(range(1, 11)):
        raise ValueError('Primary comparison requires the planned ten complete honest/star population pairs.')
    h = refs['honest']; cfg = h['config']; hs = h['summary']; lk = h['leakage']; fair = h['fairness']; baseline = cfg['baseline']
    macros = {}
    def m(name, value): macros[name] = str(value)
    def f(name, value, digits=2): m(name, f'{value:.{digits}f}')
    for key, field in [('HonestExactlyOne','pctExactly1Mean'),('HonestExactlyOneMin','pctExactly1Min'),
                       ('HonestMet','meanDistinctMetFinal'),('RandomMet','meanDistinctMetFinalRandom')]: f(key, hs[field])
    for key, field in [('RandomMetExpected','expectedDistinctRandom'),('RandomMetExpectedAllMixed','expectedDistinctRandomAllMixed'),
        ('RandomGeOneExpected','expectedFriendCoverageSchedule'),('RandomGeOneExpectedMixed','expectedFriendCoverageMixed'),
        ('RandomGeOneExpectedSame','expectedFriendCoverageSame')]: f(key, baseline[field])
    # Resample populations, not students or rotations; use unrounded chart counts.
    import numpy as np
    paired_raw=[]
    for row in honest:
        trace=json.loads((path.parent / row['traceEvidence']['path']).read_text())
        means=[]
        for key in ('tables','tablesRandom'):
            contacts={student['id']:set() for student in trace['students']}
            for rotation in trace['rotations']:
                for group in rotation[key]:
                    for i in group: contacts[i].update(set(group)-{i})
            means.append(sum(map(len,contacts.values()))/len(contacts))
        paired_raw.append(means[0]-means[1])
    paired_raw=np.asarray(paired_raw)
    rng=np.random.default_rng(20260908)
    samples=paired_raw[rng.integers(0,len(paired_raw),size=(20000,len(paired_raw)))].mean(axis=1)
    ci=np.quantile(samples,[.025,.975],method='linear')
    f('SeedDiffCILow',ci[0]); f('SeedDiffCIHigh',ci[1])
    ex = [r['pctExactly1Mean'] for r in honest]
    diff = paired_raw.tolist()
    m('NSeeds', len(honest)); m('Seed', 7)
    for name, vals in [('SeedExactlyOne',ex),('SeedDiff',diff)]:
        for suffix, value in [('Mean',sum(vals)/len(vals)),('Min',min(vals)),('Max',max(vals))]:
            m(name + suffix, f'{value:+.2f}' if name == 'SeedDiff' else f'{value:.2f}')
    for key, field in [('LeakForced','forcedEdges'),('LeakEdges','submittedEdges'),('LeakCorrect','forcedEdgesCorrect'),('LeakStudents','studentsWithForcedEdge')]: m(key, lk[field])
    f('LeakFraction', 100*lk['fractionOfEdgesForced'], 1); m('LeakFull', len(lk['fullyDeterminedStudents']))
    m('FairMin',fair['distinctMet']['min']); m('FairMax',fair['distinctMet']['max'])
    f('FairLowIn',fair['lowestInDegreeQuartile']['meanDistinctMet']); f('FairHighIn',fair['highestInDegreeQuartile']['meanDistinctMet'])
    for prefix, name in [('None','coalition_none'),('Star','coalition_min4'),('Strat','coalition_stratified'),('Screened','coalition_screened')]:
        s=refs[name]['summary']; m(prefix+'Intact',s['coalitionIntactRotations']); f(prefix+'AvgCluster',s['coalitionAvgCluster'])
    m('StarPatterns', ', '.join(f'{esc(k)} in {v} rotation' + ('s' if v != 1 else '') for k,v in sorted(refs['coalition_min4']['summary']['coalitionPatterns'].items())))
    for state in ('Same','Mixed'): m('StratIntact'+state, refs['coalition_stratified']['summary']['coalitionIntactByState'][state.lower()])
    shared=refs['coalition_shared_anchor']; m('SharedIntactSame', shared['summary']['coalitionIntactByState']['same'])
    m('SharedReturned',shared['config']['diagnosticScreen']['nReturned'])
    best, wirings=best_four_of_five_wiring(); f('StarBound', best, 0); m('StarBoundWirings',len(wirings))
    worse=hs['repeatsWorseThanRandomRotations']; m('RepeatsWorseCount',len(worse)); m('RepeatsWorseRotations',', '.join(map(str,worse)) or 'none')
    isolated=[r for r in data['communities'] if r['mu']==1 and r['omega']==0]
    if len(isolated)!=1: raise ValueError('Missing isolated-community sensitivity result')
    f('IsolatedExactlyOne', isolated[0]['pctExactly1Mean'])
    iso_trace=json.loads((path.parent / isolated[0]['traceEvidence']['path']).read_text())
    f('IsolatedMeanList',sum(map(len,iso_trace['listed']))/len(iso_trace['listed']))
    long=[r for r in data['horizons'] if r['rotations']==32]
    if len(long)!=1: raise ValueError('Missing 32-rotation sensitivity result')
    long_trace=json.loads((path.parent / long[0]['traceEvidence']['path']).read_text())
    m('LongLeakForced',long_trace['leakage']['forcedEdges'])
    f('LongLeakFraction',100*long_trace['leakage']['fractionOfEdgesForced'],1)
    m('LongLeakFull',len(long_trace['leakage']['fullyDeterminedStudents']))
    m('NonSubmitters',cfg['submission']['nNonSubmitters']); m('RejectedByRules',len(cfg['submission']['rejectedByRules']))
    f('MaxSolve', max(r['summary']['maxSolveSeconds'] for r in refs.values()),1)
    m('Workers',cfg['solver']['workers']); m('CpsatTime',cfg['solver']['cpsatTime'])
    m('AnnealIters', f"{cfg['solver']['annealIters']:,}".replace(',', r'\,'))
    m('Versions', f"Python {cfg['versions']['python']}, NumPy {cfg['versions']['numpy']}, OR-Tools {cfg['versions']['ortools']}")
    # ----- revised implementation: release statuses, optimality proofs, CP model size, outcomes, exposure
    primary_traces=[]
    for row in honest + list(stars.values()):
        primary_traces.append(json.loads((path.parent / row['traceEvidence']['path']).read_text()))
    all_rots=[r for t in primary_traces for r in t['rotations']]
    m('PrimaryRotations', len(all_rots))
    for status in ('optimized','incumbent','fallback'):
        m('Release'+status.capitalize(), sum(1 for r in all_rots if r['release']['status']==status))
    m('ProvenOptimalRotations', sum(1 for r in all_rots if r['release'].get('optimalityProven')))
    m('CpsatAcceptedRotations', sum(1 for r in all_rots if r['stats']['acceptedPhase']=='cpsat'))
    m('CpsatFeasibleRotations', sum(1 for r in all_rots if r['stats'].get('cpsatStatus') in ('FEASIBLE','OPTIMAL')))
    m('CpsatPairVarsMax', max((r['stats'].get('cpsatPairVariables') or 0) for r in all_rots))
    m('CpsatConstraintsMax', f"{max((r['stats'].get('cpsatConstraints') or 0) for r in all_rots):,}".replace(',', r'\,'))
    f('CpsatMeanSeconds', sum(r['pipeline'][-1]['seconds'] for r in h['rotations'])/len(h['rotations']), 1)
    f('MeanSolveSeconds', sum(r['stats']['solveTime'] for r in h['rotations'])/len(h['rotations']), 1)
    m('ConstructionInfeasibleRotations', sum(1 for r in all_rots if r['pipeline'][1]['cost']['violations']>0))
    outc=h['outcomes']['proposed']; outr=h['outcomes']['random']
    m('PeersMin', outc['distinctPeers']['min']); f('PeersPTen', outc['distinctPeers']['p10'], 1); f('PeersMedian', outc['distinctPeers']['median'], 1)
    m('PeersMinRandom', outr['distinctPeers']['min']); f('PeersPTenRandom', outr['distinctPeers']['p10'], 1)
    f('RepeatSameMedian', outc['repeatedCompanionship']['maxRepeatWithSameListedPeer']['median'], 1)
    m('RepeatSameMax', outc['repeatedCompanionship']['maxRepeatWithSameListedPeer']['max'])
    f('ConcentrationMedian', 100*outc['repeatedCompanionship']['concentration']['median'], 0)
    f('ExtrasPerObligatedRotation', outc['extraCompanions']['perObligatedRotation'], 4)
    f('ExactlyOneObligated', outc['coverageAmongObligated']['exactlyOnePct'])
    sub=cfg['submissions']
    m('PendingReview', len(sub['pendingReview'])); m('ApprovedExceptions', len(sub['approvedExceptions'])); m('VoluntaryNonsubmission', len(sub['voluntaryNonsubmission']))
    m('ObligatedStudents', sub['obligated'])
    expo=h['leakage']['coseatingExposure']
    f('ExposureTopOne', 100*expo['proposed']['top1ListedRate'], 1); f('ExposureTopOneRandom', 100*expo['random']['top1ListedRate'], 1)
    f('ExposureTopThree', 100*expo['proposed']['topKListedRate'], 1)
    m('CurrentOnlyForced', h['leakage']['currentOnlyDistribution']['forcedEdges'])
    fm=h['config'].get('fullModelScreen', {})
    m('FullModelExamined', sum((fm.get(st) or {}).get('coverage', {}).get('candidatesExamined', 0) for st in ('mixed','same')))
    screened=refs['coalition_screened']['config']['screen']
    fms=screened.get('fullModelScreen', {})
    m('ScreenedFullModelForced', len(fms.get('forcedGroups', [])))
    m('ScreenedFullModelExamined', sum((fms.get('perState', {}).get(st) or {}).get('coverage', {}).get('candidatesExamined', 0) for st in ('mixed','same')))
    m('SourceHash', cfg['provenance']['effectiveSourceHash'][:12])
    # ----- CP-SAT formulation benchmark (results/benchmarks), measured on the same machine
    bench_path=ROOT/'results/benchmarks/cpsat_formulation_257.json'
    if bench_path.exists():
        bench=json.loads(bench_path.read_text())
        def stat(key, field):
            vals=[row['formulations'][key][field] for row in bench if key in row['formulations']]
            return vals
        m('BenchRotations', len(bench))
        f('BenchExactMeanSeconds', sum(stat('exact@3.5','wall'))/len(bench), 1)
        f('BenchExactMaxSeconds', max(stat('exact@3.5','wall')), 1)
        f('BenchSurrogateMeanSeconds', sum(stat('legacy@3.5','wall'))/len(bench), 1)
        m('BenchExactWorsened', sum(1 for v in stat('exact@3.5','improvedTotal') if v<0))
        m('BenchExactImproved', sum(1 for v in stat('exact@3.5','improvedTotal') if v>0))
        m('BenchSurrogateWorsened', sum(1 for v in stat('legacy@3.5','improvedTotal') if v<0))
        m('BenchPreviousCountWorsened', sum(1 for v in stat('previous-count@3.5','improvedTotal') if v<0))
        m('BenchMaxHistoryPairs', max(row['historyPairs'] for row in bench))
        m('BenchAnnealIters', '100\\,000')

    tables={}
    rows=[]
    for name,t in refs.items():
        s=t['summary']; q=len(t['config']['coalition']) if t['config']['coalitionMode'] else None
        rows.append([LABEL[name],q or '--',f"{s['pctGe1Min']:.0f}",f"{s['pctExactly1Mean']:.2f}",f"{s['meanDistinctMetFinal']:.2f}",
            f"{s['coalitionIntactRotations']}/16" if q else '--',f"{s['coalitionAvgCluster']:.2f}" if q else '--'])
    tables['summary']=table('summary','Six verified seed-seven reference scenarios. Minimum guarantee and mean exactly-one rates are percentages of submitters; distinct contacts average over all participants. Intact and cluster values use the actual coalition size $q$.',
        ['Scenario','$q$','$\\ge1$','Exactly 1','Contacts','Intact','$H$'], rows,'lrrrrrr')
    rows=[]
    for r in honest:
        s=stars[r['populationSeed']]
        rows.append([r['populationSeed'],f"{r['pctExactly1Mean']:.2f}",f"{r['meanDistinctMetFinal']:.2f}",f"{r['meanDistinctMetFinalRandom']:.2f}",
                     f"{r['meanDistinctMetFinal']-r['meanDistinctMetFinalRandom']:+.2f}",r['leakageForcedEdges'],f"{s['coalitionAvgCluster']:.2f}"])
    tables['seeds']=table('seeds','Primary population comparisons at the default budget. Exactly-one percentages, distinct contacts (proposed and random), their paired difference, forced directed list entries, and the omission-star mean cluster size are computed from full traces.',
        ['Seed','Exactly 1','Contacts','Random','$\\Delta$','Forced','Star $H$'],rows,'rrrrrrr')
    def group(a):
        if a['category']=='seeds': return 'Primary population pairs' if a['configuration']['scenario'] in ('honest','coalition_min4') else 'Additional reference attacks'
        if a['category']=='budgets': return 'Annealing sensitivity' if a['configuration']['run']['anneal_iters']!=300000 else 'CP sensitivity'
        return {'horizons':'Horizon sensitivity','communities':'Community sensitivity'}[a['category']]
    groups=['Primary population pairs','Additional reference attacks','Annealing sensitivity','CP sensitivity','Horizon sensitivity','Community sensitivity']
    rows=[]
    for g in groups:
        aa=[a for a in attempts.values() if group(a)==g]; counts=Counter(a['status'] for a in aa)
        interrupted=sum(v for k,v in counts.items() if k.startswith('interrupted'))
        rows.append([g,len(aa),counts['success'],interrupted,len(aa)-counts['success']-interrupted])
    counts=Counter(a['status'] for a in attempts.values())
    tables['ledger']=table('ledger','Attempt-level evidence inventory. Interrupted processes remain in the denominator after resumption; they do not establish either model infeasibility or solver failure. Other terminal outcomes, if any, are detailed in the machine-readable ledger.',
        ['Experiment family','Attempts','Success','Interrupted','Other'],rows,'lrrrr')
    m('VerifiedAttempts',len(attempts));m('VerifiedRuns',counts['success']);m('VerifiedRotations',sum(r['rotations'] for k in ('seeds','budgets','horizons','communities') for r in data[k]))
    screen_rows=[]
    for name in ('honest','coalition_stratified','coalition_shared_anchor','coalition_screened'):
        t=refs[name]; sc=t['config'].get('diagnosticScreen') or t['config'].get('screen')
        if not sc: continue
        fm=(t['config'].get('screen') or {}).get('fullModelScreen', {}).get('perState', {}) if name!='coalition_shared_anchor' else {}
        reports = [(LABEL[name], sc, fm)]
        if name == 'coalition_screened':
            reports = [('Initial screened attack', sc, {}),
                       ('After resubmission', sc['afterResubmission'], fm)]
        for label, structural, full_model in reports:
            for state in ('mixed','same'):
                ss=structural['perState'][state]; cert=[c for c in ss['candidates'] if c['verdict']=='proved-coercive']
                cov=ss['coverage']; fs=full_model.get(state) or {}
                full_counts=fs.get('verdictCounts', {})
                full=(f"{fs['coverage']['candidatesExamined']}/{fs['coverage']['candidatesDiscovered']}"
                      f"; {full_counts.get('forced',0)}/{full_counts.get('separable',0)}/{full_counts.get('unresolved',0)}") if fs else '--'
                screen_rows.append([label, state, len(cert),len(ss.get('unresolvedCandidates',[])),
                    f"{cov['targetCandidatesExamined']}/{cov['targetCandidatesDiscovered']}", full])
    tables['screen']=table('screen','Reference screening by eligibility state. The initial screened attack and its replacement lists are separate rows: retained full-model tests use the replacement lists. Certificates may overlap and do not count distinct students. Target cores show examined/discovered bounded candidates. Full model shows examined/discovered tests, followed by forced/separable/unresolved counts. These are checks on the archived full-attendance states, not recall against all possible attacks.',
        ['Submission','State','Certificates','Unresolved','Target cores','Full model'],screen_rows,'llrrrl')
    rows=[]
    settings=[('Reference (16 rotations)',next(r for r in honest if r['populationSeed']==7))]
    for r in data['budgets']:
        setting=f"Anneal {r['annealIters']:,}" if r['annealIters']!=300000 else f"CP budget {r['cpsatTime']:g}"
        settings.append((setting,r))
    settings += [(f"Horizon {r['rotations']}",r) for r in data['horizons']]
    settings += [(f"Groups $\\mu={r['mu']:g},\\omega={r['omega']:g}$",r) for r in data['communities']]
    for setting,r in settings:
        rows.append([setting,r['rotations'],f"{r['pctExactly1Mean']:.2f}",f"{r['meanDistinctMetFinal']:.2f}",f"{r['meanDistinctMetFinalRandom']:.2f}",r['leakageForcedEdges'],
                     r['config']['submissions']['counts']['voluntary_nonsubmission']+r['config']['submissions']['counts']['pending_review'],
                     len(r.get('fallbackRotations',[]))+len(r.get('incumbentRotations',[]))])
    tables['sensitivity']=table('sensitivity','Seed-seven honest sensitivity, with one setting changed at a time. Contact counts and forced entries depend on horizon and should be compared at equal horizons. "No list" counts voluntary nonsubmission and pending requests; it is distinct from an unmet seating guarantee. "Cached" counts rotations that released a validated cached chart (incumbent or fallback) rather than a chart produced by that rotation\'s search.',
        ['Setting','$R$','Exactly 1','Contacts','Random','Forced','No list','Cached'],rows,'lrrrrrrr')
    net=cfg['network']; run=cfg['solver']
    rows=[['Population',f"{cfg['n']} ({cfg['n11']} grade 11; {cfg['n12']} grade 12)"],
        ['Tables',r'17 $\times$ 7 and 23 $\times$ 6'],['Rotations','16, alternating mixed and same grade'],
        ['Defended study lists','None or 4--8 names; at least 2 same grade'],
        ['Reference submission states',f"{sub['counts']['accepted']} accepted, {len(sub['pendingReview'])} pending, {len(sub['approvedExceptions'])} approved exceptions, {len(sub['voluntaryNonsubmission'])} voluntary nonsubmission"],
        ['Objective weights',f"extra companion {cfg['objective']['extraWeight']:g}, $\\lambda={cfg['objective']['lambda']:g}$, repeats {cfg['objective']['incidentalRepeat']}/{cfg['objective']['listedRepeat']}; integer scale {cfg['objective']['integerScale']}"],
        ['CP-SAT formulation',f"{cfg['solver']['cpsatPairs']} history pairs, integer extras ({cfg['solver']['cpsatExtras']})"],
        ['Attendance',f"absence rate {cfg['attendance']['absenceRate']:g}; conflict policy {cfg['attendance']['conflictPolicy']}"],
        ['Popularity / within-grade weight',f"$\\sigma={net['popularitySigma']}$ / {net['withinBias']:g}"],
        ['Reciprocity target / realized',f"{net['targetReciprocity']} / {net['reciprocity']:.3f}"],
        ['Realized within-grade fraction',f"{net['withinGradeFrac']:.3f}"],['Reference communities',r'$\mu=0,\ \omega=0$'],
        ['Annealing budget / temperature',r'300,000 iterations / $25\to0.2$ (integer energy)'],
        ['CP budget / workers',f"{run['cpsatTime']} deterministic-time units / {run['workers']}"],
        ['Pre-feasibility budget',f"{run['feasibilityTime']} deterministic-time units per state"],
        ['Runtime versions',r'\Versions']]
    tables['parameters']=table('params','Reference configuration. Complete generator, submission, and solver configurations are retained in every trace.', ['Parameter','Value'],rows,'lp{9.2cm}')
    for out in OUTS:
        (out/'generated').mkdir(parents=True,exist_ok=True)
        (out/'macros.tex').write_text('% Study macros derive from verified full traces; Bench macros use the separately disclosed exploratory summary.\n'+'\n'.join(f'\\newcommand{{\\{k}}}{{{v}}}' for k,v in macros.items())+'\n')
        for name,content in tables.items(): (out/'generated'/f'{name}.tex').write_text(content)
        (out/'tables.tex').write_text('\n'.join(tables.values()))
    (ROOT/'paper/numerical_claims.json').write_text(json.dumps({'manifest':str(path.relative_to(ROOT)),'macros':macros,'sourceHashes':sorted({a['source']['effectiveSourceHash'] for a in attempts.values()})},indent=2)+'\n')
    print(f'Generated {len(macros)} numerical macros and {len(tables)} tables from {counts["success"]} verified runs.')


if __name__=='__main__': main(sys.argv[1] if len(sys.argv) > 1 else None)
