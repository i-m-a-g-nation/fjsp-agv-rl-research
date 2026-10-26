"""Literal independent mappings catch paired encoder/decoder column mistakes."""
from dataclasses import FrozenInstanceError, replace
import importlib
import random
import struct

import pytest

from src.graduation import ConstructionObservation, ParallelMaintenanceEnv
from tests.graduation_helpers import one_machine


def api():
    return importlib.import_module('src.graduation.state_encoding')


def observation():
    data,_=one_machine(fixed_start=None)
    return ParallelMaintenanceEnv(data,mode='joint').observe()


def literal_rows():
    # W=4; two p2 tasks with due dates2/4; one q2 machine/window0..6/no f.
    tasks=[(0.5,0.5,0.0)+(0.0,)*7+(1.0,0.0,1.0),
           (0.5,1.0,0.0)+(0.0,)*7+(1.0,0.0,1.0)]
    tasks += [(0.0,)*10+(1.0,0.0,0.0)]*22
    machines=[(0.0,)*3+(0.0,0.5,0.0,1.5,-1.0,0.0,0.0)+(0.0,1.0,1.0)]
    machines += [(0.0,)*10+(0.0,1.0,0.0)]*3
    return tuple(tasks+machines)


def changed_row(rows,index,column,value):
    mutable=list(rows)
    row=list(mutable[index]);row[column]=value;mutable[index]=tuple(row)
    return tuple(mutable)


def test_encode_literal_columns_types_presence_sentinel_and_original_auxiliary_fields():
    module=api(); original=observation()
    state=random.getstate()
    encoded=module.encode_construction_observation(original)
    assert encoded.rows==literal_rows()
    assert (encoded.mode,encoded.status,encoded.steps,encoded.scale,encoded.version)==('joint','ACTIVE',0,4,1)
    assert encoded.action_mask==(True,False,False,False,True)+(False,)*91+(True,False,False,False)
    assert random.getstate()==state and original==observation()


def test_decode_independently_constructed_rows_instead_of_encoder_output():
    module=api()
    mask=tuple(i in(0,4,96) for i in range(100))
    encoded=module.TypedStateEncoding(mode='joint',status='ACTIVE',steps=0,scale=4,rows=literal_rows(),action_mask=mask)
    decoded=module.decode_construction_observation(encoded)
    assert decoded==observation()
    assert decoded.task_features[1]==(0.5,1.0,0.0)
    assert decoded.machine_features[0]==(0.0,0.5,0.0,1.5,-1.0,0.0,0.0)
    assert decoded.task_presence==(True,True)+(False,)*22


def test_fractional_payload_and_signed_zero_bits_are_not_recomputed_or_rounded():
    module=api();original=observation()
    tasks=( (0.1,-0.0,0.0),)+original.task_features[1:]
    original=replace(original,task_features=tasks)
    encoded=module.encode_construction_observation(original)
    restored=module.decode_construction_observation(encoded)
    for before,after in zip(original.task_features[0],restored.task_features[0]):
        assert struct.pack('!d',before)==struct.pack('!d',after)


def test_encoded_rows_and_metadata_are_deeply_immutable_snapshots():
    module=api();data,_=one_machine(fixed_start=None);env=ParallelMaintenanceEnv(data,mode='joint')
    encoded=module.encode_construction_observation(env.observe())
    with pytest.raises(FrozenInstanceError): encoded.steps=1
    with pytest.raises(TypeError): encoded.rows[0][0]=99.0
    env.step(0)
    assert encoded.steps==0 and encoded.rows[0][2]==0.0
    assert module.encode_construction_observation(env.observe()).rows[0][2]==1.0
    assert encoded.rows[0][12]==1.0


@pytest.mark.parametrize('status',['ACTIVE','TERMINATED','TRUNCATED','FAILED'])
def test_lifecycle_fields_are_preserved_without_inventing_a_legal_mask(status):
    module=api();original=replace(observation(),status=status,action_mask=(False,)*100,steps=2)
    assert module.decode_construction_observation(module.encode_construction_observation(original))==original


def test_maximum24_task4_machine_observation_is_never_cropped():
    from src.graduation import ProductionTask,ParallelMaintenanceInstance,MaintenanceRequirement
    module=api()
    data=ParallelMaintenanceInstance(tuple(ProductionTask(j,1,j) for j in range(24)),4,
        tuple(MaintenanceRequirement(m,1,0,30,0) for m in range(4)))
    original=ParallelMaintenanceEnv(data,mode='joint').observe()
    encoded=module.encode_construction_observation(original)
    assert len(encoded.rows)==28 and all(row[12]==1.0 for row in encoded.rows)
    assert encoded.rows[23][:3]==(1/6,23/6,0.0)
    assert module.decode_construction_observation(encoded)==original


