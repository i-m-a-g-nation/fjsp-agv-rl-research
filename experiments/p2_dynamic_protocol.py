"""Phase 2A: run the fixed dynamic-rescheduling protocol (experiments/inputs/phase2a_v1.json).

For every instance x event type x seed, one perturbation of the FIFO
initial schedule is built (fjsp_lab.dynamic.perturbation) and rescheduled by
each rule, ``timing_repetitions`` times. A run passes only if both the
static and the dynamic checker accept it; repeated runs must give the same
schedule. Writes rows.csv (one row per run), groups.csv and manifest.json.
Seeds and repetitions are not independent statistical samples.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
import statistics
import time

from _common import ROOT, parse_args, provenance, sha256, write_csv, write_json

from fjsp_lab.dynamic import check_dynamic_feasibility, reschedule_from_state
from fjsp_lab.dynamic.perturbation import build_case, parse_protocol
from fjsp_lab.fjsp import check_feasibility, load_project_benchmark_file

LOGGER = logging.getLogger(__name__)


def schedule_hash(result) -> str:
    records = sorted((r.job_id, r.op_id, r.machine_id, r.start, r.end) for r in result.records)
    return hashlib.sha256(json.dumps(records).encode('utf-8')).hexdigest()


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'p2_dynamic_protocol',
                      lambda p: p.add_argument('--protocol', type=Path, default=ROOT / 'experiments/inputs/phase2a_v1.json'))
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)   # recorded at start: the code that actually runs
    protocol = parse_protocol(args.protocol.read_bytes())
    rows = []
    for instance_id, path in protocol.instances:
        instance = load_project_benchmark_file(ROOT / path)
        for event_type in protocol.event_types:
            for seed in protocol.seeds:
                case = build_case(instance, event_type, seed)
                for rule in protocol.rules:
                    for repeat in range(protocol.timing_repetitions):
                        started = time.perf_counter()
                        result = reschedule_from_state(case.state, case.frozen, rule=rule)
                        seconds = time.perf_counter() - started
                        static_ok, static_issues = check_feasibility(result, expected_instance=case.state.instance)
                        dynamic_ok, dynamic_issues = check_dynamic_feasibility(result, case.state, case.frozen)
                        rows.append({'case_id': f'{instance_id}-{event_type}-{seed}', 'instance': instance_id,
                                     'event_type': event_type, 'seed': seed, 'event': json.dumps(case.event_spec),
                                     'rule': rule, 'repeat': repeat, 'initial_makespan': case.initial.makespan,
                                     'frozen_operations': len(case.frozen), 'feasible': static_ok and dynamic_ok,
                                     'makespan': result.makespan, 'seconds': round(seconds, 6),
                                     'schedule_sha256': schedule_hash(result),
                                     'issues': '' if static_ok and dynamic_ok else f'{static_issues} {dynamic_issues}'})
        LOGGER.info('%s done', instance_id)
    groups = []
    for key in dict.fromkeys((r['case_id'], r['rule']) for r in rows):
        members = [r for r in rows if (r['case_id'], r['rule']) == key]
        groups.append({'case_id': key[0], 'rule': key[1], 'runs': len(members),
                       'passed': sum(r['feasible'] for r in members),
                       'reproducible': len({r['schedule_sha256'] for r in members}) == 1,
                       'makespan': members[0]['makespan'],
                       'median_seconds': statistics.median(r['seconds'] for r in members)})
    write_csv(args.output_dir / 'rows.csv', rows)
    write_csv(args.output_dir / 'groups.csv', groups)
    passed = sum(r['feasible'] for r in rows)
    complete = passed == protocol.expected_runs == len(rows) and all(g['reproducible'] for g in groups)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'p2_dynamic_protocol', 'protocol_id': protocol.protocol_id,
        'protocol_sha256': sha256(args.protocol), 'expected_runs': protocol.expected_runs, 'passed_runs': passed,
        'status': 'COMPLETED' if complete else 'FAILED', **prov})
    LOGGER.info('%d/%d runs passed both checkers', passed, protocol.expected_runs)
    return 0 if complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
