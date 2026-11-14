"""Gemini Live protocol checks using in-memory transports and no credentials."""
import asyncio
import base64
from types import SimpleNamespace as NS

import pytest
from starlette.websockets import WebSocketDisconnect

from agentic.openarms_lab import live


def response(**fields):
    return NS(**dict(dict(server_content=None, tool_call=None, tool_call_cancellation=None,
                         session_resumption_update=None, go_away=None, usage_metadata=None), **fields))


def content(**fields):
    return NS(**dict(dict(interrupted=False, input_transcription=None, output_transcription=None,
                         model_turn=None, turn_complete=False), **fields))


class Browser:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []
        self.closed = False

    async def receive_json(self):
        message = await self.incoming.get()
        if isinstance(message, Exception):
            raise message
        return message

    async def send_json(self, message):
        self.sent.append(message)

    async def close(self):
        self.closed = True


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
    return {'experiment': {'id': 'transfer'}, 'requests': [], 'observations': [], 'messages': []}


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(.001)


def assert_no_live_tasks():
    assert not [task for task in asyncio.all_tasks() if task is not asyncio.current_task()
                and 'serve_live.<locals>' in task.get_coro().__qualname__]


@pytest.mark.asyncio
async def test_missing_credentials_keeps_fallback_and_disconnect_cleanup(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setattr(live.genai, 'Client', lambda **_: pytest.fail('credential-free path built a client'))
    browser = Browser()
    calls = []

    async def tool(name, args):
        pytest.fail(f'unexpected tool {name}')

    async def stop():
        calls.append('stop')

    await live.serve_live(browser, context, tool, stop)
    assert any(message['type'] == 'error' and 'Text controls' in message['message'] for message in browser.sent)
    assert calls == ['stop']
    assert browser.closed
    assert_no_live_tasks()


@pytest.mark.asyncio
async def test_pcm_transcripts_usage_text_and_stop_protocol_without_provider():
    browser, client = Browser(), Client()
    calls = []

    async def tool(name, args):
        calls.append((name, args))
        return {}

    async def stop():
        calls.append(('disconnect', {}))

    task = asyncio.create_task(live.serve_live(browser, context, tool, stop, client_factory=lambda: client))
    try:
        await until(lambda: bool(client.sessions))
        session = client.sessions[0]
        pcm = b'\x00\x01\x02\x03'
        browser.incoming.put_nowait({'type': 'audio', 'data': base64.b64encode(pcm).decode()})
        browser.incoming.put_nowait({'type': 'audio', 'data': base64.b64encode(b'x').decode()})
        browser.incoming.put_nowait({'type': 'audio_end'})
        browser.incoming.put_nowait({'type': 'text', 'text': 'What do I observe?'})
        browser.incoming.put_nowait({'type': 'text', 'text': 'STOP'})
        session.incoming.put_nowait(response(server_content=content(
            input_transcription=NS(text='my prediction'), output_transcription=NS(text='check the evidence'),
            model_turn=NS(parts=[NS(inline_data=NS(data=pcm))]), turn_complete=True),
            usage_metadata=NS(model_dump=lambda **_: {'total_token_count': 17})))
        await until(lambda: any(name == '_record_usage' for name, _ in calls)
                    and any(name == 'stop_lab' for name, _ in calls))
        assert session.realtime[0]['audio'].data == pcm
        assert session.realtime[0]['audio'].mime_type == 'audio/pcm;rate=16000'
        assert session.realtime[1] == {'audio_stream_end': True}
        assert len(session.realtime) == 2  # odd-length PCM was rejected
        assert len(session.turns) == 1  # STOP never reaches model reasoning
        assert session.turns[0]['turns'].parts[0].text == 'What do I observe?'
        assert {'type': 'audio', 'data': base64.b64encode(pcm).decode()} in browser.sent
        assert {'type': 'transcript', 'role': 'user', 'text': 'my prediction'} in browser.sent
        assert {'type': 'transcript', 'role': 'assistant', 'text': 'check the evidence'} in browser.sent
        assert ('_record_usage', {'usage': {'total_token_count': 17}}) in calls
        assert any(message['type'] == 'error' and 'PCM' in message['message'] for message in browser.sent)
        browser.incoming.put_nowait(WebSocketDisconnect())
        await asyncio.wait_for(task, timeout=2)
    finally:
        if not task.done():
            browser.incoming.put_nowait({'type': 'close'})
            await asyncio.wait_for(task, timeout=2)
    assert ('disconnect', {}) in calls
    assert browser.closed and client.closed and session.exited
    assert_no_live_tasks()


@pytest.mark.asyncio
async def test_tool_ids_duplicate_prevention_and_cancelled_proposal_cleanup():
    browser, client = Browser(), Client()
    calls, pending = [], {}

    async def tool(name, args):
        calls.append((name, args))
        if name == 'request_action':
            pending['request_id'] = 'proposal-1'
            return {'pending': dict(pending)}
        if name == '_cancel_tool_request':
            assert args['request_id'] == 'proposal-1'
            pending.clear()
        return {}

    async def stop():
        pass

    task = asyncio.create_task(live.serve_live(browser, context, tool, stop, client_factory=lambda: client))
    try:
        await until(lambda: bool(client.sessions))
        session = client.sessions[0]
        call = NS(id='provider-call-1', name='request_action', args={'text': 'move mandarin A to B'})
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[call, call])))
        await until(lambda: len(session.tools) == 1)
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[call])))
        await until(lambda: len(session.tools) == 2)
        assert sum(name == 'request_action' for name, _ in calls) == 1
        assert [result.id for result in session.tools] == ['provider-call-1'] * 2
        assert all(result.name == 'request_action' for result in session.tools)
        assert all(result.response['result']['pending']['request_id'] == 'proposal-1' for result in session.tools)
        session.incoming.put_nowait(response(tool_call_cancellation=NS(ids=['provider-call-1'])))
        await until(lambda: not pending)
        assert any(name == '_cancel_tool_request' for name, _ in calls)
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[call])))
        browser.incoming.put_nowait({'type': 'close'})
        await asyncio.wait_for(task, timeout=2)
        assert len(session.tools) == 2
    finally:
        if not task.done():
            browser.incoming.put_nowait({'type': 'close'})
            await asyncio.wait_for(task, timeout=2)
    assert_no_live_tasks()


