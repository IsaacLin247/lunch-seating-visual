#!/usr/bin/env python
"""Build all manuscript numbers from the finalized, verified experiment ledger.

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


def main():
    path = ROOT / 'results/verified_experiments.json'
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
        for state in ('mixed','same'):
            ss=sc['perState'][state]; cert=[c for c in ss['candidates'] if c['verdict']=='proved-coercive']
            cov=ss['coverage']
            screen_rows.append(['Initial screened attack' if name=='coalition_screened' else LABEL[name], state, len(cert),len(ss.get('unresolvedCandidates',[])),
                f"{cov['targetCandidatesExamined']}/{cov['targetCandidatesDiscovered']}"])
    tables['screen']=table('screen','Reference diagnostic screening by eligibility state, before any modeled resubmission. Certificates may overlap; they are not counts of distinct students. Target coverage is examined/discovered bounded cores, not recall against all possible attacks. All screens also record closure and capacity checks.',
        ['Submission','State','Certificates','Unresolved','Target cores'],screen_rows,'llrrr')
    rows=[]
    settings=[('Reference (16 rotations)',next(r for r in honest if r['populationSeed']==7))]
    for r in data['budgets']:
        setting=f"Anneal {r['annealIters']:,}" if r['annealIters']!=300000 else f"CP budget {r['cpsatTime']:g}"
        settings.append((setting,r))
    settings += [(f"Horizon {r['rotations']}",r) for r in data['horizons']]
    settings += [(f"Groups $\\mu={r['mu']:g},\\omega={r['omega']:g}$",r) for r in data['communities']]
    for setting,r in settings:
        rows.append([setting,r['rotations'],f"{r['pctExactly1Mean']:.2f}",f"{r['meanDistinctMetFinal']:.2f}",f"{r['meanDistinctMetFinalRandom']:.2f}",r['leakageForcedEdges'],r['config']['submission']['nNonSubmitters']])
    tables['sensitivity']=table('sensitivity','Seed-seven honest sensitivity, with one setting changed at a time. Contact counts and forced entries depend on horizon and should be compared at equal horizons. Nonsubmission includes generated lists rejected by the admission rule; it is distinct from an unmet seating guarantee.',
        ['Setting','$R$','Exactly 1','Contacts','Random','Forced','No list'],rows,'lrrrrrr')
    net=cfg['network']; run=cfg['solver']
    rows=[['Population',f"{cfg['n']} ({cfg['n11']} grade 11; {cfg['n12']} grade 12)"],
        ['Tables',r'17 $\times$ 7 and 23 $\times$ 6'],['Rotations','16, alternating mixed and same grade'],
        ['Defended study lists','None or 4--8 names; at least 2 same grade'],['Reference nonsubmitters',cfg['submission']['nNonSubmitters']],
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
        (out/'macros.tex').write_text('% Generated exclusively from verified full traces.\n'+'\n'.join(f'\\newcommand{{\\{k}}}{{{v}}}' for k,v in macros.items())+'\n')
        for name,content in tables.items(): (out/'generated'/f'{name}.tex').write_text(content)
        (out/'tables.tex').write_text('\n'.join(tables.values()))
    (ROOT/'paper/numerical_claims.json').write_text(json.dumps({'manifest':'results/verified_experiments.json','macros':macros,'sourceHashes':sorted({a['source']['effectiveSourceHash'] for a in attempts.values()})},indent=2)+'\n')
    print(f'Generated {len(macros)} numerical macros and {len(tables)} tables from {counts["success"]} verified runs.')


if __name__=='__main__': main()
