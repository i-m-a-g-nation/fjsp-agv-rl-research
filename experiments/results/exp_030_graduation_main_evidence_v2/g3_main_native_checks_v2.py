"""Delivery probes on DEVTEST inputs; never approve or execute the formal grid."""
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
from src.ai_workflow.process_supervisor import supervised_json_process

OUT=ROOT/'experiments/runs/g3_main_devtest_20261029_v2'
REVIEW=ROOT/'experiments/runs/g3_main_review_17bc1aa7'
SCOPE=ROOT/'experiments/runs/g3_main_scope_20261029_d'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
def snapshot():
    return {str(p.relative_to(ROOT)):sha(p) for folder in (REVIEW,SCOPE)
            for p in folder.rglob('*') if p.is_file()}

def independent_plan(data,payload,mode):
    tasks={t['job_id']:t for t in data['tasks']}
    reqs={r['machine_id']:r for r in data['maintenance']}
    records=payload['records'];maintenance=payload['maintenance_records']
    assert sorted(r['job_id'] for r in records)==sorted(tasks)
    assert sorted(r['machine_id'] for r in maintenance)==sorted(reqs)
    intervals={i:[] for i in reqs}
    total=0
    for r in records:
        t=tasks[r['job_id']]
        assert r['op_id']==0 and r['start']>=0
        assert r['end']-r['start']==r['processing_time']==t['processing_time']
        intervals[r['machine_id']].append((r['start'],r['end']))
        total+=max(0,r['end']-t['due_date'])
    for r in maintenance:
        q=reqs[r['machine_id']]
        assert q['window_start']<=r['start']<r['end']<=q['window_end']
        assert r['end']-r['start']==r['duration']==q['duration']
        assert mode!='fixed' or r['start']==q['fixed_start']
        intervals[r['machine_id']].append((r['start'],r['end']))
    for group in intervals.values():
        ordered=sorted(group)
        assert all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:]))
    assert total==payload['total_tardiness']==payload['solver_objective_value']
    assert max(r['end'] for r in records)==payload['makespan']
    return total

def independent_optimum(data,mode):
    # Enumerate machine assignments, job orders, maintenance starts and each
    # machine's before/after-maintenance cut. Earliest placement dominates idle
    # time here: release zero, regular tardiness objective, no shared crew.
    tasks=data['tasks'];m=data['num_machines'];best=None;checked=0
    windows=[(q['fixed_start'],) if mode=='fixed' else
             range(q['window_start'],q['window_end']-q['duration']+1) for q in data['maintenance']]
    for assignment in itertools.product(range(m),repeat=len(tasks)):
        for order in itertools.permutations(range(len(tasks))):
            queues=[[j for j in order if assignment[j]==i] for i in range(m)]
            for starts in itertools.product(*windows):
                for cuts in itertools.product(*(range(len(queue)+1) for queue in queues)):
                    total=0;valid=True;checked+=1
                    for i,queue in enumerate(queues):
                        clock=0
                        for index,j in enumerate(queue):
                            if index==cuts[i]:clock=max(clock,starts[i]+data['maintenance'][i]['duration'])
                            end=clock+tasks[j]['processing_time']
                            if index<cuts[i] and end>starts[i]:valid=False;break
                            total+=max(0,end-tasks[j]['due_date']);clock=end
                        if not valid:break
                    if valid and (best is None or total<best):best=total
    assert best is not None
    return best,checked

before=snapshot()
rejected=ROOT/'experiments/runs/g3_main_unapproved_probe_20261029_v2'
assert not rejected.exists()
probe=subprocess.run([sys.executable,'experiments/exp_030_graduation_main.py','run',
    '--review-dir',str(REVIEW),'--evidence-dir',str(ROOT/'experiments/runs/MISSING_EVIDENCE_DEVTEST'),
    '--output-dir',str(rejected)],capture_output=True,text=True,timeout=30)
assert probe.returncode==1 and not rejected.exists() and snapshot()==before
write(ROOT/'.superpowers/sdd/g3-main-unapproved-probe-v2.json',{
    'status':'PASSED','cli_exit_code':probe.returncode,'stdout':probe.stdout.strip(),
    'no_output_created':True,'original_scope_and_control_bytes_unchanged':True,
    'formal_solver_calls':0,'model_calls':0,'checked_files':len(before)})

reply=supervised_json_process(ROOT/'tests/fixtures/g3_tiny_worker.py',{'output_dir':str(OUT)},30)
assert reply['status']=='DEVTEST_COMPLETED'
cases=read(OUT/'cases.json');totals=[];checks=[]
for i in range(4):
    case=cases[i//2];mode=('fixed','joint')[i%2]
    row=read(OUT/'rows'/f'{i:04d}.json')
    assert row['status']=='ACCEPTED' and row['solver_status']=='OPTIMAL'
    value=independent_plan(case['data'],row['payload'],mode)
    optimum,count=independent_optimum(case['data'],mode)
    assert value==optimum==row['metrics']['total_tardiness']
    assert row['metrics']['solver_objective_bound']==value and row['metrics']['solver_gap']==0
    checks.append({'case_id':case['case_id'],'mode':mode,'total_tardiness':value,
                   'independent_optimum':optimum,'enumerated_states':count,'trace_sha256':sha(OUT/'rows'/f'{i:04d}.json')})
    totals.append(value)
assert totals==[4,0,6,0] and snapshot()==before
write(ROOT/'.superpowers/sdd/g3-main-native-independent-check-v2.json',{
    'status':'PASSED','actual_development_cp_calls':4,'formal_solver_calls':0,'model_calls':0,
    'method':'standard-library plan arithmetic and independent order/assignment/cut enumeration',
    'project_model_checker_and_enumerator_imported':False,'checked_rows':checks,
    'original_scope_and_control_bytes_unchanged':True})
print(json.dumps({'status':'PASSED','development_totals':totals,'formal_solver_calls':0}))
