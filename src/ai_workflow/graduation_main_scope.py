"""Materialize the G3A main scope for review; this module executes no solver."""
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time

from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.review import make_review_request
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget
from src.graduation.reference_protocol import encoded, digest
from src.graduation.reference_main_protocol import main_protocol, build_main_cases

ROOT = Path(__file__).resolve().parents[2]
LIMITS = BudgetLimits(600, 0, 0)
FINALIZATION_ALLOWANCE = 5.0
FILES = {'protocol.json','inputs.json','planned_runs.json','aliases.json','summary.json',
    'budget_snapshot.json','scope_summary.txt','scope_review.json','state.json'}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _write(path, value):
    path = Path(path)
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def _sources():
    paths = ['src/graduation/data.py','src/graduation/reference_protocol.py',
        'src/graduation/reference_main_protocol.py','src/ai_workflow/graduation_main_scope.py',
        'src/ai_workflow/contracts.py','src/ai_workflow/review.py','src/ai_workflow/runtime_budget.py',
        'experiments/exp_029_graduation_main_scope.py']
    return {p:_sha(ROOT/p) for p in paths}


def _materials():
    protocol, cases = main_protocol(), build_main_cases()
    rows = [{'sequence':i*2+j,'case_id':c['case_id'],'group':c['group'], 'mode':mode,
        'input_sha256':digest(c['data']),'request_hash':c['request_hash'],'status':'NOT_RUN'}
        for i,c in enumerate(cases) for j,mode in enumerate(('fixed','joint'))]
    aliases = {}
    for case in cases:
        aliases.setdefault(case['core_model_hash'], []).append(case['case_id'])
    summary = {'status':'WAITING_HUMAN_SCOPE','paired_requests':len(cases),
        'primary_pairs':sum(c['group'] == 'primary' for c in cases),
        'sensitivity_pairs':sum(c['group'] == 'sensitivity' for c in cases),
        'planned_solver_calls':len(rows),'base_workloads':len({c['workload_hash'] for c in cases}),
        'unique_core_models':len(aliases),'solver_calls_executed':0,'model_calls':0,'network_calls':0,
        'scope_approved':False,'research_status':'not_achieved','execution_backend_available':False}
    if (summary['paired_requests'], summary['primary_pairs'], summary['sensitivity_pairs'],
            summary['planned_solver_calls'], summary['base_workloads']) != (240,160,80,480,10):
        raise ValueError('Formal main matrix denominator differs from the registered design')
    return {'protocol.json':protocol,'inputs.json':cases,'planned_runs.json':rows,
        'aliases.json':aliases,'summary.json':summary}


def _human(summary):
    return ('毕设G3A正式主比较：范围审核材料\n'
        '研究问题：相同模型和输入下，允许维护开始时刻调整，对总延期有什么影响？\n'
        '模型：同质平行机、单工序、全部0时刻到达、每机一次必需维护、完整维护区间在窗口内、无共享维修班组。\n'
        '任务数8/24，机器数2/4，维护强度10%/30%，窗口可调宽度25%/75%，交期系数75%/125%。\n'
        '实例种子101/202/303/404/505；主比较使用窗口中点固定维护，160对。\n'
        '预先指定n8/m2子集，再比较最早/最晚固定维护，80对。先主比较，再敏感性；每对fixed后joint。\n'
        f"共{summary['paired_requests']}对、{summary['planned_solver_calls']}次求解请求，"
        f"{summary['base_workloads']}组基础随机工作负载、{summary['unique_core_models']}个不同物理模型。条件间共享随机流，不视为独立样本。\n"
        '每次CP-SAT最多1秒、单线程、seed42。总累计主动预算600秒，准备输入已记账；等待审核不计时。模型/网络调用0。\n'
        '最终预算回执封装保守预扣5秒，封装本身也限定5秒，未用额度不退；这些均包含在600秒内。\n'
        '保留UNKNOWN/失败/未运行行；FEASIBLE只称限时可行参考。保存两模式完整计划、目标/界/gap和实际重算总延期。\n'
        '只有双方OPTIMAL才能比较最优目标；限时观测差可能为负。固定延期0时不计算百分比。\n'
        '比较差的最优值界为[max(0,LB_fixed-T_joint),T_fixed-LB_joint]；异常界必须披露。\n'
        '本次只申请scope批准。下一道为evidence；执行后还需conclusion审核。scope批准不直接启动求解。\n'
        '当前执行后端尚未接入。本批未运行CP-SAT、RL或最终测试，不生成课题达成结论。\n')


