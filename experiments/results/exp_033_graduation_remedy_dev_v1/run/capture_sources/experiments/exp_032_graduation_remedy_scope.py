"""Prepare/recheck an unapproved solver-remedy scope; no execution command."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.graduation.reference_protocol import digest,encoded
from src.graduation.solver_diagnostics import audit_saved_failures
from src.ai_workflow.graduation_main_evidence import backend_source_hashes

FORMAL=ROOT/'experiments/results/exp_030_graduation_main_attempt2_v1'
DIAGNOSIS=ROOT/'experiments/results/exp_031_consistency_diagnostic_dev_v1'


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_bytes(encoded(value))


def materials():
    selection=audit_saved_failures(FORMAL)
    index=read(DIAGNOSIS/'archive_manifest.json')['files_sha256']
    actual={p.relative_to(DIAGNOSIS).as_posix():sha(p) for p in DIAGNOSIS.rglob('*')
            if p.is_file() and p.relative_to(DIAGNOSIS).as_posix()!='archive_manifest.json'}
    if actual!=index:raise ValueError('Original diagnosis archive changed')
    sources=backend_source_hashes()
    recorded=read(FORMAL/'run/manifest.json')['source_hashes']
    if sources!=recorded:raise ValueError('Original baseline sources changed')
    for name in ('src/graduation/solver_diagnostics.py','experiments/exp_032_graduation_remedy_scope.py'):
        sources[name]=sha(ROOT/name)
    inputs=[];runs=[]
    for item in selection['requests']:
        case=copy.deepcopy(item['case']);inputs.append(case)
        for presolve in (True,False):
            runs.append({'sequence':len(runs),'group':'historical_error_counterfactual',
                'case_id':case['case_id'],'input_sha256':digest(case['data']),
                'original_sequence':item['sequence'],'mode':item['mode'],
                'cp_model_presolve':presolve,'expected_tardiness':None})
    control={'case_id':'g2-two-task-remedy-control','data':{'num_machines':1,
        'tasks':[{'job_id':0,'processing_time':2,'due_date':2},{'job_id':1,'processing_time':2,'due_date':4}],
        'maintenance':[{'machine_id':0,'duration':2,'window_start':0,'window_end':6,'fixed_start':0}]}}
    inputs.append(control)
    for mode,expected in (('fixed',4),('joint',0)):
        for presolve in (True,False):
            runs.append({'sequence':len(runs),'group':'enumerable_control','case_id':control['case_id'],
                'input_sha256':digest(control['data']),'original_sequence':None,'mode':mode,
                'cp_model_presolve':presolve,'expected_tardiness':expected})
    protocol={'version':1,'purpose':'development_counterfactual_not_formal_G3',
        'question':'Does disabling CP-SAT model presolve remove the observed objective/returned-solution disagreement?',
        'planned_solver_calls':14,'native_solver_calls':0,'model_calls':0,
        'shared_solver_parameters':{'max_time_in_seconds':1.,'num_search_workers':1,'random_seed':42},
        'required_runtime':{'python':'3.11.15','ortools':'9.15.6755'},
        'new_budget':{'max_active_seconds':60,'max_provider_calls':0,'max_output_tokens':0,
            'starts_at':'approved execution preflight','covers':'preflight, supervised worker, validation and receipt',
            'development_preparation_included':False,'automatic_retry':False,'resume':False},
        'authorization':{'scope_approved':False,'new_budget_approved':False,'native_execution_approved':False},
        'execution_entry':'not implemented by this preparation-only script',
        'original_scope_sha256':'17bc1aa7d715f2090468718c8f3a14327d979178ef48b7980c5964b99fa0c0a3',
        'original_locked_ledger_sha256':sha(DIAGNOSIS/'original_ledger_after_failure.sqlite'),
        'original_ledger_may_be_modified':False,'original_formal_rows_may_be_replaced':False,
        'formal_archive_index_sha256':sha(FORMAL/'archive_manifest.json'),
        'diagnosis_archive_index_sha256':sha(DIAGNOSIS/'archive_manifest.json'),
        'source_hashes':sources,
        'validation':['Save every raw response and candidate, including failures and missing rows.',
            'Preserve exact objective/bound checks and independently recheck schedule/tardiness.',
            'Require tiny fixed/joint OPTIMAL objectives4/0 and independent enumeration agreement.',
            'If original errors do not reproduce, report the counterfactual as inconclusive; never retry automatically.',
            'Presolve-off success on five cases is not proof of universal correctness or a performance improvement.'],
        'stop_conditions':['14 calls reached','60 active seconds reached','lost process/budget ownership',
                           'changed inputs/sources','unvalidated or incomplete evidence'],
        'research_status':'not_achieved',
        'primary_sources':['https://github.com/google/or-tools/issues/5453',
                          'https://github.com/google/or-tools/blob/stable/ortools/sat/sat_parameters.proto']}
    return {'protocol':protocol,'inputs':inputs,'planned_runs':runs}


def summary(scope_hash):
    return ('毕设求解器补救：独立开发范围提案，尚未批准\n'
        f'材料哈希：{scope_hash}\n'
        '范围：5个历史ERROR各原配置/关闭cp_model_presolve比较，共10次；'
        '再对双任务固定/联合维护在两配置下做4次可枚举控制，总计14次。\n'
        '每次最多1秒、单线程、seed42，原模型/严格checker/目标均不变。\n'
        '建议新预算60累计主动秒，覆盖获批后的入口检查、子进程、复核和收尾；'
        '本次材料开发与准备不计入该未来执行预算。0模型调用、不自动重试、不恢复。\n'
        '旧600秒账本锁定状态及全部正式结果保留，不能退款、解锁或替换原5条错误。\n'
        '本入口只准备/复检材料，不创建预算、不批准也不运行；执行入口尚未实现。\n'
        '需先明确批准本范围和新预算，再实现并验证有界执行入口。\n'
        '判断：控制例OPTIMAL固定4/联合0、枚举一致；5问题例保存完整原始证据，'
        '比较目标/变量/延期/界一致性。原错误不复现则反事实证据不足。\n'
        '不认可普遍性能优势、完整G3通过、RL优势或课题验收。\n')


def prepare(out):
    out=Path(out)
    if out.exists():raise FileExistsError('Use a new proposal directory')
    bundle=materials();scope_hash=digest(bundle);out.mkdir(parents=True)
    for key,value in bundle.items():write(out/(key+'.json'),value)
    (out/'scope_summary.txt').write_text(summary(scope_hash),encoding='utf-8')
    receipt={'status':'WAITING_SCOPE_AND_NEW_BUDGET','scope_sha256':scope_hash,
        'files_sha256':{p.name:sha(p) for p in out.iterdir() if p.is_file()}}
    write(out/'manifest.json',receipt)
    return receipt


def recheck(out):
    out=Path(out);manifest=read(out/'manifest.json');expected=materials()
    actual={p.relative_to(out).as_posix():sha(p) for p in out.rglob('*')
            if p.is_file() and p.relative_to(out).as_posix()!='manifest.json'}
    if (set(manifest)!={'status','scope_sha256','files_sha256'} or actual!=manifest['files_sha256']
            or manifest['status']!='WAITING_SCOPE_AND_NEW_BUDGET'
            or manifest['scope_sha256']!=digest(expected)):
        raise ValueError('Proposal identity, status or file closure changed')
    if any(encoded(read(out/(key+'.json')))!=encoded(value) for key,value in expected.items()):
        raise ValueError('Proposal differs from source-bound scope')
    if (out/'scope_summary.txt').read_text(encoding='utf-8')!=summary(digest(expected)):
        raise ValueError('Human scope summary changed')
    return {'status':'VERIFIED_UNAPPROVED_PROPOSAL','scope_sha256':manifest['scope_sha256'],
            'planned_calls':14,'new_solver_calls':0,'budget_created':False}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['prepare','recheck'])
    parser.add_argument('--output-dir',type=Path,required=True);args=parser.parse_args(argv)
    result=prepare(args.output_dir) if args.action=='prepare' else recheck(args.output_dir)
    print(json.dumps(result,ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
