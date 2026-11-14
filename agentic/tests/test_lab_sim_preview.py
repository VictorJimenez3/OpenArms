"""The simulation preview runs on every proposal, and only a cleared plan can be executed."""
import asyncio
import json
from pathlib import Path
import pytest
from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.runtime import Lab,LabError
from agentic.openarms_lab.sim_preview import MujocoPreview,grasp_pose,from_env

ROOT=Path(__file__).resolve().parents[2]

class FakePreview:
    def __init__(self,status='ready',**extra):
        self.status,self.extra,self.calls=status,extra,[]
    def __call__(self,backend,request):
        self.calls.append(request)
        return {'status':self.status,'provenance':'SIMULATED','warnings':['a note'],'blocks':[],**self.extra}

async def proposed(lab,text='test sample at A in B'):
    s=await lab.create()
    sid=s['session_id']
    await lab.prediction(sid,'A will float because its density is below water.')
    s=await lab.request(sid,text,'client-1')
    assert s['pending'],s['messages'][-1]
    return sid,s['pending']['request_id']

async def previewed(lab,sid):
    await asyncio.gather(*lab.preview_tasks.get(sid,()))
    return lab.snapshot(sid)

def lab_with(tmp_path,previewer):
    return Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001),previewer=previewer)

@pytest.mark.asyncio
async def test_every_proposal_is_simulated_before_anything_executes(tmp_path):
    fake=FakePreview()
    lab=lab_with(tmp_path,fake)
    sid,pid=await proposed(lab)
    s=lab.snapshot(sid)
    assert s['pending']['preview']['status']=='running'
    assert 'Simulating it first' in s['messages'][-1]['text']
    with pytest.raises(LabError,match='still running'):
        await lab.confirm(sid,pid)
    s=await previewed(lab,sid)
    assert s['pending']['preview']['status']=='ready'
    assert [c['parameters']['source'] for c in fake.calls]==['A']
    assert 'execute' in s['messages'][-1]['text'] and 'SIMULATED' in s['messages'][-1]['text']
    assert s['requests'][-1]['status']=='requested' and sid not in lab.tasks
    assert 'simulation_preview' in {e['kind'] for e in s['notebook']}

@pytest.mark.asyncio
async def test_typing_execute_runs_the_previewed_plan_once(tmp_path):
    lab=lab_with(tmp_path,FakePreview())
    sid,pid=await proposed(lab)
    await previewed(lab,sid)
    s=await lab.request(sid,'Execute.','client-2')
    assert s['requests'][-1]['student_confirmed'] and s['pending'] is None
    await lab.tasks[sid]
    s=lab.snapshot(sid)
    assert s['requests'][-1]['status']=='completed' and len(s['requests'])==1
    s=await lab.request(sid,'execute','client-3')
    assert 'no simulated plan waiting' in s['messages'][-1]['text']
    assert len(s['requests'])==1

@pytest.mark.asyncio
@pytest.mark.parametrize('status',['blocked','error'])
async def test_a_plan_the_simulation_did_not_clear_cannot_execute(tmp_path,status):
    lab=lab_with(tmp_path,FakePreview(status,blocks=['The gripper closed on nothing.'],reason='boom'))
    sid,pid=await proposed(lab)
    s=await previewed(lab,sid)
    assert 'not be executed' in s['messages'][-1]['text'] or 'Nothing will be executed' in s['messages'][-1]['text']
    with pytest.raises(LabError,match='did not clear'):
        await lab.confirm(sid,pid)
    s=await lab.request(sid,'execute','client-2')
    assert 'did not clear' in s['messages'][-1]['text']
    assert s['requests'][-1]['status']=='requested' and sid not in lab.tasks

@pytest.mark.asyncio
async def test_an_action_with_no_simulation_model_can_still_execute(tmp_path):
    lab=lab_with(tmp_path,FakePreview('unavailable',reason='No model of the pour.'))
    sid,pid=await proposed(lab)
    s=await previewed(lab,sid)
    assert 'without a preview' in s['messages'][-1]['text']
    await lab.confirm(sid,pid)
    await lab.tasks[sid]
    assert lab.snapshot(sid)['requests'][-1]['status']=='completed'

@pytest.mark.asyncio
async def test_a_correction_gets_its_own_preview_and_the_old_one_is_ignored(tmp_path):
    fake=FakePreview()
    lab=lab_with(tmp_path,fake)
    sid,first=await proposed(lab)
    s=await lab.request(sid,'test sample at C in B','client-2')
    second=s['pending']['request_id']
    assert second!=first
    s=await previewed(lab,sid)
    assert [c['parameters']['source'] for c in fake.calls]==['A','C']
    assert s['pending']['request_id']==second and s['pending']['preview']['status']=='ready'
    with pytest.raises(LabError,match='Stale'):
        await lab.confirm(sid,first)

@pytest.mark.asyncio
async def test_without_a_previewer_execute_is_not_a_command_and_nothing_changes(tmp_path):
    lab=lab_with(tmp_path,None)
    sid,pid=await proposed(lab)
    s=lab.snapshot(sid)
    assert 'preview' not in s['pending'] and 'confirm or correct' in s['messages'][-1]['text']
    await lab.confirm(sid,pid)
    await lab.tasks[sid]
    assert lab.snapshot(sid)['requests'][-1]['status']=='completed'

def test_grasp_pose_is_where_the_gripper_first_closes():
    g='gripper.pos'
    above,grasp={'shoulder_pan.pos':1.0},{'shoulder_pan.pos':2.0}
    assert grasp_pose([{g:90},above,grasp,{g:20},above])==grasp
    assert grasp_pose([{g:90},above,grasp,above]) is None

