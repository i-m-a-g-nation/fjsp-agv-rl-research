"""One approved14-request development counterfactual; no resume or approval command."""
import time
ENTERED=time.monotonic()
import argparse
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments import exp_032_graduation_remedy_scope as scope
from src.graduation.remedy_validation import capture_configured,recheck_configured,classify_pairs
from src.graduation.enumeration import enumerate_parallel_maintenance
from src.graduation.reference_main_results import _data
from src.graduation.reference_protocol import digest,encoded
from src.ai_workflow.graduation_main_evidence import _read as read,runtime_identity
from src.ai_workflow.runtime_budget import RunBudget,BudgetLimits,BudgetExceeded
from src.ai_workflow.research_controller import _exclusive_lock
from src.ai_workflow.process_supervisor import supervised_json_process

PROPOSAL=ROOT/'experiments/results/exp_032_graduation_remedy_scope_v1'
SCOPE_SHA='6f9f88f81315bbfdda2da1c7a7c0c29577ab5e0a0fec9039e5b442282918d83e'
BASE_CI_SHA='4aa655a4e24ce1650e11f53cd8712c73c319630c'
OLD_LEDGER=ROOT/'experiments/runs/g3_main_scope_20261029_d/budget.sqlite'
LIMITS=BudgetLimits(60,0,0)
TESTS=('tests/test_remedy_validation.py','tests/test_graduation_remedy_execution.py')
EXTRA_SOURCES=('src/graduation/remedy_validation.py','experiments/exp_033_graduation_remedy.py',
               'src/ai_workflow/research_controller.py')


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):
    p=Path(p);temporary=p.with_suffix(p.suffix+'.tmp');temporary.write_bytes(encoded(v));temporary.replace(p)
def old_ledger_sha():return sha(OLD_LEDGER)


def sources():
    result=dict(read(PROPOSAL/'protocol.json')['source_hashes'])
    for name in result:
        if sha(ROOT/name)!=result[name]:raise ValueError('Approved source changed: '+name)
    for name in EXTRA_SOURCES:
        result[name]=sha(ROOT/name)
    return result


def observed_sources():
    names=set(read(PROPOSAL/'protocol.json')['source_hashes'])|set(EXTRA_SOURCES)
    return {name:sha(ROOT/name) for name in sorted(names)}


def check_authorization(proposal,review,recorded_review_dir):
    proposal,review=Path(proposal),Path(review);a=read(review/'approval.json')
    if (a.get('kind')!='ACTUAL_USER_AUTHORIZATION' or a.get('scope_sha256')!=SCOPE_SHA
            or any(a.get(k) is not True for k in ('scope_approved','new_budget_approved','native_execution_approved'))
            or a.get('packet_manifest_sha256')!=sha(proposal/'manifest.json')
            or a.get('raw_authorization_sha256')!=sha(review/'raw_authorization.json')):
        raise ValueError('Actual content-bound scope and new-budget authorization required')
    if a.get('recorded_review_dir')!=recorded_review_dir:
        raise ValueError('Approval cannot be moved to obtain another attempt')
    raw=read(review/'raw_authorization.json')
    if (raw.get('questionItemId')!='["request_user_input_async","call_abf95b525fbb402ab0a44191fe83cfdf",0]'
            or '6f9f88f8' not in raw.get('question','')
            or raw.get('answer')!='批准该范围与新60秒预算，按条件实施并执行一次'):
        raise ValueError('The raw human reply did not approve this execution')
    constraints={'planned_solver_calls':14,'max_active_seconds':60,'max_time_in_seconds':1.,
        'num_search_workers':1,'random_seed':42,'model_calls':0,'attempts':1,'formal_G3_rerun':False,'RL_training':False}
    if encoded(a.get('constraints'))!=encoded(constraints):raise ValueError('Approved execution constraints changed')
    return a


def review_id(review):
    review=Path(review).resolve()
    try:return review.relative_to(ROOT).as_posix()
    except ValueError:return review.as_posix()


def approval(proposal,review):
    review=Path(review)
    return check_authorization(proposal,review,review_id(review))


def check_ci(ci):
    if ci.get('headSha')!=BASE_CI_SHA or ci.get('conclusion')!='success' or ci.get('status')!='completed':
        raise ValueError('Required4aa655aCI has not passed')


