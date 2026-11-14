"""Free-form commands: parsed with fixed patterns, checked by the agent validator, simulated, then run."""
import asyncio
from pathlib import Path
import pytest
from agentic.openarms_lab.backends import MockBackend
from agentic.openarms_lab.free_plan import FreePlans,PlanProblem,SKILL,repeat_requested
from agentic.openarms_lab.runtime import Lab,LabError
from agentic.openarms_lab.sim_preview import MujocoPreview

ROOT=Path(__file__).resolve().parents[2]
POSES=ROOT/'firmware/openarms_executor/poses.json'

def backend(a='mandarin',b=None):
    m=MockBackend(delay=.001)
    m._state['point_holds']={'A':a,'C':None,'B':b}
    return m

def go(pose):return {'action':'go_to','args':{'pose':pose}}
def grip(state):return {'action':'gripper','args':{'state':state}}
def move(a,b):return {'action':'move_block','args':{'from':a,'to':b}}

@pytest.mark.parametrize('text,steps',[
    ('move the mandarin from B to A',[move('B','A')]),
    ('Put it back from station B to station A.',[move('B','A')]),
    ('just go to ABOVE_B, don\'t grasp it and return to HOME',[go('ABOVE_B'),go('HOME')]),
    ('go above A, open the gripper, go down to A, close the gripper, go up, then return home',
     [go('ABOVE_A'),grip('open'),go('GRASP_A'),grip('close'),go('ABOVE_A'),go('HOME')]),
    ('go to B then go down and release and lift and go home',[go('ABOVE_B'),go('GRASP_B'),grip('open'),go('ABOVE_B'),go('HOME')]),
    ('move the mandarin from A to B, then move it from B to A',[move('A','B'),move('B','A')]),
    ('go to A and then B and then home after that',[go('ABOVE_A'),go('ABOVE_B'),go('HOME')]),
    ('Go to B, then to A, then back to B, then home.',[go('ABOVE_B'),go('ABOVE_A'),go('ABOVE_B'),go('HOME')]),
    ('go over B, wait 2 seconds, return home',[go('ABOVE_B'),{'action':'wait','args':{'seconds':2}},go('HOME')]),
])
def test_commands_become_plan_actions(text,steps):
    assert FreePlans(POSES).parse(text,backend())==steps

@pytest.mark.parametrize('text',['B','open the gripper and then B','what is density?','test sample at A in B','go above A and juggle','add water from A into B',''])
def test_a_command_that_is_not_fully_understood_makes_no_plan(text):
    assert FreePlans(POSES).parse(text,backend()) is None

def test_unknown_stations_are_explained():
    with pytest.raises(PlanProblem,match='no saved station Z'):
        FreePlans(POSES).parse('move it from A to Z',backend())

def test_the_validator_decides_what_is_allowed():
    free=FreePlans(POSES)
    with pytest.raises(PlanProblem,match='nothing at B'):
        free.validate(backend(),[move('B','A')])
    with pytest.raises(PlanProblem,match='end at HOME'):
        free.validate(backend(),[go('ABOVE_B')])
    with pytest.raises(PlanProblem,match='ABOVE_B before going down'):
        free.validate(backend(),[go('GRASP_B'),go('HOME')])
    assert free.validate(backend(a=None,b='mandarin'),[move('B','A')])['end_state']['point_holds']=={'A':'mandarin','B':None}

@pytest.mark.parametrize('text,yes',[('again',True),('do it again',True),('repeat the previous command',True),('one more time',True),
    ('execute the previous command again',True),('move it from A to B again',False),('go home',False),('execute',False)])
def test_repeat_phrases(text,yes):
    assert repeat_requested(text) is yes

