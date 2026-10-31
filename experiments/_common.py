"""Shared helpers for experiment scripts: paths, output, provenance, paired statistics."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / 'src') not in sys.path:
    sys.path.insert(0, str(ROOT / 'src'))

from fjsp_lab.maintenance import check_parallel_maintenance_feasibility  # noqa: E402


def parse_args(description: str, name: str, extra=None) -> argparse.Namespace:
    """Common CLI: ``--output-dir`` (default experiments/runs/<name>-<UTC stamp>)."""
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--output-dir', type=Path, default=None,
                        help='new directory for this run; use experiments/results/<name> to archive it')
    if extra is not None:
        extra(parser)
    args = parser.parse_args()
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        args.output_dir = ROOT / 'experiments' / 'runs' / f'{name}-{stamp}'
    args.output_dir.mkdir(parents=True, exist_ok=False)   # never overwrite earlier evidence
    return args


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with open(path, 'w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8')


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def provenance(script: str, packages=('numpy', 'scipy', 'ortools')) -> dict:
    """Code version, environment and hashes of every library source file plus the script."""
    def git(*args):
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=False).stdout.strip()

    sources = sorted((ROOT / 'src/fjsp_lab').rglob('*.py')) + [ROOT / 'experiments/_common.py', Path(script).resolve()]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'git_commit': git('rev-parse', 'HEAD'),
        'git_dirty': bool(git('status', '--porcelain', '--', 'src', 'experiments/_common.py', str(script))),
        'python': platform.python_version(), 'platform': platform.platform(), 'packages': versions,
        'source_sha256': {p.relative_to(ROOT).as_posix(): sha256(p) for p in sources},
    }


def checked_tardiness(result, data, mode: str) -> int:
    """Re-run the maintenance checker on a returned plan (defence in depth) and return T."""
    accepted, issues = check_parallel_maintenance_feasibility(result, data, mode=mode)
    if not accepted:
        raise ValueError(f'Checker rejected a returned plan: {issues}')
    return result.total_tardiness


def paired(rows: list[dict], method: str, baseline: str) -> dict:
    """Paired comparison (lower is better); Wilcoxon signed-rank on non-zero differences."""
    from scipy.stats import wilcoxon

    diffs = [float(row[method]) - float(row[baseline]) for row in rows]
    nonzero = [d for d in diffs if d != 0]
    base_mean = statistics.fmean(float(row[baseline]) for row in rows)
    return {'method': method, 'baseline': baseline, 'n': len(rows),
            'method_mean': statistics.fmean(float(row[method]) for row in rows), 'baseline_mean': base_mean,
            'mean_difference': statistics.fmean(diffs),
            'relative_difference': statistics.fmean(diffs) / base_mean if base_mean else None,
            'wins': sum(d < 0 for d in diffs), 'ties': sum(d == 0 for d in diffs), 'losses': sum(d > 0 for d in diffs),
            'wilcoxon_p_nonzero': float(wilcoxon(nonzero).pvalue) if len(nonzero) >= 10 else None}


def by_size(rows: list[dict]) -> dict[str, list[dict]]:
    groups = {'all': rows}
    for n, m in sorted({(int(r['num_tasks']), int(r['num_machines'])) for r in rows}):
        groups[f'n{n}-m{m}'] = [r for r in rows if (int(r['num_tasks']), int(r['num_machines'])) == (n, m)]
    return groups