def validate(review):
    review=Path(review);review.mkdir(parents=True,exist_ok=True);before=sources()
    test_hashes={name:sha(ROOT/name) for name in TESTS}
    log=review/('validation-'+digest(before)[:12]+'.log')
    if log.exists():raise FileExistsError('Preserve each validation attempt')
    with log.open('wb') as handle:
        process=subprocess.run([sys.executable,'-m','pytest',*TESTS,'-q'],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT)
    text=log.read_text(encoding='utf-8',errors='replace')
    matches=re.findall(r'(\d+) passed(?:, \d+ (?:warnings?|skipped|deselected))* in [^\r\n]+',text)
    if (process.returncode!=0 or not matches or int(matches[-1])<18 or before!=sources()
            or test_hashes!={name:sha(ROOT/name) for name in TESTS}):
        raise ValueError('Focused execution validation failed or sources changed; see '+str(log))
    record=review/(log.stem+'.json')
    write(record,{'status':'PASSED','source_hashes':before,'test_hashes':test_hashes,
        'exit_code':process.returncode,'passed':int(matches[-1]),'log_name':log.name,'log_sha256':sha(log),
        'runtime':runtime_identity()})
    return record


def full_gate(proposal,review,validation,*,worker_mode=False):
    proposal,review,validation=Path(proposal),Path(review),Path(validation)
    approval(proposal,review);scope.recheck(proposal);bundle={k:read(proposal/(k+'.json')) for k in ('protocol','inputs','planned_runs')}
    if digest(bundle)!=SCOPE_SHA:raise ValueError('Wrong approved proposal')
    if validation.resolve().parent!=review.resolve():raise ValueError('Validation record must stay in its review folder')
    current=sources();v=read(validation)
    if (v.get('status')!='PASSED' or v.get('source_hashes')!=current or type(v.get('exit_code')) is not int or v.get('exit_code')!=0
            or type(v.get('passed')) is not int or v['passed']<18
            or v.get('test_hashes')!={name:sha(ROOT/name) for name in TESTS}
            or Path(v['log_name']).name!=v['log_name'] or sha(validation.parent/v['log_name'])!=v['log_sha256']):
        raise ValueError('Missing current-source focused validation')
    log=(validation.parent/v['log_name']).read_text(encoding='utf-8',errors='replace')
    if not re.search(rf'\b{v["passed"]} passed(?:, \d+ (?:warnings?|skipped|deselected))* in ',log):
        raise ValueError('Validation count does not match log')
    review_record=read(review/'code_review.json')
    if review_record.get('status')!='NO_IMPORTANT_FINDINGS' or review_record.get('source_hashes')!=current:
        raise ValueError('Current execution entry must pass its independent review')
    check_ci(read(review/'base_ci.json'))
    runtime=runtime_identity();required=bundle['protocol']['required_runtime']
    if v.get('runtime')!=runtime:raise ValueError('Validation and execution runtime differ')
    if runtime['ortools']!=required['ortools'] or '.'.join(map(str,sys.version_info[:3]))!=required['python']:
        raise ValueError('Approved Python/OR-Tools versions differ')
    expected_env=Path(os.environ.get('FJSP_CONDA_ENV',str(ROOT/'.conda-env'))).resolve()
    if not worker_mode and Path(sys.executable).resolve().parent!=expected_env:raise ValueError('Use the dedicated Conda environment')
    if old_ledger_sha()!=bundle['protocol']['original_locked_ledger_sha256']:
        raise ValueError('Original locked ledger changed; never replace or unlock it')
    return bundle


def read_budget(review):
    path=Path(review)/'budget.sqlite'
    if not path.is_file() or path.is_symlink() or any(Path(str(path)+x).exists() for x in ('-wal','-shm','-journal')):
        raise ValueError('Missing or interrupted new ledger; never initialize while reading')
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1',uri=True)
    try:
        records=db.execute('SELECT id,limits_json,active_seconds,provider_calls,output_tokens_reserved FROM workflow_budget').fetchall()
        rows=db.execute('SELECT id,reserved_seconds,finished_seconds FROM workflow_segments ORDER BY id').fetchall()
    except sqlite3.Error as exc:raise ValueError('Invalid new ledger') from exc
    finally:db.close()
    if (len(records)!=1 or records[0][0]!=1 or records[0][1]!=json.dumps(asdict(LIMITS),sort_keys=True)
            or records[0][3:]!=(0,0) or not rows):raise ValueError('New budget limits changed')
    total=0.;reserved=0.;segments=[]
    for index,(identifier,amount,finished) in enumerate(rows,1):
        if identifier!=index or amount!=60-total or amount<=0:raise ValueError('New budget sequence or reservation changed')
        if finished is None:
            if index!=len(rows):raise ValueError('Segment follows unfinished reservation')
            reserved=amount
        elif type(finished) not in (int,float) or not math.isfinite(finished) or finished<0:
            raise ValueError('Invalid active duration')
        else:total+=finished
        segments.append({'id':identifier,'reserved_seconds':amount,'finished_seconds':finished})
    if total!=records[0][2]:raise ValueError('New budget charge differs from segments')
    return {'limits':asdict(LIMITS),'active_seconds':total,'active_seconds_reserved':reserved,
        'remaining_active_seconds':max(0.,60-total-reserved),'segments':segments,'model_calls':0}


