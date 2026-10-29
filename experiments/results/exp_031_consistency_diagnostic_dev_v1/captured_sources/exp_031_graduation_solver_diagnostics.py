"""Audit saved errors, or capture one bounded DEVELOPMENT diagnosis (no ranking)."""
import time
ENTERED=time.monotonic()
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.graduation.solver_diagnostics import audit_saved_failures,capture_case,recheck_capture
from src.graduation.reference_protocol import digest,encoded
from src.ai_workflow.graduation_main_evidence import backend_source_hashes,load_scope_context
from src.ai_workflow.graduation_main_budget import run_main_phase,read_main_budget
from src.ai_workflow.process_supervisor import supervised_json_process

ARCHIVE=ROOT/'experiments/results/exp_030_graduation_main_attempt2_v1'
OLD_REVIEW=ROOT/'experiments/runs/g3_main_review_17bc1aa7_attempt2'
MAX_CALLS=5
MAX_ACTIVE_SECONDS=30.

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);temp=p.with_suffix(p.suffix+'.tmp');temp.write_bytes(encoded(v));temp.replace(p)

def source_hashes():
    return {**backend_source_hashes(),
        'src/graduation/solver_diagnostics.py':sha(ROOT/'src/graduation/solver_diagnostics.py'),
        'experiments/exp_031_graduation_solver_diagnostics.py':sha(__file__)}

def initial_state(selection):
    return {'version':1,'status':'DEVELOPMENT_ONLY','rows':[{
        'sequence':r['sequence'],'case_id':r['case']['case_id'],'mode':r['mode'],
        'status':'NOT_RUN','capture_sha256':None} for r in selection['requests']]}

def _valid_selection(selection):
    rows=selection['requests'];ids=[r['sequence'] for r in rows]
    if not 0<len(rows)<=MAX_CALLS or len(set(ids))!=len(ids) or ids!=sorted(ids):
        raise ValueError('Development diagnosis accepts at most five distinct ordered requests')

def worker(payload):
    expected={'purpose','archive','output_dir','selection_sha256','source_hashes','deadline'}
    if (not isinstance(payload,dict) or set(payload)!=expected or payload['purpose']!='DEVELOPMENT_DIAGNOSIS_ONLY'
            or type(payload['deadline']) not in (int,float) or not math.isfinite(payload['deadline'])):
        return {'status':'REJECTED_PAYLOAD','diagnostic_solver_calls':0}
    calls=0
    try:
        selection=audit_saved_failures(payload['archive']);_valid_selection(selection)
        if digest(selection)!=payload['selection_sha256'] or source_hashes()!=payload['source_hashes']:
            raise ValueError('Development input/source identity changed')
        out=Path(payload['output_dir']);state=read(out/'state.json')
        if state!=initial_state(selection):raise ValueError('A development worker is never resumed')
        for item,thin in zip(selection['requests'],state['rows']):
            if time.monotonic()>=payload['deadline']:raise TimeoutError('Development deadline exhausted')
            thin['status']='RUNNING';write(out/'state.json',state);calls+=1
            capture=capture_case(item['case'],item['mode'])
            if time.monotonic()>=payload['deadline']:raise TimeoutError('Late development capture')
            recheck_capture(capture,item['case'],item['mode'])
            (out/'captures').mkdir(exist_ok=True)
            path=out/'captures'/f"{item['sequence']:04d}.json";write(path,capture)
            thin.update(status='CAPTURED',capture_sha256=sha(path));write(out/'state.json',state)
        if source_hashes()!=payload['source_hashes']:raise ValueError('Development sources changed')
        return {'status':'CAPTURED','diagnostic_solver_calls':calls}
    except TimeoutError as exc:
        return {'status':'DEADLINE_EXHAUSTED','diagnostic_solver_calls':calls,'error':str(exc)[:1000]}
    except Exception as exc:
        return {'status':'DEVELOPMENT_FAILED','diagnostic_solver_calls':calls,
                'error':f'{type(exc).__name__}: {str(exc)[:1000]}'}

def _collect(out,selection):
    state=read(out/'state.json');expected=initial_state(selection)
    if len(state['rows'])!=len(expected['rows']):raise ValueError('Development denominator changed')
    records=[]
    for row,planned,item in zip(state['rows'],expected['rows'],selection['requests']):
        if any(row[k]!=planned[k] for k in ('sequence','case_id','mode')):
            raise ValueError('Development order/identity changed')
        if row['status']=='CAPTURED':
            path=out/'captures'/f"{row['sequence']:04d}.json"
            if sha(path)!=row['capture_sha256']:raise ValueError('Development capture changed')
            result=read(path);recheck_capture(result,item['case'],item['mode'])
            if result['execution_kind']!='NATIVE_DEVELOPMENT_DIAGNOSTIC':
                raise ValueError('A synthetic fixture cannot be a native diagnostic result')
            records.append({'sequence':row['sequence'],'case_id':row['case_id'],'mode':row['mode'],
                'baseline_status':result['baseline_row']['status'],'capture_status':result['capture_status'],
                'historical_error_reproduced':result['baseline_row']['status']=='ERROR' and
                    result['baseline_row']['error']==item['historical_row']['error'],
                'numeric_checks':result['numeric_checks']})
        elif row['status'] not in ('NOT_RUN','RUNNING','INTERRUPTED'):
            raise ValueError('Unsupported development row status')
    return {'planned_requests':len(state['rows']),'captures':records,
        'reproduced_errors':sum(r['historical_error_reproduced'] for r in records),
        'complete_captures':sum(r['capture_status']=='COMPLETE' for r in records),
        'uncompleted_requests':len(state['rows'])-len(records)}

