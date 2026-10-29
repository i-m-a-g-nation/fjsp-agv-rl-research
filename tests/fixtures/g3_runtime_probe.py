"""Return runtime identity through the real supervisor, without any solve."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from src.ai_workflow.graduation_main_evidence import runtime_identity

if __name__=='__main__':
    assert json.loads(sys.stdin.read(8192))=={}
    sys.stdout.write(json.dumps(runtime_identity()))
