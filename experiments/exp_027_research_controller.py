"""One entry point for the bounded offline outer research controller."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ai_workflow.research_controller import run_controller, read_controller_status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'status'])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--track', choices=['graduation', 'innovation'], default='graduation')
    parser.add_argument('--max-active-seconds', type=float, default=120)
    parser.add_argument('--max-tasks', type=int, default=2)
    parser.add_argument('--steps', type=int, default=2)
    args = parser.parse_args()
    if args.command == 'status':
        result = read_controller_status(args.output_dir)
    else:
        result = run_controller(args.output_dir, track=args.track, max_active_seconds=args.max_active_seconds,
                                max_tasks=args.max_tasks, steps=args.steps)
    print(json.dumps({key: result[key] for key in ('status', 'stop_reason', 'tasks', 'next_task',
                     'skipped_candidates', 'research_status', 'budget')}, ensure_ascii=False, indent=2))
    return 0 if result['stop_reason'] in ('implementation_required', 'invocation_slice',
        'no_registered_innovation_executor', 'task_count_budget') else 1


if __name__ == '__main__':
    raise SystemExit(main())
