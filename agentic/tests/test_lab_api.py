import asyncio
import pytest
from fastapi.testclient import TestClient
from agentic.openarms_lab.app import create_app
from agentic.openarms_lab.runtime import Lab,LabError
from agentic.openarms_lab.backends import MockBackend


def test_api_full_flow_and_origin_guard(tmp_path):
    lab=Lab(tmp_path,backend_factory=lambda:MockBackend(delay=.001))
    with TestClient(create_app(lab)) as c:
        assert c.get('/').status_code==200
        assert 'GEMINI_API_KEY' not in c.get('/api/health').text
        s=c.post('/api/sessions',json={}).json();sid=s['session_id'];base=f'/api/sessions/{sid}'
        assert c.post(base+'/prediction',json={'text':'A floats'}).status_code==200
        s=c.post(base+'/request',json={'text':'test sample at A in B','client_request_id':'1'}).json()
        pid=s['pending']['request_id']
        assert c.post(base+'/confirm',json={'request_id':pid},headers={'Origin':'https://evil.example'}).status_code==403
        with c.websocket_connect(base+'/events') as ws:
            assert ws.receive_json()['state']['pending']['request_id']==pid
            assert c.post(base+'/confirm',json={'request_id':pid}).status_code==200
            for _ in range(20):
                snap=ws.receive_json()['state']
                if snap['requests'][-1]['status']=='completed':break
            assert snap['requests'][-1]['status']=='completed'
            assert {o['provenance'] for o in snap['observations']}=={'MOCK','MODEL-PREDICTED'}
            assert c.post(base+'/confirm',json={'request_id':pid}).status_code==409
            assert c.post(base+'/answer',json={'question_id':snap['quiz']['id'],'answer':'A'}).status_code==200
        assert c.get(base).json()['connected'] is False
        assert c.get('/api/sessions').json()[0]['session_id']==sid
        assert c.get('/api/sessions/not-a-session').status_code==404


def test_websocket_host_and_origin_allowlist(tmp_path):
    from starlette.websockets import WebSocketDisconnect
    lab=Lab(tmp_path)
    with TestClient(create_app(lab)) as c:
        sid=c.post('/api/sessions').json()['session_id']
        for channel in ('live','events'):
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect(f'/api/sessions/{sid}/{channel}',headers={'Host':'evil.example','Origin':'http://evil.example'}):pass
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect(f'/api/sessions/{sid}/{channel}',headers={'Origin':'https://evil.example'}):pass


@pytest.mark.asyncio
async def test_stop_revokes_inflight_model_turn(tmp_path,monkeypatch):
    from agentic.openarms_lab import live
    lab=Lab(tmp_path);sid=(await lab.create())['session_id']
    await lab.prediction(sid,'A floats')
    entered=asyncio.Event();release=asyncio.Event()
    async def delayed(text,context,tool):
        entered.set()
        try:await release.wait()
        except asyncio.CancelledError:
            # Even an uncooperative callback cannot mutate the revoked generation.
            release.set()
        try:await tool('request_action',{'text':'test sample at A in B'})
        except LabError:pass
        return 'Late model response'
    monkeypatch.setattr(live,'key',lambda:'configured-test')
    monkeypatch.setattr(live,'text_reply',delayed)
    task=asyncio.create_task(lab.converse(sid,'Why does A float?'))
    await entered.wait();await lab.stop(sid,disconnect=True);release.set();await task
    assert lab.snapshot(sid)['pending'] is None
    assert lab.snapshot(sid)['requests']==[]
    assert lab.snapshot(sid)['connected'] is False


@pytest.mark.asyncio
async def test_model_tool_cancellation_revokes_only_matching_proposal(tmp_path):
    lab=Lab(tmp_path);sid=(await lab.create())['session_id']
    await lab.prediction(sid,'A floats')
    a=await lab.tool(sid,'request_action',{'text':'test sample at A in B','_tool_call_id':'a'})
    b=await lab.tool(sid,'request_action',{'text':'test sample at C in B','_tool_call_id':'b'})
    await lab.tool(sid,'_cancel_tool_request',{'tool_call_id':'a'})
    assert lab.snapshot(sid)['pending']['request_id']==b['pending']['request_id']
    await lab.tool(sid,'_cancel_tool_request',{'tool_call_id':'b'})
    assert lab.snapshot(sid)['pending'] is None


class SharedPhysical:
    mode='physical'
    def __init__(self):
        self.gate=asyncio.Event();self.stops=0
        self._state={'at':'HOME','holding':None,'armed':True,'portions_left':{},'receiver_load':{},'point_holds':{'A':'mandarin','B':None,'C':'mandarin'}}
    def state(self):return self._state.copy()
    def capabilities(self):return {'routes':[['A','B']],'objects':['mandarin']}
    async def authorize(self,request):await self.gate.wait();return False
    async def stop(self):self.stops+=1


@pytest.mark.asyncio
async def test_competing_session_does_not_stop_physical_owner(tmp_path):
    backend=SharedPhysical();lab=Lab(tmp_path,backend_factory=lambda:backend)
    ids=[]
    for i in range(2):
        sid=(await lab.create())['session_id'];ids.append(sid)
        await lab.prediction(sid,'Transfer')
        s=await lab.request(sid,'move mandarin from A to B',str(i))
        await lab.confirm(sid,s['pending']['request_id'])
        await asyncio.sleep(.001)
    await lab.tasks[ids[1]]
    assert lab.snapshot(ids[1])['requests'][-1]['status']=='rejected'
    assert backend.stops==0
    await lab.stop(ids[1],disconnect=True)
    assert backend.stops==0
    backend.gate.set();await lab.tasks[ids[0]]


@pytest.mark.asyncio
async def test_stop_failure_latches_physical_unavailable(tmp_path):
    class FailingStop(SharedPhysical):
        async def stop(self):raise OSError('controller disconnected')
    backend=FailingStop();lab=Lab(tmp_path,backend_factory=lambda:backend)
    sid=(await lab.create())['session_id'];await lab.prediction(sid,'Transfer')
    s=await lab.request(sid,'move mandarin from A to B','1');await lab.confirm(sid,s['pending']['request_id'])
    await asyncio.sleep(.001);await lab.stop(sid)
    assert lab.physical_unavailable
    assert lab.snapshot(sid)['requests'][-1]['status']=='unknown'