def _request(folder, summary, sources):
    bound = ('protocol.json','inputs.json','planned_runs.json','aliases.json','summary.json',
        'budget_snapshot.json','scope_summary.txt')
    payload = {'protocol_id':main_protocol()['protocol_id'], 'material_sha256':{p:_sha(folder/p) for p in bound},
        'source_hashes':sources, 'counts':{k:summary[k] for k in
            ('paired_requests','primary_pairs','sensitivity_pairs','planned_solver_calls','base_workloads','unique_core_models')},
        'budget':asdict(LIMITS),'next_gate':'evidence','approval_does_not_start_execution':True}
    return make_review_request('scope', get_research_contract('graduation').to_dict(), payload)


def _publish(folder, summary, sources, snapshot, *, preparing=False):
    _write(folder/'budget_snapshot.json',snapshot)
    request=_request(folder,summary,sources)
    status='PREPARING' if preparing else 'WAITING_HUMAN_SCOPE'
    _write(folder/'scope_review.json',request)
    _write(folder/'state.json',{'status':status,'stage':'scope',
        'scope_approved':False,'evidence_approved':False,'conclusion_approved':False,
        'research_status':'not_achieved','review_hash':request['artifact_hash']})
    _write(folder/'manifest.json',{'version':1,'status':status,
        'source_hashes':sources,'artifacts':{p:_sha(folder/p) for p in sorted(FILES)},
        'mutable_control_files':['budget.sqlite']})
    return request


def prepare_main_scope(output_dir):
    started = time.monotonic()
    folder = Path(output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=False)
    budget = RunBudget(folder/'budget.sqlite', LIMITS)
    segment, _ = budget.reserve_active_segment()
    budget.start_segment(segment)
    try:
        try:
            sources = _sources()
            for name,value in _materials().items():
                budget.remaining_seconds()
                _write(folder/name, value)
            summary = _read(folder/'summary.json')
            (folder/'scope_summary.txt').write_text(_human(summary), encoding='utf-8')
            if sources != _sources():
                raise ValueError('Scope generator sources changed during preparation')
            # Substantive construction and independent reconstruction are timed.
            _publish(folder,summary,sources,budget.snapshot(),preparing=True)
            _check_materials(folder,preparing=True)
            budget.remaining_seconds()
        finally:
            final_started=time.monotonic()
            budget.finish_active_segment(segment, final_started-started)
        _budget(folder, before_finalization=True)
        # Prepay a bounded final receipt allowance. This breaks the recursive
        # receipt/timing dependency without refunding unmeasured finalization.
        extra,remaining=budget.reserve_active_segment()
        if remaining < FINALIZATION_ALLOWANCE:
            raise BudgetExceeded('Insufficient remaining budget for final receipts')
        budget.finish_active_segment(extra,FINALIZATION_ALLOWANCE)
        snapshot=_budget(folder)
        request=_publish(folder,summary,sources,snapshot)
        if (sources != _sources() or time.monotonic()-started > 600
                or time.monotonic()-final_started > FINALIZATION_ALLOWANCE):
            raise BudgetExceeded('Final receipt deadline/source changed; scope cannot become ready')
        return {**summary,'review_hash':request['artifact_hash'],
            'preparation_active_seconds':snapshot['active_seconds'],
            'remaining_active_seconds':600-snapshot['active_seconds']}
    except Exception as exc:
        _write(folder/'state.json',{'status':'STOPPED_PREPARATION_FAILED','error_type':type(exc).__name__,
            'elapsed_seconds_through_failure':time.monotonic()-started,'scope_approved':False})
        raise