def run_development(output_dir,*,started_at=None):
    entered=time.monotonic() if started_at is None else started_at
    out=Path(output_dir).resolve()
    if out.exists():raise FileExistsError('Never overwrite or resume a development diagnosis')
    selection=audit_saved_failures(ARCHIVE);_valid_selection(selection)
    context=load_scope_context(OLD_REVIEW);scope=context['scope_dir']
    for protected in (ARCHIVE.resolve(),scope.resolve(),OLD_REVIEW.resolve()):
        if out==protected or protected in out.parents:raise ValueError('Development output overlaps protected evidence')
    sources=source_hashes();out.mkdir(parents=True)
    write(out/'selection.json',selection);write(out/'state.json',initial_state(selection))
    write(out/'development_context.json',{'purpose':'development diagnosis, not a formal comparison rerun',
        'authorization_basis':'User said 继续 after the specific diagnostic-development next step.',
        'scope_choice_by_agent':{'max_calls':MAX_CALLS,'time_limit_per_call':1.,'num_workers':1,'seed':42,
                                 'max_active_seconds':MAX_ACTIVE_SECONDS},
        'formal_scope_or_evidence_approval_claimed':False,'original_closed_batch_resumed':False,
        'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'research_status':'not_achieved'})
    def work(window):
        window.check()
        available=min(15.,window.remaining()-3.,entered+MAX_ACTIVE_SECONDS-5.-3.-time.monotonic())
        if available<=0:raise TimeoutError('No time remains to dispatch development diagnosis')
        receipt=supervised_json_process(Path(__file__).resolve(),{
            'purpose':'DEVELOPMENT_DIAGNOSIS_ONLY','archive':str(ARCHIVE),'output_dir':str(out),
            'selection_sha256':digest(selection),'source_hashes':sources,
            'deadline':time.monotonic()+available},available)
        write(out/'worker_receipt.json',receipt);window.check()
        summary=_collect(out,selection)
        if source_hashes()!=sources:raise ValueError('Development source bytes changed')
        summary['status']='DEVELOPMENT_CAPTURED' if receipt['status']=='CAPTURED' and summary['complete_captures']==len(selection['requests']) else 'DEVELOPMENT_PARTIAL'
        summary.update(original_experiment_status='FAILED',formal_results_modified=False,accepted_for_research=False,
            new_formal_benchmark_calls=0,diagnostic_solver_calls=receipt['diagnostic_solver_calls'],model_calls=0,
            research_status='not_achieved')
        if time.monotonic()>=entered+MAX_ACTIVE_SECONDS-5.:raise TimeoutError('Development postcheck deadline exhausted')
        return summary
    def finalize(summary,budget,check):
        check()
        if time.monotonic()>=entered+MAX_ACTIVE_SECONDS:raise TimeoutError('Development30second cap exhausted')
        write(out/'summary.json',summary);write(out/'budget_snapshot.json',budget)
        write(out/'manifest.json',{'version':1,'status':summary['status'],'source_hashes':sources,
            'artifacts':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
                if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}})
        check()
        if time.monotonic()>=entered+MAX_ACTIVE_SECONDS:raise TimeoutError('Late development receipt')
        return summary
    try:return run_main_phase(scope,out/'control',work,finalize,started_at=entered)
    except Exception as exc:
        state=read(out/'state.json')
        for row in state['rows']:
            if row['status']=='RUNNING':row['status']='INTERRUPTED'
        state['status']='DEVELOPMENT_FAILED';write(out/'state.json',state)
        summary={'status':'DEVELOPMENT_FAILED','error':f'{type(exc).__name__}: {str(exc)[:1000]}',
                 'planned_requests':len(selection['requests']),'accepted_for_research':False,'automatic_retry':False}
        write(out/'summary.json',summary)
        write(out/'manifest.json',{'status':'DEVELOPMENT_FAILED','source_hashes':sources,
            'artifacts':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
                if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}})
        return summary

def recheck_development(out):
    out=Path(out);manifest=read(out/'manifest.json')
    actual={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
            if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}
    if actual!=manifest['artifacts']:raise ValueError('Development artifacts changed')
    selection=read(out/'selection.json');audit=audit_saved_failures(ARCHIVE)
    if digest(selection)!=digest(audit):raise ValueError('Archived input selection changed')
    derived=_collect(out,selection);saved=read(out/'summary.json')
    if any(saved.get(k)!=v for k,v in derived.items()):raise ValueError('Development summary differs from captures')
    return {'status':'READ_ONLY_DIAGNOSTIC_RECHECK_PASSED','captures':len(derived['captures']),
            'reproduced_errors':derived['reproduced_errors'],'new_solver_calls':0}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='action',required=True)
    subs.add_parser('audit');run=subs.add_parser('dev-probe');run.add_argument('--output-dir',type=Path,required=True)
    replay=subs.add_parser('recheck');replay.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.action=='audit':
        selection=audit_saved_failures(ARCHIVE)
        value={'original_experiment_status':selection['original_experiment_status'],
               'selected_error_requests':len(selection['requests']),'solver_calls':0,'model_calls':0}
    elif args.action=='recheck':value=recheck_development(args.output_dir)
    else:value=run_development(args.output_dir,started_at=ENTERED)
    print(json.dumps(value,ensure_ascii=False))
    return 0 if value.get('status') not in ('DEVELOPMENT_FAILED','DEVELOPMENT_PARTIAL') else 1

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1].isdigit():
        print(json.dumps(worker(json.loads(sys.stdin.read(65536)))))
    else:raise SystemExit(main())
