"""Managed development-only controls; never grants or consumes main approval."""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from src.ai_workflow.graduation_main_backend import initial_state
from src.graduation.data import ParallelMaintenanceInstance,ProductionTask,MaintenanceRequirement
from src.graduation.reference_main_worker import execute_rows
from src.graduation.reference_protocol import encoded,digest


def development_cases():
    cases=[]
    for name,n,m,due,group in (('one_machine',2,1,(2,4),'primary'),('two_machines',3,2,(2,2,4),'sensitivity')):
        data=ParallelMaintenanceInstance(tuple(ProductionTask(j,2,d) for j,d in enumerate(due)),m,
            tuple(MaintenanceRequirement(i,2,0,6,0) for i in range(m)))
        cases.append({'case_id':'DEVTEST-'+name,'group':group,'data':asdict(data),
            'workload_hash':digest({'development':name}),'core_model_hash':digest(asdict(data))})
    return cases


if __name__=='__main__':
    payload=json.loads(sys.stdin.read(8192))
    if set(payload)!={'output_dir'}:raise ValueError('Only development output is accepted')
    folder=Path(payload['output_dir'])
    folder.mkdir(parents=True,exist_ok=False)
    (folder/'rows').mkdir()
    cases=development_cases()
    (folder/'cases.json').write_bytes(encoded(cases))
    (folder/'state.json').write_bytes(encoded(initial_state(cases,digest('DEVTEST-scope'),digest('DEVTEST-evidence'))))
    result=execute_rows(cases,folder,time.monotonic()+25)
    (folder/'development_receipt.json').write_bytes(encoded({'status':'DEVTEST_COMPLETED',
        'formal_main_executed':False,'actual_tiny_cp_calls':4,'worker':result}))
    sys.stdout.write(json.dumps({'status':'DEVTEST_COMPLETED','actual_tiny_cp_calls':4,'formal_main_executed':False}))