def initial(bundle):
    return {'status':'DEVELOPMENT_ONLY','rows':[{**r,'status':'NOT_RUN','capture_sha256':None} for r in bundle['planned_runs']]}


def copy_context(out,proposal,review,validation,bundle):
    shutil.copytree(proposal,out/'approved_scope')
    (out/'authorization').mkdir();(out/'validation').mkdir();(out/'capture_sources').mkdir()
    for name in ('approval.json','raw_authorization.json','attempt.json'):shutil.copyfile(review/name,out/'authorization'/name)
    observed=observed_sources()
    for name in set(observed)|set(TESTS):
        target=out/'capture_sources'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    write(out/'source_hashes.json',observed);write(out/'runtime.json',runtime_identity())
    write(out/'context.json',{'review_dir':read(review/'approval.json')['recorded_review_dir'],
        'validation_record':validation.name,'scope_sha256':SCOPE_SHA,'old_ledger_sha256':old_ledger_sha()})
    for name in ('code_review.json','base_ci.json'):
        if (review/name).is_file():shutil.copyfile(review/name,out/'validation'/name)
    if validation.is_file():
        shutil.copyfile(validation,out/'validation'/validation.name)
        try:log=read(validation)['log_name']
        except (ValueError,KeyError,TypeError):return
        if isinstance(log,str) and Path(log).name==log and (validation.parent/log).is_file():
            shutil.copyfile(validation.parent/log,out/'validation'/log)


def review_hashes(review,validation):
    review,validation=Path(review),Path(validation)
    paths=[review/n for n in ('approval.json','raw_authorization.json','attempt.json','code_review.json','base_ci.json')]
    paths.extend([validation,validation.parent/read(validation)['log_name']])
    return {str(p.resolve()):sha(p) for p in paths}


def _lease(payload):
    out,review=Path(payload['output_dir']).resolve(),Path(payload['review_dir']).resolve()
    path=review/'worker_lease.json'
    if sha(path)!=payload['lease_sha256']:raise ValueError('Execution lease changed')
    lease=read(path);parent=int(sys.argv[1]) if len(sys.argv)>1 and sys.argv[1].isdigit() else -1
    if (lease['parent_pid']!=parent or parent!=os.getppid() or lease['output_dir']!=str(out)
            or lease['deadline']!=payload['deadline'] or not time.monotonic()<lease['deadline']<=time.monotonic()+45
            or lease['sources']!=sources() or lease['runtime']!=runtime_identity()
            or lease['approval_sha256']!=sha(review/'approval.json')
            or lease['ledger_sha256']!=sha(review/'budget.sqlite') or lease['old_ledger_sha256']!=old_ledger_sha()):
        raise ValueError('Execution parent, source, runtime or ledger identity changed')
    validation_name=lease['validation_name']
    if Path(validation_name).name!=validation_name:raise ValueError('Invalid validation filename')
    if lease['review_files']!=review_hashes(review,review/validation_name):
        raise ValueError('Execution approval or validation set changed')
    marker=read(review/'attempt.json')
    if (marker.get('scope_sha256')!=SCOPE_SHA or type(marker.get('attempt')) is not int or marker['attempt']!=1
            or marker.get('output_dir')!=str(out) or marker.get('approval_sha256')!=sha(review/'approval.json')
            or marker.get('review_dir')!=read(review/'approval.json')['recorded_review_dir']):
        raise ValueError('Single-attempt ownership marker changed')
    admitted=read(out/'admission.json')
    if (admitted.get('admitted') is not True or admitted.get('validation_record')!=validation_name
            or lease['admission_sha256']!=sha(out/'admission.json')):
        raise ValueError('Worker has not passed the conditional execution gate')
    state=read_budget(review)
    if state['segments'][-1]['id']!=lease['segment'] or state['segments'][-1]['finished_seconds'] is not None:
        raise ValueError('Worker no longer owns its reserved segment')
    expected_files=read(out/'approved_scope/manifest.json')['files_sha256']|{'manifest.json':sha(out/'approved_scope/manifest.json')}
    if lease['packet_files']!=expected_files:raise ValueError('Execution input file set changed')
    for name,h in expected_files.items():
        if sha(out/'approved_scope'/name)!=h:raise ValueError('Approved execution input changed')
    try:
        with _exclusive_lock(review):pass
    except ValueError as exc:
        if str(exc)!='Controller is already running':raise
    else:raise ValueError('Execution parent lock was released')
    if time.monotonic()>=payload['deadline']:raise TimeoutError('Lease check exceeded worker deadline')
    return lease


