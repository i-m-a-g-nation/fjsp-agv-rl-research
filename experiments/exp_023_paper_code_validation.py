"""Read-only real-paper/author-code validation; no algorithm or approval is applied."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ai_workflow.config import LLMConfig, load_dotenv_if_present
from src.ai_workflow.contracts import get_research_contract
from src.ai_workflow.evidence_sources import assert_source_files_unchanged
from src.ai_workflow.evidence import CLAIM_FIELDS
from src.ai_workflow.extraction_quality import extract_with_feedback
from src.ai_workflow.field_extraction import extract_paper_field
from src.ai_workflow.langgraph_pipeline import _llm_extract_paper
from src.ai_workflow.runtime_budget import BudgetExceeded, BudgetLimits, RunBudget
from src.ai_workflow.source_bundle import (
    acquire_source_bundle, make_paper_context, make_paper_excerpt, validate_excerpt_selection,
    validate_source_request, verify_source_bundle,
)


def _limits(request: dict) -> BudgetLimits:
    if request.get('version') != 1 or request.get('track') != 'graduation':
        raise ValueError('This validation requires version1 and graduation track')
    limits = BudgetLimits(**request['limits'])
    if limits.max_active_seconds > 300 or limits.max_provider_calls > 4 or limits.max_output_tokens > 32768:
        raise ValueError('Real-source validation exceeds the bounded budget')
    units = request['units']
    if not isinstance(units, list) or not 1 <= len(units) <= 2:
        raise ValueError('Select one or two targeted extraction units')
    ids = set()
    selected = {item['path'] for item in request['repository']['files']}
    for unit in units:
        if not isinstance(unit.get('id'), str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', unit['id']) or unit['id'] in ids:
            raise ValueError('Unique simple unit IDs are required')
        ids.add(unit['id'])
        if not isinstance(unit.get('goal'), str) or len(unit['goal']) > 2000:
            raise ValueError('Targeted extraction goal exceeds scope')
        pages = unit['pages']
        if (not isinstance(pages, list) or not 1 <= len(pages) <= 10
                or any(type(p) is not int or not 1 <= p <= 100 for p in pages)
                or pages != sorted(set(pages))):
            raise ValueError('Select sorted unique physical PDF pages')
        if 'field' in unit or 'excerpts' in unit:
            if unit.get('field') not in CLAIM_FIELDS or not unit['goal'].strip():
                raise ValueError('Select one supported paper field and a nonempty question')
            validate_excerpt_selection(unit.get('excerpts'))
            if pages != sorted({span['page'] for span in unit['excerpts']}):
                raise ValueError('Field pages must match exact excerpt selectors')
        ranges = unit['code_ranges']
        if not isinstance(ranges, list) or len(ranges) > 8:
            raise ValueError('Too many code evidence ranges')
        for item in ranges:
            if (item['path'] not in selected or type(item['start']) is not int or type(item['end']) is not int
                    or not 1 <= item['start'] <= item['end'] or item['end'] - item['start'] >= 80):
                raise ValueError('Invalid selected code range')
    return limits


def _code_context(bundle: Path, request: dict, ranges: list[dict]) -> list[dict]:
    verify_source_bundle(bundle)
    result = []
    for item in ranges:
        path = bundle / 'code' / item['path']
        lines = path.read_text(encoding='utf-8').splitlines()
        if item['end'] > len(lines):
            raise ValueError('Code evidence range exceeds the pinned file')
        chosen = []
        for line in lines[item['start'] - 1:item['end']]:
            if len('\n'.join([*chosen, line])) > 1200:
                break
            chosen.append(line)
        if not chosen:
            raise ValueError('Code evidence line exceeds the bounded context')
        content = '\n'.join(chosen)
        end = item['start'] + len(chosen) - 1
        source = (f'https://github.com/{request["repository"]["name"]}/blob/'
                  f'{request["repository"]["commit"]}/{item["path"]}#L{item["start"]}-L{end}')
        result.append({'source': source, 'title': 'EXTERNAL AUTHOR CODE (not project src)',
                       'content': content, 'path': item['path'], 'start': item['start'], 'end': end,
                       'snippet_sha256': hashlib.sha256(content.encode('utf-8')).hexdigest()})
    return result


def _model_profile(request: dict, limits: BudgetLimits, *, extract: bool) -> dict:
    profile = request.get('model_request', {'profile': 'bounded', 'max_output_tokens': 8192,
                                           'request_timeout_seconds': 60})
    if not isinstance(profile, dict) or set(profile) - {'profile', 'max_output_tokens', 'request_timeout_seconds', 'repair_attempts'}:
        raise ValueError('Unsupported model request profile')
    allowed = {'bounded': (8192, 60), 'paper_excerpt': (16384, 120)}
    if (profile.get('profile') not in allowed
            or (profile.get('max_output_tokens'), profile.get('request_timeout_seconds')) != allowed[profile['profile']]):
        raise ValueError('Unsupported explicit model request caps')
    repairs = profile.get('repair_attempts', 1)
    if type(repairs) is not int or not 0 <= repairs <= 1:
        raise ValueError('Bounded extraction repair limit required')
    if extract and (limits.max_output_tokens < profile['max_output_tokens']
                    or limits.max_active_seconds < profile['request_timeout_seconds']):
        raise ValueError('Per-request profile must fit inside the declared batch envelope')
    return {**profile, 'repair_attempts': repairs}


def run_validation(request: dict, output_dir: Path, *, extract: bool = False,
                   pdf_cache: Path | None = None, repository_cache: Path | None = None,
                   config: LLMConfig | None = None) -> dict:
    validate_source_request(request)
    limits = _limits(request)
    model_request = _model_profile(request, limits, extract=extract)
    cfg = config
    if extract:
        cfg = cfg or LLMConfig()
        if (not cfg.has_api_key or cfg.base_url != 'https://api.deepseek.com' or cfg.model_name != 'deepseek-flash'
                or cfg.thinking_mode != 'enabled' or cfg.reasoning_effort != 'max'
                or cfg.max_output_tokens != 8192 or cfg.request_timeout_seconds != 60 or cfg.max_retries != 0):
            raise ValueError('Live extraction requires the explicit official Flash max8192/60 profile and a key')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    effective_limits = limits if extract else replace(limits, max_provider_calls=0, max_output_tokens=0)
    budget = RunBudget(output_dir / 'budget.sqlite', effective_limits)
    if cfg is not None and extract:
        cfg = replace(cfg, budget=budget, allow_fallback=False, request_profile=model_request['profile'],
            max_output_tokens=model_request['max_output_tokens'],
            request_timeout_seconds=model_request['request_timeout_seconds'],
            extraction_repair_attempts=model_request['repair_attempts'])
    record = {'kind': 'real_paper_author_code_validation', 'status': 'ACQUIRING_SOURCES',
        'research_status': 'not_achieved', 'reproduction_status': 'not_executed',
        'candidate_application_status': 'not_applied', 'request': request,
        'target_contract': get_research_contract('graduation').to_dict(),
        'limits': asdict(effective_limits), 'units': [{'id': unit['id'], 'status': 'NOT_RUN'} for unit in request['units']],
        'notice': 'Source integrity and citation locations do not certify semantic agreement or research completion.'}
    if extract:
        record['model_profile'] = {'model': cfg.model_name, 'thinking': cfg.thinking_mode,
            'reasoning_effort': cfg.reasoning_effort, 'max_output_tokens': cfg.max_output_tokens,
            'request_timeout_seconds': cfg.request_timeout_seconds, 'max_retries': cfg.max_retries,
            'request_profile': cfg.request_profile, 'repair_attempts': cfg.extraction_repair_attempts}
    record['controller_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def save():
        encoded = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)
        if cfg is not None and cfg.api_key:
            encoded = encoded.replace(cfg.api_key, '<redacted>')
        pending = output_dir / 'result.tmp'
        pending.write_text(encoded + '\n', encoding='utf-8')
        pending.replace(output_dir / 'result.json')

    started = time.monotonic()
    budget.start_segment()
    current = None
    try:
        save()
        bundle = output_dir / 'source_bundle'
        sources = acquire_source_bundle(request, bundle, pdf_cache=pdf_cache, repository_cache=repository_cache,
                                        remaining_seconds=budget.remaining_seconds)
        record['sources'] = sources
        if sources['status'] != 'COMPLETED':
            record['status'] = 'SOURCE_FAILED'
        else:
            verify_source_bundle(bundle)
            budget.remaining_seconds()
            record['status'] = 'SOURCES_VERIFIED_UNREVIEWED'
            if extract or any('field' in unit for unit in request['units']):
                for unit, current in zip(request['units'], record['units']):
                    if not extract and 'field' not in unit:
                        continue
                    budget.remaining_seconds()
                    text, source_map = (make_paper_excerpt(bundle, unit['excerpts']) if 'field' in unit
                                        else make_paper_context(bundle, unit['pages']))
                    assert_source_files_unchanged(source_map)
                    context = _code_context(bundle, request, unit['code_ranges'])
                    budget.remaining_seconds()
                    current.update(status='EXTRACTING' if extract else 'PREVIEW_READY',
                                   source_map=source_map, code_context=context)
                    if 'field' in unit:
                        current['field'] = unit['field']
                    save()
                    if not extract:
                        continue

                    def response_snapshot(diagnostic):
                        current.setdefault('responses', []).append(diagnostic)
                        save()

                    def once(feedback):
                        if 'field' in unit:
                            return extract_paper_field(cfg=cfg, paper_title=request['paper']['title'],
                                paper_text=text, source_map=source_map, field=unit['field'],
                                question=unit['goal'], feedback=feedback, on_response=response_snapshot)
                        return _llm_extract_paper(cfg=cfg, paper_title=request['paper']['title'], paper_text=text,
                            content_depth='full_text', resolution_log=[
                                f'Selected complete physical PDF pages {unit["pages"]}; not the entire article.',
                                'Pinned external code is comparative context, not paper evidence or project implementation.'],
                            goal=('Extract only original-paper facts; project adaptation is a later, separate review.\n'
                                  + unit['goal']),
                            retrieved_literature=[], retrieved_codebase=context, lit_sources=[], feedback=feedback,
                            on_response=response_snapshot)

                    def snapshot(quality):
                        current['quality'] = quality
                        save()

                    report, quality = extract_with_feedback(cfg, once, paper_text=text,
                        source_map=source_map, on_attempt=snapshot)
                    assert_source_files_unchanged(source_map)
                    budget.remaining_seconds()
                    current.update(status='COMPLETE' if quality['status'] == 'complete' else 'EVIDENCE_INCOMPLETE',
                                   extraction=report.model_dump(), quality=quality)
                    save()
                budget.remaining_seconds()
                if extract:
                    record['status'] = ('EVIDENCE_READY_UNREVIEWED' if all(
                        item['status'] == 'COMPLETE' for item in record['units']) else 'EVIDENCE_INCOMPLETE')
    except Exception as exc:
        record['status'] = 'BUDGET_EXHAUSTED' if isinstance(exc, BudgetExceeded) else 'FAILED'
        record['error'] = {'type': type(exc).__name__}
        if current is not None:
            current['status'] = record['status']
            if getattr(exc, 'extraction_quality', None):
                current['quality'] = exc.extraction_quality
    finally:
        elapsed = time.monotonic() - started
        if record['status'] in ('SOURCES_VERIFIED_UNREVIEWED', 'EVIDENCE_READY_UNREVIEWED') and elapsed >= effective_limits.max_active_seconds:
            record.update(status='BUDGET_EXHAUSTED', error={'type': 'BudgetExceeded'})
        budget.record_active_seconds(elapsed)
        record['budget'] = budget.snapshot()
        save()
        lines = ['<!-- fjsp-generated-report track=graduation -->', '# Real paper / author code validation', '',
            f'Status: {record["status"]}', f'Paper: {request["paper"]["title"]}',
            f'Repository: {request["repository"]["name"]}@{request["repository"]["commit"]}', '',
            'Research: not_achieved; reproduction: not_executed; candidate application: not_applied.',
            'All extraction remains unverified. No approvals, trained policies or scheduling results are created.', '']
        for unit in record['units']:
            summary = unit.get('extraction', {}).get('evidence_audit', {}).get('summary', {})
            lines.append(f'- {unit["id"]}: {unit["status"]}; located {summary.get("claims_located", 0)}/{summary.get("claims_total", 0)}')
        (output_dir / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return record


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate source request field')
        result[key] = value
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, default=ROOT / 'experiments/requests/paper_code_validation_v1.json')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--pdf-cache', type=Path)
    parser.add_argument('--repository-cache', type=Path, help='Explicit pinned GitHub records/files cache; never bypasses identity checks.')
    parser.add_argument('--extract', action='store_true', help='Explicitly enable the bounded paid max-thinking extraction.')
    args = parser.parse_args(argv)
    try:
        if args.request.stat().st_size > 1024 * 1024:
            raise ValueError('Request too large')
        request = json.loads(args.request.read_text(encoding='utf-8'), object_pairs_hook=_unique_fields,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite request value')))
        config = None
        if args.extract:
            load_dotenv_if_present()
            config = LLMConfig()
        now = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d-%H%M%S')
        output = args.output_dir or ROOT / 'experiments/runs' / f'paper-code-{now}-{uuid4().hex[:8]}'
        result = run_validation(request, output, extract=args.extract, pdf_cache=args.pdf_cache,
                                repository_cache=args.repository_cache, config=config)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        print(f'Validation setup failed: {type(exc).__name__}; no secret values displayed.')
        return 1
    print(json.dumps({'status': result['status'], 'provider_calls': result['budget']['provider_calls'],
                      'output_dir': str(output), 'research_status': result['research_status']}, ensure_ascii=False))
    return 0 if result['status'] in ('SOURCES_VERIFIED_UNREVIEWED', 'EVIDENCE_READY_UNREVIEWED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
