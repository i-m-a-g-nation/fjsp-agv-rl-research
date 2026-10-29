"""Content-bound G3A evidence review; preparation never starts the main solver."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import ntpath
from pathlib import Path
import posixpath
import re
import platform
import sys
import sysconfig
import time

from src.ai_workflow import graduation_main_scope as scope
from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.graduation_main_budget import read_main_budget, run_main_phase
from src.ai_workflow.review import make_review_request, validate_review_decision
from src.graduation.reference_pilot import recheck_pilot
from src.graduation.reference_protocol import encoded


ROOT = Path(__file__).resolve().parents[2]
SCOPE_ARCHIVE = 'experiments/results/exp_029_graduation_main_scope_v1/materials'
PILOT_ARCHIVE = 'experiments/results/exp_028_graduation_reference_pilot_v1'
SOURCE_PATHS = tuple(sorted({
    'src/ai_workflow/graduation_main_evidence.py',
    'src/ai_workflow/graduation_main_backend.py',
    'src/graduation/reference_main_worker.py',
    'experiments/exp_030_graduation_main.py',
    'src/ai_workflow/graduation_main_budget.py',
    'src/graduation/reference_main_results.py',
    'src/graduation/data.py', 'src/graduation/solver.py',
    'src/graduation/feasibility.py', 'src/graduation/_production.py',
    'src/graduation/metrics.py', 'src/graduation/result.py',
    'src/graduation/enumeration.py', 'src/graduation/reference_pilot.py',
    'src/ai_workflow/graduation_backend.py',
    'src/scheduling/encoding.py', 'src/scheduling/feasibility.py',
    'src/data/instance.py', 'src/ai_workflow/process_supervisor.py',
    'src/ai_workflow/session_watchdog.py',
    'src/graduation/reference_protocol.py', 'src/graduation/reference_main_protocol.py',
    'src/ai_workflow/graduation_main_scope.py', 'src/ai_workflow/contracts.py',
    'src/ai_workflow/review.py', 'src/ai_workflow/runtime_budget.py',
    'experiments/exp_029_graduation_main_scope.py',
}))
REQUIRED_TEST_PATHS = {
    'tests/test_reference_main_results.py', 'tests/test_graduation_main_budget.py',
    'tests/test_graduation_main_evidence.py', 'tests/test_graduation_main_backend.py',
}
BOUND_FILES = {
    'scope_approval.json', 'scope_reference.json', 'backend_sources.json',
    'validation.log', 'validation_record.json', 'pilot_receipts.json',
    'budget_snapshot.json', 'summary.json', 'evidence_summary.txt', 'runtime.json',
}
FILES = BOUND_FILES | {'evidence_review.json'}
READY = 'WAITING_HUMAN_EVIDENCE'


def runtime_identity():
    return {'python':sys.version,'executable':sys.executable,
        'ortools':importlib.metadata.version('ortools'),
        # Windows platform.machine() depends on PROCESSOR_ARCHITECTURE, which
        # the supervised worker intentionally does not inherit. Bind the actual
        # interpreter target instead, retaining equality across that boundary.
        'system':platform.system(),'python_platform':sysconfig.get_platform()}


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate evidence JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite evidence JSON')))


def _write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(encoded(value))
    temporary.replace(path)


def backend_source_hashes() -> dict:
    """Bind the exact implementation files, including all eight approved sources."""
    try:
        return {name: _sha(ROOT / name) for name in SOURCE_PATHS}
    except OSError as exc:
        raise ValueError('Missing main evidence/backend implementation source') from exc


def _hash_map(value, *, expected=None):
    if (not isinstance(value, dict) or not value
            or expected is not None and set(value) != set(expected)
            or any(not isinstance(name, str) or not isinstance(digest, str)
                   or not re.fullmatch('[0-9a-f]{64}', digest) for name, digest in value.items())):
        raise ValueError('Missing or malformed evidence source/file identities')


def _approved_scope(folder, approval):
    if (not isinstance(approval, dict) or not isinstance(approval.get('reviewed_scope_packet'), str)
            or approval.get('scope_approved') is not True):
        raise ValueError('An actual recorded scope approval is required')
    _, request = scope._check_materials(folder)
    decision = validate_review_decision(request, approval.get('decision'))
    if decision['decision'] != 'approve':
        raise ValueError('Scope approval was rejected')
    return {'scope_dir': Path(folder).resolve(), 'scope_request': request, 'scope_decision': decision,
            'cases': _read(Path(folder) / 'inputs.json'),
            'planned_rows': _read(Path(folder) / 'planned_runs.json'),
            'scope_hash': request['artifact_hash'], 'scope_approval_record': approval}


def load_scope_context(review_dir) -> dict:
    """Validate the human scope decision against the actual frozen input packet."""
    approval = _read(Path(review_dir) / 'scope_approval.json')
    if not isinstance(approval, dict) or not isinstance(approval.get('reviewed_scope_packet'), str):
        raise ValueError('Missing reviewed scope packet path')
    folder = Path(approval['reviewed_scope_packet']).resolve()
    if not folder.is_dir():
        raise ValueError('Original approved scope directory is missing; cannot replace its budget')
    return _approved_scope(folder, approval)


def _validation(log, record, sources, *, require_current_sources):
    keys = {'version', 'status', 'exit_code', 'passed', 'log_sha256',
            'backend_source_hashes', 'test_hashes'}
    if (not isinstance(record, dict) or set(record) != keys
            or type(record['version']) is not int or record['version'] != 1
            or record['status'] != 'PASSED' or type(record['exit_code']) is not int
            or record['exit_code'] != 0 or type(record['passed']) is not int or record['passed'] <= 0
            or record['log_sha256'] != hashlib.sha256(log).hexdigest()
            or record['backend_source_hashes'] != sources):
        raise ValueError('Invalid development test receipt or source/log mismatch')
    _hash_map(record['test_hashes'])
    if (not REQUIRED_TEST_PATHS <= set(record['test_hashes'])
            or any(not name.startswith('tests/') or not name.endswith('.py')
                   or '..' in Path(name).parts or '\\' in name
                   for name in record['test_hashes'])):
        raise ValueError('Development receipt is missing required backend tests')
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', log.decode('utf-8-sig'))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    final = re.fullmatch(r'(?:=+\s*)?(\d+) passed(?:, (?!.*(?:failed|error))[^\r\n]*?)? in \d+(?:\.\d+)?s'
                         r'(?: \(\d+:[0-5]\d:[0-5]\d\))?(?:\s*=+)?',
                         lines[-1] if lines else '')
    if final is None or int(final.group(1)) != record['passed']:
        raise ValueError('Development log final pytest passed count does not match the receipt')
    if require_current_sources:
        if sources != backend_source_hashes():
            raise ValueError('Main backend sources changed since development validation')
        if any(_sha(ROOT / name) != value for name, value in record['test_hashes'].items()):
            raise ValueError('Development test files changed since validation')


def _pilot_receipts(check=lambda: None):
    receipts = {}
    for run in ('run_1', 'run_2'):
        check()
        relative = f'{PILOT_ARCHIVE}/{run}'
        folder = ROOT / relative
        summary = recheck_pilot(folder, require_current_sources=False)
        check()
        if (summary['status'] != 'COMPLETED' or summary['validated_runs'] != 24
                or summary['main_grid_executed'] is not False):
            raise ValueError('Archived development pilot did not pass recheck')
        receipts[run] = {'path': relative, 'manifest_sha256': _sha(folder / 'manifest.json'),
                         'summary': summary}
    return receipts


def _budget_snapshot(snapshot, folder):
    frozen = _read(Path(folder) / 'budget_snapshot.json')
    keys = {'limits', 'active_seconds', 'active_seconds_charged', 'active_seconds_reserved',
            'provider_calls', 'output_tokens_reserved', 'segments',
            'finalization_prepaid_seconds', 'remaining_active_seconds'}
    if (not isinstance(snapshot, dict) or set(snapshot) != keys
            or encoded(snapshot.get('limits')) != encoded(frozen['limits'])
            or type(snapshot.get('provider_calls')) is not int or snapshot['provider_calls'] != 0
            or type(snapshot.get('output_tokens_reserved')) is not int or snapshot['output_tokens_reserved'] != 0
            or type(snapshot.get('active_seconds_reserved')) not in (int, float)
            or snapshot['active_seconds_reserved'] != 0
            or snapshot.get('finalization_prepaid_seconds') != 5.0
            or not isinstance(snapshot.get('segments'), list)
            or len(snapshot['segments']) < 4 or len(snapshot['segments']) % 2
            or snapshot['segments'][:2] != frozen['segments']):
        raise ValueError('Evidence budget must continue the original frozen preparation ledger')
    elapsed = 0.0
    for identifier, segment in enumerate(snapshot['segments'], 1):
        if (not isinstance(segment, dict) or set(segment) != {'id', 'reserved_seconds', 'finished_seconds'}
                or type(segment['id']) is not int or segment['id'] != identifier
                or type(segment['reserved_seconds']) not in (int, float)
                or not math.isfinite(segment['reserved_seconds'])
                or segment['reserved_seconds'] != 600 - elapsed
                or type(segment['finished_seconds']) not in (int, float)
                or not math.isfinite(segment['finished_seconds'])
                or not 0 <= segment['finished_seconds'] <= segment['reserved_seconds']):
            raise ValueError('Invalid settled evidence budget history')
        elapsed += segment['finished_seconds']
    if (any(type(snapshot.get(key)) not in (int, float) or not math.isfinite(snapshot[key])
            for key in ('active_seconds', 'active_seconds_charged', 'remaining_active_seconds'))
            or snapshot['segments'][-1]['finished_seconds'] != 5.0
            or snapshot.get('active_seconds') != elapsed
            or snapshot.get('active_seconds_charged') != elapsed
            or snapshot.get('remaining_active_seconds') != 600 - elapsed
            or not 0 < snapshot['remaining_active_seconds'] < 600):
        raise ValueError('Evidence remaining budget disagrees with settled original history')


def _summary(context, snapshot, passed):
    counts = context['scope_request']['payload']['counts']
    return {'status': READY, 'scope_hash': context['scope_hash'], **counts,
            'scope_approved': True, 'evidence_approved': False, 'conclusion_approved': False,
            'solver_calls_executed': 0, 'model_calls': 0, 'network_calls': 0,
            'development_tests_passed': passed, 'prior_pilot_runs_rechecked': 2,
            'independent_backend_review': 'not_completed_quota_limit',
            'active_seconds_charged': snapshot['active_seconds_charged'],
            'remaining_active_seconds': snapshot['remaining_active_seconds'],
            'next_gate_after_execution': 'conclusion', 'research_status': 'not_achieved'}


def _human(summary):
    return ('毕设G3A正式主比较：evidence审核材料\n'
            f"已绑定scope人审批准：{summary['scope_hash']}。\n"
            f"完整输入与顺序：{summary['paired_requests']}对、{summary['planned_solver_calls']}次计划请求；"
            f"主比较{summary['primary_pairs']}对，敏感性{summary['sensitivity_pairs']}对。\n"
            f"基础工作负载{summary['base_workloads']}组，不同物理核心{summary['unique_core_models']}个；重复joint不增加独立样本。\n"
            '两模式逐字节使用相同完整输入，每对fixed后joint；每次1秒、单线程、seed42，不重试。\n'
            f"开发验证{summary['development_tests_passed']}项通过；两份先导归档已只读复检，不重新运行CP-SAT。\n"
            '最终整批独立代码审查未完成：审查代理触达账户用量限制；当前有模块测试和主进程复核，不能将其写成独立审查通过。\n'
            f"原始600秒累计主动账本已计{summary['active_seconds_charged']}秒，精确剩余{summary['remaining_active_seconds']}秒。等待人审不计时。\n"
            '保留全部失败与未运行行和完整生产/维护计划；仅领域合法OPTIMAL/FEASIBLE接受指标，FEASIBLE不称最优。\n'
            '观察差可为负，固定延期0时百分比NA；最优差界[max(0,LB_fixed-T_joint),T_fixed-LB_joint]，矛盾须披露。\n'
            '预算耗尽终止进程树并保留全分母，不续跑、不加时。当前未执行正式主网格、RL或最终测试。\n'
            '现停在等待evidence人审；批准后才可启动有界批次，执行后下一道为conclusion人审。research_status=not_achieved。\n')


def _request(folder, context, sources, snapshot):
    return make_review_request('evidence', get_research_contract('graduation').to_dict(), {
        'scope_hash': context['scope_hash'],
        'scope_approval_sha256': _sha(folder / 'scope_approval.json'),
        'material_sha256': {name: _sha(folder / name) for name in sorted(BOUND_FILES)},
        'frozen_scope_material_sha256': context['scope_request']['payload']['material_sha256'],
        'source_hashes': sources, 'counts': context['scope_request']['payload']['counts'],
        'solver': {'time_limit': 1.0, 'num_workers': 1, 'seed': 42},
        'budget_snapshot': snapshot, 'next_gate': 'conclusion',
        'execution_requires_evidence_approval': True, 'research_status': 'not_achieved',
    })


def _control_state(review_dir, status, **fields):
    state = _read(Path(review_dir) / 'state.json')
    state.update(status=status, evidence_approved=False, conclusion_approved=False,
                 research_status='not_achieved', **fields)
    _write(Path(review_dir) / 'state.json', state)


def prepare_main_evidence(review_dir, output_dir, validation_log, validation_record) -> dict:
    """Prepare a new packet under the original ledger, then wait for human review."""
    entered = time.monotonic()
    review, folder = Path(review_dir).resolve(), Path(output_dir).resolve()
    state = _read(review / 'state.json')
    if state.get('status') != 'EVIDENCE_PREPARATION_REQUIRED':
        raise ValueError('Control state does not authorize evidence preparation')
    approval = _read(review / 'scope_approval.json')
    if not isinstance(approval, dict) or not isinstance(approval.get('reviewed_scope_packet'), str):
        raise ValueError('Missing original approved scope packet')
    original_scope = Path(approval['reviewed_scope_packet']).resolve()
    if folder == review or folder == original_scope or original_scope in folder.parents:
        raise ValueError('Evidence output must be new and outside the frozen scope packet')
    if folder.exists():
        raise FileExistsError('Evidence output already exists; never overwrite or resume it')
    owned = False

    def work(handle):
        nonlocal owned
        current = _read(review / 'state.json')
        if current.get('status') != 'EVIDENCE_PREPARATION_REQUIRED':
            raise ValueError('Evidence control state changed while acquiring the lock')
        context = load_scope_context(review)
        handle.check()
        if current.get('scope_review_hash') != context['scope_hash'] or current.get('scope_approved') is not True:
            raise ValueError('Control state does not bind the approved scope')
        owned = True
        sources = backend_source_hashes()
        log = Path(validation_log).read_bytes()
        record = validation_record if isinstance(validation_record, dict) else _read(validation_record)
        _validation(log, record, sources, require_current_sources=True)
        handle.check()
        pilots = _pilot_receipts(handle.check)
        handle.check()
        folder.mkdir(parents=True, exist_ok=False)
        (folder / 'scope_approval.json').write_bytes((review / 'scope_approval.json').read_bytes())
        _write(folder / 'scope_reference.json', {
            'scope_hash': context['scope_hash'], 'original_scope_dir': str(context['scope_dir']),
            'repository_archive': SCOPE_ARCHIVE,
            'material_sha256': context['scope_request']['payload']['material_sha256'],
        })
        _write(folder / 'backend_sources.json', sources)
        _write(folder / 'runtime.json', runtime_identity())
        (folder / 'validation.log').write_bytes(log)
        _write(folder / 'validation_record.json', record)
        _write(folder / 'pilot_receipts.json', pilots)
        if sources != backend_source_hashes() or approval != _read(review / 'scope_approval.json'):
            raise ValueError('Sources or scope human approval changed during evidence preparation')
        return context, sources, record

    def finalize(value, snapshot, check):
        context, sources, record = value
        check()
        _budget_snapshot(snapshot, context['scope_dir'])
        summary = _summary(context, snapshot, record['passed'])
        _write(folder / 'budget_snapshot.json', snapshot)
        _write(folder / 'summary.json', summary)
        (folder / 'evidence_summary.txt').write_text(_human(summary), encoding='utf-8')
        request = _request(folder, context, sources, snapshot)
        _write(folder / 'evidence_review.json', request)
        _write(folder / 'manifest.json', {'version': 1, 'status': READY,
            'scope_hash': context['scope_hash'], 'review_hash': request['artifact_hash'],
            'source_hashes': sources, 'artifacts': {name: _sha(folder / name) for name in sorted(FILES)}})
        check()
        if sources != backend_source_hashes():
            raise ValueError('Backend source identity changed before evidence became ready')
        if (_approved_scope(context['scope_dir'], _read(review / 'scope_approval.json'))['scope_hash']
                != context['scope_hash']
                or (folder / 'scope_approval.json').read_bytes() != (review / 'scope_approval.json').read_bytes()):
            raise ValueError('Approved scope or human decision changed before evidence became ready')
        _control_state(review, READY, evidence_review_hash=request['artifact_hash'],
                       evidence_packet=str(folder))
        check()
        return {**summary, 'evidence_hash': request['artifact_hash'], 'evidence_dir': str(folder)}

    try:
        return run_main_phase(original_scope, review, work, finalize, started_at=entered)
    except Exception as exc:
        if not owned:
            raise
        try:
            if folder.is_dir():
                _write(folder / 'manifest.json', {'version': 1, 'status': 'STOPPED_EVIDENCE_PREPARATION_FAILED',
                                                 'error': f'{type(exc).__name__}: {str(exc)[:1000]}'})
        finally:
            _control_state(review, 'STOPPED_EVIDENCE_PREPARATION_FAILED', error=f'{type(exc).__name__}: {str(exc)[:1000]}')
        raise


def _locate_scope(reference, explicit):
    if explicit is not None:
        candidates = [Path(explicit)]
    else:
        candidates = [Path(reference['original_scope_dir']), ROOT / SCOPE_ARCHIVE]
    for candidate in candidates:
        if candidate.is_dir():
            _, request = scope._check_materials(candidate)
            if request['artifact_hash'] != reference['scope_hash']:
                raise ValueError('Evidence scope reference resolves to a different full scope hash')
            return candidate.resolve()
    raise ValueError('No original or archived packet matches this evidence scope')


def _recorded_path(value):
    """Compare recorded Windows paths portably without resolving them on a clone."""
    if not isinstance(value, str) or not value:
        raise ValueError('Malformed recorded scope path')
    if re.match(r'^[A-Za-z]:[\\/]', value) or value.startswith('\\\\'):
        return ntpath.normcase(ntpath.normpath(value))
    return posixpath.normpath(value)


def recheck_main_evidence(evidence_dir, scope_dir=None, *, require_current_sources=True) -> dict:
    """Read-only portable packet verification; archived scope never grants a budget."""
    folder = Path(evidence_dir).resolve()
    try:
        manifest = _read(folder / 'manifest.json')
        names = {path.name for path in folder.iterdir()}
        if (names != FILES | {'manifest.json'} or any(not path.is_file() or path.is_symlink() for path in folder.iterdir())
                or type(manifest.get('version')) is not int or manifest['version'] != 1
                or set(manifest) != {'version', 'status', 'scope_hash', 'review_hash', 'source_hashes', 'artifacts'}
                or manifest.get('status') != READY
                or manifest.get('artifacts') != {name: _sha(folder / name) for name in sorted(FILES)}):
            raise ValueError('Evidence packet is incomplete or artifact identities changed')
        sources = _read(folder / 'backend_sources.json')
        _hash_map(sources, expected=SOURCE_PATHS)
        if manifest.get('source_hashes') != sources:
            raise ValueError('Evidence source receipts disagree')
        reference = _read(folder / 'scope_reference.json')
        if (set(reference) != {'scope_hash', 'original_scope_dir', 'repository_archive', 'material_sha256'}
                or reference['repository_archive'] != SCOPE_ARCHIVE):
            raise ValueError('Malformed evidence scope reference')
        actual_scope = _locate_scope(reference, scope_dir)
        approval = _read(folder / 'scope_approval.json')
        context = _approved_scope(actual_scope, approval)
        if (reference['scope_hash'] != context['scope_hash']
                or _recorded_path(reference['original_scope_dir']) != _recorded_path(approval['reviewed_scope_packet'])
                or reference['material_sha256'] != context['scope_request']['payload']['material_sha256']):
            raise ValueError('Evidence scope approval, inputs or order changed')
        record = _read(folder / 'validation_record.json')
        _validation((folder / 'validation.log').read_bytes(), record, sources,
                    require_current_sources=require_current_sources)
        if _read(folder / 'pilot_receipts.json') != _pilot_receipts():
            raise ValueError('Archived pilot evidence or its checked receipt changed')
        snapshot = _read(folder / 'budget_snapshot.json')
        _budget_snapshot(snapshot, actual_scope)
        summary = _summary(context, snapshot, record['passed'])
        if (_read(folder / 'summary.json') != summary
                or (folder / 'evidence_summary.txt').read_text(encoding='utf-8') != _human(summary)):
            raise ValueError('Evidence summary differs from checked receipts')
        request = _request(folder, context, sources, snapshot)
        if (encoded(_read(folder / 'evidence_review.json')) != encoded(request)
                or manifest.get('review_hash') != request['artifact_hash']
                or manifest.get('scope_hash') != context['scope_hash']):
            raise ValueError('Evidence review does not bind the current complete packet')
        return {**summary, 'evidence_hash': request['artifact_hash'], 'evidence_dir': str(folder),
                'current_sources_checked': require_current_sources}
    except (OSError, KeyError, TypeError, AttributeError, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError(f'Invalid main evidence packet: {type(exc).__name__}') from exc


def export_execution_context(review_dir, evidence_dir, *, allow_running=False, allow_reserved=False) -> dict:
    """Validate the actual evidence decision and original live ledger, without writes."""
    review, evidence = Path(review_dir).resolve(), Path(evidence_dir).resolve()
    state = _read(review / 'state.json')
    allowed = {'RUNNING'} if allow_running else {READY}
    if state.get('status') not in allowed:
        raise ValueError('Control state does not authorize a main execution gate')
    context = load_scope_context(review)
    summary = recheck_main_evidence(evidence, context['scope_dir'], require_current_sources=True)
    if encoded(_read(evidence/'runtime.json'))!=encoded(runtime_identity()):
        raise ValueError('Approved execution runtime changed; new evidence is required')
    request = _read(evidence / 'evidence_review.json')
    raw = _read(review / 'evidence_approval.json')
    decision = validate_review_decision(request, raw.get('decision') if isinstance(raw, dict) else None)
    if (decision['decision'] != 'approve' or state.get('scope_review_hash') != context['scope_hash']
            or state.get('evidence_review_hash') != request['artifact_hash']
            or Path(state.get('evidence_packet', '')).resolve() != evidence
            or (evidence / 'scope_approval.json').read_bytes() != (review / 'scope_approval.json').read_bytes()):
        raise ValueError('Actual evidence approval or control binding is missing/stale')
    budget = read_main_budget(context['scope_dir'])
    recorded = _read(evidence / 'budget_snapshot.json')
    if budget['segments'][:len(recorded['segments'])] != recorded['segments']:
        raise ValueError('Original main budget lost or changed its evidence preparation history')
    if allow_running or allow_reserved:
        # Only the one currently owned reservation may follow this evidence.
        # It reserves all remaining time, so its available balance reads zero.
        if (len(budget['segments']) != len(recorded['segments'])+1
                or budget['segments'][-1]['finished_seconds'] is not None
                or budget['active_seconds'] != recorded['active_seconds']):
            raise ValueError('Main gate requires exactly its active execution reservation')
    elif (budget['segments'] != recorded['segments'] or budget['remaining_active_seconds'] <= 0):
        raise ValueError('Original main budget is exhausted, interrupted or already used after evidence')
    return {**context, 'evidence_dir': evidence, 'evidence_request': request,
            'evidence_decision': decision, 'evidence_hash': request['artifact_hash'],
            'backend_source_hashes': _read(evidence / 'backend_sources.json'),
            'budget_snapshot': budget, 'evidence_summary': summary}


execution_context = export_execution_context
