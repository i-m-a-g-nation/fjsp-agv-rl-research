"""Read-only main-result mathematics and a separately budgeted conclusion packet.

No solver calls. --recheck ARCHIVE replays a saved archive without modifying it.
"""
import time
ENTERED=time.monotonic()
import collections
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT))
from src.ai_workflow.graduation_main_backend import recheck_main_run
from src.ai_workflow.graduation_main_budget import run_main_phase
from src.ai_workflow.graduation_main_evidence import load_scope_context
from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.review import make_review_request,artifact_hash
from src.graduation.reference_protocol import encoded,digest

REVIEW=ROOT/'experiments/runs/g3_main_review_17bc1aa7_attempt2'
RUN=ROOT/'experiments/runs/g3_main_formal_20261029_v2'
PACKET=ROOT/'experiments/runs/g3_main_conclusion_20261029_v1'
FACTORS=('num_tasks','num_machines','alpha_percent','beta_percent','tau_percent','fixed_policy')
MATERIALS=('inputs.json','comparison.json','conditions.csv','size_groups.csv','independent_check.json',
           'authorization_receipts.json','provenance.json','budget_snapshot.json','conclusion_summary.txt','analysis.py')

def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,value):
    p=Path(p);temp=p.with_suffix(p.suffix+'.tmp');temp.write_bytes(encoded(value));temp.replace(p)
def close(a,b):return math.isclose(a,b,rel_tol=0,abs_tol=1e-12)

def plan_math(case,row):
    """Independent integer interval/tardiness arithmetic, no project checker."""
    data=case['data'];payload=row['payload'];m=data['num_machines']
    tasks={t['job_id']:t for t in data['tasks']}
    reqs={r['machine_id']:r for r in data['maintenance']}
    production=payload['records'];maintenance=payload['maintenance_records']
    assert len(tasks)==len(data['tasks']) and sorted(tasks)==list(range(len(tasks)))
    assert sorted(reqs)==list(range(m))
    assert sorted(r['job_id'] for r in production)==sorted(tasks)
    assert sorted(r['machine_id'] for r in maintenance)==list(range(m))
    intervals={i:[] for i in range(m)};total=0
    for r in production:
        assert all(type(r[k]) is int for k in ('job_id','op_id','machine_id','start','end','processing_time'))
        t=tasks[r['job_id']]
        assert r['op_id']==0 and r['start']>=0 and 0<=r['machine_id']<m
        assert r['end']-r['start']==r['processing_time']==t['processing_time']>0
        total+=max(0,r['end']-t['due_date'])
        intervals[r['machine_id']].append((r['start'],r['end']))
    for r in maintenance:
        assert all(type(r[k]) is int for k in ('machine_id','start','end','duration'))
        q=reqs[r['machine_id']]
        assert q['window_start']<=r['start']<r['end']<=q['window_end']
        assert r['end']-r['start']==r['duration']==q['duration']
        assert row['mode']!='fixed' or r['start']==q['fixed_start']
        intervals[r['machine_id']].append((r['start'],r['end']))
    for values in intervals.values():
        ordered=sorted(values)
        assert all(a[1]<=b[0] for a,b in zip(ordered,ordered[1:]))
    makespan=max(r['end'] for r in production)
    metrics=row['metrics']
    assert all(payload[k]==metrics[k] for k in ('makespan','total_tardiness','solver_status',
        'solver_objective_value','solver_objective_bound','solver_gap','solver_wall_time'))
    assert total==payload['total_tardiness']==metrics['total_tardiness']==metrics['solver_objective_value']
    assert makespan==payload['makespan']==metrics['makespan']
    bound=metrics['solver_objective_bound'];gap=metrics['solver_gap']
    assert all(type(v) in (int,float) and math.isfinite(v) for v in (bound,gap,metrics['solver_wall_time']))
    assert 0<=bound<=total and metrics['solver_wall_time']>=0
    assert close(gap,(total-bound)/max(1.,total))
    assert row['solver_status']==metrics['solver_status'] in ('OPTIMAL','FEASIBLE')
    assert metrics['solver_status']!='OPTIMAL' or bound==total
    return {'total_tardiness':total,'makespan':makespan,'solver_status':row['solver_status'],
            'bound':bound,'gap':gap,'production_records':len(production),'maintenance_records':len(maintenance)}

