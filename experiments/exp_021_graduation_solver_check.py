"""Tiny fixed/joint maintenance solver validation, not a research comparison."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.graduation import (MaintenanceRequirement, ParallelMaintenanceInstance, ProductionTask,
    check_parallel_maintenance_feasibility, enumerate_parallel_maintenance, solve_parallel_maintenance)

CONFIG = {'time_limit': 10.0, 'num_workers': 1, 'seed': 42, 'max_states': 200000}


@dataclass(frozen=True)
class ValidationCase:
    name: str
    data: ParallelMaintenanceInstance
    expected: dict[str, int] | None = None


def build_cases():
    one = ParallelMaintenanceInstance(tuple(ProductionTask(j, 2, d) for j, d in enumerate((2, 4))), 1,
        (MaintenanceRequirement(0, 2, 0, 6, 0),))
    two = ParallelMaintenanceInstance(tuple(ProductionTask(j, 2, d) for j, d in enumerate((2, 2, 4))), 2,
        tuple(MaintenanceRequirement(m, 2, 0, 6, 0) for m in range(2)))
    idle = ParallelMaintenanceInstance((ProductionTask(0, 2, 2),), 2,
        tuple(MaintenanceRequirement(m, 2, 0, 2, 0) for m in range(2)))
    late = ParallelMaintenanceInstance((ProductionTask(0, 1, 1),), 1,
        (MaintenanceRequirement(0, 1, 3, 4, 3),))
    cases = [ValidationCase('one_machine', one, {'fixed': 4, 'joint': 0}),
             ValidationCase('two_machines', two, {'fixed': 6, 'joint': 0}),
             ValidationCase('idle_machine', idle, {'fixed': 2, 'joint': 2}),
             ValidationCase('late_maintenance', late, {'fixed': 0, 'joint': 0})]
    for index in range(8):
        rng = random.Random(20261025 + index)
        tasks = tuple(ProductionTask(j, rng.randint(1, 3), rng.randint(0, 9)) for j in range(1 + index % 3))
        requirements = []
        for machine in range(1 + index % 2):
            start, duration, slack = rng.randint(0, 3), rng.randint(1, 2), rng.randint(0, 2)
            requirements.append(MaintenanceRequirement(machine, duration, start, start + duration + slack,
                                                       start + rng.randint(0, slack)))
        cases.append(ValidationCase(f'tiny_seed_{20261025 + index}',
            ParallelMaintenanceInstance(tasks, len(requirements), tuple(requirements))))
    return cases


def _encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _snapshot(result):
    if result is None:
        return None
    try:
        fields = ('makespan', 'total_tardiness', 'solver_status', 'solver_objective_value',
                  'solver_objective_bound', 'solver_gap', 'solver_wall_time')
        value = {field: getattr(result, field) for field in fields}
        value.update(records=[asdict(record) for record in result.records],
                     maintenance_records=[asdict(record) for record in result.maintenance_records])
        _encoded(value)
        return value
    except Exception as exc:
        return {'diagnostic_error': f'{type(exc).__name__}: {str(exc)[:300]}', 'repr': repr(result)[:1000]}


def _report(manifest, rows):
    lines = ['<!-- fjsp-generated-report track=graduation -->', '# 毕设 G2 极小算例参考求解验证', '',
        f"状态：{manifest['status']}；核对通过 {manifest['passed_runs']}/{manifest['expected_runs']}。", '',
        '| 算例 | 模式 | 调度合法 | 求解状态 | 总延期 | 枚举最优延期 | 核对 |',
        '|---|---|---|---|---:|---:|---|']
    for row in rows:
        lines.append('| ' + ' | '.join(str(row[key]) if row[key] is not None else '' for key in
            ('case', 'mode', 'schedule_accepted', 'solver_status', 'total_tardiness',
             'reference_total_tardiness', 'validation_status')) + ' |')
    lines += ['', '## 数据与判定', '',
        '同一算例的两模式共享任务、交期、每机必需维护时长和完整窗口；固定模式另要求维护开始等于预设值。',
        '每条生产/维护计划独立过 G1 检查；枚举也重新检查。核对通过要求 CP-SAT 为 OPTIMAL 且总延期等于枚举最优值。',
        '合法 FEASIBLE 保留真实状态与合法指标，但不能作为已证最优的核对通过；非法调度的接受指标留空，诊断另存。',
        'raw.csv 保存原始目标值、下界、按总延期计算的 gap 和求解耗时；schedules/ 保存完整生产、维护及校验诊断。',
        '输入、配置和核对结果绑定确定性摘要；同值最优计划可不同，耗时和具体计划不要求跨运行或版本逐字节一致。',
        '四组手算/边界例加八组预定种子的极小实例只验证建模正确性；不用于统计性能排名、RL效果或最终课题验收。',
        'G3正式协议、工作流接入及大创生产—物流研究尚未完成。没有生成任何人工批准。', '', '## 失败诊断', '']
    lines.extend(f"- {row['case']}/{row['mode']}: {row['error']}" for row in rows if row['error'])
    return '\n'.join(lines) + '\n'


def run_experiment(output_dir: Path):
    cases = build_cases()
    if not cases or len({case.name for case in cases}) != len(cases):
        raise ValueError('Validation cases must be nonempty and uniquely named')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / 'inputs').mkdir()
    (output_dir / 'schedules').mkdir()
    rows, input_hashes = [], {}
    for case in cases:
        source = _encoded({'data': asdict(case.data), 'expected': case.expected})
        (output_dir / 'inputs' / f'{case.name}.json').write_bytes(source)
        input_hashes[case.name] = _sha(source)
        fixed_row = None
        for mode in ('fixed', 'joint'):
            candidate = reference = None
            accepted = reference_accepted = passed = False
            issues, error = [], ''
            try:
                candidate = solve_parallel_maintenance(case.data, mode=mode,
                    **{key: CONFIG[key] for key in ('time_limit', 'num_workers', 'seed')})
                accepted, problems = check_parallel_maintenance_feasibility(candidate, case.data, mode=mode)
                issues = [asdict(problem) for problem in problems]
                if not accepted:
                    raise ValueError(f'CP-SAT schedule rejected: {issues}')
                reference = enumerate_parallel_maintenance(case.data, mode=mode, max_states=CONFIG['max_states'])
                reference_accepted, problems = check_parallel_maintenance_feasibility(reference, case.data, mode=mode)
                if not reference_accepted:
                    raise ValueError(f'Enumeration schedule rejected: {problems}')
                if candidate.solver_status != 'OPTIMAL' or reference.solver_status != 'OPTIMAL':
                    raise ValueError('Tiny reference validation requires proven OPTIMAL status')
                if candidate.total_tardiness != reference.total_tardiness:
                    raise ValueError('Solver and independent enumeration objective mismatch')
                if case.expected is not None and candidate.total_tardiness != case.expected[mode]:
                    raise ValueError('Computed objective disagrees with the literal hand-derived value')
                if (mode == 'joint' and fixed_row['validation_status'] == 'PASS'
                        and candidate.total_tardiness > fixed_row['total_tardiness']):
                    raise ValueError('Proven joint optimum exceeds proven fixed optimum')
                passed = True
            except Exception as exc:
                error = f'{type(exc).__name__}: {str(exc)[:1000]}'
            row = {'case': case.name, 'mode': mode, 'validation_status': 'PASS' if passed else 'FAIL',
                   'schedule_accepted': accepted, 'solver_status': getattr(candidate, 'solver_status', None),
                   'total_tardiness': candidate.total_tardiness if accepted else None,
                   'reference_total_tardiness': reference.total_tardiness if reference_accepted else None,
                   'makespan': candidate.makespan if accepted else None,
                   'solver_objective_value': candidate.solver_objective_value if accepted else None,
                   'solver_objective_bound': candidate.solver_objective_bound if accepted else None,
                   'solver_gap': candidate.solver_gap if accepted else None,
                   'solver_wall_time': candidate.solver_wall_time if accepted else None, 'error': error}
            trace = {'candidate': _snapshot(candidate), 'reference': _snapshot(reference),
                     'schedule_accepted': accepted, 'reference_accepted': reference_accepted,
                     'validation_passed': passed, 'issues': issues, 'error': error}
            (output_dir / 'schedules' / f'{case.name}-{mode}.json').write_bytes(_encoded(trace))
            rows.append(row)
            if mode == 'fixed': fixed_row = row
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    (output_dir / 'raw.csv').write_bytes(stream.getvalue().encode('utf-8'))
    keys = ('case', 'mode', 'validation_status', 'schedule_accepted', 'solver_status',
            'total_tardiness', 'reference_total_tardiness', 'error')
    outcome = {'inputs': input_hashes, 'config': CONFIG, 'rows': [{key: row[key] for key in keys} for row in rows]}
    paths = [*sorted((ROOT / 'src').rglob('*.py')), Path(__file__).resolve(), ROOT / 'pyproject.toml']
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()
    passed_count = sum(row['validation_status'] == 'PASS' for row in rows)
    manifest = {'version': 1, 'purpose': 'graduation_g2_tiny_validation',
        'status': 'COMPLETED' if passed_count == len(rows) else 'FAILED',
        'expected_runs': len(rows), 'passed_runs': passed_count, 'config': CONFIG, 'input_hashes': input_hashes,
        'outcome_digest': _sha(_encoded(outcome)), 'runtime': {'git_head': revision, 'python': sys.version,
            'platform': platform.platform(), 'packages': {'ortools': importlib.metadata.version('ortools')},
            'source_hashes': {path.relative_to(ROOT).as_posix(): _sha(path.read_bytes()) for path in paths}}}
    (output_dir / 'report.md').write_bytes(_report(manifest, rows).encode('utf-8'))
    manifest['artifacts'] = {path.relative_to(output_dir).as_posix(): _sha(path.read_bytes())
        for path in sorted(output_dir.rglob('*')) if path.is_file() and path.name != 'manifest.json'}
    (output_dir / 'manifest.json').write_bytes(_encoded(manifest))
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output = args.output_dir or ROOT / 'experiments/runs/graduation_g2' / stamp
    try:
        result = run_experiment(output)
    except (ValueError, OSError) as exc:
        print(f'Graduation validation stopped: {exc}')
        return 1
    print(f"{result['status']}: {result['passed_runs']}/{result['expected_runs']}; {output / 'report.md'}")
    print(f"Outcome digest: {result['outcome_digest']}")
    return 0 if result['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
