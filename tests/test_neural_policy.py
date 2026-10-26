"""Numerical gradients and literal masked distributions verify the neural baseline."""
from dataclasses import replace
import importlib
import math
import random

import numpy as np
import pytest

from src.graduation import ParallelMaintenanceEnv
from src.graduation.state_encoding import encode_construction_observation
from tests.graduation_helpers import one_machine


def api():return importlib.import_module('src.graduation.neural_policy')


def state():
    data,_=one_machine(fixed_start=None)
    return encode_construction_observation(ParallelMaintenanceEnv(data,mode='joint').observe())


def sample(value=1.0):
    m=api();encoded=state()
    return m.PolicySample(m.policy_features(encoded),encoded.action_mask,0,value)


def test_policy_input_consumes_matrix_type_presence_mode_and_aux_without_mutation():
    m=api();encoded=state();features=m.policy_features(encoded)
    assert len(features)==372 and features[:13]==encoded.rows[0]
    assert features[24*13:25*13]==encoded.rows[24]
    assert features[364:370]==(0.0,1.0,1.0,0.0,0.0,0.0)
    assert features[370]==0.0 and features[371]==pytest.approx(math.log1p(4)/math.log1p(2**50))
    assert encoded.scale==4 and encoded.rows[24][7]==-1.0
    with pytest.raises(ValueError):m.policy_features(replace(encoded,scale=2**50+1))


def test_large_illegal_logits_never_receive_probability_or_win_greedy_selection():
    m=api();mask=state().action_mask;logits=np.full(100,1e6,dtype=np.float64)
    logits[0],logits[4],logits[96]=1000.,1001.,999.
    probs=m.masked_probabilities(logits,mask)
    assert probs[[0,4,96]]==pytest.approx([0.24472847105479764,0.6652409557748218,0.09003057317038046])
    assert np.count_nonzero(probs)==3 and probs.sum()==pytest.approx(1.)
    actor=m.MaskedMLP(seed=1,hidden_size=2);parameters=actor.state_dict()
    parameters['w2'][:]=0.;parameters['b2'][:]=logits
    actor=m.MaskedMLP.from_state(parameters)
    assert actor.select_action(state(),rng=np.random.default_rng(5),deterministic=True)==4


@pytest.mark.parametrize('fault',['empty','short','not_bool','nan','inf','float32','wrong_shape'])
def test_invalid_distribution_rejects_instead_of_repairing(fault):
    m=api();mask=state().action_mask;logits=np.zeros(100,dtype=np.float64)
    if fault=='empty':mask=(False,)*100
    if fault=='short':mask=mask[:-1]
    if fault=='not_bool':mask=(1,)+mask[1:]
    if fault=='nan':logits[0]=np.nan
    if fault=='inf':logits[1]=np.inf
    if fault=='float32':logits=logits.astype(np.float32)
    if fault=='wrong_shape':logits=logits.reshape(10,10)
    with pytest.raises(ValueError):m.masked_probabilities(logits,mask)


def test_local_seed_repeatability_no_global_rng_and_terminal_refusal():
    m=api();py=random.getstate();legacy=np.random.get_state()
    actor=m.MaskedMLP(seed=17,hidden_size=3);other=m.MaskedMLP(seed=17,hidden_size=3)
    a=np.random.default_rng(123);b=np.random.default_rng(123)
    actions=[actor.select_action(state(),rng=a) for _ in range(60)]
    assert actions==[other.select_action(state(),rng=b) for _ in range(60)]
    assert all(x in(0,4,96) for x in actions)
    assert py==random.getstate()
    after=np.random.get_state();assert legacy[0]==after[0] and np.array_equal(legacy[1],after[1]) and legacy[2:]==after[2:]
    with pytest.raises(ValueError):actor.probabilities(replace(state(),status='TERMINATED',action_mask=(False,)*100))