def stats(cases,rows,pairs,indices):
    selected=[pairs[i] for i in indices];valid=[p for p in selected if p['status']=='COMPLETE']
    counts=collections.Counter(r['status'] for i in indices for r in rows[2*i:2*i+2])
    solver=collections.Counter(r['solver_status'] for i in indices for r in rows[2*i:2*i+2] if r['status']=='ACCEPTED')
    differences=[p['observed_difference'] for p in valid]
    return {'planned_pairs':len(indices),'complete_pairs':len(valid),
        'both_optimal_pairs':sum(p['both_optimal'] for p in valid),
        'strict_positive_observed':sum(d>0 for d in differences),'ties':sum(d==0 for d in differences),
        'negative_observed':sum(d<0 for d in differences),
        'incomplete_pairs':sum(p['status']=='INCOMPLETE' for p in selected),
        'integrity_errors':sum(p['status']=='INTEGRITY_ERROR' for p in selected),
        'accepted_runs':counts['ACCEPTED'],'error_runs':counts['ERROR'],
        'no_schedule_runs':counts['NO_SCHEDULE'],'not_run_runs':counts['NOT_RUN'],'interrupted_runs':counts['INTERRUPTED'],
        'optimal_runs':solver['OPTIMAL'],'feasible_runs':solver['FEASIBLE'],
        'fixed_zero_pairs':sum(rows[2*i]['metrics']['total_tardiness']==0 for i in indices
                               if pairs[i]['status']=='COMPLETE'),
        'positive_optimum_difference_lower_bounds':sum(p['optimum_difference_lower']>0 for p in valid),
        'observed_difference_min':min(differences,default=None),'observed_difference_max':max(differences,default=None)}

def csv_bytes(records):
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(records[0]),lineterminator='\n')
    writer.writeheader();writer.writerows(records);return stream.getvalue().encode('utf-8')

