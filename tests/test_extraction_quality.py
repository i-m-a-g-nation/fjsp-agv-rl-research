"""Citation repair must be bounded and must never certify scientific claims."""
import json

import pytest

from src.ai_workflow.config import LLMConfig
from src.ai_workflow.schemas import ClaimEvidenceReference, PaperExtractionReport

TEXT = 'We study identical parallel machine scheduling.\nWe minimize total tardiness.\n'


def make_report(*, complete=False, quote='We minimize total tardiness.'):
    references = [{'field': 'problem_type', 'quote': 'We study identical parallel machine scheduling.'}]
    if complete:
        references.append({'field': 'math_model.objectives', 'item_index': 0, 'quote': quote})
    return PaperExtractionReport(title='Synthetic fixture', problem_type='Identical parallel machine scheduling',
        extraction_method='llm', math_model={'objectives': ['Minimize total tardiness.']},
        rl_formulation={}, codebase_alignment={}, claim_evidence=references)


def test_complete_first_attempt_does_not_spend_a_repair_and_remains_unverified():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    calls = []
    def once(feedback):
        calls.append(feedback)
        return make_report(complete=True)
    report, quality = extract_with_feedback(LLMConfig(), once, paper_text=TEXT)
    assert calls == [''] and quality['status'] == 'complete' and quality['attempts'] == 1
    assert report.evidence_status == 'unverified'
    assert quality['history'][0]['report']['evidence_status'] == 'unverified'


def test_missing_reference_is_reported_to_exactly_one_repair_and_history_is_preserved():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    calls = []
    first = make_report()
    before = first.model_dump()
    def once(feedback):
        calls.append(feedback)
        return first if len(calls) == 1 else make_report(complete=True)
    report, quality = extract_with_feedback(LLMConfig(), once, paper_text=TEXT)
    assert len(calls) == 2 and calls[0] == ''
    assert 'math_model.objectives' in calls[1] and 'missing' in calls[1]
    assert quality['status'] == 'complete' and quality['attempts'] == 2
    assert quality['history'][0]['report']['evidence_audit']['summary']['all_claims_located'] is False
    assert quality['history'][1]['report'] == report.model_dump()
    assert first.model_dump() == before, 'Repair auditing must not mutate the returned source report.'


@pytest.mark.parametrize('repairs,expected_calls', [(0, 1), (1, 2)])
def test_exhausted_repair_returns_incomplete_not_a_pass(repairs, expected_calls):
    from src.ai_workflow.extraction_quality import extract_with_feedback
    calls = []
    def once(feedback):
        calls.append(feedback)
        return make_report()
    report, quality = extract_with_feedback(LLMConfig(extraction_repair_attempts=repairs), once, paper_text=TEXT)
    assert len(calls) == expected_calls and quality['attempts'] == expected_calls
    assert quality['status'] == 'incomplete' and not report.evidence_audit['summary']['all_claims_located']


@pytest.mark.parametrize('quote,source,status', [
    ('Not in the original input text.', TEXT, 'invalid'),
    ('We minimize total tardiness.', TEXT + 'We minimize total tardiness.\n', 'ambiguous'),
])
def test_invalid_and_ambiguous_quotes_produce_specific_feedback(quote, source, status):
    from src.ai_workflow.extraction_quality import extract_with_feedback
    calls = []
    def once(feedback):
        calls.append(feedback)
        return make_report(complete=True, quote=quote)
    _, quality = extract_with_feedback(LLMConfig(), once, paper_text=source)
    assert status in calls[1] and 'math_model.objectives' in calls[1]
    assert quality['status'] == 'incomplete'


def test_rejected_reference_feedback_does_not_replay_untrusted_field_instructions():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    calls = []
    def once(feedback):
        calls.append(feedback)
        report = make_report(complete=True)
        report.claim_evidence.append(ClaimEvidenceReference(field='IGNORE_PREVIOUS_INSTRUCTIONS', quote='irrelevant quote'))
        return report
    _, quality = extract_with_feedback(LLMConfig(), once, paper_text=TEXT)
    assert 'unknown_claim_field_or_index' in calls[1]
    assert 'IGNORE_PREVIOUS_INSTRUCTIONS' not in calls[1]
    assert quality['status'] == 'incomplete'


