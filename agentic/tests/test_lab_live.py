"""Gemini Live protocol checks using in-memory transports and no credentials."""
import asyncio
import base64
from types import SimpleNamespace as NS

import pytest

from agentic.openarms_lab import live


def response(**fields):
    return NS(**dict(dict(server_content=None, tool_call=None, tool_call_cancellation=None,
                         session_resumption_update=None, go_away=None, usage_metadata=None), **fields))


def content(**fields):
    return NS(**dict(dict(interrupted=False, input_transcription=None, output_transcription=None,
                         model_turn=None, turn_complete=False), **fields))


class Session:
    def __init__(self, initial=None):
        self.incoming = asyncio.Queue()
        self.realtime = []
        self.turns = []
        self.tools = []
        self.exited = False
        if initial is not None:
            self.incoming.put_nowait(initial)

    async def send_realtime_input(self, **message):
        self.realtime.append(message)

    async def send_client_content(self, **message):
        self.turns.append(message)

    async def send_tool_response(self, **message):
        self.tools.extend(message['function_responses'])

    async def receive(self):
        message = await self.incoming.get()
        if isinstance(message, Exception):
            raise message
        yield message


class Connection:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *_exc):
        self.session.exited = True


class Client:
    def __init__(self, factory=Session):
        self.factory = factory
        self.sessions = []
        self.configs = []
        self.closed = False
        self.aio = NS(live=NS(connect=self.connect), aclose=self.aclose)

    def connect(self, **kwargs):
        session = self.factory()
        self.sessions.append(session)
        self.configs.append(kwargs)
        return Connection(session)

    async def aclose(self):
        self.closed = True


def context():
    return {'requests': [], 'tasks': [], 'observations': [], 'messages': []}


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.001)


async def assert_clean(bridge, client):
    assert not bridge.ready and not bridge.pending_tools and bridge.watcher_id is None
    assert client.closed and all(session.exited for session in client.sessions)
    handlers = (live.GeminiBridge._upstream.__qualname__, live.GeminiBridge._downstream.__qualname__,
                live.GeminiBridge._tool.__qualname__)
    assert not [task for task in asyncio.all_tasks() if task.get_coro().__qualname__ in handlers]


async def finish(bridge, runner):
    await bridge.close()
    runner.cancel()
    await asyncio.wait_for(asyncio.gather(runner, return_exceptions=True), 2)


def transcript(text, *, finished=True):
    return response(server_content=content(input_transcription=NS(text=text, finished=finished)))


def tool_call(cid, name, **args):
    return NS(id=cid, name=name, args=args)


def function_calls(*calls):
    return response(tool_call=NS(function_calls=calls))


def output_reply(text):
    return response(server_content=content(output_transcription=NS(text=text),
        model_turn=NS(parts=[NS(inline_data=NS(data=b'\0\0'))]), turn_complete=True))


def add_event(state, kind, **data):
    notebook = state.setdefault('notebook', [])
    seq = len(notebook) + 1
    notebook.append({'kind': kind, 'event_id': f'event-{seq}', 'sequence': seq,
                     **live.brief(data, live.EVENT_FIELDS), 'data': data})


