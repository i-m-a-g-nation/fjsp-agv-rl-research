"""One-parameter development observations; original solver and acceptance stay intact."""
from dataclasses import asdict
from unittest.mock import patch

from src.graduation import solver as baseline
from src.graduation import solver_diagnostics as diagnostics
from src.graduation import reference_main_results as main
from src.graduation.data import to_fjsp_instance
from src.graduation.feasibility import check_parallel_maintenance_feasibility
from src.graduation.metrics import calculate_total_tardiness
from src.graduation.result import MaintenanceRecord,MaintenanceScheduleResult
from src.graduation.reference_protocol import encoded
from src.scheduling.encoding import ScheduleRecord


def parameters(presolve):
    if type(presolve) is not bool:raise ValueError('Presolve choice must be an explicit bool')
    return {'cp_model_presolve':presolve,'max_time_in_seconds':1.,'num_search_workers':1,
            'random_seed':42,'log_search_progress':False}


class _ParameterObserver:
    def __init__(self,delegate):self.delegate=delegate;self.seen=None;self.calls=0
    def __getattr__(self,name):return getattr(self.delegate,name)
    def Solve(self,model):
        self.seen={key:getattr(self.delegate.parameters,key) for key in parameters(True)}
        self.calls+=1
        return self.delegate.Solve(model)


def capture_configured(case,mode,presolve,*,_solver_factory=None):
    """Use only inside the dedicated worker or explicitly synthetic tests."""
    parameters(presolve);main._identity(case,mode);main._data(case)
    original=baseline.cp_model.CpSolver;factory=_solver_factory or original;wrappers=[]
    def configured():
        delegate=factory();delegate.parameters.cp_model_presolve=presolve
        wrapper=_ParameterObserver(delegate);wrappers.append(wrapper);return wrapper
    with patch.object(baseline.cp_model,'CpSolver',configured):
        result=diagnostics.capture_case(case,mode)
    result.update(configured_presolve=presolve,
        effective_parameters=wrappers[0].seen if len(wrappers)==1 else None,
        solver_solve_calls=sum(w.calls for w in wrappers))
    if _solver_factory is not None:result['execution_kind']='SYNTHETIC_SOLVER_TEST'
    encoded(result)
    return result


def _raw_schedule(result,case,mode):
    candidate=result['candidate']
    if candidate is None:return None
    if candidate['complete'] is not True:raise ValueError('Incomplete raw candidate')
    data=main._data(case);schedule=MaintenanceScheduleResult(instance=to_fjsp_instance(data))
    for r in candidate['production']:
        if len(r['selected_machines'])!=1:raise ValueError('Raw assignment is not unique')
        schedule.records.append(ScheduleRecord(r['job_id'],0,r['selected_machines'][0],
            r['start'],r['end'],r['processing_time_expected']))
    schedule.maintenance_records=[MaintenanceRecord(r['machine_id'],r['start'],r['end'],r['duration_expected'])
                                  for r in candidate['maintenance']]
    schedule.compute_makespan();schedule.total_tardiness=calculate_total_tardiness(data,schedule)
    valid,issues=check_parallel_maintenance_feasibility(schedule,data,mode=mode)
    if not valid:raise ValueError('Raw candidate failed G1: '+','.join(i.code for i in issues))
    response=result['observation']['response'];model=result['observation']['model']
    variables=response['variables']
    if ([v['index'] for v in variables]!=list(range(len(variables)))
            or len({v['name'] for v in variables})!=len(variables)
            or model['variables']!=[{k:v[k] for k in ('index','name','domain')} for v in variables]):
        raise ValueError('Raw response/model variable identity differs')
    for variable in variables:
        domain,value=variable['domain'],variable['value']
        if (type(value) is not int or len(domain)%2 or not any(a<=value<=b for a,b in zip(domain[::2],domain[1::2]))):
            raise ValueError('Raw integer domain is invalid')
    raw={v['name']:v['value'] for v in variables};objective=model['objective']
    if (len(objective['vars'])!=len(data.tasks) or len(objective['coeffs'])!=len(data.tasks)
            or any(c!=1 for c in objective['coeffs'])
            or sorted(variables[i]['name'] for i in objective['vars'])!=sorted(f't{t.job_id}' for t in data.tasks)
            or objective['offset']['value']!=0 or objective['scaling_factor']['value']!=1):
        raise ValueError('Raw objective is not the original sum of tardiness')
    if any(raw[f't{t.job_id}']!=max(0,r.end-t.due_date) for t,r in zip(data.tasks,schedule.records)):
        raise ValueError('Raw task tardiness differs from exact max')
    checks=result['numeric_checks']
    if (checks['api_response_value_disagreements'] or checks['derived_total_tardiness']!=schedule.total_tardiness
            or checks['raw_integer_objective_expression']!=schedule.total_tardiness
            or checks['integer_tardiness_sum']!=schedule.total_tardiness):
        raise ValueError('Raw objective/API/independent arithmetic differs')
    if result['baseline_row']['status']=='ACCEPTED':
        payload=result['baseline_row']['payload']
        if (encoded(payload['records'])!=encoded([asdict(r) for r in schedule.records])
                or encoded(payload['maintenance_records'])!=encoded([asdict(r) for r in schedule.maintenance_records])):
            raise ValueError('Accepted baseline row differs from observed candidate')
    return schedule


