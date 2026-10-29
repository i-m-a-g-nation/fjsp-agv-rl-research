"""Content-gated, one-shot G3A main execution and complete-denominator evidence."""
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import subprocess
import time

from src.ai_workflow.graduation_main_budget import run_main_phase, read_main_budget
from src.ai_workflow.graduation_main_evidence import execution_context, backend_source_hashes,runtime_identity
from src.ai_workflow.process_supervisor import supervised_json_process
from src.ai_workflow.runtime_budget import BudgetExceeded
from src.ai_workflow.review import artifact_hash,validate_review_decision
from src.graduation.reference_main_results import recheck_row, summarize_rows
from src.graduation.reference_protocol import encoded, digest

POSTCHECK_SECONDS=10.0
COMMITTED={'ACCEPTED','NO_SCHEDULE','ERROR'}


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path,value):
    path=Path(path)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def initial_state(cases,scope_hash,evidence_hash):
    return {'version':1,'status':'RUNNING','scope_hash':scope_hash,'evidence_hash':evidence_hash,
        'rows':[{'sequence':2*i+j,'case_id':c['case_id'],'mode':mode,'status':'NOT_RUN',
            'error':'','trace_sha256':None} for i,c in enumerate(cases) for j,mode in enumerate(('fixed','joint'))]}


def _unfinished(case,mode,status,error=''):
    return {'case_id':case['case_id'],'mode':mode,'input_sha256':digest(case['data']),
        'status':status,'solver_status':None,'metrics':None,'payload':None,'error':error,
        'solver':{'time_limit':1.0,'num_workers':1,'seed':42}}