async def test_missing_credentials_keeps_text_fallback_without_constructing_client(monkeypatch):
    for name in ('GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(live.genai, 'Client', lambda **_: pytest.fail('Unexpected provider client'))
    sent = []

    async def emit(message):
        sent.append(message)

    async def tool(*_):
        pytest.fail('Starting unavailable voice must not execute a control')

    bridge = live.GeminiBridge(context, tool, emit)
    await bridge.run()
    assert sent[-1]['status'] == 'unavailable' and 'text' in sent[-1]['message'].lower()
    assert not bridge.ready
    await bridge.close()
    assert bridge.closed


async def test_pcm_turn_records_usage_and_exact_stop_without_a_model_tool():
    client, sent, calls = Client(), [], []

    async def emit(message):
        sent.append(message)

    async def tool(name, args):
        calls.append((name, args))

    bridge = live.GeminiBridge(context, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        pcm = b'\x00\x01\x02\x03'
        await bridge.audio(base64.b64encode(pcm).decode())
        with pytest.raises(ValueError, match='PCM'):
            await bridge.audio(base64.b64encode(b'x').decode())
        await bridge.end_audio()
        session.incoming.put_nowait(transcript('ST', finished=False))
        await until(lambda: any(m.get('text') == 'ST' for m in sent))
        assert calls == []
        session.incoming.put_nowait(transcript('OP'))
        session.incoming.put_nowait(response(server_content=content(
            output_transcription=NS(text='Check the evidence.'),
            model_turn=NS(parts=[NS(inline_data=NS(data=pcm))]), turn_complete=True),
            usage_metadata=NS(model_dump=lambda **_: {'total_token_count': 17})))
        await until(lambda: len(session.realtime) == 2 and len(calls) == 4)
        assert session.realtime[0]['audio'].data == pcm
        assert session.realtime[0]['audio'].mime_type == 'audio/pcm;rate=16000'
        assert session.realtime[1] == {'audio_stream_end': True}
        assert [turn['turns'].parts[0].text for turn in session.turns] == ['Start voice.']
        user_partial, user_final = [m for m in sent if m.get('role') == 'user']
        assert user_final['text'] == 'STOP' and user_final['final'] and not user_partial['final']
        assert user_final['turn_id'] == user_partial['turn_id']
        audio, = [m for m in sent if m['type'] == 'audio']
        assert base64.b64decode(audio['data']) == pcm
        assert ('_record_transcript', {'role': 'assistant', 'text': 'Check the evidence.',
                                       'turn_id': audio['reply_id'], 'final': True}) in calls
        assert calls.count(('stop_lab', {})) == 1 and not session.tools
        assert ('_record_usage', {'usage': {'total_token_count': 17}}) in calls
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


async def test_duplicate_tool_id_returns_cached_reply_and_cancelled_id_never_reenters():
    client, state, actions = Client(), context(), []

    async def emit(_):
        pass

    async def tool(name, args):
        if name == 'request_action':
            actions.append(args['_tool_call_id'])
            state['tasks'].append({'task_id': 'queued-task', 'status': 'queued'})

    bridge = live.GeminiBridge(lambda: state, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        call = tool_call('original', 'request_action', text='Test the prepared vinegar sample.')
        session.incoming.put_nowait(transcript(call.args['text']))
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[call, call])))
        await until(lambda: len(session.tools) == 1)
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[call])))
        await until(lambda: len(session.tools) == 2)
        assert actions == ['original']
        assert all(r.id == 'original' and r.response['result']['tasks'] == live.compact_snapshot(state)['tasks']
                   for r in session.tools)
        session.incoming.put_nowait(response(tool_call_cancellation=NS(ids=['original'])))
        sentinel = tool_call('read', 'get_lab_state')
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[call, sentinel])))
        await until(lambda: any(r.id == 'read' for r in session.tools))
        assert [r.id for r in session.tools] == ['original', 'original', 'read']
        assert actions == ['original']
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


async def test_provider_cancels_only_matching_pending_callback():
    client, entered, cancelled = Client(), asyncio.Event(), asyncio.Event()
    other_entered, release = asyncio.Event(), asyncio.Event()

    async def emit(_):
        pass

    async def tool(name, args):
        if name == 'request_action':
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        elif name == 'get_lab_state':
            other_entered.set()
            await release.wait()

    bridge = live.GeminiBridge(context, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        text = 'Test the prepared vinegar sample.'
        session.incoming.put_nowait(transcript(text))
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[
            tool_call('cancel-me', 'request_action', text=text),
            tool_call('leave-alone', 'get_lab_state')])))
        await asyncio.wait_for(asyncio.gather(entered.wait(), other_entered.wait()), 2)
        session.incoming.put_nowait(response(tool_call_cancellation=NS(ids=['cancel-me'])))
        await asyncio.wait_for(cancelled.wait(), 2)
        assert 'leave-alone' in bridge.pending_tools and not bridge.pending_tools['leave-alone'].done()
        release.set()
        await until(lambda: len(session.tools) == 1)
        assert [r.id for r in session.tools] == ['leave-alone']
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


