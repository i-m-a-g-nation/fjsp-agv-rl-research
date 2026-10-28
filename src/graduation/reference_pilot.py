"""Offline, one-shot development pilot for the proposed G3A reference protocol."""
import csv
from dataclasses import asdict
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time

from src.ai_workflow.graduation_backend import _checked_metrics, _restore, METRICS
from src.ai_workflow.process_supervisor import supervised_json_process
from src.graduation.data import ParallelMaintenanceInstance, ProductionTask, MaintenanceRequirement
from src.graduation.enumeration import enumerate_parallel_maintenance
from src.graduation.solver import solve_parallel_maintenance
from src.graduation.reference_protocol import build_pilot_cases, pilot_protocol, encoded, digest

ROOT = Path(__file__).resolve().parents[2]


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def _data(case):
    raw = case['data']
    return ParallelMaintenanceInstance(tuple(ProductionTask(**t) for t in raw['tasks']),
        raw['num_machines'], tuple(MaintenanceRequirement(**m) for m in raw['maintenance']))


def _snapshot(result):
    return {**{key:getattr(result, key) for key in METRICS},
        'records':[asdict(r) for r in result.records],
        'maintenance_records':[asdict(r) for r in result.maintenance_records]}


def solve_case(case, mode):
    """Keep rejected diagnostics, but expose no accepted metric for a failed row."""
    data, candidate, reference = _data(case), None, None
    try:
        settings = {k:pilot_protocol()['solver'][k] for k in ('time_limit','num_workers','seed')}
        candidate = solve_parallel_maintenance(data, mode=mode, **settings)
        _checked_metrics(data, candidate, mode)
        reference = enumerate_parallel_maintenance(data, mode=mode, max_states=200000)
        _checked_metrics(data, reference, mode)
        if (candidate.solver_status != 'OPTIMAL' or reference.solver_status != 'OPTIMAL'
                or candidate.total_tardiness != reference.total_tardiness):
            raise ValueError('Pilot requires OPTIMAL CP-SAT and matching independent enumeration')
        return {'status':'PASS', 'total_tardiness':candidate.total_tardiness, 'error':'',
            'candidate':_snapshot(candidate), 'reference':_snapshot(reference)}
    except Exception as exc:
        return {'status':'FAILED', 'total_tardiness':None,
            'error':f'{type(exc).__name__}: {str(exc)[:500]}',
            'candidate':None if candidate is None else _snapshot(candidate),
            'reference':None if reference is None else _snapshot(reference)}


def _sources():
    files = [*sorted((ROOT/'src').rglob('*.py')), ROOT/'experiments/exp_028_graduation_reference_pilot.py']
    return {p.relative_to(ROOT).as_posix():file_sha(p) for p in files}


def _clock(deadline):
    if time.monotonic() >= deadline:
        raise subprocess.TimeoutExpired('reference pilot', 90)


