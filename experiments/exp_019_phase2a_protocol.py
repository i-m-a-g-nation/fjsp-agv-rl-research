"""Execute a fixed Phase 2A baseline protocol without models or code generation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.research.batch import run_protocol


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=ROOT / "experiments/protocols/phase2a_v1.json")
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args(argv)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = args.output_dir or ROOT / "experiments/runs/phase2a_protocol" / stamp
    try:
        manifest = run_protocol(args.protocol, output, args.project_root, plots=not args.no_plots)
    except (ValueError, OSError) as exc:
        print(f"Protocol stopped: {exc}")
        return 1
    print(f"{manifest['status']}: {manifest['passed_runs']}/{manifest['expected_runs']} feasible runs; report: {output / 'report.md'}")
    print(f"Deterministic digest: {manifest['deterministic_digest']}; research goals remain not achieved.")
    return 0 if manifest["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