def worker(payload):
    calls=0
    if (not isinstance(payload,dict) or set(payload)!={'purpose','deadline','output_dir','review_dir','lease_sha256'}
            or payload['purpose']!='APPROVED_REMEDY_ONLY' or type(payload['deadline']) not in (int,float)
            or not math.isfinite(payload['deadline'])):
        return {'status':'REJECTED_PAYLOAD','attempted_requests':0}
    try:
        if time.monotonic()>=payload['deadline']:raise TimeoutError('Worker deadline already expired')
        lease=_lease(payload);out=Path(payload['output_dir']);packet=out/'approved_scope'
        full_gate(packet,Path(payload['review_dir']),Path(payload['review_dir'])/lease['validation_name'],worker_mode=True)
        bundle={k:read(packet/(k+'.json')) for k in ('protocol','inputs','planned_runs')}
        approval(packet,Path(payload['review_dir']))
        state=read(out/'state.json')
        if state!=initial(bundle):raise ValueError('Worker cannot resume or change request denominator')
        cases={c['case_id']:c for c in bundle['inputs']};(out/'captures').mkdir()
        for request,row in zip(bundle['planned_runs'],state['rows']):
            _lease(payload);row['status']='RUNNING';write(out/'state.json',state);calls+=1
            result=capture_configured(cases[request['case_id']],request['mode'],request['cp_model_presolve'])
            path=out/'captures'/f"{request['sequence']:04d}.json";write(path,result)
            row.update(status='CAPTURED',capture_sha256=sha(path));write(out/'state.json',state)
            recheck_configured(result,cases[request['case_id']],request['mode'],request['cp_model_presolve'])
            if result['execution_kind']!='NATIVE_DEVELOPMENT_DIAGNOSTIC':raise ValueError('Synthetic capture cannot be native')
            if time.monotonic()>=payload['deadline']:raise TimeoutError('Capture returned after worker deadline')
        return {'status':'CAPTURED','attempted_requests':calls}
    except TimeoutError as exc:return {'status':'DEADLINE_EXHAUSTED','attempted_requests':calls,'error':str(exc)[:1000]}
    except Exception as exc:return {'status':'DEVELOPMENT_FAILED','attempted_requests':calls,'error':f'{type(exc).__name__}: {str(exc)[:1000]}'}


def collect(out,bundle):
    state=read(out/'state.json');planned=initial(bundle)['rows'];cases={c['case_id']:c for c in bundle['inputs']};reports=[]
    if len(state['rows'])!=14:raise ValueError('Execution denominator changed')
    for row,request in zip(state['rows'],planned):
        if any(row[k]!=v for k,v in request.items() if k not in ('status','capture_sha256')):raise ValueError('Request identity changed')
        if row['status']=='CAPTURED':
            path=out/'captures'/f"{row['sequence']:04d}.json"
            if sha(path)!=row['capture_sha256']:raise ValueError('Saved capture changed')
            capture=read(path)
            if capture['execution_kind']!='NATIVE_DEVELOPMENT_DIAGNOSTIC':raise ValueError('Synthetic evidence in native output')
            try:
                report=recheck_configured(capture,cases[row['case_id']],row['mode'],row['cp_model_presolve'])
                report['capture_validation']='PASS'
            except ValueError as exc:
                report={'case_id':row['case_id'],'mode':row['mode'],'cp_model_presolve':row['cp_model_presolve'],
                    'baseline_status':'INVALID_EVIDENCE','solver_status':None,'objective_consistent':False,
                    'error_reproduced':False,'capture_validation':'INVALID','raw_schedule_status':'INVALID',
                    'error':str(exc)[:1000],'accepted_for_research':False}
            reports.append({**report,'sequence':row['sequence'],'group':row['group']})
        elif row['status'] not in ('NOT_RUN','RUNNING','INTERRUPTED'):raise ValueError('Unknown execution row status')
    originals=[r for r in reports if r['group']=='historical_error_counterfactual' and r['cp_model_presolve']]
    alternatives=[r for r in reports if r['group']=='historical_error_counterfactual' and not r['cp_model_presolve']]
    controls=[r for r in reports if r['group']=='enumerable_control']
    control=cases[bundle['inputs'][-1]['case_id']]
    oracle={m:enumerate_parallel_maintenance(_data(control),mode=m).total_tardiness for m in ('fixed','joint')}
    controls_ok=len(controls)==4 and oracle=={'fixed':4,'joint':0} and all(
        r['baseline_status']=='ACCEPTED' and r['solver_status']=='OPTIMAL' and r['objective_consistent']
        and r['derived_tardiness']==oracle[r['mode']] for r in controls)
    reproduced=sum(r['error_reproduced'] for r in originals)
    remedy_ok=sum(r['baseline_status']=='ACCEPTED' and r['objective_consistent'] for r in alternatives)
    invalid=sum(r['capture_validation']!='PASS' for r in reports)
    return {'planned_requests':14,'captured_requests':len(reports),'rows':reports,'reproduced_original_errors':reproduced,
        'presolve_off_accepted':remedy_ok,'tiny_controls_ok':controls_ok,'enumeration':oracle,
        'invalid_captures':invalid,'confirmed_solver_calls':len(reports)-invalid,
        'counterfactual_status':'FAILED_EVIDENCE' if invalid else classify_pairs(reproduced,remedy_ok,controls_ok) if len(reports)==14 else 'INCOMPLETE',
        'accepted_for_research':False,'research_status':'not_achieved','model_calls':0,'new_formal_G3_calls':0,
        'automatic_retry':False,'resume':False}