def _budget(folder,*,before_finalization=False):
    path = folder/'budget.sqlite'
    if not path.is_file():
        raise ValueError('Missing main execution budget; never recreate it on recheck')
    try:
        with path.open('rb') as handle:
            header=handle.read(100)
        if header[:16] != b'SQLite format 3\x00' or header[18:20] != b'\x01\x01':
            raise ValueError('Prepared ledger must use the closed DELETE journal format')
        # immutable=1 prevents even read-only SQLite from creating WAL/SHM files.
        db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro&immutable=1', uri=True)
        try:
            records=db.execute('SELECT id,limits_json,active_seconds,provider_calls,output_tokens_reserved FROM workflow_budget').fetchall()
            segments=db.execute('SELECT id,reserved_seconds,finished_seconds FROM workflow_segments').fetchall()
        finally:
            db.close()
        if len(records)!=1 or records[0][0]!=1 or len(segments)!=(1 if before_finalization else 2):
            raise ValueError('Prepared ledger reservation denominator changed')
        _,limits_json,active,calls,tokens=records[0]
        limits=json.loads(limits_json)
        first_id,reserved,finished=segments[0]
        if (encoded(limits)!=encoded(asdict(LIMITS)) or calls!=0 or tokens!=0
                or type(active) not in (int,float) or not math.isfinite(active) or not 0<active<=600
                or first_id!=1 or reserved!=600 or finished is None
                or not math.isfinite(finished) or not 0<finished<=reserved):
            raise ValueError('Invalid or interrupted main preparation budget')
        if not before_finalization:
            second_id,second_reserved,second_finished=segments[1]
            if (second_id!=2 or second_reserved!=600-finished
                    or second_reserved<FINALIZATION_ALLOWANCE or second_finished!=FINALIZATION_ALLOWANCE):
                raise ValueError('Finalization allowance or reservation changed')
        if not math.isclose(math.fsum(f for _,r,f in segments),active,rel_tol=1e-12,abs_tol=1e-8):
            raise ValueError('Prepared ledger charge differs from its segments')
        return {'limits':limits,'active_seconds':active,'active_seconds_charged':active,
            'active_seconds_reserved':0,'provider_calls':calls,'output_tokens_reserved':tokens,
            'segments':[{'id':i,'reserved_seconds':r,'finished_seconds':f} for i,r,f in segments],
            'finalization_prepaid_seconds':0 if before_finalization else FINALIZATION_ALLOWANCE}
    except (sqlite3.Error,TypeError) as exc:
        raise ValueError('Invalid main preparation budget ledger') from exc


def _check_materials(output_dir,*,preparing=False):
    """Reconstruct all cases and ordered requests; read no model or solver output."""
    folder = Path(output_dir)
    manifest = _read(folder/'manifest.json')
    status='PREPARING' if preparing else 'WAITING_HUMAN_SCOPE'
    if (type(manifest.get('version')) is not int or manifest['version']!=1 or manifest.get('status')!=status
            or manifest.get('source_hashes') != _sources()
            or manifest.get('mutable_control_files') != ['budget.sqlite']):
        raise ValueError('Main scope identity or sources changed')
    names = {p.name for p in folder.iterdir() if p.is_file()}
    if names != FILES|{'manifest.json','budget.sqlite'} or any(p.is_dir() for p in folder.iterdir()):
        raise ValueError('Unexpected or missing scope material')
    if manifest['artifacts'] != {p:_sha(folder/p) for p in sorted(FILES)}:
        raise ValueError('Main scope artifact identity changed')
    for name,value in _materials().items():
        if (folder/name).read_bytes() != encoded(value):
            raise ValueError(f'Main scope {name} differs from the registered protocol')
    summary, state = _read(folder/'summary.json'), _read(folder/'state.json')
    if (folder/'scope_summary.txt').read_text(encoding='utf-8') != _human(summary):
        raise ValueError('Human-readable scope differs from the complete matrix')
    request = _request(folder, summary, manifest['source_hashes'])
    if (folder/'scope_review.json').read_bytes()!=encoded(request):
        raise ValueError('Scope review does not bind current materials')
    expected_state = {'status':status,'stage':'scope','scope_approved':False,
        'evidence_approved':False,'conclusion_approved':False,'research_status':'not_achieved',
        'review_hash':request['artifact_hash']}
    if (folder/'state.json').read_bytes()!=encoded(expected_state):
        raise ValueError('Scope approval cannot be inferred or forged by preparation')
    return summary,request


def recheck_main_scope(output_dir):
    folder=Path(output_dir)
    summary,request=_check_materials(folder)
    snapshot,recorded=_budget(folder),_read(folder/'budget_snapshot.json')
    if encoded(snapshot)!=encoded(recorded):
        raise ValueError('Frozen preparation ledger differs from the bound receipt')
    return {**summary,'review_hash':request['artifact_hash'],
        'preparation_active_seconds':snapshot['active_seconds'],
        'remaining_active_seconds':600-snapshot['active_seconds']}
