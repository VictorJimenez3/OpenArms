import copy
import pytest
from bench_vision.policy import check_compatibility,denormalize_actions,training_preflight

def pair():
    policy={'policy_id':'test','revision':'abc','metadata_source':'fixture','joint_names':['a','g'],'joint_units':['degree','percent'],
            'control_mode':'absolute','camera_keys':['overview','side'],'action_dim':2,'horizon':2,'normalization':{'mode':'q01_q99','low':[-20,0],'high':[20,100]}}
    target={k:copy.deepcopy(policy[k]) for k in ('joint_names','joint_units','control_mode','camera_keys')}
    target.update(joint_limits={'a':[-30,30],'g':[0,100]},mapping_receipt='fixture-only',embodiment_id='fake')
    return policy,target

def test_shapes_normalization_bounds_and_no_activation():
    p,t=pair()
    assert check_compatibility(p,t)['physical_execution_allowed'] is False
    assert denormalize_actions([[-1,-1],[1,1]],p,t)==[[-20,0],[20,100]]

@pytest.mark.parametrize('key,value',[('joint_units',None),('camera_keys',[]),('joint_names',['g','a']),('control_mode','delta')])
def test_missing_or_mismatched_convention(key,value):
    p,t=pair(); p[key]=value
    assert check_compatibility(p,t)['status']=='blocked'
    with pytest.raises(ValueError):denormalize_actions([[0,0],[0,0]],p,t)

@pytest.mark.parametrize('actions',[[[0,0]],[[0,0],[0]],[[0,0],[float('nan'),0]],[[0,0],[2,0]]])
def test_invalid_actions(actions):
    p,t=pair()
    with pytest.raises(ValueError):denormalize_actions(actions,p,t)

def test_denormalized_outside_target_and_no_mapping():
    p,t=pair(); t['joint_limits']['a']=[-10,10]
    with pytest.raises(ValueError):denormalize_actions([[1,0],[0,0]],p,t)
    del t['mapping_receipt']
    assert check_compatibility(p,t)['status']=='blocked'

def test_training_no_data_and_leakage():
    assert training_preflight([])['status']=='blocked'
    episodes=[{'episode_id':str(i),'content_hash':str(i)*64,'provenance':'physical_recording','alignment_validated':True,'task_success_observed':True,'split':s,'position_group':'same'} for i,s in enumerate(['train','validation'])]
    assert training_preflight(episodes)['status']=='blocked'
    episodes[1]['position_group']='heldout'
    assert training_preflight(episodes)['status']=='ready_for_offline_training_setup'
    episodes[1]['content_hash']=episodes[0]['content_hash']
    assert training_preflight(episodes)['status']=='blocked'