def test_the_simulation_gets_the_same_targets_the_arm_would():
    import json
    poses=json.loads(POSES.read_text());p,g=poses['poses'],poses['gripper']
    sim=FreePlans(POSES).sim_request(backend(a=None,b='mandarin'),[move('B','A')],'mandarin')
    o,c={'gripper.pos':g['open']},{'gripper.pos':g['cup']}
    assert sim['script']==[o,p['ABOVE_B'],p['GRASP_B'],c,p['ABOVE_B'],p['ABOVE_A'],p['GRASP_A'],o,p['ABOVE_A'],p['HOME']]
    assert sim['labels'][0]=='pick(B)' and sim['labels'][-1]=='home()' and len(sim['labels'])==len(sim['script'])
    assert (sim['object'],sim['object_at'],sim['expect_at'])==('mandarin','B','A')
    assert set(sim['marks'])=={'A','B'} and sim['strict_grasp'] is False

class FakePreview:
    def __init__(self):self.calls=[]
    def __call__(self,b,request):
        self.calls.append(request)
        return {'status':'ready','provenance':'SIMULATED','warnings':[],'blocks':[],'objects':[{'name':'mandarin','at':request['sim']['expect_at']}] if 'sim' in request else []}

async def session(lab):
    sid=(await lab.create('mandarin_transfer'))['session_id']
    await lab.prediction(sid,'It will get there.')
    return sid

async def settle(lab,sid):
    await asyncio.gather(*lab.preview_tasks.get(sid,()))
    if sid in lab.tasks: await lab.tasks[sid]
    return lab.snapshot(sid)

def make_lab(tmp_path,previewer=None):
    return Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001),previewer=previewer,free_plans=FreePlans(POSES))

@pytest.mark.asyncio
async def test_there_and_back_then_again(tmp_path):
    fake=FakePreview()
    lab=make_lab(tmp_path,fake)
    sid=await session(lab)
    await lab.request(sid,'move the mandarin from A to B','c1')   # the registry's own skill still handles this in mock
    await settle(lab,sid);await lab.request(sid,'execute','c2');s=await settle(lab,sid)
    assert s['state']['point_holds']['B']=='mandarin' and s['requests'][-1]['skill_id']!=SKILL
    s=await lab.request(sid,'move the mandarin from B to A','c3')
    assert s['pending']['skill_id']==SKILL and s['pending']['summary']=='Move the mandarin from B to A'
    s=await settle(lab,sid)
    assert fake.calls[-1]['sim']['expect_at']=='A' and 'the mandarin ends at A' in s['messages'][-1]['text']
    await lab.request(sid,'execute','c4');s=await settle(lab,sid)
    assert s['requests'][-1]['status']=='completed' and s['state']['point_holds']['A']=='mandarin' and s['state']['point_holds']['B'] is None
    assert s['observations'][-1]['provenance']=='MOCK'
    s=await lab.request(sid,'again','c5')
    assert s['pending'] is None and 'nothing at B' in s['messages'][-1]['text']   # repeating B to A: B is now empty
    await lab.request(sid,'go to above B, then return home','c6');await settle(lab,sid)
    await lab.request(sid,'execute','c7');await settle(lab,sid)
    s=await lab.request(sid,'do it again','c8')
    assert s['pending']['summary']=='Go to ABOVE_B; then return to HOME'

@pytest.mark.asyncio
async def test_a_refused_plan_explains_itself_and_proposes_nothing(tmp_path):
    lab=make_lab(tmp_path)
    sid=await session(lab)
    s=await lab.request(sid,'go to above B','c1')
    assert s['pending'] is None and 'end at HOME' in s['messages'][-1]['text']
    s=await lab.request(sid,'move the mandarin from A to Z','c2')
    assert s['pending'] is None and 'no saved station Z' in s['messages'][-1]['text']
    s=await lab.request(sid,'again','c3')
    assert 'no earlier command' in s['messages'][-1]['text']

@pytest.mark.asyncio
async def test_without_free_plans_the_app_is_unchanged(tmp_path):
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001))
    sid=await session(lab)
    s=await lab.request(sid,'move the mandarin from B to A','c1')
    assert s['pending'] is None and 'Unsupported source' in s['messages'][-1]['text']