def analyze(folder,cases,check=lambda:None):
    checked=recheck_main_run(folder,cases)
    state=read(folder/'state.json');rows=[];independent=[];errors=[];by_core=collections.defaultdict(list)
    for index,thin in enumerate(state['rows']):
        check();case=cases[index//2];mode=('fixed','joint')[index%2]
        assert (thin['sequence'],thin['case_id'],thin['mode'])==(index,case['case_id'],mode)
        path=folder/'rows'/f'{index:04d}.json'
        if thin['status'] in ('ACCEPTED','NO_SCHEDULE','ERROR'):
            row=read(path);assert sha(path)==thin['trace_sha256']
        else:
            row={'case_id':case['case_id'],'mode':mode,'status':thin['status'],'solver_status':None,
                 'metrics':None,'payload':None,'error':thin['error']}
        assert row['status']==thin['status']
        if row['status']=='ACCEPTED':
            values=plan_math(case,row)
            independent.append({'sequence':index,'case_id':case['case_id'],'mode':mode,'trace_sha256':sha(path),**values})
            if mode=='joint' and row['solver_status']=='OPTIMAL':by_core[case['core_model_hash']].append(values['total_tardiness'])
        else:
            assert row['metrics'] is None and row['payload'] is None
            errors.append({'sequence':index,'case_id':case['case_id'],'mode':mode,'status':row['status'],'error':row['error'],
                           'raw_candidate_available':False})
        rows.append(row)
    assert all(len(set(values))==1 for values in by_core.values())
    for i,pair in enumerate(checked['pairs']):
        check();a,b=rows[2*i:2*i+2]
        if a['status']!='ACCEPTED' or b['status']!='ACCEPTED':
            assert pair['status']=='INCOMPLETE'
            assert all(pair[k] is None for k in ('observed_difference','relative_improvement',
                                                 'optimum_difference_lower','optimum_difference_upper'))
            continue
        fixed,joint=a['metrics'],b['metrics'];d=fixed['total_tardiness']-joint['total_tardiness']
        lo=max(0,fixed['solver_objective_bound']-joint['total_tardiness'])
        hi=fixed['total_tardiness']-joint['solver_objective_bound']
        assert pair['observed_difference']==d and pair['optimum_difference_lower']==lo and pair['optimum_difference_upper']==hi
        assert hi>=lo and (not pair['both_optimal'] or d>=0)
        if fixed['total_tardiness']==0:assert pair['relative_improvement'] is None
        else:assert close(pair['relative_improvement'],d/fixed['total_tardiness'])
    groups={g:stats(cases,rows,checked['pairs'],[i for i,c in enumerate(cases) if c['group']==g])
            for g in ('primary','sensitivity')}
    for name,group in checked['groups'].items():
        assert all(groups[name][k]==value for k,value in group.items())
    cells=collections.defaultdict(list);sizes=collections.defaultdict(list)
    for i,c in enumerate(cases):
        cells[(c['group'],*(c['factors'][f] for f in FACTORS))].append(i)
        sizes[(c['group'],c['factors']['num_tasks'],c['factors']['num_machines'])].append(i)
    conditions=[{'group':key[0],**dict(zip(FACTORS,key[1:])),**stats(cases,rows,checked['pairs'],indices)}
                for key,indices in sorted(cells.items())]
    size_groups=[{'group':key[0],'num_tasks':key[1],'num_machines':key[2],
                  **stats(cases,rows,checked['pairs'],indices)} for key,indices in sorted(sizes.items())]
    report={'version':1,'run_status':checked['status'],'planned_pairs':len(cases),'planned_calls':len(rows),
        'accepted_runs':len(independent),'completed_pairs':checked['completed_pairs'],
        'status_counts':checked['status_counts'],'solver_status_counts':dict(collections.Counter(r['solver_status'] for r in rows if r['status']=='ACCEPTED')),
        'groups':groups,'conditions':conditions,'size_groups':size_groups,'rejected_or_missing':errors,
        'base_workloads':checked['base_workloads'],'unique_core_models':checked['unique_core_models'],
        'independent_backend_review':'not_completed_quota_limit','scientific_claim':'accepted_subset_descriptive_only',
        'failure_root_cause':'not_established_from_saved_records; compound exception, no rejected candidate/diagnostics retained',
        'per_request_end_to_end_time_available':False,
        'runtime_comparison_claimed':False,
        'research_status':'not_achieved'}
    verification={'status':'PASSED_FOR_ACCEPTED_SAVED_PLANS','accepted_plans_checked':len(independent),
        'raw_failed_candidates_checked':0,'unavailable_rejected_or_missing':len(errors),
        'plan_math_calls_project_checker':False,'new_solver_calls':0,
        'joint_optimal_core_groups_checked':len(by_core),'checks':independent}
    return report,verification

def human(report,budget):
    lines=['毕设G3A正式主比较：结论审核（事实确认，非课题验收）',
        f"本次实验状态：{report['run_status']}。计划{report['planned_pairs']}对/{report['planned_calls']}次请求；接受{report['accepted_runs']}份，完整有效配对{report['completed_pairs']}对。",
        f"请求状态：{json.dumps(report['status_counts'],ensure_ascii=False)}；接受结果的求解状态：{json.dumps(report['solver_status_counts'],ensure_ascii=False)}。"]
    for name,title in (('primary','主比较'),('sensitivity','敏感性')):
        g=report['groups'][name]
        lines.append(f"{title}：计划{g['planned_pairs']}对，完整{g['complete_pairs']}对，未完整{g['incomplete_pairs']}对；观察到联合延期更低{g['strict_positive_observed']}对、相同{g['ties']}对、更高{g['negative_observed']}对；两方OPTIMAL {g['both_optimal_pairs']}对。")
    lines.extend([f"{report['accepted_runs']}份接受计划的任务唯一性、加工时长、资源互斥、完整维护窗口、固定时刻、总延期和makespan已由独立标准库算术重算；失败行没有指标或计划，不填零。",
        '5份错误均为“Solver objective/bound disagrees with independent total tardiness”；原始候选与分项诊断未保存，现有档案无法定位具体是哪项不一致。未重跑，也未放宽检查。',
        '4个联合延期更高的限时观察保留，不表示联合模型最优值更差。FEASIBLE不是最优；观察差、最优差区间和固定延期0时的NA分别记录。',
        '已保存接受结果的solver_wall_time和阶段累计账本，未保存逐请求完整端到端耗时，不作运行时性能比较。',
        f"只有{report['base_workloads']}组基础随机工作负载、{report['unique_core_models']}个物理核心，不把240配对当独立样本，不据接受子集宣称统计显著或普遍优势。",
        f"同一原600秒账本累计计账{budget['active_seconds_charged']:.3f}秒，剩余{budget['remaining_active_seconds']:.3f}秒；保留先前启动失败和本次5条失败，0模型调用。",
        '下一步优先补齐求解器拒绝候选的诊断并定位一致性异常，再决定新的验证；本次不修改求解器、重新求解或进入RL调参。',
        '整批后端独立代码审查仍因用量限制未完成；独立计划算术不等于独立代码审查。',
        '请仅确认本次FAILED批次、接受子集和未解决问题的记录；不认可完整G3通过、RL优势、大创物流协同或课题达标。conclusion尚未批准，research_status=not_achieved。'])
    return '\n'.join(lines)+'\n'

def recheck(archive):
    packet=archive/'conclusion';manifest=read(packet/'manifest.json')
    actual={p.name:sha(p) for p in packet.iterdir() if p.is_file() and p.name!='manifest.json'}
    assert actual==manifest['artifacts']
    request=read(packet/'conclusion_review.json')
    assert request['artifact_hash']==artifact_hash({k:v for k,v in request.items() if k!='artifact_hash'})
    assert request['payload']['material_sha256']=={name:sha(packet/name) for name in MATERIALS}
    assert request['payload']['run_manifest_sha256']==sha(archive/'run/manifest.json')
    provenance=read(packet/'provenance.json')
    assert sha(packet/'analysis.py')==provenance['analysis_source_sha256']
    assert sha(packet/'inputs.json')==provenance['input_file_sha256']
    assert read(archive/'run/manifest.json')['source_hashes']==provenance['run_source_hashes']
    report,verification=analyze(archive/'run',read(packet/'inputs.json'))
    assert encoded(report)==encoded(read(packet/'comparison.json'))
    assert encoded(verification)==encoded(read(packet/'independent_check.json'))
    assert csv_bytes(report['conditions'])==(packet/'conditions.csv').read_bytes()
    assert csv_bytes(report['size_groups'])==(packet/'size_groups.csv').read_bytes()
    assert human(report,read(packet/'budget_snapshot.json'))==(packet/'conclusion_summary.txt').read_text(encoding='utf-8')
    return {'status':'READ_ONLY_RECHECK_PASSED','run_status':report['run_status'],
            'accepted_plans_checked':report['accepted_runs'],'conclusion_hash':request['artifact_hash']}

def main():
    if len(sys.argv)==3 and sys.argv[1]=='--recheck':
        print(json.dumps(recheck(Path(sys.argv[2]))));return
    if PACKET.exists():raise FileExistsError('Never overwrite a conclusion packet')
    context=load_scope_context(REVIEW);owned=False
    def work(handle):
        nonlocal owned
        state=read(REVIEW/'state.json')
        assert state['status'] in ('FAILED','BUDGET_EXHAUSTED','CONCLUSION_PREPARATION_REQUIRED')
        assert state['evidence_approved'] is True and state['conclusion_approved'] is False
        owned=True;handle.check()
        report,verification=analyze(RUN,context['cases'],handle.check)
        PACKET.mkdir()
        shutil.copy2(context['scope_dir']/'inputs.json',PACKET/'inputs.json')
        write(PACKET/'comparison.json',report);write(PACKET/'independent_check.json',verification)
        (PACKET/'conditions.csv').write_bytes(csv_bytes(report['conditions']))
        (PACKET/'size_groups.csv').write_bytes(csv_bytes(report['size_groups']))
        write(PACKET/'authorization_receipts.json',{'scope':read(REVIEW/'scope_approval.json'),
            'evidence':read(REVIEW/'evidence_approval.json'),'prior_attempt':read(REVIEW/'prior_attempt.json')})
        write(PACKET/'provenance.json',{'execution_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'run_manifest_sha256':sha(RUN/'manifest.json'),'input_file_sha256':sha(PACKET/'inputs.json'),
            'run_source_hashes':read(RUN/'manifest.json')['source_hashes'],
            'analysis_source_sha256':sha(__file__),'ci':read(ROOT/'.superpowers/sdd/g3-main-managed-ci-verification.json'),
            'prior_failed_archive_manifest_sha256':sha(ROOT/'experiments/results/exp_030_graduation_main_failed_v1/archive_manifest.json')})
        shutil.copy2(__file__,PACKET/'analysis.py');handle.check()
        return report
    def finalize(report,budget,check):
        check();write(PACKET/'budget_snapshot.json',budget)
        (PACKET/'conclusion_summary.txt').write_text(human(report,budget),encoding='utf-8')
        request=make_review_request('conclusion',get_research_contract('graduation').to_dict(),{
            'scope_hash':context['scope_hash'],'evidence_hash':read(RUN/'manifest.json')['evidence_hash'],
            'run_manifest_sha256':sha(RUN/'manifest.json'),
            'material_sha256':{name:sha(PACKET/name) for name in MATERIALS},
            'run_status':report['run_status'],'status_counts':report['status_counts'],'groups':report['groups'],
            'budget_snapshot':budget,'new_solver_calls':0,'model_calls':0,
            'proposed_acceptance':'factual_record_of_failed_batch_and_accepted_subset_only',
            'independent_backend_review':'not_completed_quota_limit','research_status':'not_achieved'})
        write(PACKET/'conclusion_review.json',request)
        write(PACKET/'manifest.json',{'version':1,'status':'WAITING_HUMAN_CONCLUSION',
            'run_status':report['run_status'],'review_hash':request['artifact_hash'],
            'artifacts':{p.name:sha(p) for p in PACKET.iterdir() if p.is_file() and p.name!='manifest.json'}})
        check();state=read(REVIEW/'state.json')
        state.update(status='WAITING_HUMAN_CONCLUSION',experiment_status=report['run_status'],
            conclusion_review_hash=request['artifact_hash'],conclusion_packet=str(PACKET),
            conclusion_approved=False,research_status='not_achieved')
        write(REVIEW/'state.json',state);check()
        return {'status':'WAITING_HUMAN_CONCLUSION','run_status':report['run_status'],
                'accepted_runs':report['accepted_runs'],'groups':report['groups'],
                'conclusion_hash':request['artifact_hash'],'budget':budget}
    try:
        result=run_main_phase(context['scope_dir'],REVIEW,work,finalize,started_at=ENTERED)
    except Exception as exc:
        if owned:
            if PACKET.is_dir():write(PACKET/'manifest.json',{'status':'STOPPED_CONCLUSION_PREPARATION_FAILED','error':str(exc)[:1000]})
            state=read(REVIEW/'state.json');state.update(status='CONCLUSION_PREPARATION_FAILED',conclusion_approved=False,
                error=f'{type(exc).__name__}: {str(exc)[:1000]}',research_status='not_achieved');write(REVIEW/'state.json',state)
        raise
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
