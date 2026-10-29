"""Synthetic solver responses exercise observation without native CP search."""
from dataclasses import asdict
import json
import math
from types import SimpleNamespace

import pytest

from src.graduation import solver as baseline
from tests.graduation_helpers import one_machine
from src.graduation.solver_diagnostics import capture_case, recheck_capture, audit_saved_failures


def dev_case():
    data,_=one_machine()
    return {'case_id':'DEVTEST-diagnostic','group':'primary','data':asdict(data)}


def factory(*,objective=4.,bound=0.,name='FEASIBLE',response_failure=False):
    class SyntheticSolver:
        def __init__(self):self.parameters=SimpleNamespace();self.values={}
        def Solve(self,model):
            self.model=model
            self.values={'s0':2,'e0':4,'x0_0':1,'t0':2,'s1':4,'e1':6,'x1_0':1,'t1':2,'ms0':0,'me0':2}
            return getattr(baseline.cp_model,name)
        def StatusName(self,status):return name
        def ObjectiveValue(self):return objective
        def BestObjectiveBound(self):return bound
        def WallTime(self):return .01
        def Value(self,var):return self.values[var.Name()]
        def ResponseProto(self):
            if response_failure:raise RuntimeError('TEST_ONLY-observer-unavailable')
            return SimpleNamespace(status=int(getattr(baseline.cp_model,name)),objective_value=objective,
                best_objective_bound=bound,solution=[] if name=='UNKNOWN' else
                [self.values[v.name] for v in self.model.Proto().variables])
    return SyntheticSolver


def test_observer_preserves_original_accepted_row_and_restores_factory():
    before=baseline.cp_model.CpSolver
    result=capture_case(dev_case(),'fixed',_solver_factory=factory())
    assert baseline.cp_model.CpSolver is before
    assert result['execution_kind']=='SYNTHETIC_SOLVER_TEST'
    assert result['accepted_for_research'] is False
    assert result['baseline_row']['status']=='ACCEPTED'
    assert result['baseline_row']['metrics']['total_tardiness']==4
    assert result['candidate']['label']=='UNVALIDATED_DIAGNOSTIC_CANDIDATE'
    assert result['numeric_checks']['derived_total_tardiness']==4
    assert result['numeric_checks']['integer_tardiness_sum']==4
    assert result['numeric_checks']['objective_equals_independent_tardiness'] is True
    assert recheck_capture(result,dev_case(),'fixed')['status']=='VERIFIED_DIAGNOSTIC_CAPTURE'


@pytest.mark.parametrize('objective,bound,reason',[
    (math.nextafter(4.,math.inf),0.,'objective_equals_independent_tardiness'),
    (math.nextafter(4.,-math.inf),0.,'objective_equals_independent_tardiness'),
    (4.,math.nextafter(4.,math.inf),'bound_le_objective'),
    (4.,-math.ulp(1.),'bound_nonnegative'),
    (float('nan'),0.,'objective_finite'),
    (float('inf'),0.,'objective_finite'),
    (4.,float('nan'),'bound_finite'),
])
def test_rejected_diagnostic_keeps_exact_numeric_evidence_without_promoting(objective,bound,reason):
    result=capture_case(dev_case(),'fixed',_solver_factory=factory(objective=objective,bound=bound))
    row=result['baseline_row']
    assert row['status']=='ERROR' and row['metrics'] is row['payload'] is None
    assert row['error']=='GraduationSolverError: Solver objective/bound disagrees with independent total tardiness'
    assert result['numeric_checks'][reason] is False
    assert result['observation']['api']['objective']['repr']==repr(objective)
    assert result['observation']['api']['objective']['hex']==objective.hex()
    json.dumps(result,allow_nan=False)
    recheck_capture(result,dev_case(),'fixed')


def test_capture_failure_does_not_turn_original_success_into_error():
    result=capture_case(dev_case(),'fixed',_solver_factory=factory(response_failure=True))
    assert result['baseline_row']['status']=='ACCEPTED'
    assert result['observation']['capture_errors']
    assert result['capture_status']=='PARTIAL'
    assert result['candidate']['production'][0]['end']==4


def test_unknown_has_no_candidate_and_no_accepted_metrics():
    result=capture_case(dev_case(),'fixed',_solver_factory=factory(name='UNKNOWN'))
    assert result['baseline_row']['status']=='NO_SCHEDULE'
    assert result['candidate'] is None
    assert result['numeric_checks']['derived_total_tardiness'] is None
    recheck_capture(result,dev_case(),'fixed')