def check_receipt(receipt,captured):
    count=receipt.get('attempted_requests')
    if receipt.get('status')=='SUPERVISOR_ERROR':
        if count is not None or not receipt.get('error'):raise ValueError('Malformed unknown-call supervisor failure')
        return
    if receipt.get('status')=='PREFLIGHT_REJECTED':
        if type(count) is not int or count!=0 or captured!=0 or not receipt.get('error'):
            raise ValueError('Preflight rejection cannot contain solver observations')
        return
    if (type(count) is not int or not captured<=count<=14
            or receipt.get('status') not in ('CAPTURED','DEADLINE_EXHAUSTED','DEVELOPMENT_FAILED')
            or receipt['status']=='CAPTURED' and count!=14):
        raise ValueError('Worker receipt does not match complete request accounting')


def guard_paths(review,out):
    runtime_root=ROOT/'experiments/runs'
    for path in (review,out):
        if ROOT in path.parents and runtime_root not in path.parents:
            raise ValueError('Execution must not write into tracked sources or historical results')
        for ancestor in path.parents:
            if ancestor in (ROOT,runtime_root):break
            if ancestor!=review and any((ancestor/n).exists() for n in ('manifest.json','archive_manifest.json','state.json','budget.sqlite')):
                raise ValueError('Execution output cannot be nested in existing evidence')


def write_report(out,summary,budget):
    write(out/'summary.json',summary)
    lines=['毕设预处理开关：一次有界开发验证',f'范围：{SCOPE_SHA}',
        f"执行状态：{summary['status']}；反事实判断：{summary.get('counterfactual_status','未形成判断')}",
        f"计划14次，已捕获{summary.get('captured_requests',0)}份；确认Solve调用{summary.get('confirmed_solver_calls',0)}次。",
        f"原配置复现{summary.get('reproduced_original_errors',0)}/5；关闭预处理后接受{summary.get('presolve_off_accepted',0)}/5；小例控制通过：{summary.get('tiny_controls_ok',False)}。",
        f"新预算60秒，累计计账（含预付）{budget['active_seconds']:.3f}秒，预留{budget['active_seconds_reserved']:.3f}秒。剩余额度不授权额外求解。",
        '14条计划分母保留；未完成、错误和缺失值不填0。不自动重试、不恢复、不运行正式G3网格或RL。',
        '研究仍未达成。本次仅检查有限请求中的目标/返回解一致性，不证明通用正确、普遍性能优势或特定内部规则因果。',
        '旧600秒账本及正式结果不在本次写入范围。']
    if summary.get('error'):lines.append('失败原因：'+summary['error'])
    for r in summary.get('rows',[]):
        show=lambda k:'NA' if r.get(k) is None else str(r[k])
        lines.append(f"{r['sequence']:02d} {r['mode']} presolve={r['cp_model_presolve']} "
            f"状态={show('solver_status')}/{r['baseline_status']} 报告目标={show('reported_objective')} "
            f"重算延期={show('derived_tardiness')} 下界={show('bound')}")
    (out/'summary.txt').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))