class Arm(MockBackend):
    """Stands in for the physical adapter: a runner with a (fake) robot and the real pose file."""
    mode='physical'
    def __init__(self):
        super().__init__(delay=.001)
        from firmware.openarms_executor.motion import FakeRobot
        from firmware.openarms_executor.poses import load_poses
        from firmware.openarms_executor.transfer_runner import PoseTransferRunner
        poses=load_poses(POSES)
        self.runner=PoseTransferRunner(FakeRobot(poses['poses']['HOME']),poses,seconds=.02)
        self._state['point_holds']={'A':'mandarin','C':None,'B':None}
        self._executing=False
    def capabilities(self):return {**super().capabilities(),'objects':['mandarin']}

def physical_lab(tmp_path,monkeypatch,answers):
    monkeypatch.setenv('OPENARMS_BACKEND','physical')
    asked=[]
    def ask(q):
        asked.append(q);return answers.pop(0)
    lab=Lab(tmp_path,free_plans=FreePlans(seconds=.02,ask=ask))
    lab.physical=Arm()
    return lab,asked

@pytest.mark.asyncio
async def test_on_the_arm_plans_run_one_after_another_through_the_pose_executor(tmp_path,monkeypatch):
    lab,asked=physical_lab(tmp_path,monkeypatch,['y','y','n'])
    sid=await session(lab)
    s=await lab.request(sid,'move the mandarin from A to B','c1')
    assert s['pending']['skill_id']==SKILL            # on the arm even A to B goes through the one executor
    await lab.confirm(sid,s['pending']['request_id']);s=await settle(lab,sid)
    assert s['requests'][-1]['status']=='completed' and s['requests'][-1]['operator_authorized']
    assert s['state']['point_holds']['B']=='mandarin' and s['state']['armed'] and s['observations'][-1]['provenance']=='UNKNOWN'
    robot=lab.physical.runner.robot
    assert max(abs(robot.get_observation()[k]-v) for k,v in lab.physical.runner.poses['poses']['HOME'].items())<1
    s=await lab.request(sid,'move the mandarin from B to A','c2')
    await lab.confirm(sid,s['pending']['request_id']);s=await settle(lab,sid)
    assert s['requests'][-1]['status']=='completed' and s['state']['point_holds']['A']=='mandarin'
    s=await lab.request(sid,'again','c3')
    assert s['pending'] is None                        # B is empty again, so the repeat is refused before any motion
    s=await lab.request(sid,'go above B and return home','c4')
    await lab.confirm(sid,s['pending']['request_id']);s=await settle(lab,sid)
    assert s['requests'][-1]['status']=='rejected' and 'declined' in s['requests'][-1]['reason']
    assert len(asked)==3 and 'Move the mandarin from A to B' in asked[0] and s['state']['armed']

@pytest.mark.asyncio
async def test_on_the_arm_nothing_starts_away_from_home(tmp_path,monkeypatch):
    lab,asked=physical_lab(tmp_path,monkeypatch,['y'])
    sid=await session(lab)
    robot=lab.physical.runner.robot
    robot.send_action({'shoulder_pan.pos':robot.get_observation()['shoulder_pan.pos']+20})
    s=await lab.request(sid,'move the mandarin from A to B','c1')
    await lab.confirm(sid,s['pending']['request_id']);s=await settle(lab,sid)
    assert s['requests'][-1]['status']=='rejected' and 'not at HOME' in s['messages'][-1]['text'] and 'shoulder_pan' in s['messages'][-1]['text']
    assert asked==[] and s['state']['armed'] and s['state']['point_holds']['A']=='mandarin'

def test_real_mujoco_preview_of_a_composed_plan():
    pytest.importorskip('mujoco');pytest.importorskip('openarms_sim')
    free=FreePlans(POSES)
    b=backend(a=None,b='mandarin')
    out=MujocoPreview()(b,{'request_id':'r','skill_id':SKILL,'parameters':{},'sim':free.sim_request(b,[move('B','A')],'mandarin')})
    assert out['status']=='ready',out
    assert out['objects']==[{'name':'mandarin','at':'A','started_at':'B','moved':True}]
    hover=[go('ABOVE_B'),go('HOME')]
    out=MujocoPreview()(b,{'request_id':'r','skill_id':SKILL,'parameters':{},'sim':free.sim_request(b,hover,'mandarin')})
    assert out['status']=='ready' and out['objects'][0]['at']=='B' and not out['objects'][0]['moved']
    assert out['motion_seconds']==3.0