@pytest.mark.parametrize('failure', [ConnectionError, RuntimeError])
async def test_upstream_reconnects_are_bounded_and_resume_without_replaying_student_turn(failure):
    client = Client()
    sent, controls = [], []

    def make_session():
        if not client.sessions:
            session = Session(response(session_resumption_update=NS(resumable=True, new_handle='resume-1')))
            session.incoming.put_nowait(response(go_away=NS()))
            return session
        return Session(failure('stand-in upstream unavailable'))

    client.factory = make_session

    async def emit(message):
        sent.append(message)

    async def tool(name, args):
        controls.append((name, args))

    bridge = live.GeminiBridge(context, tool, emit, client_factory=lambda: client, reconnect_delay=0)
    await asyncio.wait_for(bridge.run(), 2)
    assert len(client.sessions) == 4
    assert client.configs[0]['config'].session_resumption.handle is None
    assert all(c['config'].session_resumption.handle == 'resume-1' for c in client.configs[1:])
    assert controls == [('stop_lab', {})] * 4
    assert [len(s.turns) for s in client.sessions] == [1, 0, 0, 0]
    assert bridge.last_error == failure.__name__
    assert sent[-1]['status'] == 'unavailable'
    await assert_clean(bridge, client)


async def test_spoken_preview_is_only_presented_after_matching_playback():
    state = {**context(), 'pending': {'request_id': 'proposal', 'proposal_version': 1,
                                     'summary': 'Inspect the prepared sample.'}}
    client, sent, presented = Client(), [], []

    async def emit(message):
        sent.append(message)

    async def tool(name, args):
        if name == '_present_audio':
            presented.append(args)

    bridge = live.GeminiBridge(lambda: state, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]

        async def reply(text, index):
            session.incoming.put_nowait(output_reply(text))
            await until(lambda: sum(m['type'] == 'reply_end' for m in sent) == index)
            return [m['reply_id'] for m in sent if m['type'] == 'reply_end'][-1]

        wrong = await reply('It is ready to run.', 1)
        await bridge.played(wrong)
        stale = await reply(state['pending']['summary'], 2)
        state['pending']['proposal_version'] = 2
        await bridge.played(stale)
        assert presented == []
        exact = await reply(state['pending']['summary'], 3)
        assert presented == []  # Provider turn completion is not student playback.
        await bridge.played(exact)
        await bridge.played(exact)
        assert presented == [{'request_id': 'proposal', 'proposal_version': 2, 'reply_id': exact}]
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


async def test_paraphrased_confirmation_prompt_requests_exact_readout_after_playback():
    state = {**context(), 'pending': {'request_id':'proposal','proposal_version':1,
                                     'summary':'Inspect the prepared sample.'}}
    client, sent, presented = Client(), [], []
    async def emit(frame):
        sent.append(frame)
    async def tool(name,args):
        if name == '_present_audio':
            presented.append(args)
    bridge = live.GeminiBridge(lambda:state,tool,emit,client_factory=lambda:client)
    runner=asyncio.create_task(bridge.run())
    try:
        await until(lambda:bridge.ready)
        session=client.sessions[0]
        session.incoming.put_nowait(function_calls(tool_call('watch','watch_lab_events')))
        await until(lambda:len(session.tools)==1)
        session.incoming.put_nowait(output_reply('I will take a look. Say confirm or cancel.'))
        await until(lambda:any(e['type']=='reply_end'for e in sent))
        rid=next(e['reply_id']for e in sent if e['type']=='reply_end')
        assert len(session.tools)==1 and not presented
        await bridge.played(rid)
        await until(lambda:len(session.tools)==2)
        repair=session.tools[-1]
        assert repair.scheduling.value=='WHEN_IDLE'
        assert state['pending']['summary'] in repair.response['instruction']
        assert not presented
    finally:
        await finish(bridge,runner)