def test_large_exact_integer_machine_clocks_stay_in_environment_not_decoded_features():
    from src.graduation import ProductionTask,ParallelMaintenanceInstance,MaintenanceRequirement
    module=api();large=2**40+1
    data=ParallelMaintenanceInstance((ProductionTask(0,large,large),ProductionTask(1,large+1,large)),2,
        tuple(MaintenanceRequirement(m,1,0,2*large+2,0) for m in range(2)))
    env=ParallelMaintenanceEnv(data,mode='joint');env.step(0);env.step(5)
    original=env.observe();clocks=env.machine_tails
    assert module.decode_construction_observation(module.encode_construction_observation(original))==original
    assert env.machine_tails==clocks==(large,large+1) and all(type(t) is int for t in clocks)


@pytest.mark.parametrize('change',[
    'mode','status','bool_steps','negative_steps','too_many_steps','bool_scale','zero_scale',
    'task_count','task_width','machine_count','list_features','list_row','mask_length','mask_int',
    'presence_length','presence_int','nan','inf','negative_inf','int_feature','bool_feature',
    'scheduled_flag','maintenance_flag','fixed_flag','task_padding','machine_padding'])
def test_invalid_observation_format_rejected_without_coercion(change):
    module=api();original=observation();updates={}
    scalar={'mode':('mode','other'),'status':('status','other'),'bool_steps':('steps',True),
        'negative_steps':('steps',-1),'too_many_steps':('steps',29),'bool_scale':('scale',True),'zero_scale':('scale',0)}
    if change in scalar: key,value=scalar[change];updates[key]=value
    if change=='task_count':updates['task_features']=original.task_features[:-1]
    if change=='task_width':updates['task_features']=(original.task_features[0]+(0.0,),)+original.task_features[1:]
    if change=='machine_count':updates['machine_features']=original.machine_features[:-1]
    if change=='list_features':updates['task_features']=list(original.task_features)
    if change=='list_row':updates['task_features']=(list(original.task_features[0]),)+original.task_features[1:]
    if change=='mask_length':updates['action_mask']=original.action_mask[:-1]
    if change=='mask_int':updates['action_mask']=(1,)+original.action_mask[1:]
    if change=='presence_length':updates['task_presence']=original.task_presence[:-1]
    if change=='presence_int':updates['task_presence']=(1,)+original.task_presence[1:]
    features={'nan':float('nan'),'inf':float('inf'),'negative_inf':-float('inf'),'int_feature':1,'bool_feature':False}
    if change in features:updates['task_features']=((features[change],0.5,0.0),)+original.task_features[1:]
    if change=='scheduled_flag':updates['task_features']=((0.5,0.5,0.5),)+original.task_features[1:]
    if change in ('maintenance_flag','fixed_flag'):
        machines=list(original.machine_features);row=list(machines[0]);row[5 if change=='maintenance_flag' else 6]=0.5
        machines[0]=tuple(row);updates['machine_features']=tuple(machines)
    if change=='task_padding':updates['task_presence']=(False,)+original.task_presence[1:]
    if change=='machine_padding':updates['machine_presence']=(False,)+original.machine_presence[1:]
    with pytest.raises(ValueError):module.encode_construction_observation(replace(original,**updates))


@pytest.mark.parametrize('change',['row_count','row_width','list_rows','list_row','row_type','presence',
    'task_cross_payload','machine_cross_payload','padding_payload','flag','nan','version','bool_version','mask'])
def test_corrupt_encoding_is_rejected_instead_of_silently_dropping_values(change):
    module=api();original=module.encode_construction_observation(observation());updates={}
    if change=='row_count':updates['rows']=original.rows[:-1]
    if change=='row_width':updates['rows']=(original.rows[0][:-1],)+original.rows[1:]
    if change=='list_rows':updates['rows']=list(original.rows)
    if change=='list_row':updates['rows']=(list(original.rows[0]),)+original.rows[1:]
    for name,row,column,value in [('row_type',0,10,0.0),('presence',0,12,0.2),
        ('task_cross_payload',0,3,0.1),('machine_cross_payload',24,0,0.1),
        ('padding_payload',2,0,0.1),('flag',0,2,0.5),('nan',0,0,float('nan'))]:
        if change==name:updates['rows']=changed_row(original.rows,row,column,value)
    if change=='version':updates['version']=2
    if change=='bool_version':updates['version']=True
    if change=='mask':updates['action_mask']=(1,)+original.action_mask[1:]
    with pytest.raises(ValueError):replace(original,**updates)


def test_decoder_revalidates_even_after_frozen_dataclass_is_bypassed():
    module=api();encoded=module.encode_construction_observation(observation())
    object.__setattr__(encoded,'rows',changed_row(encoded.rows,0,3,0.5))
    with pytest.raises(ValueError):module.decode_construction_observation(encoded)


@pytest.mark.parametrize('value',[None,{},(),True])
def test_wrong_object_types_rejected_by_both_boundaries(value):
    module=api()
    with pytest.raises(ValueError):module.encode_construction_observation(value)
    with pytest.raises(ValueError):module.decode_construction_observation(value)
