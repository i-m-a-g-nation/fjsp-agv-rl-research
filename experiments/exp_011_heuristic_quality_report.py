"""
exp_011_heuristic_quality_report.py

Phase 1 BKS-aware heuristic quality report:
- Load structured upstream FJSPLib lower and upper bounds for tracked instances
- Load the audited exp_010 per-instance heuristic-family summary
- Compute relative quality ratios against the upstream BKS upper bound
- Write per-instance quality rows and cross-instance family aggregates
"""
from __future__ import annotations

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True)
class BenchmarkReference:
    """Structured upstream reference bounds for one tracked FJSPLib file."""

    instance_name: str
    lower_bound: int
    upper_bound: int


@dataclass(frozen=True)
class HeuristicQuality:
    """BKS-relative quality metrics for one algorithm family and instance."""

    instance_name: str
    family: str
    variants: str
    feasible_runs: int
    reference: BenchmarkReference
    best_makespan: int
    best_gap_ratio: float
    mean_makespan: float
    mean_gap_ratio: float
    stdev_makespan: float
    worst_makespan: int
    worst_gap_ratio: float
    statuses: str

    def to_csv_row(self) -> dict[str, str]:
        """Convert quality metrics to stable CSV text values."""

        return {
            "instance_name": self.instance_name,
            "algorithm_family": self.family,
            "variants": self.variants,
            "feasible_runs": str(self.feasible_runs),
            "fjsplib_lb": str(self.reference.lower_bound),
            "fjsplib_bks": str(self.reference.upper_bound),
            "best_makespan": str(self.best_makespan),
            "best_gap_ratio": f"{self.best_gap_ratio:.6f}",
            "mean_makespan": f"{self.mean_makespan:.6f}",
            "mean_gap_ratio": f"{self.mean_gap_ratio:.6f}",
            "stdev_makespan": f"{self.stdev_makespan:.6f}",
            "worst_makespan": str(self.worst_makespan),
            "worst_gap_ratio": f"{self.worst_gap_ratio:.6f}",
            "statuses": self.statuses,
        }


@dataclass(frozen=True)
class FamilyQuality:
    """Cross-instance summary for one heuristic family."""

    family: str
    instances: int
    mean_best_gap_ratio: float
    max_best_gap_ratio: float
    mean_mean_gap_ratio: float
    max_mean_gap_ratio: float

    def to_csv_row(self) -> dict[str, str]:
        """Convert family quality metrics to stable CSV text values."""

        return {
            "algorithm_family": self.family,
            "instances": str(self.instances),
            "mean_best_gap_ratio": f"{self.mean_best_gap_ratio:.6f}",
            "max_best_gap_ratio": f"{self.max_best_gap_ratio:.6f}",
            "mean_mean_gap_ratio": f"{self.mean_mean_gap_ratio:.6f}",
            "max_mean_gap_ratio": f"{self.max_mean_gap_ratio:.6f}",
        }


def relative_gap(makespan: float, bks: int) -> float:
    """Return a non-negative BKS-relative makespan gap."""

    if bks <= 0:
        raise ValueError("BKS must be positive")
    if makespan < bks:
        raise ValueError(f"makespan {makespan:g} is below upstream BKS {bks}")
    return (makespan - bks) / bks


def load_benchmark_references(path: str | Path) -> dict[str, BenchmarkReference]:
    """Load distinct positive upstream FJSPLib bounds from a UTF-8 CSV file."""

    references: dict[str, BenchmarkReference] = {}
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"instance_name", "fjsplib_lb", "fjsplib_ub"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("BKS CSV must contain instance_name, fjsplib_lb, and fjsplib_ub")
        for row in reader:
            instance_name = row["instance_name"].strip()
            if not instance_name:
                raise ValueError("BKS CSV contains an empty instance_name")
            if instance_name in references:
                raise ValueError(f"duplicate BKS instance: {instance_name}")
            lower_bound = int(row["fjsplib_lb"])
            upper_bound = int(row["fjsplib_ub"])
            if lower_bound <= 0 or upper_bound <= 0:
                raise ValueError(f"BKS bounds must be positive: {instance_name}")
            if lower_bound > upper_bound:
                raise ValueError(f"BKS lower bound exceeds upper bound: {instance_name}")
            references[instance_name] = BenchmarkReference(
                instance_name=instance_name,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            )
    if not references:
        raise ValueError("BKS CSV must contain at least one instance")
    return references


