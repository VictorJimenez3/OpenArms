"""Integration checks at real runtime/backend seams; never connects a motor."""
import asyncio
import time
from pathlib import Path
import pytest
from agentic.openarms_lab.runtime import Lab,LabError
from agentic.openarms_lab.backends import MockBackend,TransferRunnerAdapter
from agentic.openarms_lab.contracts import SkillRequest

async def prepared(lab,text='test sample at A in B'):
    s=await lab.create()
    sid=s['session_id']
    await lab.prediction(sid,'A will float because its density is below water.')
    s=await lab.request(sid,text,'client-1')
    assert s['pending'],s['messages'][-1]
    return sid,s['pending']['request_id']

@pytest.mark.asyncio
async def test_full_trial_notebook_and_two_conditions(tmp_path):
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001))
    sid,pid=await prepared(lab)
    s=await lab.confirm(sid,pid)
    assert s['requests'][-1]['student_confirmed']
    await lab.tasks[sid]
    s=lab.snapshot(sid)
    assert s['requests'][-1]['status']=='completed'
    assert s['requests'][-1]['operator_authorized'] is False
    assert {'MOCK','MODEL-PREDICTED'}=={o['provenance'] for o in s['observations']}
    assert s['quiz']
    await lab.answer(sid,s['quiz']['id'],'The sample is less dense than the water.')
    await lab.prepare(sid)
    await lab.prediction(sid,'C will sink because it is denser than water.')
    s=await lab.request(sid,'test sample at C in B','client-2')
    await lab.confirm(sid,s['pending']['request_id'])
    await lab.tasks[sid]
    s=lab.snapshot(sid)
    assert len(s['observations'])==4
    kinds={e['kind'] for e in s['notebook']}
    assert {'prediction','request_proposed','student_confirmed','execution_result','observation','quiz_answer','question'}<=kinds
    restored=Lab(tmp_path)
    assert len(restored.snapshot(sid)['notebook'])>=len(s['notebook'])
    assert not restored.snapshot(sid)['state']['armed']

@pytest.mark.asyncio
async def test_duplicates_stale_correction_cancel_and_expiry(tmp_path):
    lab=Lab(tmp_path)
    sid,pid=await prepared(lab)
    await lab.request(sid,'test sample at A in B','client-1')
    assert len(lab.get(sid)['requests'])==1
    with pytest.raises(LabError):await lab.request(sid,'test sample at C in B','client-1')
    s=await lab.request(sid,'test sample at C in B','client-2')
    with pytest.raises(LabError):await lab.confirm(sid,pid)
    pid=s['pending']['request_id']
    await lab.cancel(sid,pid)
    with pytest.raises(LabError):await lab.confirm(sid,pid)
    s=await lab.request(sid,'test sample at A in B','client-3')
    lab.get(sid)['pending']['expires_at']=time.time()-1
    with pytest.raises(LabError):await lab.confirm(sid,s['pending']['request_id'])
    assert lab.snapshot(sid)['pending'] is None

@pytest.mark.asyncio
async def test_confirmation_single_use_and_stop(tmp_path):
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.2))
    sid,pid=await prepared(lab)
    await lab.confirm(sid,pid)
    with pytest.raises(LabError):await lab.confirm(sid,pid)
    await asyncio.sleep(.01)
    await lab.stop(sid)
    s=lab.snapshot(sid)
    assert s['requests'][-1]['status']=='stopped'
    assert s['state']['point_holds']['B'] is None

@pytest.mark.asyncio
async def test_disconnect_cancels_pending_and_active(tmp_path):
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.2))
    sid,pid=await prepared(lab)
    await lab.stop(sid,disconnect=True)
    with pytest.raises(LabError):await lab.confirm(sid,pid)
    s=await lab.request(sid,'test sample at A in B','second')
    await lab.confirm(sid,s['pending']['request_id'])
    await asyncio.sleep(.01)
    await lab.stop(sid,disconnect=True)
    assert lab.snapshot(sid)['requests'][-1]['status']=='stopped'

@pytest.mark.asyncio
@pytest.mark.parametrize('fault,expected',[('failure','failed'),('disconnect','unknown'),('timeout','unknown'),('unknown','completed')])
async def test_fault_scenarios(tmp_path,fault,expected):
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001,fault=fault),execution_timeout=.025)
    sid,pid=await prepared(lab)
    await lab.confirm(sid,pid)
    await lab.tasks[sid]
    s=lab.snapshot(sid)
    assert s['requests'][-1]['status']==expected
    assert not any(o['provenance']=='REAL' for o in s['observations'])
    if fault=='unknown':assert {o['provenance'] for o in s['observations']}=={'UNKNOWN'}

@pytest.mark.asyncio
async def test_invalid_unknown_and_ambiguous_requests(tmp_path):
    lab=Lab(tmp_path)
    sid=(await lab.create())['session_id']
    await lab.prediction(sid,'I predict a transfer.')
    for n,text in enumerate(['move an apple from A to B','move the sample','move sample from A to D','rotate servo 99','test sample at A in A']):
        s=await lab.request(sid,text,str(n))
        assert s['pending'] is None,text
    assert not lab.tasks

class PhysicalFake:
    mode='physical'
    scripts={'A':None}
    def __init__(self):self.called=[];self.gate=asyncio.Event();self.stop_count=0
    async def authorize(self,plan):
        self.called.append(('authorize',plan))
        await self.gate.wait()
        return True
    async def execute(self,plan):
        self.called.append(('execute',plan))
        from types import SimpleNamespace
        return SimpleNamespace(plan_id=plan['plan_id'],mode='physical',status='completed',operator_authorized=True,placement=None)
    async def stop(self):self.stop_count+=1

@pytest.mark.asyncio
async def test_physical_separate_operator_unknown_and_capabilities(tmp_path):
    fake=PhysicalFake();adapter=TransferRunnerAdapter(fake)
    assert adapter.capabilities()['routes']==[['A','B']]
    lab=Lab(tmp_path,backend_factory=lambda:adapter)
    sid=(await lab.create())['session_id']
    await lab.prediction(sid,'The mandarin should reach B; actual placement must be checked.')
    s=await lab.request(sid,'move orange from A to B','1')
    await lab.confirm(sid,s['pending']['request_id'])
    await asyncio.sleep(.01)
    assert lab.snapshot(sid)['requests'][-1]['status']=='awaiting_operator'
    assert not any(c[0]=='execute' for c in fake.called)
    fake.gate.set();await lab.tasks[sid]
    s=lab.snapshot(sid)
    assert s['requests'][-1]['result']['physical_success'] is None
    assert {o['provenance'] for o in s['observations']}=={'UNKNOWN'}
    assert s['requests'][-1]['operator_authorized'] is True

@pytest.mark.asyncio
async def test_cancelled_operator_late_yes_never_executes(tmp_path):
    fake=PhysicalFake();adapter=TransferRunnerAdapter(fake)
    lab=Lab(tmp_path,backend_factory=lambda:adapter)
    sid=(await lab.create())['session_id']
    await lab.prediction(sid,'B')
    s=await lab.request(sid,'move orange from A to B','1')
    await lab.confirm(sid,s['pending']['request_id'])
    await asyncio.sleep(.01)
    await lab.stop(sid)
    assert not adapter._authorization.done()
    fake.gate.set();await adapter._authorization
    assert not any(c[0]=='execute' for c in fake.called)
    assert lab.snapshot(sid)['requests'][-1]['status']=='stopped'
