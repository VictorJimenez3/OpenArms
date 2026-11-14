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
        assert all(r.id == 'original' and r.response['result']['tasks'] == state['tasks']
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
        if name != 'request_action':
            return
        if args['_tool_call_id'] == 'cancel-me':
            entered.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()
        else:
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
            tool_call('leave-alone', 'request_action', text=text)])))
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
            session.incoming.put_nowait(response(server_content=content(
                output_transcription=NS(text=text), turn_complete=True)))
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
