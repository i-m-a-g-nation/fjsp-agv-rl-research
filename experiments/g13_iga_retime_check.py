"""Graduation G5: spot re-timing of IGA on an idle machine (checks the G4/G5 search timings).

Samples instances whose recorded IGA run used the full 10 s (G5 and G4, n = 100
and n = 20), reruns IGA exactly as g7_g4_search_curves.run_instance does (seed 0,
10 s, 2 processes) and compares with the record:
* decodes in 10 s, new / recorded;
* speed ratio: with a fixed seed IGA follows the same path whatever its stopping
  point, so an improvement recorded at the same (decodes, value) in both runs
  gives recorded seconds / new seconds; the last common point with more than
  1000 decodes is used. Above 1 means the recorded run was faster than now.
Writes rows.jsonl, summary.json and manifest.json.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
import json
import logging
import statistics
import time
from pathlib import Path

from _common import parse_args, provenance, write_json
from fjsp_lab.maintenance.generator import grid_cases
from g7_g4_search_curves import run_instance

LOGGER = logging.getLogger(__name__)
RESULTS = Path(__file__).resolve().parent / 'results'
SAMPLES = (('g5', 'g5_search_curves', 100, 12), ('g4', 'g4_search_curves_retimed', 100, 12),
           ('g5', 'g5_search_curves', 20, 6), ('g4', 'g4_search_curves_retimed', 20, 6))
MIN_DECODES = 1000


def sample(grid: str, record_dir: str, n: int, count: int) -> list[tuple]:
    """Every k-th instance (sorted by case and mode) of size n whose recorded IGA did not stop early at 0."""
    with open(RESULTS / record_dir / 'rows.jsonl', encoding='utf-8') as handle:
        record = {(row['case_id'], row['mode']): row for row in map(json.loads, handle)}
    keys = sorted(key for key, row in record.items() if row['num_tasks'] == n and row['IGA']['value'] > 0)
    chosen = keys[::max(1, len(keys) // count)][:count]
    cases = {case.case_id: case for case in grid_cases(grid)}
    return [((cases[case_id], mode, 60.0, ('IGA',)), record[case_id, mode], grid, record_dir)
            for case_id, mode in chosen]


def speed_ratio(old_trace: list, new_trace: list) -> tuple[float | None, int]:
    old = {(decodes, value): seconds for seconds, decodes, value in old_trace}
    common = [(old[decodes, value], seconds) for seconds, decodes, value in new_trace
              if (decodes, value) in old and decodes > MIN_DECODES]
    return (common[-1][0] / common[-1][1] if common else None), len(common)


def main() -> int:
    args = parse_args(__doc__.splitlines()[0], 'g13_iga_retime_check')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prov = provenance(__file__)
    plan = [item for spec in SAMPLES for item in sample(*spec)]
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=2) as pool:
        new_rows = list(pool.map(run_instance, [job for job, *_ in plan]))
    rows = []
    for (_, old, grid, record_dir), new in zip(plan, new_rows):
        ratio, common = speed_ratio(old['IGA']['trace'], new['IGA']['trace'])
        rows.append({'grid': grid, 'record': record_dir, 'case_id': old['case_id'], 'mode': old['mode'],
                     'num_tasks': old['num_tasks'], 'num_machines': old['num_machines'],
                     'decodes_recorded': old['IGA']['decodes'], 'decodes_new': new['IGA']['decodes'],
                     'decode_ratio_new_over_recorded': new['IGA']['decodes'] / old['IGA']['decodes'],
                     'speed_ratio_recorded_over_new': ratio, 'common_points': common,
                     'value_recorded': old['IGA']['value'], 'value_new': new['IGA']['value']})
    with open(args.output_dir / 'rows.jsonl', 'w', encoding='utf-8', newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(',', ':')) + '\n')
    summary = []
    for grid, record_dir, n, _ in SAMPLES:
        group = [r for r in rows if r['grid'] == grid and r['num_tasks'] == n]
        speeds = sorted(r['speed_ratio_recorded_over_new'] for r in group
                        if r['speed_ratio_recorded_over_new'] is not None)
        decode = [r['decode_ratio_new_over_recorded'] for r in group]
        summary.append({'grid': grid, 'record': record_dir, 'num_tasks': n, 'runs': len(group),
                        'speed_ratio_median': statistics.median(speeds) if speeds else None,
                        'speed_ratios': [round(s, 3) for s in speeds],
                        'decode_ratio_median': statistics.median(decode),
                        'new_decodes_per_second_median': statistics.median(r['decodes_new'] / 10 for r in group)})
        LOGGER.info('%s n=%d: speed ratio median %s over %d runs', grid, n, summary[-1]['speed_ratio_median'],
                    len(speeds))
    write_json(args.output_dir / 'summary.json', summary)
    write_json(args.output_dir / 'manifest.json', {
        'experiment': 'g13_iga_retime_check', 'samples': SAMPLES, 'min_decodes': MIN_DECODES,
        'search_seconds': 10.0, 'seed': 0, 'parallel_processes': 2, 'instances': len(rows),
        'elapsed_minutes_this_session': round((time.monotonic() - started) / 60, 1), **prov})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