def test_from_env(monkeypatch):
    monkeypatch.delenv('OPENARMS_PREVIEW',raising=False)
    assert from_env() is None
    monkeypatch.setenv('OPENARMS_PREVIEW','mujoco')
    assert isinstance(from_env(),MujocoPreview)
    monkeypatch.setenv('OPENARMS_PREVIEW','isaac')
    with pytest.raises(ValueError):from_env()

def request(source='A',skill='known_station_transfer.v1'):
    return {'request_id':'r1','skill_id':skill,'parameters':{'object':'sample','source':source,'destination':'B'}}

def test_the_preview_request_is_the_runners_own_script(monkeypatch):
    monkeypatch.delenv('OPENARMS_POSES',raising=False)
    poses=json.loads((ROOT/'firmware/openarms_executor/poses.json').read_text())
    sim,reason=MujocoPreview().describe(MockBackend(),request())
    assert reason is None and sim['seconds']==1.5 and sim['object_at']=='A'
    assert sim['marks']=={'A':poses['poses']['GRASP_A'],'B':poses['poses']['GRASP_B']}
    assert sim['script'][-1]==poses['poses']['HOME'] and sim['script'][0]=={'gripper.pos':poses['gripper']['open']}
    shifted,_=MujocoPreview(c_offset_deg=5).describe(MockBackend(),request('C'))
    assert shifted['marks']['C']['shoulder_pan.pos']==pytest.approx(poses['poses']['GRASP_A']['shoulder_pan.pos']+5)
    assert shifted['_note'] and 'not taught' in shifted['_note']
    sim,reason=MujocoPreview().describe(MockBackend(),request(skill='premeasured_dilution.v1'))
    assert sim is None and 'pour' in reason

def test_an_empty_source_is_simulated_as_empty():
    backend=MockBackend()
    backend._state['point_holds']['A']=None
    sim,_=MujocoPreview().describe(backend,request())
    assert sim['object_at'] is None

def test_real_mujoco_preview_end_to_end():
    pytest.importorskip('mujoco')
    pytest.importorskip('openarms_sim')
    previewer=MujocoPreview()
    out=previewer(MockBackend(),request())
    assert out['status']=='ready',out
    assert out['provenance']=='SIMULATED' and out['objects'][0]['at']=='B'
    assert previewer.video_path(out['video'].rsplit('/',1)[1]).is_file()
    assert previewer.video_path('../lab.sqlite3') is None

def test_preview_video_route(tmp_path):
    from fastapi.testclient import TestClient
    from agentic.openarms_lab.app import create_app
    previewer=MujocoPreview()
    previewer.video_dir=tmp_path
    (tmp_path/'script-0123456789abcdef.mp4').write_bytes(b'video')
    (tmp_path/'secret.txt').write_text('no')
    with TestClient(create_app(Lab(tmp_path/'data',previewer=previewer))) as client:
        assert client.get('/api/previews/script-0123456789abcdef.mp4').content==b'video'
        assert client.get('/api/previews/secret.txt').status_code==404
        assert client.get('/api/previews/script-ffffffffffffffff.mp4').status_code==404
        assert client.get('/api/health').json()['preview']=='mujoco'

def test_a_connected_runner_supplies_its_own_script_and_speed():
    """With the physical adapter, the preview plays what that exact runner would send."""
    from firmware.openarms_executor.motion import FakeRobot
    from firmware.openarms_executor.poses import load_poses
    from firmware.openarms_executor.transfer_runner import PoseTransferRunner
    poses=load_poses(ROOT/'research/joseph/mandarin-transfer-2026-11-14/poses/bench-a.json')
    runner=PoseTransferRunner(FakeRobot(poses['poses']['HOME']),poses,seconds=3.0)
    class Adapter:
        mode='physical'
        def __init__(self):self.runner=runner
        def state(self):return {'point_holds':{'A':'mandarin','C':'mandarin','B':None}}
    sim,reason=MujocoPreview().describe(Adapter(),request())
    assert reason is None and sim['script']==runner.scripts['A'] and sim['seconds']==3.0
    assert sim['marks']['A']==poses['poses']['GRASP_A']
    # This runner was not configured with a C pickup, so the preview shows the offset construction and says so.
    sim,_=MujocoPreview().describe(Adapter(),request('C'))
    assert 'not taught' in sim['_note']

@pytest.mark.asyncio
async def test_restoring_an_old_session_does_not_disarm_the_shared_physical_arm(tmp_path,monkeypatch):
    """Reloading the page after a restart restores the old session; new sessions must still work."""
    class Arm(MockBackend):
        mode='physical'
        def capabilities(self):return {**super().capabilities(),'objects':['mandarin']}
    first=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001))
    old=(await first.create('mandarin_transfer'))['session_id']
    await first.shutdown()
    monkeypatch.setenv('OPENARMS_BACKEND','physical')
    lab=Lab(tmp_path)
    lab.physical=Arm(delay=.001)
    lab.physical.prepare('mandarin')
    restored=lab.snapshot(old)
    assert restored['state']['armed'] is True and lab.physical.state()['armed'] is True
    await lab.prediction(old,'It will reach B.')
    s=await lab.request(old,'move the mandarin from A to B','c1')
    assert s['pending'] is None and 'Start a new session' in s['messages'][-1]['text']
    fresh=(await lab.create())['session_id']
    await lab.prediction(fresh,'It will reach B.')
    s=await lab.request(fresh,'move the mandarin from A to B','c2')
    assert s['pending'],s['messages'][-1]
