"""Strict offline graduation requests and independently rechecked artifacts."""

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import re

from src.graduation import (MaintenanceRecord, MaintenanceRequirement, MaintenanceScheduleResult,
    ParallelMaintenanceInstance, ProductionTask, check_parallel_maintenance_feasibility,
    solve_parallel_maintenance, to_fjsp_instance)
from src.scheduling.encoding import ScheduleRecord

MODEL = 'graduation_g2_identical_singleop_v1'
METRICS = ('makespan', 'total_tardiness', 'solver_status', 'solver_objective_value',
           'solver_objective_bound', 'solver_gap', 'solver_wall_time')
ARTIFACTS = {'request.json', 'fixed.json', 'joint.json', 'report.md'}


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError('Duplicate JSON key')
            value[key] = item
        return value
    def invalid(value):
        raise ValueError('Nonfinite JSON constant')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode('utf-8')


def _parse(raw):
    if len(raw) > 1048576:
        raise ValueError('Graduation request exceeds 1 MiB')
    value = _json(raw)
    keys = {'schema_version', 'request_id', 'tasks', 'num_machines', 'maintenance', 'solver'}
    if not isinstance(value, dict) or set(value) != keys or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Invalid graduation request schema')
    if not isinstance(value['request_id'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', value['request_id']):
        raise ValueError('Invalid request_id')
    if (not isinstance(value['tasks'], list) or not 1 <= len(value['tasks']) <= 50
            or type(value['num_machines']) is not int or not 1 <= value['num_machines'] <= 10
            or not isinstance(value['maintenance'], list) or len(value['maintenance']) > 10):
        raise ValueError('Graduation reference supports 1..50 tasks and 1..10 machines')
    try:
        data = ParallelMaintenanceInstance(tuple(ProductionTask(**item) for item in value['tasks']), value['num_machines'],
                                          tuple(MaintenanceRequirement(**item) for item in value['maintenance']))
    except TypeError as exc:
        raise ValueError('Unknown or malformed model fields') from exc
    if any(item.fixed_start is None for item in data.maintenance):
        raise ValueError('Both modes require a prespecified fixed_start on every machine')
    settings = value['solver']
    if not isinstance(settings, dict) or set(settings) != {'time_limit', 'num_workers', 'seed'}:
        raise ValueError('Invalid solver settings')
    limit = settings['time_limit']
    if type(limit) not in (int, float) or not 0 < limit <= 30 or not math.isfinite(limit):
        raise ValueError('Solver time_limit must be finite in (0,30]')
    if type(settings['num_workers']) is not int or not 1 <= settings['num_workers'] <= 4:
        raise ValueError('Solver num_workers must be an integer in 1..4')
    if type(settings['seed']) is not int or not 0 <= settings['seed'] < 2**31:
        raise ValueError('Solver seed must be an integer in 0..2^31-1')
    n, m = len(data.tasks), data.num_machines
    horizon = max(item.window_end for item in data.maintenance) + sum(task.processing_time for task in data.tasks)
    if max(horizon*(4*n*m + 4*m + 4*n + 1), max(task.due_date for task in data.tasks)) > 2**50:
        raise ValueError('Request exceeds G2 numeric domain')
    description = {'request_id': value['request_id'], 'request_hash': _sha(raw), 'model': MODEL,
        'data': asdict(data), 'solver': settings, 'modes': ['fixed', 'joint'], 'expected_runs': 2,
        'assumptions': ['identical_machines', 'one_nonpreemptive_operation', 'release_zero',
                        'one_mandatory_maintenance_per_machine_including_idle', 'complete_window', 'no_shared_crew']}
    return description, data, settings


def _read_request(path):
    with Path(path).open('rb') as handle:
        return handle.read(1048577)


def describe_graduation_request(path: Path) -> dict:
    return _parse(_read_request(path))[0]


def _checked_metrics(data, result, mode):
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    if not accepted:
        raise ValueError(f'Graduation domain rejected schedule: {issues}')
    values = {field: getattr(result, field) for field in METRICS}
    if values['solver_status'] not in ('OPTIMAL', 'FEASIBLE'):
        raise ValueError('No extractable solver status')
    numeric = [values[field] for field in ('solver_objective_value', 'solver_objective_bound', 'solver_gap', 'solver_wall_time')]
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in numeric):
        raise ValueError('Invalid solver diagnostics')
    objective, bound, gap, elapsed = numeric
    if (objective != result.total_tardiness or not 0 <= bound <= objective or elapsed < 0
            or not math.isclose(gap, (objective-bound)/max(1.0, objective), rel_tol=0, abs_tol=1e-12)
            or values['solver_status'] == 'OPTIMAL' and bound != objective):
        raise ValueError('Solver metadata disagrees with independent total tardiness')
    return values


def _restore(data, raw):
    if not isinstance(raw, dict) or set(raw) != {*METRICS, 'records', 'maintenance_records'}:
        raise ValueError('Malformed saved graduation result')
    return MaintenanceScheduleResult(instance=to_fjsp_instance(data),
        records=[ScheduleRecord(**item) for item in raw['records']],
        maintenance_records=[MaintenanceRecord(**item) for item in raw['maintenance_records']],
        **{field: raw[field] for field in METRICS})


def _comparison_error(results):
    fixed, joint = results['fixed'], results['joint']
    if (fixed['solver_status'] == joint['solver_status'] == 'OPTIMAL'
            and joint['total_tardiness'] > fixed['total_tardiness']):
        return 'Proven joint optimum exceeds proven fixed optimum'
    return ''


def run_graduation_request(path: Path, output_dir: Path, *, expected_request_hash: str) -> dict:
    raw = _read_request(path)
    description, data, settings = _parse(raw)
    if description['request_hash'] != expected_request_hash:
        raise ValueError('Reviewed graduation request changed')
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    (output / 'request.json').write_bytes(raw)
    results = {}
    for mode in ('fixed', 'joint'):
        candidate = None
        try:
            candidate = solve_parallel_maintenance(data, mode=mode, **settings)
            metrics = _checked_metrics(data, candidate, mode)
            saved = {**metrics, 'records': [asdict(item) for item in candidate.records],
                     'maintenance_records': [asdict(item) for item in candidate.maintenance_records]}
            record = {'accepted': True, 'result': saved, 'error': ''}
        except Exception as exc:
            metrics = dict.fromkeys(METRICS)
            record = {'accepted': False, 'result': None,
                      'error': f'{type(exc).__name__}: {str(exc)[:1000]}', 'diagnostic': repr(candidate)[:1000]}
        (output / f'{mode}.json').write_bytes(_encoded(record))
        results[mode] = {**metrics, 'accepted': record['accepted'], 'error': record['error']}
    comparison_error = _comparison_error(results)
    accepted_count = sum(row['accepted'] for row in results.values())
    manifest = {'version': 1, 'model': MODEL, 'request_hash': description['request_hash'],
        'status': 'COMPLETED' if accepted_count == 2 and not comparison_error else 'FAILED',
        'expected_runs': 2, 'accepted_runs': accepted_count, 'failed_runs': 2-accepted_count,
        'results': results, 'comparison_error': comparison_error}
    lines = ['<!-- fjsp-generated-report track=graduation -->', '# 毕设固定/联合参考求解', '',
             f"请求：{description['request_id']}；状态：{manifest['status']}。", '',
             '| 模式 | 合法 | 求解状态 | 总延期 | 下界 | gap |', '|---|---|---|---:|---:|---:|']
    for mode, row in results.items():
        values = [mode, row['accepted'], row['solver_status'], row['total_tardiness'], row['solver_objective_bound'], row['solver_gap']]
        lines.append('| ' + ' | '.join('' if item is None else str(item) for item in values) + ' |')
    lines += ['', '该结果仅验证当前输入的参考模型；FEASIBLE未证明最优，不保证其目标优于另一模式的限时结果。',
              '总延期与生产makespan分别保存。G3正式比较、最终算法与完整任务书确认未完成；研究状态not_achieved。',
              '本路线没有文献/RAG/模型调用/生成代码，也没有自动生成人工批准。', '', '诊断：' + comparison_error]
    lines.extend(row['error'] for row in results.values() if row['error'])
    (output / 'report.md').write_bytes(('\n'.join(lines).rstrip() + '\n').encode('utf-8'))
    manifest['artifacts'] = {name: _sha((output / name).read_bytes()) for name in sorted(ARTIFACTS)}
    (output / 'manifest.json').write_bytes(_encoded(manifest))
    return manifest


def verify_graduation_artifacts(output_dir: Path, manifest_hash: str) -> dict:
    output = Path(output_dir).resolve()
    try:
        raw = (output / 'manifest.json').read_bytes()
        if _sha(raw) != manifest_hash:
            raise ValueError('Reviewed graduation manifest changed')
        manifest = _json(raw)
        if (set(manifest['artifacts']) != ARTIFACTS or manifest['model'] != MODEL or manifest['version'] != 1
                or {item.name for item in output.iterdir()} != ARTIFACTS | {'manifest.json'}):
            raise ValueError('Graduation artifact set changed')
        for name, digest in manifest['artifacts'].items():
            target = (output / name).resolve()
            if not target.is_relative_to(output) or _sha(target.read_bytes()) != digest:
                raise ValueError('Reviewed graduation artifact changed')
        description, data, _ = _parse((output / 'request.json').read_bytes())
        if description['request_hash'] != manifest['request_hash']:
            raise ValueError('Graduation input snapshot mismatch')
        results = {}
        for mode in ('fixed', 'joint'):
            record = _json((output / f'{mode}.json').read_bytes())
            if record['accepted'] is True:
                metrics = _checked_metrics(data, _restore(data, record['result']), mode)
                if record['error']:
                    raise ValueError('Accepted result contains a failure')
            elif record['accepted'] is False and record['result'] is None and record['error']:
                metrics = dict.fromkeys(METRICS)
            else:
                raise ValueError('Invalid result acceptance record')
            results[mode] = {**metrics, 'accepted': record['accepted'], 'error': record['error']}
        count = sum(row['accepted'] for row in results.values())
        error = _comparison_error(results)
        if (results != manifest['results'] or manifest['accepted_runs'] != count or manifest['failed_runs'] != 2-count
                or manifest['expected_runs'] != 2 or manifest['comparison_error'] != error
                or manifest['status'] != ('COMPLETED' if count == 2 and not error else 'FAILED')):
            raise ValueError('Saved graduation metrics/status mismatch')
        return manifest
    except (TypeError, KeyError, AttributeError, OSError) as exc:
        raise ValueError(f'Invalid graduation artifacts: {type(exc).__name__}') from exc