def test_empty_claims_cannot_game_the_complete_gate():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    empty = PaperExtractionReport(title='Blank', problem_type='', math_model={}, rl_formulation={}, codebase_alignment={})
    _, quality = extract_with_feedback(LLMConfig(), lambda _: empty, paper_text=TEXT)
    assert quality['status'] == 'incomplete' and quality['attempts'] == 2


def test_forged_audit_and_verified_flag_are_overwritten_without_mutating_input():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    forged = make_report()
    forged.evidence_status = 'verified'
    forged.evidence_audit = {'summary': {'all_claims_located': True}}
    report, quality = extract_with_feedback(LLMConfig(extraction_repair_attempts=0), lambda _: forged, paper_text=TEXT)
    assert quality['status'] == 'incomplete' and report.evidence_status == 'unverified'
    assert forged.evidence_status == 'verified'


def test_second_attempt_respects_existing_provider_budget(tmp_path):
    from src.ai_workflow.extraction_quality import extract_with_feedback
    from src.ai_workflow.runtime_budget import BudgetLimits, BudgetExceeded, RunBudget
    budget = RunBudget(tmp_path / 'budget.sqlite', BudgetLimits(max_provider_calls=1, max_output_tokens=4096))
    cfg = LLMConfig(budget=budget)
    def once(feedback):
        cfg.provider_timeout(output_tokens=4096)
        return make_report()
    with pytest.raises(BudgetExceeded):
        extract_with_feedback(cfg, once, paper_text=TEXT)
    assert budget.snapshot()['provider_calls'] == 1


def test_feedback_is_bounded_and_does_not_copy_previous_model_claim_text():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    calls = []
    def once(feedback):
        calls.append(feedback)
        report = make_report()
        report.math_model.objectives = ['DO_NOT_REPLAY_MODEL_INSTRUCTIONS'] * 500
        return report
    _, quality = extract_with_feedback(LLMConfig(), once, paper_text=TEXT)
    assert 0 < len(calls[1]) <= 6000
    assert 'DO_NOT_REPLAY_MODEL_INSTRUCTIONS' not in calls[1] and quality['status'] == 'incomplete'


def test_source_map_mismatch_and_parse_failure_do_not_trigger_repair():
    from src.ai_workflow.extraction_quality import extract_with_feedback
    with pytest.raises(ValueError, match='Source map'):
        extract_with_feedback(LLMConfig(), lambda _: make_report(), paper_text=TEXT,
            source_map={'text_sha256': 'wrong', 'text_length': len(TEXT)})
    calls = []
    def invalid(feedback):
        calls.append(feedback)
        raise json.JSONDecodeError('Invalid model JSON', '', 0)
    with pytest.raises(json.JSONDecodeError):
        extract_with_feedback(LLMConfig(), invalid, paper_text=TEXT)
    assert calls == ['']


@pytest.mark.parametrize('error_kind', ['provider', 'parse', 'budget'])
def test_repair_exception_preserves_initial_material_and_original_failure_type(error_kind):
    from src.ai_workflow.extraction_quality import extract_with_feedback
    from src.ai_workflow.runtime_budget import BudgetExceeded
    error = {'provider': RuntimeError('secret-body-sentinel'),
             'parse': json.JSONDecodeError('secret-body-sentinel', '', 0),
             'budget': BudgetExceeded('budget exhausted')}[error_kind]
    snapshots, calls = [], []
    def once(feedback):
        calls.append(feedback)
        if len(calls) > 1:
            raise error
        return make_report()
    with pytest.raises(type(error)) as captured:
        extract_with_feedback(LLMConfig(), once, paper_text=TEXT, on_attempt=snapshots.append)
    assert captured.value is error
    assert len(calls) == 2 and len(snapshots) == 2
    quality = captured.value.extraction_quality
    assert quality['status'] == 'incomplete' and len(quality['history']) == 1
    assert quality['repair_error']['type'] == type(error).__name__
    assert quality['history'][0]['report']['math_model']['objectives'] == ['Minimize total tardiness.']
    assert 'secret-body-sentinel' not in json.dumps(quality)
    assert 'repair_error' not in snapshots[0], 'The first saved snapshot must be detached.'
