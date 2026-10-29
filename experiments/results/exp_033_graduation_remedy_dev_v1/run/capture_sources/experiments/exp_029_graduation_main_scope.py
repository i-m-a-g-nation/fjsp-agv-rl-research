"""Prepare/recheck the complete G3A main scope; never start solver execution."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ai_workflow.graduation_main_scope import prepare_main_scope, recheck_main_scope
from src.ai_workflow.runtime_budget import BudgetExceeded


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--recheck',type=Path)
    args = parser.parse_args(argv)
    if args.output_dir and args.recheck:
        parser.error('Choose preparation or read-only recheck')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    try:
        result = recheck_main_scope(args.recheck) if args.recheck else prepare_main_scope(
            args.output_dir or ROOT/'experiments/runs/graduation_main_scope'/stamp)
    except (ValueError,OSError,BudgetExceeded) as exc:
        print(f'Scope preparation stopped: {exc}')
        return 1
    print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
