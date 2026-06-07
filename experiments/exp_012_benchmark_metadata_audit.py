"""
exp_012_benchmark_metadata_audit.py

Phase 1 tracked-benchmark metadata audit:
- Discover tracked static FJSPLib files recursively in stable path order
- Load structured upstream FJSPLib lower and upper bounds
- Require a one-to-one match between tracked files and metadata rows
- Require every discovered benchmark file to remain loadable
- Write an auditable per-file CSV report
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).parent.parent))

from experiments.exp_005_benchmark_batch import discover_benchmark_files  # noqa: E402
from experiments.exp_011_heuristic_quality_report import (  # noqa: E402
    BenchmarkReference,
    load_benchmark_references,
)
from src.data.loader import load_benchmark_file  # noqa: E402


@dataclass(frozen=True)
class BenchmarkMetadataAudit:
    """One tracked-file metadata integrity result."""

    instance_name: str
    file_tracked: bool
    bks_recorded: bool
    loadable: bool
    lower_bound: int | None
    upper_bound: int | None
    status: str
    note: str

    def to_csv_row(self) -> dict[str, str]:
        """Convert an audit result to stable CSV text values."""

        return {
            "instance_name": self.instance_name,
            "file_tracked": _format_bool(self.file_tracked),
            "bks_recorded": _format_bool(self.bks_recorded),
            "loadable": _format_bool(self.loadable),
            "fjsplib_lb": _format_optional_int(self.lower_bound),
            "fjsplib_ub": _format_optional_int(self.upper_bound),
            "status": self.status,
            "note": self.note,
        }


def _format_bool(value: bool) -> str:
    """Format booleans consistently for tracked CSV output."""

    return "PASS" if value else "FAIL"


def _format_optional_int(value: int | None) -> str:
    """Format optional integer metadata values."""

    return "" if value is None else str(value)


def audit_benchmark_metadata(
    input_dir: str | Path,
    references: dict[str, BenchmarkReference],
) -> list[BenchmarkMetadataAudit]:
    """Audit one-to-one tracked-file, metadata, and loader consistency."""

    root = Path(input_dir)
    discovered_paths = discover_benchmark_files(root)
    discovered = {
        path.relative_to(root).as_posix(): path
        for path in discovered_paths
    }
    instance_names = sorted(set(discovered) | set(references))
    if not instance_names:
        raise ValueError("metadata audit requires at least one tracked instance")

    rows = []
    for instance_name in instance_names:
        path = discovered.get(instance_name)
        reference = references.get(instance_name)
        failures = []
        loadable = False

        if path is None:
            failures.append("tracked benchmark file is missing")
        else:
            try:
                load_benchmark_file(path)
            except Exception as exc:
                failures.append(f"benchmark loader failed: {exc}")
            else:
                loadable = True

        if reference is None:
            failures.append("BKS metadata row is missing")

        rows.append(
            BenchmarkMetadataAudit(
                instance_name=instance_name,
                file_tracked=path is not None,
                bks_recorded=reference is not None,
                loadable=loadable,
                lower_bound=reference.lower_bound if reference else None,
                upper_bound=reference.upper_bound if reference else None,
                status="PASS" if not failures else "FAIL",
                note="PASS" if not failures else "; ".join(failures),
            )
        )
    return rows


def write_metadata_audit_csv(
    path: str | Path,
    rows: Sequence[BenchmarkMetadataAudit],
) -> None:
    """Write per-file benchmark metadata audit rows to a UTF-8 CSV file."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "instance_name",
        "file_tracked",
        "bks_recorded",
        "loadable",
        "fjsplib_lb",
        "fjsplib_ub",
        "status",
        "note",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())


def print_metadata_audit(rows: Sequence[BenchmarkMetadataAudit]) -> None:
    """Print a compact benchmark metadata audit table."""

    header = (
        f"{'Instance':48s} {'file':>4s} {'LB/UB':>5s} "
        f"{'load':>4s} {'status':>6s}"
    )
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row.instance_name:48s} "
            f"{_format_bool(row.file_tracked):>4s} "
            f"{_format_bool(row.bks_recorded):>4s} "
            f"{_format_bool(row.loadable):>4s} "
            f"{row.status:>6s}"
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the benchmark metadata audit."""

    root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=root / "instances" / "fjsplib",
        help="Directory scanned recursively for tracked FJSPLib files",
    )
    parser.add_argument(
        "--bks-input",
        type=Path,
        default=root / "instances" / "fjsplib_bks.csv",
        help="Structured tracked FJSPLib reference CSV",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=(
            root
            / "experiments"
            / "results"
            / "exp_012_benchmark_metadata_audit.csv"
        ),
        help="Per-file benchmark metadata audit CSV",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Generate the tracked-benchmark metadata audit artifact."""

    args = parse_args(argv)
    try:
        references = load_benchmark_references(args.bks_input)
        rows = audit_benchmark_metadata(args.input_dir, references)
    except (OSError, ValueError) as exc:
        print(f"Configuration error: {exc}")
        return 2

    write_metadata_audit_csv(args.output, rows)
    print_metadata_audit(rows)
    print()
    print(f"Metadata audit CSV written to: {args.output}")

    failures = [row for row in rows if row.status != "PASS"]
    if failures:
        print("FAILURES:")
        for row in failures:
            print(f"  - {row.instance_name}: {row.note}")
        return 1

    print("Tracked benchmark files, LB/UB rows, and loader checks are consistent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