def run_once(proposal,review,out,validation,*,started_at=None):
    entered=time.monotonic() if started_at is None else started_at
    proposal,review,out,validation=map(lambda p:Path(p).resolve(),(proposal,review,out,validation))
    if out.exists() or (review/'budget.sqlite').exists() or (review/'attempt.json').exists():raise FileExistsError('One attempt only; never overwrite or resume')
    guard_paths(review,out)
    if out==review or out in review.parents or review in out.parents:raise ValueError('Control lock must stay outside artifacts')
    approval(proposal,review)
    with _exclusive_lock(review):
        if (review/'attempt.json').exists():raise FileExistsError('Attempt already consumed')
        decision=read(review/'approval.json')
        with (review/'attempt.json').open('xb') as f:f.write(encoded({'scope_sha256':SCOPE_SHA,'attempt':1,'output_dir':str(out),
            'approval_sha256':sha(review/'approval.json'),'review_dir':decision.get('recorded_review_dir','TEST_ONLY')}))
        budget=RunBudget(review/'budget.sqlite',LIMITS);segment,_=budget.reserve_active_segment()
        out.mkdir(parents=True);bundle={k:read(proposal/(k+'.json')) for k in ('protocol','inputs','planned_runs')}
        write(out/'state.json',initial(bundle));old=old_ledger_sha();deadline=entered+55
        dispatched=False
        write(out/'admission.json',{'admitted':False,'validation_record':validation.name})
        try:
            if time.monotonic()>=deadline:raise BudgetExceeded('Approved preflight deadline exhausted')
            copy_context(out,proposal,review,validation,bundle)
            bundle=full_gate(proposal,review,validation)
            write(out/'admission.json',{'admitted':True,'validation_record':validation.name})
            available=min(45.,deadline-time.monotonic())
            if available<=0:raise BudgetExceeded('No execution time left')
            worker_deadline=time.monotonic()+available
            write(review/'worker_lease.json',{'parent_pid':os.getpid(),'output_dir':str(out),'deadline':worker_deadline,
                'sources':sources(),'runtime':runtime_identity(),'approval_sha256':sha(review/'approval.json'),
                'ledger_sha256':sha(review/'budget.sqlite'),'old_ledger_sha256':old,'segment':segment,
                'review_files':review_hashes(review,validation),
                'validation_name':validation.name,'admission_sha256':sha(out/'admission.json'),
                'packet_files':read(proposal/'manifest.json')['files_sha256']|{'manifest.json':sha(proposal/'manifest.json')}})
            dispatched=True
            receipt=supervised_json_process(Path(__file__).resolve(),{'purpose':'APPROVED_REMEDY_ONLY','deadline':worker_deadline,
                'output_dir':str(out),'review_dir':str(review),'lease_sha256':sha(review/'worker_lease.json')},available)
            write(out/'worker_receipt.json',receipt)
            if time.monotonic()>=deadline:raise BudgetExceeded('Late execution evidence')
            summary=collect(out,bundle)
            check_receipt(receipt,summary['captured_requests'])
            if old_ledger_sha()!=old:raise ValueError('Original locked ledger changed')
            summary.update(status='DEVELOPMENT_CAPTURED' if receipt['status']=='CAPTURED' and summary['captured_requests']==14 and not summary['invalid_captures'] else 'DEVELOPMENT_PARTIAL',
                           attempted_requests=receipt['attempted_requests'])
        except Exception as exc:
            error=f'{type(exc).__name__}: {str(exc)[:1000]}'
            if not (out/'worker_receipt.json').exists():
                write(out/'worker_receipt.json',{'status':'SUPERVISOR_ERROR' if dispatched else 'PREFLIGHT_REJECTED',
                    'attempted_requests':None if dispatched else 0,'error':error})
            state=read(out/'state.json');state['status']='DEVELOPMENT_FAILED'
            for row in state['rows']:
                if row['status']=='RUNNING':row['status']='INTERRUPTED'
            write(out/'state.json',state)
            try:summary=collect(out,bundle)
            except Exception as check_error:
                summary={'planned_requests':14,'captured_requests':sum(r['status']=='CAPTURED' for r in state['rows']),
                    'accepted_for_research':False,'research_status':'not_achieved','evidence_error':str(check_error)[:1000]}
            summary.update(status='DEVELOPMENT_FAILED',attempted_requests=read(out/'worker_receipt.json')['attempted_requests'],
                           automatic_retry=False,error=error)
        finished=time.monotonic();budget.finish_active_segment(segment,finished-entered)
        final_deadline=min(entered+60,finished+5)
        try:
            extra,remaining=budget.reserve_active_segment()
            if remaining<5:raise BudgetExceeded('Insufficient receipt allowance')
            budget.finish_active_segment(extra,5.)
            shutil.copyfile(review/'budget.sqlite',out/'budget.sqlite');snapshot=read_budget(out)
            write(out/'budget_snapshot.json',snapshot);write_report(out,summary,snapshot)
            write(out/'manifest.json',{'status':summary['status'],'source_hashes':observed_sources(),
                'files_sha256':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
                    if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}})
            if time.monotonic()>=final_deadline:raise BudgetExceeded('Receipt deadline exhausted')
        except Exception as exc:
            try:budget.reserve_active_segment()
            except BudgetExceeded:pass
            summary.update(status='DEVELOPMENT_FAILED',automatic_retry=False,failure_phase='FINALIZATION',
                           error=f'{type(exc).__name__}: {str(exc)[:1000]}')
            shutil.copyfile(review/'budget.sqlite',out/'budget.sqlite');snapshot=read_budget(out)
            write(out/'budget_snapshot.json',snapshot);write_report(out,summary,snapshot)
            write(out/'manifest.json',{'status':summary['status'],'source_hashes':observed_sources(),
                'files_sha256':{p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
                    if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}})
        return summary


