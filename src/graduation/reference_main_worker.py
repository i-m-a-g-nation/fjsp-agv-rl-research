"""Managed formal worker; the parent and worker independently check approvals."""
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from src.graduation.reference_protocol import encoded,digest
from src.graduation.reference_main_results import evaluate_row


def _write(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def execute_rows(cases,output_dir,deadline):
    """Serial trusted core; tiny/mocked development controls call this directly."""
    folder=Path(output_dir)
    state=json.loads((folder/'state.json').read_text(encoding='utf-8'))
    if len(state['rows'])!=len(cases)*2:
        raise ValueError('Worker row denominator changed')
    for index,row in enumerate(state['rows']):
        if time.monotonic()>=deadline:raise TimeoutError('Main worker deadline exhausted')
        case,mode=cases[index//2],('fixed','joint')[index%2]
        if row['sequence']!=index or row['case_id']!=case['case_id'] or row['mode']!=mode or row['status']!='NOT_RUN':
            raise ValueError('Main worker identity/order changed')
        row['status']='RUNNING'
        _write(folder/'state.json',state)
        trace=evaluate_row(case,mode)
        if time.monotonic()>=deadline:raise TimeoutError('Late main solver result cannot be accepted')
        path=folder/'rows'/f'{index:04d}.json'
        _write(path,trace)
        row.update(status=trace['status'],error=trace['error'],trace_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        _write(folder/'state.json',state)
    return {'status':'WORKER_FINISHED','completed_rows':len(cases)*2,'input_set_sha256':digest(cases)}


if __name__=='__main__':
    stage='payload_validation'
    try:
        from src.ai_workflow.graduation_main_evidence import execution_context
        payload=json.loads(sys.stdin.read(32768))
        if set(payload)!={'review_dir','evidence_dir','output_dir','deadline'}:
            raise ValueError('Unknown main worker payload')
        stage='approval_gate'
        context=execution_context(payload['review_dir'],payload['evidence_dir'],allow_running=True)
        control=json.loads((Path(payload['review_dir'])/'state.json').read_text(encoding='utf-8'))
        if control.get('output_dir')!=str(Path(payload['output_dir']).resolve()):
            raise ValueError('Worker output is not the authorized main run')
        stage='execution'
        result=execute_rows(context['cases'],payload['output_dir'],payload['deadline'])
    except TimeoutError as exc:
        result={'status':'BUDGET_EXHAUSTED','error_type':type(exc).__name__,
                'stage':stage,'error':str(exc)[:1000]}
    except Exception as exc:
        result={'status':'FAILED','error_type':type(exc).__name__,
                'stage':stage,'error':str(exc)[:1000]}
    sys.stdout.write(json.dumps(result))