@pytest.mark.parametrize('key,index',[('w1',(0,0)),('w1',(371,1)),('b1',(0,)),
    ('w2',(0,0)),('w2',(1,4)),('w2',(0,96)),('w2',(0,1)),('b2',(0,)),('b2',(1,))])
def test_log_probability_derivative_matches_independent_central_difference(key,index):
    m=api();actor=m.MaskedMLP(seed=3,hidden_size=2);item=sample()
    logp,gradients=actor.log_probability_gradient(item)
    original=actor.state_dict();eps=1e-6
    plus={k:v.copy() for k,v in original.items()};minus={k:v.copy() for k,v in original.items()}
    plus[key][index]+=eps;minus[key][index]-=eps
    def objective(weights):return math.log(m.MaskedMLP.from_state(weights).probabilities(state())[0])
    want=(objective(plus)-objective(minus))/(2*eps)
    assert gradients[key][index]==pytest.approx(want,rel=2e-4,abs=1e-7)
    assert logp==pytest.approx(objective(original))
    assert np.all(gradients['b2'][[j for j in range(100) if j not in(0,4,96)]]==0.)
    for name in original:assert np.array_equal(original[name],actor.state_dict()[name])


@pytest.mark.parametrize('reward,direction',[(1.0,1),(-1.0,-1)])
def test_update_sign_and_gradient_clipping_without_illegal_probability(reward,direction):
    m=api();actor=m.MaskedMLP(seed=4,hidden_size=3);before=actor.probabilities(state())[0]
    update=actor.reinforce_update((sample(reward),),learning_rate=.001,max_grad_norm=.1)
    assert direction*(actor.probabilities(state())[0]-before)>0
    assert update['changed'] is True and update['samples']==1
    assert 0<=update['applied_gradient_norm']<=.1+1e-12 and math.isfinite(update['loss'])
    assert all(p==0. for p,legal in zip(actor.probabilities(state()),state().action_mask) if not legal)


def test_single_legal_action_has_zero_gradient_and_no_fake_parameter_change():
    m=api();actor=m.MaskedMLP(seed=5,hidden_size=2);s=sample(-5.)
    s=replace(s,action_mask=tuple(i==0 for i in range(100)))
    before=actor.state_dict();update=actor.reinforce_update((s,))
    assert update['changed'] is False and update['gradient_norm']==0.
    for name in before:assert np.array_equal(before[name],actor.state_dict()[name])


def test_checkpoint_copies_and_load_validation_prevent_external_mutation():
    m=api();actor=m.MaskedMLP(seed=7,hidden_size=2);before=actor.probabilities(state());weights=actor.state_dict()
    restored=m.MaskedMLP.from_state(weights)
    weights['b2'][0]=99.
    assert actor.probabilities(state())==restored.probabilities(state())==before
    for bad in (dict(weights,extra=np.zeros(1)),dict(weights,w1=weights['w1'].astype(np.float32)),
                dict(weights,b2=np.full(100,np.nan)),dict(weights,w2=np.zeros((3,100)))):
        with pytest.raises(ValueError):m.MaskedMLP.from_state(bad)


@pytest.mark.parametrize('fault',['mask','action','return','features','learning_rate','norm'])
def test_bad_update_is_rejected_before_any_parameter_changes(fault):
    m=api();actor=m.MaskedMLP(seed=8,hidden_size=2);item=sample();before=actor.state_dict();options={}
    if fault=='mask':object.__setattr__(item,'action_mask',(False,)*100)
    if fault=='action':object.__setattr__(item,'action',1)
    if fault=='return':object.__setattr__(item,'return_value',float('nan'))
    if fault=='features':object.__setattr__(item,'features',(0.,)*371)
    if fault=='learning_rate':options['learning_rate']=float('nan')
    if fault=='norm':options['max_grad_norm']=0.
    with pytest.raises(ValueError):actor.reinforce_update((item,),**options)
    for name in before:assert np.array_equal(before[name],actor.state_dict()[name])