def _rows(folder,cases,state,*,repair=False,check=lambda:None):
    expected=initial_state(cases,state['scope_hash'],state['evidence_hash'])['rows']
    if len(state['rows'])!=len(expected):
        raise ValueError('Main result denominator changed')
    rows=[]
    for index,(thin,planned) in enumerate(zip(state['rows'],expected)):
        check()
        if (set(thin)!=set(planned) or any(thin[k]!=planned[k] for k in ('sequence','case_id','mode'))):
            raise ValueError('Main result order/identity changed')
        case,mode=cases[index//2],planned['mode']
        path=folder/'rows'/f'{index:04d}.json'
        if thin['status']=='RUNNING' and repair:
            thin.update(status='INTERRUPTED',error='Worker stopped before committing this request',trace_sha256=None)
        if thin['status'] in COMMITTED:
            try:
                if not path.is_file() or _sha(path)!=thin['trace_sha256']:
                    raise ValueError('Main saved-row identity changed')
                row=_read(path)
                if row['status']!=thin['status'] or row['error']!=thin['error']:
                    raise ValueError('Main row status/diagnostic differs from its receipt')
                recheck_row(case,mode,row)
            except (ValueError,KeyError,TypeError,OSError) as exc:
                if not repair:
                    raise ValueError(f'Rejected committed main row {index}: {exc}') from exc
                (folder/'diagnostics').mkdir(exist_ok=True)
                if path.is_file():
                    (folder/'diagnostics'/f'{index:04d}-rejected.json').write_bytes(path.read_bytes())
                row=_unfinished(case,mode,'ERROR',f'Saved row rejected: {type(exc).__name__}: {str(exc)[:500]}')
                _write(path,row)
                thin.update(status='ERROR',error=row['error'],trace_sha256=_sha(path))
        elif thin['status'] in ('NOT_RUN','INTERRUPTED'):
            if thin['trace_sha256'] is not None or not isinstance(thin['error'],str):
                raise ValueError('Unfinished row cannot expose a committed plan')
            row=_unfinished(case,mode,thin['status'],thin['error'])
        else:
            raise ValueError('Unknown main row status')
        rows.append(row)
    return rows


def _report_bytes(summary,rows):
    stream=io.StringIO(newline='')
    fields=['sequence','case_id','mode','status','solver_status','total_tardiness',
        'solver_objective_bound','solver_gap','solver_wall_time','makespan','error']
    writer=csv.DictWriter(stream,fieldnames=fields,lineterminator='\n')
    writer.writeheader()
    for index,row in enumerate(rows):
        metrics=row['metrics'] or {}
        writer.writerow({'sequence':index,**{k:row[k] for k in ('case_id','mode','status','solver_status','error')},
            **{k:metrics.get(k) for k in fields if k in ('total_tardiness','solver_objective_bound','solver_gap','solver_wall_time','makespan')}})
    outputs={'raw.csv':stream.getvalue().encode('utf-8')}
    for group in ('primary','sensitivity'):
        pairs=[p for p in summary['pairs'] if p['group']==group]
        text=io.StringIO(newline='')
        writer=csv.DictWriter(text,fieldnames=list(pairs[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(pairs)
        outputs[f'{group}_pairs.csv']=text.getvalue().encode('utf-8')
    return outputs


def _reports(folder,summary,rows):
    for name,raw in _report_bytes(summary,rows).items():
        (folder/name).write_bytes(raw)


def _authorization(context):
    return {key:context[key] for key in ('scope_request','scope_decision','evidence_request','evidence_decision')}


def _check_authorization(record,scope_hash,evidence_hash,cases,sources):
    for stage,expected in (('scope',scope_hash),('evidence',evidence_hash)):
        request=record[stage+'_request']
        if (request['stage']!=stage or request['artifact_hash']!=expected
                or artifact_hash({k:v for k,v in request.items() if k!='artifact_hash'})!=expected
                or validate_review_decision(request,record[stage+'_decision'])['decision']!='approve'):
            raise ValueError('Stored approval is missing or bound to different material')
    if (record['scope_request']['payload']['material_sha256']['inputs.json']!=digest(cases)
            or record['evidence_request']['payload']['scope_hash']!=scope_hash
            or record['evidence_request']['payload']['source_hashes']!=sources):
        raise ValueError('Stored approvals do not bind the checked inputs/backend')


def _state_identity(state,scope_hash,evidence_hash):
    if (type(state.get('version')) is not int or state['version']!=1
            or state.get('scope_hash')!=scope_hash or state.get('evidence_hash')!=evidence_hash):
        raise ValueError('Main run state identity changed')


def _check_budget_receipt(snapshot,authorization,status):
    if snapshot.get('status')=='UNAVAILABLE_NO_BUDGET_REPAIR' and status!='COMPLETED':
        return
    base=authorization['evidence_request']['payload']['budget_snapshot']
    limits={'max_active_seconds':600,'max_provider_calls':0,'max_output_tokens':0}
    if (encoded(snapshot.get('limits'))!=encoded(limits) or snapshot.get('provider_calls')!=0
            or snapshot.get('output_tokens_reserved')!=0 or not isinstance(snapshot.get('segments'),list)
            or encoded(snapshot['segments'][:len(base['segments'])])!=encoded(base['segments'])):
        raise ValueError('Run budget no longer continues the approved evidence history')
    active,reserved=0.0,0.0
    for index,segment in enumerate(snapshot['segments'],1):
        r,f=segment['reserved_seconds'],segment['finished_seconds']
        if (type(segment['id']) is not int or segment['id']!=index or type(r) not in (int,float)
                or not math.isfinite(r) or not 0<r<=600 or r!=600-active):
            raise ValueError('Run budget reservation changed')
        if f is None:
            if index!=len(snapshot['segments']):raise ValueError('Unsettled run budget was reused')
            reserved=r
        elif type(f) not in (int,float) or not math.isfinite(f) or f<0:
            raise ValueError('Run budget contains invalid active time')
        else:active+=f
    expected={'active_seconds':active,'active_seconds_charged':active+reserved,
        'active_seconds_reserved':reserved,'remaining_active_seconds':max(0.,600-active-reserved)}
    if any(type(snapshot.get(k)) not in (int,float) or snapshot[k]!=v for k,v in expected.items()):
        raise ValueError('Run budget totals were refunded or corrupted')
    if status=='COMPLETED' and (reserved or active>600 or len(snapshot['segments'])<len(base['segments'])+2):
        raise ValueError('Completed main run lacks a settled in-budget execution')


def _persist(folder,state,summary,rows,sources,snapshot):
    _write(folder/'state.json',state)
    _reports(folder,summary,rows)
    _write(folder/'summary.json',summary)
    _write(folder/'budget_snapshot.json',snapshot)
    _write(folder/'manifest.json',{'version':1,'status':summary['status'],
        'runtime':runtime_identity(),
        'scope_hash':state['scope_hash'],'evidence_hash':state['evidence_hash'],
        'source_hashes':sources,'research_status':'not_achieved',
        'artifacts':{p.relative_to(folder).as_posix():_sha(p) for p in sorted(folder.rglob('*'))
            if p.is_file() and p.relative_to(folder).as_posix()!='manifest.json'}})


def run_main(review_dir,evidence_dir,output_dir):
    """The only formal entry; require actual content-bound evidence approval."""
    entered=time.monotonic()
    review,evidence,folder=Path(review_dir),Path(evidence_dir),Path(output_dir).resolve()
    context=execution_context(review,evidence)
    if any(folder==p or p in folder.parents for p in (Path(context['scope_dir']).resolve(),evidence.resolve())):
        raise ValueError('Main output must be outside frozen scope and evidence materials')
    if folder.exists():
        raise ValueError('An existing main output is never restarted or overwritten')
    cases=context['cases']
    sources=context['backend_source_hashes']
    state=initial_state(cases,context['scope_hash'],context['evidence_hash'])
    authorization=_authorization(context)
    _check_authorization(authorization,context['scope_hash'],context['evidence_hash'],cases,sources)
    initialized=False

    def work(window):
        nonlocal initialized,state
        window.check()
        current=execution_context(review,evidence,allow_reserved=True)
        if any(encoded(current[k])!=encoded(context[k]) for k in
                ('scope_hash','evidence_hash','backend_source_hashes','cases')):
            raise ValueError('Main authorization changed while acquiring the execution lock')
        folder.mkdir(parents=True,exist_ok=False)
        (folder/'rows').mkdir()
        _write(folder/'state.json',state)
        _write(folder/'authorization.json',authorization)
        initialized=True
        _write(review/'state.json',{'status':'RUNNING','scope_approved':True,'evidence_approved':True,
            'conclusion_approved':False,'scope_review_hash':context['scope_hash'],
            'evidence_review_hash':context['evidence_hash'],'evidence_packet':str(evidence.resolve()),
            'output_dir':str(folder),'research_status':'not_achieved'})
        forced,error=None,''
        try:
            available=window.remaining()-POSTCHECK_SECONDS
            if available<=0:
                raise BudgetExceeded('Insufficient remaining budget to dispatch and verify main worker')
            reply=supervised_json_process(Path(__file__).parents[1]/'graduation/reference_main_worker.py',
                {'review_dir':str(review.resolve()),'evidence_dir':str(evidence.resolve()),
                 'output_dir':str(folder),'deadline':time.monotonic()+available},available)
            _write(folder/'worker_receipt.json',reply)
            if reply.get('status')=='BUDGET_EXHAUSTED':
                raise BudgetExceeded('Managed main worker reached its deadline')
            if reply.get('status')=='FAILED':
                raise ValueError(f"Worker failed at {reply.get('stage','unknown')}: "
                                 f"{reply.get('error_type','unknown')}: {str(reply.get('error','No diagnostic'))[:500]}")
            if reply!={'status':'WORKER_FINISHED','completed_rows':480,'input_set_sha256':digest(cases)}:
                raise ValueError('Worker completion receipt is incomplete')
        except (subprocess.TimeoutExpired,BudgetExceeded) as exc:
            forced,error='BUDGET_EXHAUSTED',f'{type(exc).__name__}: {str(exc)[:500]}'
        except Exception as exc:
            forced,error='FAILED',f'{type(exc).__name__}: {str(exc)[:500]}'
        state=_read(folder/'state.json')
        _state_identity(state,context['scope_hash'],context['evidence_hash'])
        rows=_rows(folder,cases,state,repair=True,check=window.check)
        summary=summarize_rows(cases,rows)
        if sources!=backend_source_hashes():
            raise ValueError('Approved backend sources changed during execution')
        integrity=sum(g['integrity_errors'] for g in summary['groups'].values())
        incomplete=summary['status_counts']['NOT_RUN']+summary['status_counts']['INTERRUPTED']
        status=forced or ('FAILED' if integrity or summary['status_counts']['ERROR'] or incomplete else 'COMPLETED')
        summary.update(status=status,error=error,scope_hash=context['scope_hash'],evidence_hash=context['evidence_hash'],
            input_set_sha256=digest(cases),
            interpretation='Complete means all requests accounted for; only accepted plans have metrics. No scientific acceptance.')
        state['status']=status
        window.check()
        return state,summary,rows

    def finalize(value,snapshot,check):
        state,summary,rows=value
        check()
        _persist(folder,state,summary,rows,sources,snapshot)
        check()
        _write(review/'state.json',{'status':'CONCLUSION_PREPARATION_REQUIRED' if summary['status']=='COMPLETED' else summary['status'],
            'scope_approved':True,'evidence_approved':True,'conclusion_approved':False,
            'scope_review_hash':context['scope_hash'],'evidence_review_hash':context['evidence_hash'],
            'evidence_packet':str(evidence.resolve()),
            'output_dir':str(folder),'research_status':'not_achieved'})
        return summary

    try:
        return run_main_phase(context['scope_dir'],review,work,finalize,started_at=entered)
    except Exception as exc:
        # Failure cleanup preserves every planned row and cannot authorize retry.
        if not initialized:
            # No run was created/owned: do not overwrite another invocation's
            # control state after a lock, stale-gate or preflight failure.
            raise
        elif (folder/'state.json').exists():
            state=_read(folder/'state.json')
        error=f'{type(exc).__name__}: {str(exc)[:500]}'
        try:
            _state_identity(state,context['scope_hash'],context['evidence_hash'])
            rows=_rows(folder,cases,state,repair=True)
        except Exception:
            (folder/'diagnostics').mkdir(exist_ok=True)
            _write(folder/'diagnostics/rejected-state.json',state)
            state=initial_state(cases,context['scope_hash'],context['evidence_hash'])
            rows=[_unfinished(c,m,'NOT_RUN',error) for c in cases for m in ('fixed','joint')]
            for thin in state['rows']:thin['error']=error
        summary=summarize_rows(cases,rows)
        status='BUDGET_EXHAUSTED' if isinstance(exc,(BudgetExceeded,subprocess.TimeoutExpired)) else 'FAILED'
        summary.update(status=status,error=error,scope_hash=context['scope_hash'],evidence_hash=context['evidence_hash'],
            input_set_sha256=digest(cases))
        state['status']=status
        if not (folder/'authorization.json').is_file():_write(folder/'authorization.json',authorization)
        try:snapshot=read_main_budget(context['scope_dir'])
        except Exception:snapshot={'status':'UNAVAILABLE_NO_BUDGET_REPAIR'}
        _persist(folder,state,summary,rows,sources,snapshot)
        _write(review/'state.json',{'status':status,'scope_review_hash':context['scope_hash'],
            'evidence_review_hash':context['evidence_hash'],'output_dir':str(folder),
            'evidence_packet':str(evidence.resolve()),
            'scope_approved':True,'evidence_approved':True,'conclusion_approved':False,'research_status':'not_achieved'})
        return summary


def recheck_main_run(output_dir,cases,*,require_current_sources=True):
    """Recompute stored feasibility/metrics, pair bounds and denominators; no solve."""
    folder=Path(output_dir)
    manifest=_read(folder/'manifest.json')
    if type(manifest.get('version')) is not int or manifest['version']!=1:
        raise ValueError('Unsupported main result version')
    actual={p.relative_to(folder).as_posix():_sha(p) for p in sorted(folder.rglob('*'))
        if p.is_file() and p.relative_to(folder).as_posix()!='manifest.json'}
    if actual!=manifest['artifacts']:
        raise ValueError('Stored main artifact identities changed')
    if require_current_sources and manifest['source_hashes']!=backend_source_hashes():
        raise ValueError('Main backend sources changed')
    state,summary=_read(folder/'state.json'),_read(folder/'summary.json')
    _state_identity(state,manifest['scope_hash'],manifest['evidence_hash'])
    authorization=_read(folder/'authorization.json')
    _check_authorization(authorization,manifest['scope_hash'],manifest['evidence_hash'],cases,manifest['source_hashes'])
    _check_budget_receipt(_read(folder/'budget_snapshot.json'),authorization,summary['status'])
    if (summary.get('scope_hash')!=manifest['scope_hash'] or summary.get('evidence_hash')!=manifest['evidence_hash']
            or summary.get('input_set_sha256')!=digest(cases)):
        raise ValueError('Main report scope/evidence/input identity changed')
    rows=_rows(folder,cases,state)
    checked=summarize_rows(cases,rows)
    if any(summary.get(k)!=v for k,v in checked.items()) or state['status']!=summary['status'] or manifest['status']!=summary['status']:
        raise ValueError('Main summary differs from stored checked plans')
    if summary['status']=='COMPLETED' and (checked['status_counts']['ERROR']
            or checked['status_counts']['NOT_RUN'] or checked['status_counts']['INTERRUPTED']
            or any(g['integrity_errors'] for g in checked['groups'].values())):
        raise ValueError('Incomplete or invalid main requests cannot claim completion')
    for name,expected in _report_bytes(checked,rows).items():
        if (folder/name).read_bytes()!=expected:
            raise ValueError('Main CSV report differs from the checked plans')
    return summary