@pytest.mark.asyncio
async def test_cancelled_inflight_tool_clears_partially_published_proposal():
    browser, client = Browser(), Client()
    published, cancelled = asyncio.Event(), asyncio.Event()
    pending, cleanup = {}, []

    async def tool(name, args):
        if name == 'request_action':
            pending.update(request_id='partial-proposal', client_request_id='live:' + args['_tool_call_id'])
            published.set()
            try:
                await asyncio.Event().wait()  # publication yielded before callback returned
            finally:
                cancelled.set()
        elif name == '_cancel_tool_request':
            cleanup.append(args)
            if pending.get('client_request_id') == 'live:' + args['tool_call_id']:
                pending.clear()
        return {}

    async def stop():
        pass

    task = asyncio.create_task(live.serve_live(browser, context, tool, stop, client_factory=lambda: client))
    try:
        await until(lambda: bool(client.sessions))
        session = client.sessions[0]
        session.incoming.put_nowait(response(tool_call=NS(function_calls=[
            NS(id='partial-call', name='request_action', args={'text': 'move mandarin A to B'})])))
        await asyncio.wait_for(published.wait(), timeout=2)
        session.incoming.put_nowait(response(tool_call_cancellation=NS(ids=['partial-call'])))
        await until(lambda: not pending and cancelled.is_set())
        assert cleanup == [{'tool_call_id': 'partial-call', 'request_id': None}]
        assert session.tools == []
    finally:
        browser.incoming.put_nowait({'type': 'close'})
        await asyncio.wait_for(task, timeout=2)
    assert_no_live_tasks()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [ConnectionError, RuntimeError])
async def test_upstream_reconnects_are_bounded_resume_and_leave_no_tasks(failure):
    browser = Browser()
    sessions = []

    def make_session():
        if not sessions:
            session = Session(response(session_resumption_update=NS(resumable=True, new_handle='resume-1')))
            session.incoming.put_nowait(response(go_away=NS()))
        else:
            session = Session(failure('stand-in upstream unavailable'))
        sessions.append(session)
        return session

    client = Client(make_session)
    stops = []

    async def tool(name, args):
        return {}

    async def stop():
        stops.append('stop')

    await asyncio.wait_for(live.serve_live(browser, context, tool, stop,
                                         client_factory=lambda: client, reconnect_delay=0), timeout=2)
    assert len(client.sessions) == 4
    assert client.configs[0]['config'].session_resumption.handle is None
    assert all(config['config'].session_resumption.handle == 'resume-1' for config in client.configs[1:])
    assert len(stops) >= 4
    assert all(session.exited for session in sessions)
    assert client.closed and browser.closed
    assert any(message['type'] == 'error' and failure.__name__ in message['message'] for message in browser.sent)
    assert_no_live_tasks()
