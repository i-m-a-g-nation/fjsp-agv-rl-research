"""Run/recheck the 12-pair G3A development pilot; formal main grid is unavailable."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.graduation.reference_pilot import run_pilot, recheck_pilot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--recheck', type=Path)
    parser.add_argument('--max-active-seconds', type=float, default=90)
    args = parser.parse_args(argv)
    if args.recheck and args.output_dir:
        parser.error('Choose either a new run or read-only recheck')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    try:
        result = recheck_pilot(args.recheck) if args.recheck else run_pilot(
            args.output_dir or ROOT/'experiments/runs/graduation_reference_pilot'/stamp,
            max_active_seconds=args.max_active_seconds)
    except (ValueError, OSError) as exc:
        print(f'Pilot stopped: {exc}')
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['status'] == 'COMPLETED' else 1


if __name__ == '__main__':
    raise SystemExit(main())
