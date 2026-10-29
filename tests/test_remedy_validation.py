"""Configured observer tests use synthetic solvers, never native CP search."""
import copy
import pytest

from tests.test_solver_diagnostics import dev_case,factory
from src.graduation import solver as baseline
from src.graduation.remedy_validation import capture_configured,recheck_configured,classify_pairs


@pytest.mark.parametrize('presolve',[True,False])
def test_only_presolve_changes_and_synthetic_evidence_cannot_be_native(presolve):
    before=baseline.cp_model.CpSolver
    result=capture_configured(dev_case(),'fixed',presolve,_solver_factory=factory())
    assert baseline.cp_model.CpSolver is before
    assert result['execution_kind']=='SYNTHETIC_SOLVER_TEST'
    assert result['effective_parameters']=={'cp_model_presolve':presolve,'max_time_in_seconds':1.,
        'num_search_workers':1,'random_seed':42,'log_search_progress':False}
    report=recheck_configured(result,dev_case(),'fixed',presolve)
    assert report['raw_schedule_status']=='PASS' and report['derived_tardiness']==4
    assert report['reported_objective']==4 and report['objective_consistent'] is True
    assert report['accepted_for_research'] is False


def test_original_integer_disagreement_stays_rejected_with_valid_raw_schedule():
    result=capture_configured(dev_case(),'fixed',True,_solver_factory=factory(objective=7.))
    report=recheck_configured(result,dev_case(),'fixed',True)
    assert report['baseline_status']=='ERROR' and report['raw_schedule_status']=='PASS'
    assert report['reported_objective']==7 and report['derived_tardiness']==4
    assert report['objective_consistent'] is False and report['error_reproduced'] is True


@pytest.mark.parametrize('fault',['parameters','flag','candidate','accepted_payload'])
def test_replay_rejects_configuration_or_evidence_changes(fault):
    result=capture_configured(dev_case(),'fixed',False,_solver_factory=factory())
    if fault=='parameters':result['effective_parameters']['num_search_workers']=2
    elif fault=='flag':result['configured_presolve']=True
    elif fault=='candidate':result['candidate']['production'][0]['end']=3
    else:result['baseline_row']['payload']['records'][0]['start']=1
    with pytest.raises(ValueError):recheck_configured(result,dev_case(),'fixed',False)


@pytest.mark.parametrize('reproduced,remedy_ok,controls_ok,expected',[
    (5,5,True,'SUPPORTED_ON_FIVE_REQUESTS'),(4,5,True,'INCONCLUSIVE_ORIGINAL_NOT_REPRODUCED'),
    (5,4,True,'REMEDY_NOT_CONFIRMED'),(5,5,False,'FAILED_TINY_CONTROLS'),
])
def test_counterfactual_never_claims_support_without_all_controls(reproduced,remedy_ok,controls_ok,expected):
    assert classify_pairs(reproduced,remedy_ok,controls_ok)==expected


def test_observed_status_cannot_promote_a_feasible_baseline_to_optimal():
    result=capture_configured(dev_case(),'fixed',False,_solver_factory=factory())
    result['observation']['status_name']='OPTIMAL'
    result['observation']['status_code']=int(baseline.cp_model.OPTIMAL)
    result['observation']['response']['status_code']=int(baseline.cp_model.OPTIMAL)
    with pytest.raises(ValueError):recheck_configured(result,dev_case(),'fixed',False)


def test_unknown_stays_without_a_plan_and_cannot_support_the_remedy():
    result=capture_configured(dev_case(),'fixed',False,_solver_factory=factory(name='UNKNOWN'))
    report=recheck_configured(result,dev_case(),'fixed',False)
    assert report['baseline_status']=='NO_SCHEDULE' and report['raw_schedule_status']=='NO_CANDIDATE'
    assert report['objective_consistent'] is report['error_reproduced'] is False