@pytest.mark.parametrize('fault',['input','mode','numeric','candidate','raw_response','row'])
def test_replay_rejects_changed_diagnostic(fault):
    result=capture_case(dev_case(),'fixed',_solver_factory=factory())
    if fault=='input':result['input_sha256']='0'*64
    elif fault=='mode':result['mode']='joint'
    elif fault=='numeric':result['numeric_checks']['derived_total_tardiness']=3
    elif fault=='candidate':result['candidate']['production'][0]['end']=3
    elif fault=='raw_response':result['observation']['response']['variables'][0]['value']+=1
    else:result['baseline_row']['metrics']['total_tardiness']+=1
    with pytest.raises(ValueError):recheck_capture(result,dev_case(),'fixed')


def test_saved_audit_is_readonly_and_selects_only_five_original_errors():
    from pathlib import Path
    archive=Path(__file__).resolve().parents[1]/'experiments/results/exp_030_graduation_main_attempt2_v1'
    selection=audit_saved_failures(archive)
    assert selection['original_experiment_status']=='FAILED'
    assert [r['sequence'] for r in selection['requests']]==[167,186,222,226,229]
    assert len(selection['requests'])==5 and selection['solver_calls']==0
    assert all(r['historical_row']['status']=='ERROR' for r in selection['requests'])


def test_factory_is_restored_even_when_solver_is_interrupted():
    before=baseline.cp_model.CpSolver
    class Interrupted:
        parameters=SimpleNamespace()
        def Solve(self,model):raise KeyboardInterrupt('TEST_ONLY-interrupted')
    with pytest.raises(KeyboardInterrupt):
        capture_case(dev_case(),'fixed',_solver_factory=Interrupted)
    assert baseline.cp_model.CpSolver is before


def test_observer_row_is_byte_identical_to_unobserved_synthetic_baseline():
    from unittest.mock import patch
    from src.graduation import reference_main_results as main
    from src.graduation.reference_protocol import encoded
    with patch.object(baseline.cp_model,'CpSolver',factory()):
        expected=main.evaluate_row(dev_case(),'fixed')
    actual=capture_case(dev_case(),'fixed',_solver_factory=factory())
    assert encoded(actual['baseline_row'])==encoded(expected)


def test_solver_exception_is_partial_capture_and_keeps_original_rejection():
    class Failed:
        parameters=SimpleNamespace()
        def Solve(self,model):raise RuntimeError('TEST_ONLY-native failure')
    result=capture_case(dev_case(),'fixed',_solver_factory=Failed)
    assert result['baseline_row']['status']=='ERROR'
    assert result['baseline_row']['error']=='RuntimeError: TEST_ONLY-native failure'
    assert result['capture_status']=='PARTIAL' and result['observation']['capture_errors']
    assert result['candidate'] is None
    recheck_capture(result,dev_case(),'fixed')


@pytest.mark.parametrize('fault',['maintenance','raw_objective','promoted'])
def test_independent_arithmetic_audit_rejects_rehashed_bad_candidates(tmp_path,fault):
    import hashlib
    from pathlib import Path
    import runpy
    import shutil
    archive=Path(__file__).resolve().parents[1]/'experiments/results/exp_031_consistency_diagnostic_dev_v1'
    audit=runpy.run_path(str(archive/'inspect_candidates.py'))['audit']
    assert len(audit(archive)['rows'])==5
    copied=tmp_path/'TEST_ONLY-diagnostic';shutil.copytree(archive/'run',copied/'run')
    capture=copied/'run/captures/0167.json';value=json.loads(capture.read_text(encoding='utf-8'))
    if fault=='maintenance':value['candidate']['maintenance'][0]['start']=-1
    elif fault=='raw_objective':value['observation']['model']['objective']['coeffs'][0]=2
    else:value['accepted_for_research']=True
    capture.write_text(json.dumps(value),encoding='utf-8')
    state=copied/'run/state.json';value=json.loads(state.read_text(encoding='utf-8'))
    value['rows'][0]['capture_sha256']=hashlib.sha256(capture.read_bytes()).hexdigest()
    state.write_text(json.dumps(value),encoding='utf-8')
    with pytest.raises(ValueError):audit(copied)