def verify_context(out,manifest):
    out=Path(out);packet=out/'approved_scope'
    bundle={k:read(packet/(k+'.json')) for k in ('protocol','inputs','planned_runs')}
    if digest(bundle)!=SCOPE_SHA:raise ValueError('Saved scope differs from the actual approval')
    packet_index=read(packet/'manifest.json')
    actual={p.relative_to(packet).as_posix():sha(p) for p in packet.rglob('*')
            if p.is_file() and p.relative_to(packet).as_posix()!='manifest.json'}
    if actual!=packet_index['files_sha256'] or packet_index['scope_sha256']!=SCOPE_SHA:
        raise ValueError('Saved approved scope file closure differs')
    expected_names=set(bundle['protocol']['source_hashes'])|set(EXTRA_SOURCES)
    source_map=manifest.get('source_hashes')
    if (not isinstance(source_map,dict) or set(source_map)!=expected_names
            or source_map!=read(out/'source_hashes.json')):
        raise ValueError('Missing or changed exact execution source map')
    expected_snapshots=expected_names|set(TESTS)
    actual_snapshots={p.relative_to(out/'capture_sources').as_posix() for p in (out/'capture_sources').rglob('*') if p.is_file()}
    if actual_snapshots!=expected_snapshots:raise ValueError('Execution source/test snapshot set differs')
    for name,h in source_map.items():
        if not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h) or sha(out/'capture_sources'/name)!=h:
            raise ValueError('Captured source snapshot changed')
    context=read(out/'context.json');admission=read(out/'admission.json')
    authorization=check_authorization(packet,out/'authorization',context['review_dir'])
    marker=read(out/'authorization/attempt.json')
    if (marker.get('scope_sha256')!=SCOPE_SHA or type(marker.get('attempt')) is not int or marker['attempt']!=1
            or marker.get('approval_sha256')!=sha(out/'authorization/approval.json')
            or marker.get('review_dir')!=context['review_dir'] or context['scope_sha256']!=SCOPE_SHA
            or context['old_ledger_sha256']!=bundle['protocol']['original_locked_ledger_sha256']):
        raise ValueError('Saved one-attempt authorization identity differs')
    budget=read_budget(out)
    if budget!=read(out/'budget_snapshot.json'):raise ValueError('Saved budget differs from the actual ledger image')
    if type(admission.get('admitted')) is not bool or admission['validation_record']!=context['validation_record']:
        raise ValueError('Admission receipt changed')
    if admission['admitted']:
        for name,h in bundle['protocol']['source_hashes'].items():
            if source_map[name]!=h or sha(ROOT/name)!=h:raise ValueError('Approved baseline source differs')
        record_name=context['validation_record']
        if Path(record_name).name!=record_name:raise ValueError('Invalid saved validation filename')
        v=read(out/'validation'/record_name);review=read(out/'validation/code_review.json')
        if (v.get('status')!='PASSED' or v.get('source_hashes')!=source_map
                or type(v.get('exit_code')) is not int or v['exit_code']!=0
                or type(v.get('passed')) is not int or v['passed']<18
                or v.get('test_hashes')!={n:sha(out/'capture_sources'/n) for n in TESTS}
                or review.get('status')!='NO_IMPORTANT_FINDINGS' or review.get('source_hashes')!=source_map):
            raise ValueError('Saved test/review gate is not bound to captured sources')
        log_name=v['log_name']
        if Path(log_name).name!=log_name or sha(out/'validation'/log_name)!=v['log_sha256']:
            raise ValueError('Saved validation log changed')
        if not re.search(rf'\b{v["passed"]} passed(?:, \d+ (?:warnings?|skipped|deselected))* in ',
                         (out/'validation'/log_name).read_text(encoding='utf-8',errors='replace')):
            raise ValueError('Saved validation log does not report the captured count')
        check_ci(read(out/'validation/base_ci.json'))
        runtime=read(out/'runtime.json');required=bundle['protocol']['required_runtime']
        if (runtime!=v.get('runtime') or runtime.get('ortools')!=required['ortools']
                or runtime.get('python','').split()[0]!=required['python']):
            raise ValueError('Saved runtime differs from the approved validation')
    return bundle,admission,budget