async def test_long_exact_preview_can_finish_playback_before_ack_expires(monkeypatch):
    state={**context(),'pending':{'request_id':'proposal','proposal_version':1,'summary':'Inspect the prepared sample.'}}
    clock=[100.0]
    monkeypatch.setattr(live,'time',NS(monotonic=lambda:clock[0]))
    client,sent,presented=Client(),[],[]
    async def emit(frame):sent.append(frame)
    async def tool(name,args):
        if name=='_present_audio':presented.append(args)
    bridge=live.GeminiBridge(lambda:state,tool,emit,client_factory=lambda:client)
    runner=asyncio.create_task(bridge.run())
    try:
        await until(lambda:bridge.ready)
        packet=output_reply(state['pending']['summary'])
        packet.server_content.model_turn.parts[0].inline_data.data=bytes(20*48000)
        client.sessions[0].incoming.put_nowait(packet)
        await until(lambda:any(e['type']=='reply_end'for e in sent))
        rid=next(e['reply_id']for e in sent if e['type']=='reply_end')
        clock[0]+=20
        await bridge.played(rid)
        assert len(presented)==1
    finally:await finish(bridge,runner)


@pytest.mark.parametrize('resumed', [True, False])
async def test_reconnect_recovers_subscription_and_replays_real_correlated_feedback(resumed):
    state = {**context(), 'generation': 0, 'notebook': []}
    client = Client()
    correlation = {'task_id': 't1', 'request_id': 'r1', 'trial_id': 'trial1',
                   'skill_version': 'skill-v', 'turn_id': 'student-1'}
    add_event(state, 'task_status', status='executing', **correlation)

    async def emit(_):
        pass

    async def tool(name, _):
        if name == 'stop_lab':
            state['generation'] += 1

    bridge = live.GeminiBridge(lambda: state, tool, emit, client_factory=lambda: client,
                               reconnect_delay=0)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        first = client.sessions[0]
        first.incoming.put_nowait(function_calls(tool_call('watch-1', 'watch_lab_events')))
        await until(lambda: len(first.tools) == 1)
        assert first.tools[0].response['through_sequence'] == 1
        if resumed:
            first.incoming.put_nowait(response(session_resumption_update=NS(resumable=True, new_handle='resume-1')))
            await until(lambda: bridge.resume_handle == 'resume-1')
        add_event(state, 'execution_progress', step=1, operation='mock_prepared_sample', phase='metered_dose',
                  provenance='SIMULATED', **correlation)
        add_event(state, 'message', role='assistant', text='Internal conversation')
        add_event(state, 'execution_result', provenance='SIMULATED', **correlation,
                  receipt={**correlation, 'receipt_id': 'controller-1', 'plan_hash': 'plan-1',
                           'backend': 'mujoco', 'status': 'completed', 'controller_completed': True,
                           'physical_execution': False, 'simulation': {'path': '/tmp/private'}})
        add_event(state, 'observation', provenance='UNKNOWN', evidence_ids=['frame-1'], **correlation,
                  observation={**correlation, 'observation_id': 'observed-1', 'plan_hash': 'plan-1',
                               'status': 'unknown', 'provenance': 'UNKNOWN', 'evidence': ['frame-1'],
                               'reason': 'Image unreadable', 'receipt': {'images': [{'path': '/tmp/private'}]}})
        add_event(state, 'task_status', status='failed', code='authentication', **correlation)
        await bridge.state_changed()
        await until(lambda: len(first.tools) == 2)  # Change sent after latest resumption handle.
        first.incoming.put_nowait(response(go_away=NS()))
        await until(lambda: len(client.sessions) == 2 and bridge.ready)
        second = client.sessions[1]
        if not resumed:
            second.incoming.put_nowait(function_calls(tool_call('watch-1', 'watch_lab_events')))
        await until(lambda: len(second.tools) == 1)
        replay, = second.tools
        assert replay.id == 'watch-1' and replay.will_continue
        assert replay.response['subscription'] == ('resumed' if resumed else 'current')
        assert replay.response['state']['generation'] == 1
        assert not second.turns
        assert replay.response['after_sequence'] == (1 if resumed else 0)
        assert replay.response['through_sequence'] == 6
        events = replay.response['events'][-4:]
        assert [e['sequence'] for e in events] == [2, 4, 5, 6]
        assert all(e['request_id'] == 'r1' and e['task_id'] == 't1' for e in events)
        assert events[0]['phase'] == 'metered_dose'
        assert events[1]['receipt']['receipt_id'] == 'controller-1'
        assert events[1]['receipt']['controller_completed'] is True
        assert events[2]['observation']['plan_hash'] == events[1]['receipt']['plan_hash'] == 'plan-1'
        assert events[2]['observation']['status'] == 'unknown'
        assert events[2]['observation']['evidence'] == ['frame-1']
        assert events[3]['code'] == 'authentication'
        assert '/tmp/private' not in str(replay.response)
        add_event(state, 'task_status', status='cancelled', **correlation)
        await bridge.state_changed()
        await until(lambda: len(second.tools) == 2)
        assert second.tools[-1].response['after_sequence'] == 6
        assert [e['sequence'] for e in second.tools[-1].response['events']] == [7]
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


