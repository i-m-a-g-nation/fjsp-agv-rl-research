"""Replayable static-schedule evidence; hashes detect drift, not authorship."""

from __future__ import annotations

import csv
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from importlib.metadata import distributions
from pathlib import Path
import platform
import sys

from src.data.instance import FJSPInstance, validate_instance
from src.scheduling.encoding import ScheduleRecord, ScheduleResult
from src.scheduling.feasibility import check_feasibility

ROOT = Path(__file__).resolve().parents[1]


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def source_hashes():
    paths = list((ROOT / 'src').rglob('*.py')) + list((ROOT / 'experiments').glob('*.py'))
    paths += [ROOT / 'pyproject.toml', ROOT / 'environment.yml']
    return {p.relative_to(ROOT).as_posix(): _hash(p.read_bytes()) for p in sorted(paths)}


def _instance_data(instance):
    validate_instance(instance)
    return {'num_machines': instance.num_machines,
            'jobs': [[[[m, t] for m, t in op.machine_options] for op in job.operations]
                     for job in instance.jobs]}


def capture_run(original, result, feasible, violations, error, sources):
    data = _instance_data(original)
    saved = None
    if result is not None:
        saved = {'instance': _instance_data(result.instance),
                 'records': [asdict(record) for record in result.records],
                 'makespan': result.makespan,
                 'solver_status': result.solver_status,
                 'solver_objective_bound': result.solver_objective_bound,
                 'solver_gap': result.solver_gap,
                 'solver_wall_time': result.solver_wall_time,
                 'solver_config': result.solver_config}
    # A round trip detaches mutable records/configuration from the live solver.
    return json.loads(_json_bytes({'expected_instance': data, 'instance_sha256': _hash(_json_bytes(data)),
                                  'result': saved, 'feasible': feasible, 'violations': violations,
                                  'error': error, 'source_sha256': sources}))


def write_bundle(path, csv_bytes, records):
    path = Path(path)
    sidecar = path.with_suffix('.evidence.json')
    if path.exists() or sidecar.exists():
        raise FileExistsError(f'Use a new output path; evidence already exists: {path}')
    sources = source_hashes()
    for record in records:
        if record.evidence is not None and record.evidence['source_sha256'] != sources:
            raise ValueError('Source changed between execution and evidence writing')
    rows = []
    for record in records:
        run = deepcopy(record.evidence)
        if run is not None:
            run['source_digest'] = _hash(_json_bytes(run.pop('source_sha256')))
        rows.append({'csv': record.to_csv_row(), 'run': run})
    evidence = {
        'version': 1, 'scope': 'static_fjsp_feasibility',
        'created_utc': datetime.now(timezone.utc).isoformat(),
        'csv_sha256': _hash(csv_bytes), 'source_sha256': sources,
        'runtime': {'python': sys.version, 'executable': sys.executable,
                    'platform': platform.platform(),
                    'packages': {d.metadata['Name'].lower(): d.version for d in distributions()
                                 if d.metadata.get('Name')}},
        'rows': rows,
    }
    blob = _json_bytes(evidence)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement. If interrupted between
    # writes the incomplete pair remains visibly unverifiable; never repair it silently.
    with sidecar.open('xb') as handle:
        handle.write(blob)
    with path.open('xb') as handle:
        handle.write(csv_bytes)


def _restore_instance(data):
    if not isinstance(data, dict) or set(data) != {'num_machines', 'jobs'}:
        raise ValueError('Malformed archived instance')
    return FJSPInstance.from_jobs_array(data['jobs'], num_machines=data['num_machines'])


