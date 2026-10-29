"""Read-only, standard-library arithmetic audit; never import or invoke a solver."""
import argparse
import hashlib
import json
import math
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def envelope(item):
    value = float.fromhex(item['hex'])
    require(math.isfinite(value) and item['finite'] is True and
            value == item['value'] and repr(value) == item['repr'], 'numeric envelope')
    return value


def audit(root):
    root = Path(root)
    selection = read(root / 'run/selection.json')
    state = read(root / 'run/state.json')
    require(state['status'] == 'DEVELOPMENT_FAILED', 'native packaging failure must remain')
    require(read(root / 'run/summary.json')['status'] == 'DEVELOPMENT_FAILED', 'batch status')
    require(read(root / 'run/worker_receipt.json') ==
            {'diagnostic_solver_calls': 5, 'status': 'CAPTURED'}, 'actual worker call count')
    require([r['sequence'] for r in selection['requests']] == [167, 186, 222, 226, 229], 'selection')
    require([r['sequence'] for r in state['rows']] == [167, 186, 222, 226, 229], 'state order')
    reports = []
    for request, thin in zip(selection['requests'], state['rows']):
        sequence = request['sequence']
        path = root / f'run/captures/{sequence:04d}.json'
        require(thin['status'] == 'CAPTURED' and sha(path) == thin['capture_sha256'], 'capture bytes')
        captured = read(path)
        data = request['case']['data']
        require(captured['input_sha256'] == hashlib.sha256(canonical(data)).hexdigest(), 'input identity')
        require(captured['case_id'] == thin['case_id'] == request['case']['case_id'] and
                captured['mode'] == thin['mode'] == request['mode'], 'request identity')
        require(captured['execution_kind'] == 'NATIVE_DEVELOPMENT_DIAGNOSTIC' and
                captured['accepted_for_research'] is False, 'native diagnostic boundary')
        row = captured['baseline_row']
        require(row == request['historical_row'], 'unchanged historical rejection')
        require(row['status'] == 'ERROR' and row['metrics'] is None and row['payload'] is None, 'rejected row')
        observation = captured['observation']
        require(not observation['capture_errors'] and captured['capture_status'] == 'COMPLETE', 'capture completeness')
        require(observation['status_code'] == observation['response']['status_code'] == 2 and
                observation['status_name'] == 'FEASIBLE', 'native feasibility status')
        variables = observation['response']['variables']
        require([v['index'] for v in variables] == list(range(len(variables))), 'variable index')
        raw = {v['name']: v['value'] for v in variables}
        require(len(raw) == len(variables), 'unique variable names')
        for variable in variables:
            domain, value = variable['domain'], variable['value']
            require(type(value) is int and len(domain) % 2 == 0 and
                    any(a <= value <= b for a, b in zip(domain[::2], domain[1::2])), 'integer domain')
        require(observation['model']['variables'] ==
                [{k: v[k] for k in ('index', 'name', 'domain')} for v in variables], 'pre-solve variable identity')
        calls = observation['value_calls']
        require(all(raw[c['name']] == c['value'] for c in calls), 'raw/API variable equality')
        candidate = captured['candidate']
        require(candidate['complete'] is True and candidate['label'] == 'UNVALIDATED_DIAGNOSTIC_CANDIDATE', 'candidate label')
        tasks = {t['job_id']: t for t in data['tasks']}
        production = candidate['production']
        require(len(tasks) == len(production) == 24 and
                sorted(r['job_id'] for r in production) == sorted(tasks), 'each task once')
        m = data['num_machines']
        intervals = {i: [] for i in range(m)}
        tardiness = 0
        for record in production:
            j = record['job_id']
            task = tasks[j]
            selected = [i for i in range(m) if raw[f'x{j}_{i}'] == 1]
            require(len(selected) == 1 and record['selected_machines'] == selected, 'exactly one machine')
            s, e = record['start'], record['end']
            require(s == raw[f's{j}'] and e == raw[f'e{j}'] and s >= 0 and
                    e - s == task['processing_time'] == record['processing_time_expected'], 'processing interval')
            intervals[selected[0]].append((s, e))
            late = max(0, e - task['due_date'])
            require(raw[f't{j}'] == late, 'per-task exact max tardiness')
            tardiness += late
        requirements = {r['machine_id']: r for r in data['maintenance']}
        maintenance = candidate['maintenance']
        require(len(maintenance) == len(requirements) == m and
                sorted(r['machine_id'] for r in maintenance) == list(range(m)), 'mandatory maintenance')
        for record in maintenance:
            i = record['machine_id']
            requirement = requirements[i]
            s, e = record['start'], record['end']
            require(s == raw[f'ms{i}'] and e == raw[f'me{i}'] and
                    requirement['window_start'] <= s < e <= requirement['window_end'] and
                    e - s == requirement['duration'] == record['duration_expected'], 'complete maintenance window')
            require(request['mode'] == 'joint' or s == requirement['fixed_start'], 'fixed maintenance start')
            intervals[i].append((s, e))
        for machine_intervals in intervals.values():
            ordered = sorted(machine_intervals)
            require(all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), 'no machine overlap')
        objective = observation['model']['objective']
        require(len(objective['vars']) == len(objective['coeffs']) == 24 and
                all(c == 1 for c in objective['coeffs']) and
                sorted(variables[i]['name'] for i in objective['vars']) == sorted(f't{j}' for j in tasks), 'objective terms')
        require(envelope(objective['offset']) == 0 and envelope(objective['scaling_factor']) == 1, 'objective affine transform')
        exact_objective = sum(c * variables[i]['value'] for i, c in zip(objective['vars'], objective['coeffs']))
        require(exact_objective == tardiness, 'integer objective equals independent tardiness')
        reported = envelope(observation['api']['objective'])
        bound = envelope(observation['api']['bound'])
        require(reported == envelope(observation['response']['objective']) and
                bound == envelope(observation['response']['bound']), 'raw/API objective/bound equality')
        require(0 <= bound <= tardiness < reported, 'precise observed disagreement')
        reports.append({'sequence': sequence, 'case_id': captured['case_id'], 'mode': captured['mode'],
                        'solver_status': 'FEASIBLE', 'reported_objective': reported,
                        'independent_tardiness': tardiness, 'raw_integer_objective': exact_objective,
                        'objective_delta': reported - tardiness, 'best_bound': bound,
                        'schedule_arithmetic': 'PASS', 'accepted_for_research': False})
    return {'status': 'FIVE_RAW_CANDIDATES_ARITHMETIC_VERIFIED', 'rows': reports,
            'native_batch_status': 'DEVELOPMENT_FAILED', 'original_formal_batch_status': 'FAILED',
            'new_solver_calls': 0, 'model_calls': 0, 'research_status': 'not_achieved',
            'limitation': 'Arithmetic audit does not validate the solver search ranking or prove the internal presolve trigger.'}


def recheck_archive(root):
    root = Path(root)
    index = read(root / 'archive_manifest.json')['files_sha256']
    actual = {p.relative_to(root).as_posix(): sha(p) for p in root.rglob('*')
              if p.is_file() and p.relative_to(root).as_posix() != 'archive_manifest.json'}
    require(index == actual, 'archive closure')
    result = audit(root)
    require(result == read(root / 'independent_candidate_check.json'), 'derived report changed')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recheck', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(recheck_archive(args.recheck), ensure_ascii=False))
