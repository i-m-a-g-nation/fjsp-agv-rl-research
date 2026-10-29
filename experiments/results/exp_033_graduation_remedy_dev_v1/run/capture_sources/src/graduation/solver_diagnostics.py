"""Development-only observation of the unchanged solver in an isolated worker.

Raw observations never grant research acceptance. The baseline row is returned
unchanged, including every rejection. No model or acceptance rule is patched.
"""
from pathlib import Path
import json
import math
import hashlib
from unittest.mock import patch

from src.graduation import solver as baseline
from src.graduation import reference_main_results as main
from src.graduation.reference_protocol import digest,encoded


def number(value):
    value=float(value)
    return {'value':value if math.isfinite(value) else None,'repr':repr(value),
            'hex':value.hex(),'finite':math.isfinite(value)}


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


class _Observer:
    def __init__(self,delegate):
        self.delegate=delegate
        self.data={'api':{},'value_calls':[],'response':None,'model':None,'capture_errors':[]}

    def __getattr__(self,name):return getattr(self.delegate,name)

    def _observe(self,action):
        try:action()
        except Exception as exc:
            self.data['capture_errors'].append(f'{type(exc).__name__}: {str(exc)[:1000]}')

    def Solve(self,model):
        def capture_model():
            proto=model.Proto()
            self.data['model']={'variables':[{'index':i,'name':v.name,'domain':list(v.domain)}
                for i,v in enumerate(proto.variables)],
                'objective':{'vars':list(proto.objective.vars),'coeffs':list(proto.objective.coeffs),
                    'offset':number(proto.objective.offset),'scaling_factor':number(proto.objective.scaling_factor)}}
        self._observe(capture_model)
        try:status=self.delegate.Solve(model)
        except Exception as exc:
            self.data['capture_errors'].append(f'Solve raised {type(exc).__name__}: {str(exc)[:1000]}')
            raise
        self.data['status_code']=int(status)
        def capture_response():
            response=self.delegate.ResponseProto();values=list(response.solution)
            variables=self.data['model']['variables']
            if int(status) in (int(baseline.cp_model.OPTIMAL),int(baseline.cp_model.FEASIBLE)) and len(values)!=len(variables):
                raise ValueError('Raw solution length differs from model variables')
            self.data['response']={'status_code':int(response.status),
                'objective':number(response.objective_value),'bound':number(response.best_objective_bound),
                'variables':[{**v,'value':int(values[i]) if i<len(values) else None} for i,v in enumerate(variables)]}
        self._observe(capture_response)
        return status

    def StatusName(self,status):
        name=self.delegate.StatusName(status);self.data['status_name']=name;return name

    def ObjectiveValue(self):
        value=self.delegate.ObjectiveValue()
        self._observe(lambda:self.data['api'].update(objective=number(value)))
        return value

    def BestObjectiveBound(self):
        value=self.delegate.BestObjectiveBound()
        self._observe(lambda:self.data['api'].update(bound=number(value)))
        return value

    def WallTime(self):
        value=self.delegate.WallTime()
        self._observe(lambda:self.data['api'].update(wall_time=number(value)))
        return value

    def Value(self,var):
        value=self.delegate.Value(var)
        self._observe(lambda:self.data['value_calls'].append({'name':var.Name(),'value':value}))
        return value


def _candidate(case,observation):
    values={item['name']:item['value'] for item in observation['value_calls']}
    if not values:return None
    data=case['data'];m=data['num_machines'];production=[];maintenance=[];complete=True
    for task in data['tasks']:
        j=task['job_id'];start=values.get(f's{j}');end=values.get(f'e{j}')
        selected=[i for i in range(m) if values.get(f'x{j}_{i}')==1]
        complete=complete and type(start) is int and type(end) is int and len(selected)==1
        production.append({'job_id':j,'start':start,'end':end,'selected_machines':selected,
                           'processing_time_expected':task['processing_time']})
    for requirement in data['maintenance']:
        i=requirement['machine_id'];start=values.get(f'ms{i}');end=values.get(f'me{i}')
        complete=complete and type(start) is int and type(end) is int
        maintenance.append({'machine_id':i,'start':start,'end':end,'duration_expected':requirement['duration']})
    return {'label':'UNVALIDATED_DIAGNOSTIC_CANDIDATE','complete':bool(complete),
            'production':production,'maintenance':maintenance}


