"""Past-episode centering must not alter rewards or contaminate its own mean."""
import importlib
import math

import numpy as np
import pytest


def baseline():return importlib.import_module('src.graduation.return_baseline').RunningReturnBaseline()


def test_first_episode_uses_zero_and_center_is_read_only():
    b=baseline();weights=b.center('train:0',(-1.,-2.))
    assert weights=={'baselines':(0.,0.),'advantages':(-1.,-2.),'count':0}
    assert b.snapshot()=={}
    assert b.center('train:0',(-1.,-2.))==weights


def test_means_are_per_instance_and_step_and_updated_only_after_observe():
    b=baseline();raw=(-1.,-3.);b.observe('train:0',raw)
    assert b.center('train:0',(-2.,-1.))=={'baselines':(-1.,-3.),'advantages':(-1.,2.),'count':1}
    assert b.center('train:1',(-2.,-1.))['baselines']==(0.,0.)
    b.observe('train:0',(-3.,-1.))
    assert b.center('train:0',(-1.,-3.))=={'baselines':(-2.,-2.),'advantages':(1.,-1.),'count':2}
    assert raw==(-1.,-3.)
    snap=b.snapshot();snap['train:0']['count']=99
    assert b.snapshot()['train:0']['count']==2


@pytest.mark.parametrize('key,values', [('',(-1.,)),('x'*129,(-1.,)),(1,(-1.,)),
    ('x',()),('x',(-1.,)*29),('x',[-1.]),('x',(1,)),('x',(True,)),
    ('x',(math.nan,)),('x',(math.inf,)),('x',(-math.inf,))])
def test_malformed_values_rejected_without_mutating_history(key,values):
    b=baseline();b.observe('saved',(-1.,-2.));before=b.snapshot()
    with pytest.raises(ValueError):b.center(key,values)
    with pytest.raises(ValueError):b.observe(key,values)
    assert b.snapshot()==before


def test_shape_capacity_and_advantage_overflow_fail_atomically():
    b=baseline();b.observe('one',(-1.,-2.));before=b.snapshot()
    with pytest.raises(ValueError):b.observe('one',(-1.,))
    assert b.snapshot()==before
    for i in range(15):b.observe(str(i),(-1.,))
    before=b.snapshot()
    with pytest.raises(ValueError):b.observe('seventeenth',(-1.,))
    assert b.snapshot()==before
    extreme=baseline();extreme.observe('x',(-1.7e308,))
    with pytest.raises(ValueError):extreme.center('x',(1.7e308,))
    assert extreme.snapshot()['x']['count']==1


def test_observation_cap_and_stable_constant_mean():
    b=baseline()
    for _ in range(64):b.observe('x',(-.3,))
    assert b.center('x',(-.3,))['advantages']==pytest.approx((0.,),abs=1e-15)
    assert b.snapshot()['x']['count']==64
    with pytest.raises(ValueError):b.observe('x',(-.3,))


def test_none_flag_is_explicit_default_with_exact_weights_and_log_schema():
    from src.graduation.policy_training import train_policy
    from tests.test_policy_training import _data
    options=dict(mode='joint',seed=17,episodes=2,validation_every=1)
    default=train_policy((_data(),),(_data((100,101)),),**options)
    explicit=train_policy((_data(),),(_data((100,101)),),return_baseline='none',**options)
    assert default.keys()==explicit.keys() and default['logs']==explicit['logs']
    assert all('return_baseline' not in x for x in explicit['logs'])
    for label in ('initial_state','final_state','selected_state'):
        for key in default[label]:assert np.array_equal(default[label][key],explicit[label][key])


def test_running_baseline_uses_only_previous_complete_training_visits(monkeypatch):
    from src.graduation import policy_training as training
    from src.graduation.neural_policy import MaskedMLP
    from tests.test_policy_training import _data
    seen=[];update=MaskedMLP.reinforce_update
    def capture(self,samples,**kwargs):
        seen.append(tuple(s.return_value for s in samples))
        return update(self,samples,**kwargs)
    monkeypatch.setattr(MaskedMLP,'reinforce_update',capture)
    events=[]
    result=training.train_policy((_data(),),(_data((100,101)),),mode='joint',seed=17,
        episodes=2,validation_every=1,return_baseline='running_mean',on_progress=events.append)
    first,second=[x['return_baseline'] for x in result['logs']]
    assert first['baseline_count']==0 and first['baselines']==(0.,0.,0.)
    assert first['advantages']==first['raw_returns']==seen[0]
    assert second['baseline_count']==1 and second['baselines']==first['raw_returns']
    assert second['advantages']==tuple(g-b for g,b in zip(second['raw_returns'],first['raw_returns']))==seen[1]
    assert all(log['total_reward']==pytest.approx(-log['total_tardiness']/100) for log in result['logs'])
    validations=[e for e in events if e['kind']=='validation']
    assert validations[0]['baseline_state']=={}
    assert validations[-1]['baseline_state']['train:0']['count']==2


@pytest.mark.parametrize('flag',[None,True,'bad',1])
def test_invalid_flag_fails_before_any_rollout(flag):
    from src.graduation.policy_training import train_policy
    from tests.test_policy_training import _data
    events=[]
    with pytest.raises(ValueError):train_policy((_data(),),(_data((100,101)),),mode='joint',seed=17,
        episodes=1,return_baseline=flag,on_progress=events.append)
    assert events==[]