def build_quality_rows(
    summary_path: str | Path,
    references: dict[str, BenchmarkReference],
) -> list[HeuristicQuality]:
    """Compute per-instance quality rows from the exp_010 summary CSV."""

    quality_rows = []
    with Path(summary_path).open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {
            "instance_name",
            "algorithm_family",
            "variants",
            "feasible_runs",
            "best_makespan",
            "mean_makespan",
            "stdev_makespan",
            "worst_makespan",
            "statuses",
        }
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("heuristic summary CSV is missing required fields")
        seen: set[tuple[str, str]] = set()
        for row in reader:
            instance_name = row["instance_name"]
            family = row["algorithm_family"]
            key = (instance_name, family)
            if key in seen:
                raise ValueError(f"duplicate heuristic summary row: {instance_name} / {family}")
            seen.add(key)
            if instance_name not in references:
                raise ValueError(f"missing BKS reference for instance: {instance_name}")
            reference = references[instance_name]
            best_makespan = int(row["best_makespan"])
            mean_makespan = float(row["mean_makespan"])
            worst_makespan = int(row["worst_makespan"])
            quality_rows.append(
                HeuristicQuality(
                    instance_name=instance_name,
                    family=family,
                    variants=row["variants"],
                    feasible_runs=int(row["feasible_runs"]),
                    reference=reference,
                    best_makespan=best_makespan,
                    best_gap_ratio=relative_gap(best_makespan, reference.upper_bound),
                    mean_makespan=mean_makespan,
                    mean_gap_ratio=relative_gap(mean_makespan, reference.upper_bound),
                    stdev_makespan=float(row["stdev_makespan"]),
                    worst_makespan=worst_makespan,
                    worst_gap_ratio=relative_gap(worst_makespan, reference.upper_bound),
                    statuses=row["statuses"],
                )
            )
    if not quality_rows:
        raise ValueError("heuristic summary CSV must contain at least one row")
    summarized_instances = {row.instance_name for row in quality_rows}
    missing_instances = sorted(set(references) - summarized_instances)
    if missing_instances:
        raise ValueError(
            "heuristic summary missing BKS instances: " + ", ".join(missing_instances)
        )
    return quality_rows


def aggregate_family_quality(rows: Sequence[HeuristicQuality]) -> list[FamilyQuality]:
    """Aggregate BKS-relative quality metrics by algorithm family."""

    grouped: dict[str, list[HeuristicQuality]] = {}
    for row in rows:
        grouped.setdefault(row.family, []).append(row)
    return [
        FamilyQuality(
            family=family,
            instances=len(group),
            mean_best_gap_ratio=statistics.mean(row.best_gap_ratio for row in group),
            max_best_gap_ratio=max(row.best_gap_ratio for row in group),
            mean_mean_gap_ratio=statistics.mean(row.mean_gap_ratio for row in group),
            max_mean_gap_ratio=max(row.mean_gap_ratio for row in group),
        )
        for family, group in grouped.items()
    ]


def write_quality_rows_csv(path: str | Path, rows: Sequence[HeuristicQuality]) -> None:
    """Write per-instance BKS-relative quality rows to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "instance_name",
        "algorithm_family",
        "variants",
        "feasible_runs",
        "fjsplib_lb",
        "fjsplib_bks",
        "best_makespan",
        "best_gap_ratio",
        "mean_makespan",
        "mean_gap_ratio",
        "stdev_makespan",
        "worst_makespan",
        "worst_gap_ratio",
        "statuses",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def write_family_quality_csv(path: str | Path, rows: Sequence[FamilyQuality]) -> None:
    """Write cross-instance heuristic-family quality summaries."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "algorithm_family",
        "instances",
        "mean_best_gap_ratio",
        "max_best_gap_ratio",
        "mean_mean_gap_ratio",
        "max_mean_gap_ratio",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def print_family_quality(rows: Sequence[FamilyQuality]) -> None:
    """Print a compact cross-instance quality table."""

    header = (
        f"{'Algorithm family':20s} {'instances':>9s} "
        f"{'mean_best_gap':>14s} {'max_best_gap':>13s}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.family:20s} {row.instances:>9d} "
            f"{row.mean_best_gap_ratio:>14.6f} {row.max_best_gap_ratio:>13.6f}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the BKS-aware heuristic quality report."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summary-input",
        type=Path,
        default=(
            root
            / "experiments"
            / "results"
            / "exp_010_heuristic_benchmark_matrix_summary.csv"
        ),
        help="Tracked exp_010 heuristic-family summary CSV",
    )
    parser.add_argument(
        "--bks-input",
        type=Path,
        default=root / "instances" / "fjsplib_bks.csv",
        help="Structured tracked FJSPLib reference CSV",
    )
    parser.add_argument(
        "--quality-output",
        type=Path,
        default=root / "experiments" / "results" / "exp_011_heuristic_quality_rows.csv",
        help="Per-instance BKS-relative quality CSV",
    )
    parser.add_argument(
        "--family-output",
        type=Path,
        default=(
            root
            / "experiments"
            / "results"
            / "exp_011_heuristic_quality_families.csv"
        ),
        help="Cross-instance algorithm-family quality CSV",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate BKS-aware heuristic quality artifacts."""

    args = parse_args(argv)
    try:
        references = load_benchmark_references(args.bks_input)
        quality_rows = build_quality_rows(args.summary_input, references)
        family_rows = aggregate_family_quality(quality_rows)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}")
        return 2

    write_quality_rows_csv(args.quality_output, quality_rows)
    write_family_quality_csv(args.family_output, family_rows)
    print_family_quality(family_rows)
    print()
    print(f"Per-instance quality CSV written to: {args.quality_output}")
    print(f"Family quality CSV written to: {args.family_output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
