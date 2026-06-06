"""
exp_013_cpsat_report.py

Phase 1 CP-SAT report builder:
- Read the exp_009 worker-matrix aggregate CSV
- Summarize feasibility, status, best makespan, lower bound, gap, and runtime
- Write a compact Markdown report for README/LaTeX-friendly interpretation

The script does not run the solver. It turns already feasibility-checked CSV
results into a stable report artifact.
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.exp_011_heuristic_quality_report import (
    BenchmarkReference,
    load_benchmark_references,
)


@dataclass(frozen=True)
class CpSatAggregateRow:
    """One exp_009 per-instance, per-worker aggregate row."""

    instance_name: str
    workers: str
    repeats: int
    feasible_runs: int
    best_makespan: int
    mean_makespan: float
    best_bound: float
    best_gap: float
    mean_gap: float
    mean_runtime_s: float
    statuses: str

    @property
    def proved_optimal(self) -> bool:
        """Return True when every repeated run reported OPTIMAL."""

        return self.statuses == f"OPTIMAL:{self.repeats}"


@dataclass(frozen=True)
class CpSatWorkerSummary:
    """Cross-instance summary for one CP-SAT worker configuration."""

    workers: str
    instances: int
    feasible_rows: int
    proved_optimal_rows: int
    mean_best_makespan: float
    mean_best_bound: float
    mean_best_gap: float
    mean_runtime_s: float


def _required_fields() -> set[str]:
    return {
        "instance_name",
        "workers",
        "repeats",
        "feasible_runs",
        "best_makespan",
        "mean_makespan",
        "best_bound",
        "best_gap",
        "mean_gap",
        "mean_runtime_s",
        "statuses",
    }


def load_cpsat_aggregates(path: str | Path) -> list[CpSatAggregateRow]:
    """Load and validate exp_009 aggregate rows from a UTF-8 CSV file."""

    rows: list[CpSatAggregateRow] = []
    seen: set[tuple[str, str]] = set()
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or not _required_fields().issubset(reader.fieldnames):
            raise ValueError("CP-SAT summary CSV is missing required fields")
        for raw in reader:
            key = (raw["instance_name"], raw["workers"])
            if key in seen:
                raise ValueError(f"duplicate CP-SAT summary row: {key[0]} / {key[1]}")
            seen.add(key)
            repeats = int(raw["repeats"])
            feasible_runs = int(raw["feasible_runs"])
            if repeats <= 0:
                raise ValueError(f"repeats must be positive: {key[0]} / {key[1]}")
            if feasible_runs < 0 or feasible_runs > repeats:
                raise ValueError(f"invalid feasible_runs: {key[0]} / {key[1]}")
            rows.append(
                CpSatAggregateRow(
                    instance_name=raw["instance_name"],
                    workers=raw["workers"],
                    repeats=repeats,
                    feasible_runs=feasible_runs,
                    best_makespan=int(raw["best_makespan"]),
                    mean_makespan=float(raw["mean_makespan"]),
                    best_bound=float(raw["best_bound"]),
                    best_gap=float(raw["best_gap"]),
                    mean_gap=float(raw["mean_gap"]),
                    mean_runtime_s=float(raw["mean_runtime_s"]),
                    statuses=raw["statuses"],
                )
            )
    if not rows:
        raise ValueError("CP-SAT summary CSV must contain at least one row")
    return rows


def summarize_by_worker(rows: Sequence[CpSatAggregateRow]) -> list[CpSatWorkerSummary]:
    """Aggregate CP-SAT result quality by worker configuration."""

    grouped: dict[str, list[CpSatAggregateRow]] = {}
    for row in rows:
        grouped.setdefault(row.workers, []).append(row)

    return [
        CpSatWorkerSummary(
            workers=workers,
            instances=len(group),
            feasible_rows=sum(1 for row in group if row.feasible_runs == row.repeats),
            proved_optimal_rows=sum(1 for row in group if row.proved_optimal),
            mean_best_makespan=statistics.mean(row.best_makespan for row in group),
            mean_best_bound=statistics.mean(row.best_bound for row in group),
            mean_best_gap=statistics.mean(row.best_gap for row in group),
            mean_runtime_s=statistics.mean(row.mean_runtime_s for row in group),
        )
        for workers, group in grouped.items()
    ]


def best_row_per_instance(rows: Sequence[CpSatAggregateRow]) -> list[CpSatAggregateRow]:
    """Select the best worker row for every instance by makespan then gap."""

    best: dict[str, CpSatAggregateRow] = {}
    for row in rows:
        current = best.get(row.instance_name)
        if current is None:
            best[row.instance_name] = row
            continue
        row_key = (row.best_makespan, row.best_gap, row.mean_runtime_s, row.workers)
        current_key = (
            current.best_makespan,
            current.best_gap,
            current.mean_runtime_s,
            current.workers,
        )
        if row_key < current_key:
            best[row.instance_name] = row
    return [best[name] for name in sorted(best)]


def validate_reference_coverage(
    rows: Sequence[CpSatAggregateRow],
    references: dict[str, BenchmarkReference],
) -> None:
    """Ensure the report can compare every CP-SAT instance to FJSPLib bounds."""

    instance_names = {row.instance_name for row in rows}
    missing_refs = sorted(instance_names - set(references))
    missing_rows = sorted(set(references) - instance_names)
    if missing_refs:
        raise ValueError(
            "missing BKS reference for CP-SAT instances: " + ", ".join(missing_refs)
        )
    if missing_rows:
        raise ValueError(
            "CP-SAT summary missing BKS instances: " + ", ".join(missing_rows)
        )


def _markdown_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """Build a simple GitHub-flavored Markdown table."""

    output = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    output.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(output)


def build_markdown_report(
    rows: Sequence[CpSatAggregateRow],
    references: dict[str, BenchmarkReference] | None = None,
) -> str:
    """Build a compact CP-SAT interpretation report."""

    if references is not None:
        validate_reference_coverage(rows, references)
    worker_summaries = summarize_by_worker(rows)
    best_rows = best_row_per_instance(rows)
    total_instances = len(best_rows)
    total_rows = len(rows)
    all_feasible = sum(1 for row in rows if row.feasible_runs == row.repeats)
    best_optimal = sum(1 for row in best_rows if row.proved_optimal)
    reached_bks = 0
    reached_bks_without_proof = 0
    if references is not None:
        reached_bks = sum(
            1 for row in best_rows
            if row.best_makespan <= references[row.instance_name].upper_bound
        )
        reached_bks_without_proof = sum(
            1 for row in best_rows
            if (
                row.best_makespan <= references[row.instance_name].upper_bound
                and not row.proved_optimal
            )
        )

    summary_table = _markdown_table(
        [
            "workers",
            "instances",
            "feasible rows",
            "proved optimal rows",
            "mean best makespan",
            "mean best bound",
            "mean best gap",
            "mean runtime s",
        ],
        (
            [
                row.workers,
                str(row.instances),
                str(row.feasible_rows),
                str(row.proved_optimal_rows),
                f"{row.mean_best_makespan:.3f}",
                f"{row.mean_best_bound:.3f}",
                f"{row.mean_best_gap:.6f}",
                f"{row.mean_runtime_s:.6f}",
            ]
            for row in worker_summaries
        ),
    )
    best_table = _markdown_table(
        [
            "instance",
            "best workers",
            "best makespan",
            "FJSPLib LB",
            "FJSPLib UB",
            "BKS gap",
            "reaches UB",
            "local proof",
            "best bound",
            "best gap",
            "statuses",
        ],
        (
            _best_row_to_markdown(row, references)
            for row in best_rows
        ),
    )

    return "\n\n".join(
        [
            "# CP-SAT Benchmark Report",
            (
                f"This report summarizes {total_rows} aggregate rows over "
                f"{total_instances} tracked FJSPLib instances. All values are "
                "derived from exp_009 CSV outputs whose schedules passed the "
                "independent feasibility checker."
            ),
            (
                f"Fully feasible aggregate rows: {all_feasible}/{total_rows}. "
                f"Best worker rows with all repeated runs proved OPTIMAL: "
                f"{best_optimal}/{total_instances}."
            ),
            (
                "Best worker rows reaching the upstream FJSPLib upper bound: "
                f"{reached_bks}/{total_instances}. Rows reaching UB without a "
                f"local optimality proof: {reached_bks_without_proof}/{total_instances}."
                if references is not None
                else "No FJSPLib reference file was supplied for BKS comparison."
            ),
            "## Worker Summary",
            summary_table,
            "## Best Row Per Instance",
            best_table,
            (
                "Interpretation note: `FEASIBLE` rows are valid schedules, but "
                "their objective bounds and gaps show that the local time limit "
                "did not prove optimality. Matching an upstream BKS is therefore "
                "reported as a good feasible solution unless the local status is "
                "`OPTIMAL`."
            ),
            "",
        ]
    )


def _best_row_to_markdown(
    row: CpSatAggregateRow,
    references: dict[str, BenchmarkReference] | None,
) -> list[str]:
    """Convert a best-row entry to report columns, optionally with BKS fields."""

    if references is None:
        lower_bound = ""
        upper_bound = ""
        bks_gap = ""
        reaches_bks = ""
    else:
        reference = references[row.instance_name]
        lower_bound = str(reference.lower_bound)
        upper_bound = str(reference.upper_bound)
        bks_gap = f"{((row.best_makespan - reference.upper_bound) / reference.upper_bound):.6f}"
        reaches_bks = "yes" if row.best_makespan <= reference.upper_bound else "no"

    return [
        row.instance_name,
        row.workers,
        str(row.best_makespan),
        lower_bound,
        upper_bound,
        bks_gap,
        reaches_bks,
        "yes" if row.proved_optimal else "no",
        f"{row.best_bound:.6f}",
        f"{row.best_gap:.6f}",
        row.statuses,
    ]


def write_markdown_report(path: str | Path, text: str) -> None:
    """Write a Markdown report using UTF-8 encoding."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the report builder."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-input",
        type=Path,
        default=root / "experiments" / "results" / "exp_009_cpsat_benchmark_matrix_summary.csv",
        help="Input exp_009 aggregate CSV",
    )
    parser.add_argument(
        "--bks-input",
        type=Path,
        default=root / "instances" / "fjsplib_bks.csv",
        help="Input FJSPLib lower/upper-bound CSV for report comparison",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=root / "experiments" / "results" / "exp_013_cpsat_report.md",
        help="Output Markdown report",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build the CP-SAT Markdown report and return a process exit code."""

    args = parse_args(argv)
    try:
        rows = load_cpsat_aggregates(args.summary_input)
        references = load_benchmark_references(args.bks_input)
        report = build_markdown_report(rows, references)
        write_markdown_report(args.output, report)
    except Exception as exc:
        print(f"Report error: {exc}")
        return 2

    print(f"CP-SAT report written to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