def recheck_configured(result,case,mode,presolve):
    diagnostics.recheck_capture(result,case,mode);expected=parameters(presolve)
    if (type(result['configured_presolve']) is not bool or result['configured_presolve']!=presolve
            or result['solver_solve_calls']!=1 or type(result['solver_solve_calls']) is not int
            or not isinstance(result['effective_parameters'],dict) or set(result['effective_parameters'])!=set(expected)
            or any(type(result['effective_parameters'][k]) is not type(v) or result['effective_parameters'][k]!=v
                   for k,v in expected.items())):
        raise ValueError('Effective solver parameters differ from the approved single-parameter comparison')
    if result['capture_status']!='COMPLETE':raise ValueError('Incomplete raw observation')
    observation=result['observation'];response=observation['response'];name=observation['status_name']
    if (observation['status_code']!=response['status_code']
            or observation['status_code']!=int(getattr(baseline.cp_model,name))):
        raise ValueError('Observed solver statuses differ')
    row=result['baseline_row']
    if row['status'] in ('ACCEPTED','NO_SCHEDULE') and name!=row['solver_status']:
        raise ValueError('Observed status differs from the checked baseline status')
    for key in ('objective','bound'):
        if key in observation['api'] and observation['api'][key]!=response[key]:
            raise ValueError('Reported and raw response diagnostics differ')
    schedule=_raw_schedule(result,case,mode);checks=result['numeric_checks']
    consistent=bool(schedule is not None and checks['objective_equals_independent_tardiness'] is True
                    and checks['bound_finite'] is True and checks['bound_nonnegative'] is True
                    and checks['bound_le_objective'] is True
                    and (name!='OPTIMAL' or observation['api']['bound']['value']==observation['api']['objective']['value']))
    reproduced=(row['status']=='ERROR' and row['error']==
        'GraduationSolverError: Solver objective/bound disagrees with independent total tardiness'
        and schedule is not None and checks['objective_finite'] is True
        and checks['objective_equals_independent_tardiness'] is False
        and checks['bound_nonnegative'] is True and checks['bound_le_objective'] is True)
    return {'case_id':case['case_id'],'mode':mode,'cp_model_presolve':presolve,
        'baseline_status':row['status'],'solver_status':name,
        'raw_schedule_status':'PASS' if schedule is not None else 'NO_CANDIDATE',
        'reported_objective':observation['api'].get('objective',{}).get('value'),
        'bound':observation['api'].get('bound',{}).get('value'),
        'derived_tardiness':schedule.total_tardiness if schedule is not None else None,
        'objective_consistent':consistent,'error_reproduced':bool(reproduced),
        'accepted_for_research':False}


def classify_pairs(reproduced,remedy_ok,controls_ok):
    if not controls_ok:return 'FAILED_TINY_CONTROLS'
    if remedy_ok!=5:return 'REMEDY_NOT_CONFIRMED'
    if reproduced!=5:return 'INCONCLUSIVE_ORIGINAL_NOT_REPRODUCED'
    return 'SUPPORTED_ON_FIVE_REQUESTS'