def execute_prepared(folder, deadline):
    """Trusted worker: all inputs precede all fixed-then-joint requests."""
    folder = Path(folder)
    if _read(folder/'protocol.json') != pilot_protocol():
        raise ValueError('Pilot protocol changed')
    state = _read(folder/'state.json')
    cases = build_pilot_cases()
    for case in cases:
        if encoded(_read(folder/'inputs'/f"{case['case_id']}.json")) != encoded(case):
            raise ValueError('Prepared input differs from deterministic generator')
    for index, row in enumerate(state['rows']):
        _clock(deadline)
        case = cases[index//2]
        mode = ('fixed','joint')[index%2]
        if row['case_id'] != case['case_id'] or row['mode'] != mode or row['status'] != 'NOT_RUN':
            raise ValueError('Planned pilot row changed')
        row['status'] = 'RUNNING'
        _write(folder/'state.json', state)
        trace = solve_case(case, mode)
        _clock(deadline)
        _write(folder/'schedules'/f"{case['case_id']}-{mode}.json", trace)
        row.update(status=trace['status'], total_tardiness=trace['total_tardiness'], error=trace['error'])
        _write(folder/'state.json', state)
    return {'status':'WORKER_FINISHED'}


def _recheck_rows(folder, state, check=lambda: None):
    cases = build_pilot_cases()
    if len(state['rows']) != 24 or _read(folder/'protocol.json') != pilot_protocol():
        raise ValueError('Pilot protocol or row denominator changed')
    totals = []
    for index, row in enumerate(state['rows']):
        check()
        case, mode = cases[index//2], ('fixed','joint')[index%2]
        if (encoded(_read(folder/'inputs'/f"{case['case_id']}.json")) != encoded(case)
                or row['case_id'] != case['case_id'] or row['mode'] != mode or row['status'] != 'PASS'):
            raise ValueError('Pilot input, row order or completion changed')
        trace = _read(folder/'schedules'/f"{case['case_id']}-{mode}.json")
        if trace['status'] != 'PASS' or trace['error'] or row['error']:
            raise ValueError('Pilot contains a failed trace')
        data = _data(case)
        candidate, reference = (_restore(data, trace[k]) for k in ('candidate','reference'))
        for result in (candidate, reference):
            _checked_metrics(data, result, mode)
            if result.solver_status != 'OPTIMAL':
                raise ValueError('Pilot requires proven optimality, not FEASIBLE')
        # A source-bound status label is insufficient: recompute the tiny optimum.
        oracle = enumerate_parallel_maintenance(data, mode=mode, max_states=200000)
        values = (candidate.total_tardiness, reference.total_tardiness,
                  row['total_tardiness'], trace['total_tardiness'])
        if any(value != oracle.total_tardiness for value in values):
            raise ValueError('Saved optimum differs from fresh enumeration')
        totals.append(candidate.total_tardiness)
        check()
    pairs = []
    for index, case in enumerate(cases):
        fixed, joint = totals[2*index:2*index+2]
        if joint > fixed:
            raise ValueError('Proven joint optimum exceeds fixed optimum')
        pairs.append({'case_id':case['case_id'], 'fixed_total_tardiness':fixed,
            'joint_total_tardiness':joint, 'difference':fixed-joint,
            'relative_improvement':None if fixed == 0 else (fixed-joint)/fixed})
    aliases = {}
    for case in cases:
        aliases.setdefault(case['core_model_hash'], []).append(case['case_id'])
    return {'validated_runs':24, 'paired_cases':12,
        'base_workloads':len({c['workload_hash'] for c in cases}),
        'unique_core_models':len(aliases), 'core_model_aliases':aliases, 'pairs':pairs,
        'research_status':'not_achieved', 'formal_approval':False,
        'model_calls':0, 'network_calls':0, 'scope':'pilot_development_validation',
        'final_test_evaluated':False, 'main_grid_executed':False}


def _csv(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['case_id','mode','status','total_tardiness','error'], lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def run_pilot(output_dir, *, max_active_seconds=90):
    if (type(max_active_seconds) not in (int,float) or not math.isfinite(max_active_seconds)
            or not 0 < max_active_seconds <= 90):
        raise ValueError('Pilot execution budget must be finite in (0,90]')
    started = time.monotonic()
    deadline = started + max_active_seconds
    folder = Path(output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    (folder/'inputs').mkdir()
    (folder/'schedules').mkdir()
    protocol, cases, sources = pilot_protocol(), build_pilot_cases(), _sources()
    _write(folder/'protocol.json', protocol)
    for case in cases:
        _write(folder/'inputs'/f"{case['case_id']}.json", case)
    state = {'status':'PREPARED', 'rows':[{'case_id':c['case_id'],'mode':m,'status':'NOT_RUN',
        'total_tardiness':None,'error':''} for c in cases for m in ('fixed','joint')]}
    _write(folder/'state.json', state)
    result = {'status':'FAILED', 'error':'', 'research_status':'not_achieved', 'formal_approval':False}
    try:
        _clock(deadline)
        reply = supervised_json_process(Path(__file__).with_name('reference_pilot_worker.py'),
            {'folder':str(folder), 'deadline':deadline}, max(0.001, deadline-time.monotonic()))
        if reply != {'status':'WORKER_FINISHED'}:
            raise ValueError('Worker did not finish the registered pilot')
        state = _read(folder/'state.json')
        result.update(_recheck_rows(folder, state, lambda:_clock(deadline)))
        if sources != _sources():
            raise ValueError('Pilot source identity changed during execution')
        _clock(deadline)
        result['status'] = 'COMPLETED'
    except Exception as exc:
        result.update(status='BUDGET_EXHAUSTED' if isinstance(exc, subprocess.TimeoutExpired) else 'FAILED',
            error=f'{type(exc).__name__}: {str(exc)[:500]}')
    state = _read(folder/'state.json')
    for row in state['rows']:
        if row['status'] == 'RUNNING':
            row.update(status='INTERRUPTED',total_tardiness=None,error=result['error'])
    state['status'] = result['status']
    result.update(planned_runs=24, finished_rows=sum(r['status'] == 'PASS' for r in state['rows']),
        max_active_seconds=max_active_seconds, active_seconds=time.monotonic()-started,
        note='Development inputs are exposed; not an independent final test or a formal G3 approval.')
    _write(folder/'state.json', state)
    (folder/'raw.csv').write_bytes(_csv(state['rows']))
    _write(folder/'summary.json', result)
    manifest = {'version':1,'status':result['status'],'protocol_sha256':digest(protocol),
        'source_hashes':sources, 'runtime':{'python':sys.version, 'platform':platform.platform(),
            'ortools':importlib.metadata.version('ortools')},
        'artifacts':{p.relative_to(folder).as_posix():file_sha(p)
            for p in sorted(folder.rglob('*')) if p.is_file()}}
    _write(folder/'manifest.json', manifest)
    # Receipt I/O belongs to the completion deadline too. A late filesystem
    # operation can finish after the cap, but cannot leave a successful receipt.
    settled = time.monotonic()-started
    if result['status'] == 'COMPLETED' and settled > max_active_seconds:
        result.update(status='BUDGET_EXHAUSTED', active_seconds=settled,
            error='Pilot deadline expired while persisting final receipts')
        state['status'] = result['status']
        _write(folder/'state.json', state)
    else:
        result['active_seconds'] = settled
    _write(folder/'summary.json', result)
    manifest.update(status=result['status'], artifacts={p.relative_to(folder).as_posix():file_sha(p)
        for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'manifest.json'})
    _write(folder/'manifest.json', manifest)
    if result['status'] == 'COMPLETED' and time.monotonic() > deadline:
        # Also cover the final receipt refresh, without retrying any solver.
        result.update(status='BUDGET_EXHAUSTED', active_seconds=time.monotonic()-started,
            error='Pilot deadline expired while refreshing final receipts')
        state['status'] = result['status']
        _write(folder/'state.json', state)
        _write(folder/'summary.json', result)
        manifest.update(status=result['status'], artifacts={p.relative_to(folder).as_posix():file_sha(p)
            for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'manifest.json'})
        _write(folder/'manifest.json', manifest)
    return result


def recheck_pilot(output_dir, *, require_current_sources=False):
    """Read-only portable evidence verification, including fresh tiny enumeration."""
    folder = Path(output_dir)
    manifest = _read(folder/'manifest.json')
    if (type(manifest.get('version')) is not int or manifest['version'] != 1
            or manifest['status'] != 'COMPLETED' or manifest['protocol_sha256'] != digest(pilot_protocol())):
        raise ValueError('Pilot is incomplete or protocol identity changed')
    sources, runtime = manifest.get('source_hashes'), manifest.get('runtime')
    required = {'src/graduation/'+name+'.py' for name in
        ('data','solver','enumeration','feasibility','reference_protocol','reference_pilot','reference_pilot_worker')}
    required.update({'src/ai_workflow/graduation_backend.py','src/ai_workflow/process_supervisor.py',
        'experiments/exp_028_graduation_reference_pilot.py'})
    if (not isinstance(sources,dict) or not required <= sources.keys()
            or any(not isinstance(k,str) or '..' in Path(k).parts or Path(k).is_absolute()
                or not isinstance(v,str) or len(v) != 64 or any(c not in '0123456789abcdef' for c in v)
                for k,v in sources.items())):
        raise ValueError('Missing or malformed pilot source provenance')
    if (not isinstance(runtime,dict) or set(runtime) != {'python','platform','ortools'}
            or any(not isinstance(v,str) or not v for v in runtime.values())
            or runtime['python'].split()[0] != pilot_protocol()['generator']['python_version']):
        raise ValueError('Missing or incompatible pilot runtime provenance')
    if require_current_sources and sources != _sources():
        raise ValueError('Pilot sources differ from the current checkout')
    actual = {p.relative_to(folder).as_posix():file_sha(p)
        for p in sorted(folder.rglob('*')) if p.is_file() and p.name != 'manifest.json'}
    if actual != manifest['artifacts']:
        raise ValueError('Pilot artifact identities changed')
    state, summary = _read(folder/'state.json'), _read(folder/'summary.json')
    if state['status'] != 'COMPLETED' or summary['status'] != 'COMPLETED':
        raise ValueError('Pilot summary is not complete')
    cap, elapsed = summary.get('max_active_seconds'), summary.get('active_seconds')
    if (type(cap) not in (int,float) or not math.isfinite(cap) or not 0 < cap <= 90
            or type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0 <= elapsed <= cap
            or type(summary.get('planned_runs')) is not int or summary['planned_runs'] != 24
            or type(summary.get('finished_rows')) is not int or summary['finished_rows'] != 24):
        raise ValueError('Invalid completed pilot counts or execution budget')
    checked = _recheck_rows(folder, state)
    if any(summary.get(k) != v for k,v in checked.items()) or (folder/'raw.csv').read_bytes() != _csv(state['rows']):
        raise ValueError('Pilot summary or CSV differs from checked plans')
    return {**summary, **checked, 'current_sources_checked':require_current_sources,
        'provenance_boundary':'Artifact hashes bind recorded provenance; this is not proof of the recorded host identity.'}