# ---- Claude as the planner for what the patterns do not cover --------------------------------

class Block:
    def __init__(self,name,input):self.type,self.name,self.input,self.id='tool_use',name,input,'tu_1'
class FakeClaude:
    """Returns scripted tool calls and records what it was sent."""
    def __init__(self,*replies):
        self.replies,self.calls=list(replies),[]
        self.messages=self
    def create(self,**kw):
        self.calls.append(kw)
        name,inp=self.replies.pop(0)
        return type('Resp',(),{'content':[Block(name,inp)],'usage':None})()

def agent_lab(tmp_path,*replies):
    from agentic.openarms_lab.free_plan import ClaudePlanner
    claude=FakeClaude(*replies)
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001),free_plans=FreePlans(POSES,planner=ClaudePlanner(client=claude)))
    return lab,claude

@pytest.mark.asyncio
async def test_claude_plans_what_the_patterns_miss_and_the_validator_still_decides(tmp_path):
    lab,claude=agent_lab(tmp_path,
        ('propose_plan',{'steps':[go('ABOVE_B')]}),                                     # rejected: does not end at HOME
        ('propose_plan',{'steps':[go('ABOVE_B'),go('HOME')],'added':'I added the return to HOME.'}))
    sid=await session(lab)
    s=await lab.request(sid,'hover over the far mark for me','c1')
    assert s['pending']['parameters']['steps']==[go('ABOVE_B'),go('HOME')]
    assert s['pending']['summary']=='Go to ABOVE_B; then return to HOME (I added the return to HOME.)'
    assert s['pending']['metrics']=={'model_calls':2,'planner':'claude'}
    first,second=claude.calls
    assert 'tool_choice' not in first and 'station A: the mandarin' in first['system'] and 'ABOVE_B' in first['system']
    assert 'end at HOME' in second['messages'][-1]['content'][0]['content']
    await lab.confirm(sid,s['pending']['request_id']);s=await settle(lab,sid)
    assert s['requests'][-1]['status']=='completed'

@pytest.mark.asyncio
async def test_claude_is_not_called_when_the_patterns_or_the_registry_understand(tmp_path):
    lab,claude=agent_lab(tmp_path)
    sid=await session(lab)
    assert (await lab.request(sid,'go to A and then B and then home','c1'))['pending']['metrics']['planner']=='patterns'
    assert (await lab.request(sid,'move the mandarin from A to B','c2'))['pending']['skill_id']!=SKILL
    assert claude.calls==[]

@pytest.mark.asyncio
async def test_claude_can_decline_and_cannot_get_a_bad_plan_through(tmp_path):
    lab,claude=agent_lab(tmp_path,('cannot_do',{'reason':'That is a question, not a motion. Ask me to move something.'}),
        *[('propose_plan',{'steps':[move('B','A')]})]*3)
    sid=await session(lab)
    s=await lab.request(sid,'tell me a joke about oranges','c1')
    assert s['pending'] is None and 'not a motion' in s['messages'][-1]['text']
    s=await lab.request(sid,'shuffle the fruit around somehow','c2')
    assert s['pending'] is None and 'nothing at B' in s['messages'][-1]['text'] and len(claude.calls)==4
    s=await lab.request(sid,'please do the thing','c3')          # the model call itself fails: explained, no plan
    assert s['pending'] is None and 'planning model is unavailable' in s['messages'][-1]['text']

@pytest.mark.asyncio
async def test_the_previous_command_is_given_to_claude_as_context(tmp_path):
    lab,claude=agent_lab(tmp_path,('propose_plan',{'steps':[go('ABOVE_A'),go('HOME')]}))
    sid=await session(lab)
    await lab.request(sid,'go to B then home','c1')
    await lab.request(sid,'now the same but for the other mark','c2')
    assert 'The previous command was: "go to B then home"' in claude.calls[0]['system']
