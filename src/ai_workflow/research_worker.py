"""Isolated JSON entry point. Never imports a user supplied module or .env."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.ai_workflow.research_tasks import execute_task, encoded


def main():
    try:
        payload = json.loads(sys.stdin.read(256 * 1024))
        if set(payload) != {'task_id', 'reference_archive', 'paper_archive', 'expected_inputs'}:
            raise ValueError('Unknown worker input fields')
        result = execute_task(payload['task_id'], payload['reference_archive'], payload['paper_archive'],
                              expected_inputs=payload['expected_inputs'])
        sys.stdout.buffer.write(encoded(result))
    except Exception as exc:
        sys.stdout.write(json.dumps({'status': 'FAILED', 'error_type': type(exc).__name__}))


if __name__ == '__main__':
    main()