async def test_global_interruption_revokes_completed_reply_and_allows_fresh_confirmation():
    pending = {'request_id': 'proposal', 'proposal_version': 1, 'presented': False,
               'summary': 'Inspect the prepared sample.'}
    state = {**context(), 'pending': pending}
    client, sent, actions = Client(), [], []

    async def emit(message):
        sent.append(message)

    async def tool(name, args):
        if name == '_present_audio':
            pending['presented'] = True
            actions.append((name, args['reply_id']))
        if name == 'student_confirm':
            state['pending'] = None
            actions.append((name, args['_voice_consent']['turn_id']))

    bridge = live.GeminiBridge(lambda: state, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        session.incoming.put_nowait(output_reply(pending['summary']))
        await until(lambda: any(m['type'] == 'reply_end' for m in sent))
        stale = sent[-1]['reply_id']
        assert bridge.reply_id is None and stale in bridge.replies
        session.incoming.put_nowait(response(server_content=content(interrupted=True)))
        await until(lambda: sent[-1]['type'] == 'interrupted')
        assert sent[-1]['reply_id'] is None and bridge._playback_idle()
        await bridge.played(stale)
        assert not pending['presented'] and not actions

        session.incoming.put_nowait(output_reply(pending['summary']))
        await until(lambda: sum(m['type'] == 'reply_end' for m in sent) == 2)
        fresh = sent[-1]['reply_id']
        assert fresh != stale
        await bridge.played(fresh)
        await bridge.played(stale)
        session.incoming.put_nowait(transcript('Confirm.'))
        await until(lambda: state['pending'] is None)
        assert actions == [('_present_audio', fresh), ('student_confirm', bridge.controls.turn_id)]
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


async def test_back_to_back_progress_cannot_replace_proposal_on_either_client():
    pending = {'request_id': 'proposal', 'proposal_version': 1, 'presented': False,
               'summary': 'Inspect the prepared sample.'}
    state = {**context(), 'pending': pending, 'requests': [dict(pending)]}
    client, sent, confirmed = Client(), [], []

    async def emit(message):
        sent.append(message)

    async def tool(name, args):
        if name == '_present_audio':
            pending['presented'] = state['requests'][0]['presented'] = True
            await bridge.state_changed()
        if name == 'student_confirm':
            confirmed.append(args)
            state['pending'] = None

    bridge = live.GeminiBridge(lambda: state, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        session.incoming.put_nowait(function_calls(tool_call('watch', 'watch_lab_events')))
        await until(lambda: len(session.tools) == 1)
        session.incoming.put_nowait(output_reply(pending['summary']))
        await until(lambda: sent[-1]['type'] == 'reply_end')
        rid = sent[-1]['reply_id']
        add_event(state, 'execution_progress', phase='checking')
        await bridge.state_changed()
        add_event(state, 'execution_progress', phase='finished_checking')
        await bridge.state_changed()
        # Model already had a progress reply scheduled. A second reply_start
        # would make iOS drop the preview, while the browser queues both replies.
        session.incoming.put_nowait(output_reply('Still checking.'))
        session.incoming.put_nowait(function_calls(tool_call('read', 'get_lab_state')))
        await until(lambda: any(r.id == 'read' for r in session.tools))
        assert [m['reply_id'] for m in sent if m['type'] == 'reply_start'] == [rid]
        assert len([r for r in session.tools if r.id == 'watch']) == 1

        await bridge.played(rid)
        await until(lambda: len([r for r in session.tools if r.id == 'watch']) == 2)
        watch = [r for r in session.tools if r.id == 'watch'][-1]
        assert watch.scheduling.value == 'SILENT'
        assert [e['phase'] for e in watch.response['events']] == ['checking', 'finished_checking']
        session.incoming.put_nowait(transcript('Confirm.'))
        await until(lambda: len(confirmed) == 1)
        assert confirmed[0]['request_id'] == 'proposal'
    finally:
        await finish(bridge, runner)
    await assert_clean(bridge, client)


async def test_missing_play_ack_expires_without_presenting(monkeypatch):
    clock = NS(monotonic=lambda: 1.)
    monkeypatch.setattr(live, 'time', clock)
    actions = []

    async def tool(name, args):
        actions.append((name, args))

    async def emit(_):
        pass

    bridge = live.GeminiBridge(context, tool, emit)
    bridge.replies['old'] = {'complete': True, 'proposal': {}, 'expires': 1 + live.PLAYBACK_ACK_TIMEOUT}
    assert not bridge._playback_idle()
    clock.monotonic = lambda: 2 + live.PLAYBACK_ACK_TIMEOUT
    assert bridge._playback_idle()
    await bridge.played('old')
    assert not actions


async def test_stop_revokes_buffered_playback_and_discards_superseded_stream_tail():
    state, client, sent = {**context(), 'generation': 0}, Client(), []

    async def emit(message):
        sent.append(message)

    async def tool(name, args):
        if name == 'stop_lab':
            state['generation'] += 1

    bridge = live.GeminiBridge(lambda: state, tool, emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        session.incoming.put_nowait(output_reply('The first step is ready.'))
        await until(lambda: any(m['type'] == 'reply_end' for m in sent))
        session.incoming.put_nowait(response(server_content=content(
            output_transcription=NS(text='Starting the next step.'))))
        await until(lambda: sum(m['type'] == 'reply_start' for m in sent) == 2)
        session.incoming.put_nowait(transcript('Stop.'))
        session.incoming.put_nowait(output_reply('Still executing the old step.'))
        session.incoming.put_nowait(function_calls(tool_call('read', 'get_lab_state')))
        await until(lambda: any(r.id == 'read' for r in session.tools))
        assert state['generation'] == 1
        assert not bridge.replies
        assert any(m['type'] == 'interrupted' and m['reply_id'] is None for m in sent)
        assert not any('Still executing' in m.get('text', '') for m in sent)
        session.incoming.put_nowait(transcript('What happened?'))
        session.incoming.put_nowait(output_reply('The task stopped.'))
        await until(lambda: any(m.get('text') == 'The task stopped.' and m['final'] for m in sent))
    finally:
        await finish(bridge, runner)


async def test_barging_in_does_not_cancel_a_student_task_already_accepted_by_the_server(tmp_path):
    from agentic.openarms_lab.runtime import Lab
    from agentic.tests.test_task_loop import TestExpert, TestPerception

    lab = Lab(tmp_path, expert=TestExpert(), perception=TestPerception())
    sid = (await lab.create())['session_id']
    client = Client()

    async def emit(_):
        pass

    bridge = live.GeminiBridge(lambda: lab.snapshot(sid), lambda name, args: lab.tool(sid, name, args),
                               emit, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        text = 'Test the prepared vinegar sample.'
        session.incoming.put_nowait(transcript(text))
        session.incoming.put_nowait(function_calls(tool_call('accepted', 'request_action', text=text)))
        await until(lambda: lab.snapshot(sid)['pending'])
        pending = lab.snapshot(sid)['pending']
        session.incoming.put_nowait(response(tool_call_cancellation=NS(ids=['accepted'])))
        session.incoming.put_nowait(transcript('How is it going?'))
        session.incoming.put_nowait(function_calls(tool_call('status', 'get_lab_state')))
        await until(lambda: any(reply.id == 'status' for reply in session.tools))
        status = next(reply for reply in session.tools if reply.id == 'status').response['result']
        assert status['pending']['request_id'] == pending['request_id']
        assert len(status['tasks']) == 1
        assert lab.backends[sid].executions == 0
    finally:
        await finish(bridge, runner)
        await lab.shutdown()


async def test_initial_subscription_can_prompt_voice_greeting_without_task_events():
    client = Client()

    async def noop(*_):
        pass

    bridge = live.GeminiBridge(context, noop, noop, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        session.incoming.put_nowait(function_calls(tool_call('watch', 'watch_lab_events')))
        await until(lambda: bool(session.tools))
        subscription, = session.tools
        assert subscription.response['events'] == []
        assert subscription.scheduling.value == 'WHEN_IDLE'
        assert 'greet' in subscription.response['instruction'].lower()
    finally:
        await finish(bridge, runner)


def test_voice_context_distinguishes_task_activity_from_controller_progress():
    state = {**context(), 'tasks': [{'task_id': 'task', 'request_id': 'request', 'status': 'observing'}]}
    add_event(state, 'execution_progress', request_id='request', operation='inspect_scene')
    task, = live.compact_snapshot(state)['tasks']
    assert task['status'] == 'observing' and task['controller_state'] is None
    assert 'pre-action scene check' in live.system_prompt(lambda: state)

    add_event(state, 'execution_progress', request_id='request', operation='mock_prepared_sample', phase='mock_dose')
    task, = live.compact_snapshot(state)['tasks']
    assert task['controller_state'] == 'in_progress'

    add_event(state, 'execution_result', request_id='request', receipt={'status': 'completed'})
    task, = live.compact_snapshot(state)['tasks']
    assert task['controller_state'] == 'completed'
    assert not live.compact_snapshot(state)['observations']

    state['notebook'][-1]['data']['task_id'] = 'task'
    state['tasks'][0]['request_id'] = 'observation-revision'
    task, = live.compact_snapshot(state)['tasks']
    assert task['controller_state'] == 'completed'


def test_voice_uses_the_selected_water_fixture_capabilities():
    state = {**context(), 'experiment': {'id': 'two_vessel_water', 'title': 'Two-vessel water pour — simulation'},
             'conditions': [{'id': 'water', 'title': 'Premeasured water'}],
             'capabilities': {'supported_operations': ['mock_prepared_sample'],
                              'action_description': 'pour one premeasured water portion from A into C, return donor to A and return HOME'}}
    prompt = live.system_prompt(lambda: state)
    assert 'water-only' in prompt.lower()
    assert 'Use this specific supported action' in prompt
    assert 'qualitative reference for acid' not in prompt
    assert live.compact_snapshot(state)['capabilities']['action_description'] == state['capabilities']['action_description']


async def test_watch_does_not_speak_pre_action_checkpoint_as_controller_progress():
    state = {**context(), 'tasks': [{'task_id': 'task', 'request_id': 'request', 'status': 'observing'}]}
    client = Client()

    async def noop(*_):
        pass

    bridge = live.GeminiBridge(lambda: state, noop, noop, client_factory=lambda: client)
    runner = asyncio.create_task(bridge.run())
    try:
        await until(lambda: bridge.ready)
        session = client.sessions[0]
        session.incoming.put_nowait(function_calls(tool_call('watch', 'watch_lab_events')))
        await until(lambda: len(session.tools) == 1)
        add_event(state, 'student_confirmed', request_id='request')
        add_event(state, 'task_status', status='executing', request_id='request')
        add_event(state, 'execution_progress', operation='inspect_scene', request_id='request')
        await bridge.state_changed()
        await until(lambda: len(session.tools) == 2)
        assert session.tools[-1].scheduling.value == 'SILENT'

        add_event(state, 'execution_progress', operation='mock_prepared_sample', phase='started', request_id='request')
        await bridge.state_changed()
        await until(lambda: len(session.tools) == 3)
        assert session.tools[-1].scheduling.value == 'WHEN_IDLE'
    finally:
        await finish(bridge, runner)
