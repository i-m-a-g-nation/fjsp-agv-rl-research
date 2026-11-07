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


def parse_args(description: str, name: str, extra=None, resumable: bool = False) -> argparse.Namespace:
    """Common CLI: ``--output-dir`` (default experiments/runs/<name>-<UTC stamp>).

    A resumable script also accepts ``--resume`` to continue an interrupted run
    in an existing directory; it must then skip the work already written.
    """
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--output-dir', type=Path, default=None,
                        help='new directory for this run; use experiments/results/<name> to archive it')
    if resumable:
        parser.add_argument('--resume', action='store_true', help='continue an interrupted run in --output-dir')
    if extra is not None:
        extra(parser)
    args = parser.parse_args()
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        args.output_dir = ROOT / 'experiments' / 'runs' / f'{name}-{stamp}'
    # Never overwrite earlier evidence; only an explicit resume may reuse a directory.
    args.output_dir.mkdir(parents=True, exist_ok=resumable and args.resume)
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

    script = Path(script).resolve()
    # Experiment modules the script imported (e.g. g12 reuses g9) change its results too.
    imported = {Path(module.__file__).resolve() for module in list(sys.modules.values())
                if getattr(module, '__file__', None) and Path(module.__file__).resolve().parent == ROOT / 'experiments'}
    sources = sorted((ROOT / 'src/fjsp_lab').rglob('*.py')) + [ROOT / 'experiments/_common.py', script]
    sources += sorted(imported - set(sources))
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'git_commit': git('rev-parse', 'HEAD'),
        'git_dirty': bool(git('status', '--porcelain', '--', 'src', 'experiments/_common.py',
                              *(str(p) for p in sources if p.parent == ROOT / 'experiments'))),
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


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order."""
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted, running = [0.0] * len(p_values), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def cluster_sign_flip(diffs_by_cluster: dict, alternative: str = 'less') -> dict:
    """Exact sign-flip permutation test on cluster means of paired differences (method - other).

    Each cluster counts once, whatever its size: the statistic is the mean of the
    cluster means, and under the null every cluster mean is equally likely to have
    either sign. With k clusters the smallest attainable p-value is 2**-k.
    """
    from itertools import product

    if alternative not in ('less', 'greater'):
        raise ValueError("alternative must be 'less' or 'greater'")
    means = {key: statistics.fmean(d) for key, d in diffs_by_cluster.items() if d}
    if not means:
        raise ValueError('No cluster has a paired difference')
    values = list(means.values())
    observed = statistics.fmean(values)
    tolerance = 1e-12 * max(1.0, max(abs(v) for v in values))
    extreme = 0
    for signs in product((1, -1), repeat=len(values)):
        stat = statistics.fmean(s * v for s, v in zip(signs, values))
        extreme += stat <= observed + tolerance if alternative == 'less' else stat >= observed - tolerance
    favouring = sum((v < 0) if alternative == 'less' else (v > 0) for v in values)
    against = sum((v > 0) if alternative == 'less' else (v < 0) for v in values)
    return {'clusters': len(values), 'cluster_means': means, 'clusters_favouring': favouring,
            'clusters_against': against, 'p_cluster': extreme / 2 ** len(values), 'p_cluster_min': 2.0 ** -len(values)}


def by_size(rows: list[dict]) -> dict[str, list[dict]]:
    groups = {'all': rows}
    for n, m in sorted({(int(r['num_tasks']), int(r['num_machines'])) for r in rows}):
        groups[f'n{n}-m{m}'] = [r for r in rows if (int(r['num_tasks']), int(r['num_machines'])) == (n, m)]
    return groups