def _solver_metadata(result):
    if result.solver_status is None:
        return
    if result.solver_status not in ('OPTIMAL', 'FEASIBLE'):
        raise ValueError('Unexpected archived solver status')
    bound, gap, wall = result.solver_objective_bound, result.solver_gap, result.solver_wall_time
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in (bound, gap, wall)):
        raise ValueError('Invalid archived solver diagnostics')
    if bound > result.makespan or not math.isclose(gap, (result.makespan-bound)/max(1, result.makespan), abs_tol=1e-9):
        raise ValueError('Inconsistent archived solver bound/gap')
    if result.solver_status == 'OPTIMAL' and (bound != result.makespan or gap != 0):
        raise ValueError('OPTIMAL requires matching bound and zero gap')
    config = result.solver_config
    if not isinstance(config, dict) or set(config) != {'time_limit', 'num_workers', 'seed'}:
        raise ValueError('Missing archived solver configuration')
    if (type(config['time_limit']) not in (int, float) or not math.isfinite(config['time_limit'])
            or config['time_limit'] <= 0 or any(type(config[k]) is not int or not 0 <= config[k] <= 2**31-1
                                               for k in ('num_workers', 'seed'))):
        raise ValueError('Invalid archived solver configuration')


def recheck_results_csv(path, *, require_current_sources=False):
    """Recompute feasibility and metrics from stored plans; never rerun solvers.

    This validates the static layer only. A dynamic/maintenance archive still
    needs its domain-specific checker and evidence. Source hashes are recorded
    provenance; require_current_sources explicitly checks this checkout too.
    """
    path = Path(path)
    raw = path.read_bytes()
    evidence = json.loads(path.with_suffix('.evidence.json').read_text(encoding='utf-8'))
    if type(evidence.get('version')) is not int or evidence['version'] != 1:
        raise ValueError('Unsupported evidence version')
    if evidence.get('csv_sha256') != _hash(raw):
        raise ValueError('CSV hash mismatch')
    sources = evidence.get('source_sha256')
    if not isinstance(sources, dict) or not sources or any(
            not isinstance(k, str) or not isinstance(v, str) or len(v) != 64
            or any(c not in '0123456789abcdef' for c in v) for k, v in sources.items()):
        raise ValueError('Missing source identity evidence')
    if require_current_sources and sources != source_hashes():
        raise ValueError('Current source hash mismatch')
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
    saved_rows = evidence.get('rows')
    if not isinstance(saved_rows, list) or len(saved_rows) != len(rows) or not rows:
        raise ValueError('Missing or inconsistent row evidence')
    validated = failed = 0
    for row, saved in zip(rows, saved_rows):
        if row != saved.get('csv'):
            raise ValueError('CSV row differs from archived evidence')
        run = saved.get('run')
        if not isinstance(run, dict) or run.get('source_digest') != _hash(_json_bytes(sources)):
            raise ValueError('Missing complete run evidence')
        original_data = run.get('expected_instance')
        original = _restore_instance(original_data)
        if run.get('instance_sha256') != _hash(_json_bytes(original_data)):
            raise ValueError('Instance hash mismatch')
        if type(run.get('feasible')) is not bool or row['feasible'] != ('PASS' if run['feasible'] else 'FAIL'):
            raise ValueError('Inconsistent feasibility claim')
        payload = run.get('result')
        if payload is None:
            if run['feasible'] or not run.get('error') or row['makespan']:
                raise ValueError('Missing schedule for successful run')
            failed += 1
            continue
        try:
            result = ScheduleResult(**{k: v for k, v in payload.items() if k not in ('instance', 'records')},
                                    instance=_restore_instance(payload['instance']),
                                    records=[ScheduleRecord(**v) for v in payload['records']])
            passed, issues = check_feasibility(result, expected_instance=original)
        except (TypeError, ValueError, KeyError) as exc:
            raise ValueError(f'Malformed archived schedule: {exc}') from exc
        if passed != run['feasible'] or [v.code for v in issues] != run.get('violations'):
            raise ValueError('Archived schedule feasibility disagrees with claim')
        if row['makespan'] != str(result.makespan):
            raise ValueError('Archived schedule metric differs from CSV')
        for column, value in [('objective_bound', result.solver_objective_bound),
                              ('gap', result.solver_gap), ('solver_wall_time', result.solver_wall_time)]:
            if row[column] != ('' if value is None else f'{value:.6f}'):
                raise ValueError('Archived solver diagnostics differ from CSV')
        if passed:
            _solver_metadata(result)
            validated += 1
        else:
            failed += 1
    return {'scope': 'static_fjsp_feasibility', 'rows': len(rows),
            'validated_schedules': validated, 'failed_runs': failed,
            'current_sources_checked': require_current_sources}