def recheck(out):
    out=Path(out);m=read(out/'manifest.json')
    actual={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*') if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}
    if m['files_sha256']!=actual:raise ValueError('Execution artifact closure changed')
    bundle,admission,budget=verify_context(out,m)
    derived=collect(out,bundle);saved=read(out/'summary.json');receipt=read(out/'worker_receipt.json')
    check_receipt(receipt,derived['captured_requests'])
    expected='DEVELOPMENT_CAPTURED' if receipt['status']=='CAPTURED' and derived['captured_requests']==14 and not derived['invalid_captures'] else 'DEVELOPMENT_PARTIAL'
    if (saved.get('status') not in (expected,'DEVELOPMENT_FAILED') or m['status']!=saved['status']
            or any(saved.get(k)!=v for k,v in derived.items())
            or saved.get('attempted_requests')!=receipt['attempted_requests']):raise ValueError('Execution summary differs from captures')
    if saved['status']=='DEVELOPMENT_FAILED' and (not saved.get('error') or saved.get('automatic_retry') is not False):
        raise ValueError('Missing explicit failed-attempt reason')
    if receipt['status'] in ('SUPERVISOR_ERROR','PREFLIGHT_REJECTED') and saved['status']!='DEVELOPMENT_FAILED':
        raise ValueError('Process/preflight failure cannot be a completed capture')
    if not admission['admitted'] and (receipt['status']!='PREFLIGHT_REJECTED' or derived['captured_requests']):
        raise ValueError('A rejected preflight cannot have executed solver requests')
    if saved['status']=='DEVELOPMENT_CAPTURED' and (budget['active_seconds_reserved'] or budget['active_seconds']>60
            or len(budget['segments'])!=2 or budget['segments'][-1]['finished_seconds']!=5.):
        raise ValueError('A completed capture needs a settled bounded budget')
    return {'status':'READ_ONLY_REMEDY_RECHECK_PASSED','captures':derived['captured_requests'],
        'recorded_batch_status':saved['status'],'counterfactual_status':derived['counterfactual_status'],
        'new_solver_calls':0,'accepted_for_research':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);subs=parser.add_subparsers(dest='action',required=True)
    valid=subs.add_parser('validate');valid.add_argument('--review-dir',type=Path,required=True)
    for action in ('preflight','run'):
        p=subs.add_parser(action);p.add_argument('--proposal-dir',type=Path,default=PROPOSAL)
        p.add_argument('--review-dir',type=Path,required=True);p.add_argument('--validation-record',type=Path,required=True)
        if action=='run':p.add_argument('--output-dir',type=Path,required=True)
    p=subs.add_parser('recheck');p.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.action=='validate':result={'validation_record':str(validate(args.review_dir))}
    elif args.action=='preflight':full_gate(args.proposal_dir,args.review_dir,args.validation_record);result={'status':'READY_NOT_EXECUTED','solver_calls':0}
    elif args.action=='run':result=run_once(args.proposal_dir,args.review_dir,args.output_dir,args.validation_record,started_at=ENTERED)
    else:result=recheck(args.output_dir)
    print(json.dumps(result,ensure_ascii=False));return 1 if result.get('status') in ('DEVELOPMENT_FAILED','DEVELOPMENT_PARTIAL') else 0


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1].isdigit():print(json.dumps(worker(json.loads(sys.stdin.read(65536)))))
    else:raise SystemExit(main())
