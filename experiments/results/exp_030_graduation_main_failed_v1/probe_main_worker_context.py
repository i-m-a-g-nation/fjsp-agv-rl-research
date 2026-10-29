"""Read-only diagnosis of a managed worker's preconditions; never dispatch."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from src.ai_workflow.graduation_main_evidence import runtime_identity,recheck_main_evidence,load_scope_context
from src.ai_workflow.graduation_main_budget import read_main_budget

payload=json.loads(sys.stdin.read(8192))
report={'kind':'READ_ONLY_DEV_DIAGNOSIS','solver_calls':0,'checks':{}}
for name,work in (
    ('runtime',lambda:runtime_identity()),
    ('evidence',lambda:recheck_main_evidence(payload['evidence_dir'])),
    ('scope',lambda:{k:v for k,v in load_scope_context(payload['review_dir']).items() if k in ('scope_hash',)}),
    ('budget',lambda:{k:v for k,v in read_main_budget(payload['scope_dir']).items() if k not in ('segments',)})):
    try:report['checks'][name]={'status':'PASSED','value':work()}
    except Exception as exc:report['checks'][name]={'status':'FAILED','error':f'{type(exc).__name__}: {exc}'}
sys.stdout.write(json.dumps(report))
