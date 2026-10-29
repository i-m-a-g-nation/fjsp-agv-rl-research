"""Audit saved errors, or capture one bounded DEVELOPMENT diagnosis (no ranking)."""
import time
ENTERED=time.monotonic()
import argparse
from datetime import datetime,timezone
import hashlib
import json
import math
import os
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
from src.ai_workflow.research_controller import _exclusive_lock

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


def _check_worker_lease(payload):
    """Bind the internal entry to a live parent, held lock and original segment."""
    out=Path(payload['output_dir']).resolve();control=out.with_name(out.name+'-control')
    lease_file=control/'worker_lease.json'
    if not lease_file.is_file() or sha(lease_file)!=payload['lease_sha256']:
        raise ValueError('Missing or changed live development lease')
    lease=read(lease_file);now=time.monotonic()
    parent=int(sys.argv[1]) if len(sys.argv)>1 and sys.argv[1].isdigit() else -1
    if (lease['parent_pid']!=parent or parent!=os.getppid() or lease['output_dir']!=str(out)
            or lease['deadline']!=payload['deadline'] or not now<lease['deadline']<=now+15.
            or lease['selection_sha256']!=payload['selection_sha256']
            or lease['source_hashes']!=payload['source_hashes']):
        raise ValueError('Development lease identity or parent changed')
    context=load_scope_context(OLD_REVIEW);scope=context['scope_dir'].resolve()
    if lease['scope_dir']!=str(scope) or sha(scope/'budget.sqlite')!=lease['ledger_sha256']:
        raise ValueError('Original development ledger changed')
    snapshot=read_main_budget(scope);tail=snapshot['segments'][-1]
    if tail['id']!=lease['segment_id'] or tail['finished_seconds'] is not None:
        raise ValueError('Development segment is no longer reserved')
    try:
        with _exclusive_lock(control):pass
    except ValueError as exc:
        if str(exc)!='Controller is already running':raise
    else:raise ValueError('Development parent no longer holds its control lock')
    if time.monotonic()>=payload['deadline']:raise TimeoutError('Development lease expired during validation')

def worker(payload):
    expected={'purpose','archive','output_dir','selection_sha256','source_hashes','deadline','lease_sha256'}
    if (not isinstance(payload,dict) or set(payload)!=expected or payload['purpose']!='DEVELOPMENT_DIAGNOSIS_ONLY'
            or type(payload['deadline']) not in (int,float) or not math.isfinite(payload['deadline'])):
        return {'status':'REJECTED_PAYLOAD','diagnostic_solver_calls':0}
    calls=0
    try:
        if time.monotonic()>=payload['deadline']:raise TimeoutError('Development deadline exhausted')
        _check_worker_lease(payload)
        selection=audit_saved_failures(payload['archive']);_valid_selection(selection)
        if digest(selection)!=payload['selection_sha256'] or source_hashes()!=payload['source_hashes']:
            raise ValueError('Development input/source identity changed')
        out=Path(payload['output_dir']);state=read(out/'state.json')
        if state!=initial_state(selection):raise ValueError('A development worker is never resumed')
        for item,thin in zip(selection['requests'],state['rows']):
            if time.monotonic()>=payload['deadline']:raise TimeoutError('Development deadline exhausted')
            _check_worker_lease(payload)
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
    control=out.with_name(out.name+'-control')
    if control.exists():raise FileExistsError('Never reuse a development control directory')
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
        deadline=time.monotonic()+available
        snapshot=window.snapshot()
        lease={'parent_pid':os.getpid(),'scope_dir':str(scope.resolve()),'output_dir':str(out),
            'segment_id':snapshot['segments'][-1]['id'],'ledger_sha256':sha(scope/'budget.sqlite'),
            'deadline':deadline,'selection_sha256':digest(selection),'source_hashes':sources}
        write(control/'worker_lease.json',lease)
        receipt=supervised_json_process(Path(__file__).resolve(),{
            'purpose':'DEVELOPMENT_DIAGNOSIS_ONLY','archive':str(ARCHIVE),'output_dir':str(out),
            'selection_sha256':digest(selection),'source_hashes':sources,
            'deadline':deadline,'lease_sha256':sha(control/'worker_lease.json')},available)
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
    # Runtime locks stay outside immutable result artifacts. Reading a held
    # controller.lock fails under mandatory Windows byte locking.
    try:return run_main_phase(scope,control,work,finalize,started_at=entered)
    except Exception as exc:
        state=read(out/'state.json')
        for row in state['rows']:
            if row['status']=='RUNNING':row['status']='INTERRUPTED'
        state['status']='DEVELOPMENT_FAILED';write(out/'state.json',state)
        summary={'status':'DEVELOPMENT_FAILED','error':f'{type(exc).__name__}: {str(exc)[:1000]}',
                 'planned_requests':len(selection['requests']),'accepted_for_research':False,'automatic_retry':False}
        write(out/'summary.json',summary)
        try:write(out/'live_budget_after_failure.json',read_main_budget(scope))
        except Exception:pass
        write(out/'manifest.json',{'status':'DEVELOPMENT_FAILED','source_hashes':sources,
            'artifacts':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
                if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}})
        return summary

