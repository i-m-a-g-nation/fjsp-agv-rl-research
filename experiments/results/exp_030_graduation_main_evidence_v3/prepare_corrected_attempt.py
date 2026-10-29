"""Prepare a separately reviewed second attempt; never grant approval or solve."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT=Path.cwd();sys.path.insert(0,str(ROOT))
from src.ai_workflow.graduation_main_evidence import load_scope_context,backend_source_hashes,prepare_main_evidence
from src.ai_workflow.graduation_main_backend import recheck_main_run
from src.ai_workflow.graduation_main_budget import read_main_budget

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def write(p,value):Path(p).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')

old=ROOT/'experiments/runs/g3_main_review_17bc1aa7'
new=ROOT/'experiments/runs/g3_main_review_17bc1aa7_attempt2'
packet=ROOT/'experiments/runs/g3_main_evidence_20261029_v3'
failed=ROOT/'experiments/results/exp_030_graduation_main_failed_v1'
prior=ROOT/'experiments/runs/g3_main_formal_20261029_v1'
assert read(old/'state.json')['status']=='FAILED'
assert not new.exists() and not packet.exists()
context=load_scope_context(old)
result=recheck_main_run(prior,context['cases'],require_current_sources=False)
assert result['status']=='FAILED' and result['status_counts']['NOT_RUN']==480
budget=read_main_budget(context['scope_dir'])
assert len(budget['segments'])==8 and budget['active_seconds_reserved']==0
assert budget['segments']==read(prior/'budget_snapshot.json')['segments']
log=ROOT/'.superpowers/sdd/g3-main-managed-final-related-v2.log'
assert re.search(r'236 passed in [0-9.]+s(?: \(\d+:\d{2}:\d{2}\))?$',log.read_text(encoding='utf-8').strip())
proposal={'version':1,'status':'PROPOSED_SECOND_ATTEMPT_NOT_APPROVED','recorded_at_utc':datetime.now(timezone.utc).isoformat(),
 'scope_hash':context['scope_hash'],'scope_approval_reused_from':str(old/'scope_approval.json'),
 'new_scope_approval_claimed':False,'same_inputs_model_order_and_solver_limits':True,
 'previous_evidence_hash':result['evidence_hash'],'previous_run_status':result['status'],
 'previous_actual_solver_calls':0,'previous_not_run_rows':480,
 'failure_archive':'experiments/results/exp_030_graduation_main_failed_v1',
 'failure_archive_manifest_sha256':sha(failed/'archive_manifest.json'),
 'previous_run_manifest_sha256':sha(prior/'manifest.json'),
 'failure_reason':'Windows environment-dependent machine identity differed across the sanitized process boundary.',
 'correction':'Bind interpreter target with sysconfig.get_platform; preserve stage/error and worker receipt; real managed production-entry tests.',
 'new_review_dir':str(new),'new_evidence_packet':str(packet),
 'proposed_new_output':str(ROOT/'experiments/runs/g3_main_formal_20261029_v2'),
 'original_budget_path':str(context['scope_dir']/'budget.sqlite'),
 'budget_before_preparation':budget,'automatic_retry':False,'new_evidence_approved':False,
 'independent_backend_review':'not_completed_quota_limit','research_status':'not_achieved'}
new.mkdir()
shutil.copy2(old/'scope_approval.json',new/'scope_approval.json')
write(new/'prior_attempt.json',proposal)
write(new/'state.json',{'status':'EVIDENCE_PREPARATION_REQUIRED','scope_review_hash':context['scope_hash'],
 'scope_approved':True,'evidence_approved':False,'conclusion_approved':False,'model_calls':0,'solver_calls_executed':0,
 'previous_review_dir':str(old),'previous_run_status':'FAILED','new_scope_approval_claimed':False,
 'research_status':'not_achieved','pending':['new_evidence_preparation']})
wrapped=ROOT/'.superpowers/sdd/g3-main-corrected-attempt-validation.log'
header=('CORRECTED SECOND ATTEMPT PROPOSAL, NOT AN APPROVAL.\n'
 f"Prior attempt FAILED before solve; all480NOT_RUN; prior evidence={result['evidence_hash']}.\n"
 f"Prior failure archive manifest SHA256={proposal['failure_archive_manifest_sha256']}.\n"
 f"Attempt context JSON SHA256={sha(new/'prior_attempt.json')}.\n"
 'Same scope/grid/model, same cumulative600second ledger, no refund/reset. New evidence approval required.\n'
 'Recorded validation output follows without modification:\n').encode('utf-8')
wrapped.write_bytes(header+log.read_bytes())
tests=list(read(ROOT/'.superpowers/sdd/g3-main-evidence-v2-validation-record.json')['test_hashes'])
tests.append('tests/fixtures/g3_runtime_probe.py')
record={'version':1,'status':'PASSED','exit_code':0,'passed':236,'log_sha256':sha(wrapped),
 'backend_source_hashes':backend_source_hashes(),'test_hashes':{p:sha(ROOT/p) for p in tests}}
write(ROOT/'.superpowers/sdd/g3-main-corrected-attempt-validation-record.json',record)
prepared=prepare_main_evidence(new,packet,wrapped,record)
state=read(new/'state.json');state['pending']=['human_evidence_approval_for_additional_attempt'];write(new/'state.json',state)
write(ROOT/'.superpowers/sdd/g3-main-corrected-attempt-prepared.json',prepared)
print(json.dumps(prepared,ensure_ascii=False))