def _numeric_checks(case,observation):
    candidate=_candidate(case,observation);total=None
    if candidate and all(type(r['end']) is int for r in candidate['production']):
        due={t['job_id']:t['due_date'] for t in case['data']['tasks']}
        total=sum(max(0,r['end']-due[r['job_id']]) for r in candidate['production'])
    response=observation.get('response')
    raw={v['name']:v['value'] for v in response['variables']} if response else {}
    late=[raw.get(f"t{t['job_id']}") for t in case['data']['tasks']]
    integer_sum=sum(late) if late and all(type(v) is int for v in late) else None
    api=observation['api'];obj=api.get('objective');bound=api.get('bound')
    finite_obj=obj['finite'] if obj else None;finite_bound=bound['finite'] if bound else None
    model_objective=None
    model=observation.get('model')
    if model and response:
        expression=model['objective'];by_index={v['index']:v['value'] for v in response['variables']}
        if all(type(by_index.get(i)) is int for i in expression['vars']):
            model_objective=sum(c*by_index[i] for i,c in zip(expression['vars'],expression['coeffs']))
    mismatches=[item['name'] for item in observation['value_calls']
                if response and raw.get(item['name'])!=item['value']]
    return {'derived_total_tardiness':total,'integer_tardiness_sum':integer_sum,
        'raw_integer_objective_expression':model_objective,
        'objective_finite':finite_obj,'bound_finite':finite_bound,
        'objective_equals_independent_tardiness':(obj['value']==total) if finite_obj and total is not None else
                                                  False if obj and not finite_obj else None,
        'integer_tardiness_equals_independent':integer_sum==total if integer_sum is not None and total is not None else None,
        'bound_nonnegative':bound['value']>=0 if finite_bound else False if bound else None,
        'bound_le_objective':bound['value']<=obj['value'] if finite_bound and finite_obj else None,
        'objective_minus_independent':number(obj['value']-total) if finite_obj and total is not None else None,
        'api_response_value_disagreements':mismatches}


def capture_case(case,mode,*,_solver_factory=None):
    """Call only in a dedicated worker (or synthetic tests), never shared threads."""
    main._identity(case,mode);main._data(case)
    original_factory=baseline.cp_model.CpSolver;factory=_solver_factory or original_factory
    observers=[]
    def recording_factory():
        observer=_Observer(factory());observers.append(observer);return observer
    with patch.object(baseline.cp_model,'CpSolver',recording_factory):
        row=main.evaluate_row(case,mode)
    observation=observers[0].data if len(observers)==1 else {
        'api':{},'value_calls':[],'response':None,'model':None,'capture_errors':['Expected exactly one solver instance']}
    result={'version':1,'case_id':case['case_id'],'mode':mode,'input_sha256':digest(case['data']),
        'execution_kind':'SYNTHETIC_SOLVER_TEST' if _solver_factory else 'NATIVE_DEVELOPMENT_DIAGNOSTIC',
        'accepted_for_research':False,'baseline_row':row,'observation':observation,
        'candidate':_candidate(case,observation),'numeric_checks':_numeric_checks(case,observation),
        'capture_status':'PARTIAL' if observation['capture_errors'] else 'COMPLETE'}
    encoded(result)
    return result


def _check_numbers(value):
    if isinstance(value,dict):
        if set(value)=={'value','repr','hex','finite'}:
            v=float.fromhex(value['hex'])
            if (type(value['finite']) is not bool or math.isfinite(v)!=value['finite']
                    or repr(v)!=value['repr'] or (v!=value['value'] if value['finite'] else value['value'] is not None)):
                raise ValueError('Numeric representation changed')
        for v in value.values():_check_numbers(v)
    elif isinstance(value,list):
        for v in value:_check_numbers(v)


def recheck_capture(result,case,mode):
    try:
        if (result['version']!=1 or result['case_id']!=case['case_id'] or result['mode']!=mode
                or result['input_sha256']!=digest(case['data']) or result['accepted_for_research'] is not False):
            raise ValueError('Diagnostic identity or acceptance changed')
        encoded(result);_check_numbers(result)
        main.recheck_row(case,mode,result['baseline_row'])
        if (encoded(result['candidate'])!=encoded(_candidate(case,result['observation']))
                or encoded(result['numeric_checks'])!=encoded(_numeric_checks(case,result['observation']))):
            raise ValueError('Diagnostic computations changed')
        if result['capture_status']!=('PARTIAL' if result['observation']['capture_errors'] else 'COMPLETE'):
            raise ValueError('Diagnostic capture status changed')
        return {'status':'VERIFIED_DIAGNOSTIC_CAPTURE','baseline_status':result['baseline_row']['status']}
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('Malformed diagnostic capture') from exc


def audit_saved_failures(archive):
    """Verify original bytes and select only archived errors, without solving."""
    from src.ai_workflow.graduation_main_backend import recheck_main_run
    archive=Path(archive);index=_read(archive/'archive_manifest.json')
    actual={p.relative_to(archive).as_posix():_sha(p) for p in archive.rglob('*')
            if p.is_file() and p.relative_to(archive).as_posix()!='archive_manifest.json'}
    if actual!=index['files_sha256']:raise ValueError('Original archive bytes changed')
    cases=_read(archive/'conclusion/inputs.json');summary=recheck_main_run(archive/'run',cases)
    state=_read(archive/'run/state.json');requests=[]
    for index,row in enumerate(state['rows']):
        if row['status']=='ERROR':
            saved=_read(archive/'run/rows'/f'{index:04d}.json')
            requests.append({'sequence':index,'case':cases[index//2],'mode':row['mode'],'historical_row':saved})
    if summary['status']!='FAILED' or len(requests)!=5:
        raise ValueError('Diagnosis requires exactly five archived ERROR requests')
    return {'version':1,'original_experiment_status':summary['status'],'solver_calls':0,
        'archive_manifest_sha256':_sha(archive/'archive_manifest.json'),
        'run_manifest_sha256':_sha(archive/'run/manifest.json'),'requests':requests}