def _recheck_sources(manifest,captured_sources):
    current=source_hashes();recorded=manifest['source_hashes'];snapshots=[]
    if set(recorded)!=set(current):raise ValueError('Development source map changed')
    diagnostic={'src/graduation/solver_diagnostics.py','experiments/exp_031_graduation_solver_diagnostics.py'}
    for name,expected in recorded.items():
        if current[name]==expected:continue
        if name not in diagnostic or captured_sources is None:
            raise ValueError(f'Development source differs; explicit captured source required: {name}')
        snapshot=Path(captured_sources)/Path(name).name
        if not snapshot.is_file() or sha(snapshot)!=expected:
            raise ValueError(f'Captured development source changed: {name}')
        snapshots.append(name)
    return sorted(snapshots)


def _recheck_summary(saved,derived,receipt):
    invariants={'original_experiment_status':'FAILED','formal_results_modified':False,'accepted_for_research':False,
                'new_formal_benchmark_calls':0,'model_calls':0,'research_status':'not_achieved'}
    failed=saved.get('status')=='DEVELOPMENT_FAILED'
    for key,expected in invariants.items():
        # The first failed native receipt predates these optional fields.
        if key not in saved and failed and key!='accepted_for_research':continue
        if type(saved.get(key)) is not type(expected) or saved.get(key)!=expected:
            raise ValueError('Development research boundary changed')
    calls=receipt.get('diagnostic_solver_calls')
    if (type(calls) is not int or not len(derived['captures'])<=calls<=derived['planned_requests']
            or receipt.get('status') not in ('CAPTURED','DEADLINE_EXHAUSTED','DEVELOPMENT_FAILED')):
        raise ValueError('Malformed development worker receipt')
    if failed:
        if (saved.get('automatic_retry') is not False or saved.get('planned_requests')!=derived['planned_requests']
                or not isinstance(saved.get('error'),str) or not saved['error']):
            raise ValueError('Malformed failed development receipt')
    else:
        expected_status='DEVELOPMENT_CAPTURED' if receipt['status']=='CAPTURED' and derived['complete_captures']==derived['planned_requests'] else 'DEVELOPMENT_PARTIAL'
        if (saved.get('status')!=expected_status or saved.get('diagnostic_solver_calls')!=calls
                or any(saved.get(k)!=v for k,v in derived.items())):
            raise ValueError('Development summary differs from captures')


def recheck_development(out,*,captured_sources=None):
    out=Path(out);manifest=read(out/'manifest.json')
    actual={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
            if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}
    if actual!=manifest['artifacts']:raise ValueError('Development artifacts changed')
    snapshot_files=_recheck_sources(manifest,captured_sources)
    selection=read(out/'selection.json');audit=audit_saved_failures(ARCHIVE)
    if digest(selection)!=digest(audit):raise ValueError('Archived input selection changed')
    derived=_collect(out,selection);saved=read(out/'summary.json')
    if manifest['status']!=saved.get('status'):raise ValueError('Development manifest status changed')
    _recheck_summary(saved,derived,read(out/'worker_receipt.json'))
    return {'status':'READ_ONLY_DIAGNOSTIC_RECHECK_PASSED','recorded_batch_status':saved['status'],
            'captures':len(derived['captures']),
            'reproduced_errors':derived['reproduced_errors'],'new_solver_calls':0,
            'source_snapshot_files':snapshot_files}

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='action',required=True)
    subs.add_parser('audit');run=subs.add_parser('dev-probe');run.add_argument('--output-dir',type=Path,required=True)
    replay=subs.add_parser('recheck');replay.add_argument('--output-dir',type=Path,required=True)
    replay.add_argument('--captured-sources',type=Path)
    args=parser.parse_args(argv)
    if args.action=='audit':
        selection=audit_saved_failures(ARCHIVE)
        value={'original_experiment_status':selection['original_experiment_status'],
               'selected_error_requests':len(selection['requests']),'solver_calls':0,'model_calls':0}
    elif args.action=='recheck':value=recheck_development(args.output_dir,captured_sources=args.captured_sources)
    else:value=run_development(args.output_dir,started_at=ENTERED)
    print(json.dumps(value,ensure_ascii=False))
    return 0 if value.get('status') not in ('DEVELOPMENT_FAILED','DEVELOPMENT_PARTIAL') else 1

if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1].isdigit():
        print(json.dumps(worker(json.loads(sys.stdin.read(65536)))))
    else:raise SystemExit(main())
