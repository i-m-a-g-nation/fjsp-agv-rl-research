"""Isolated entry for the one registered graduation development pilot."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.graduation.reference_pilot import execute_prepared

if __name__ == '__main__':
    try:
        payload = json.loads(sys.stdin.read(16384))
        if set(payload) != {'folder','deadline'}:
            raise ValueError('Unknown pilot payload')
        result = execute_prepared(payload['folder'], payload['deadline'])
    except Exception as exc:
        result = {'status':'FAILED','error_type':type(exc).__name__}
    sys.stdout.write(json.dumps(result))
