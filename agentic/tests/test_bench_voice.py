"""Gemini Live voice for the bench panel, with a fake Gemini session (no network, no key)."""
import asyncio
import base64
from types import SimpleNamespace as NS

import pytest

from agentic.openarms_lab.bench_voice import BenchVoice, bench_brief


class FakeBench:
    def __init__(self, real_arm=False, terminal_confirm=False):
        self.real_arm, self.terminal_confirm = real_arm, terminal_confirm
        self.log, self.requests, self.stops, self.question = [], [], 0, None

    def state(self):
        return {'arm': 'real' if self.real_arm else 'stand-in', 'armed': True, 'busy': None, 'log': list(self.log),
                'pending': None, 'question': self.question, 'last_result': None, 'camera': {'text': 'both seen'}}

    async def request(self, text):
        self.requests.append(text)
        self.log.append({'role': 'user', 'text': text})
        await asyncio.sleep(0.6)
        self.log.append({'role': 'assistant', 'text': 'Simulating it first.'})
        await asyncio.sleep(0.6)
        self.log.append({'role': 'assistant', 'text': 'Simulation finished.'})
        return self.state()

    async def stop(self):
        self.stops += 1
        return self.state()

    async def cancel(self):
        return self.state()

    async def look_all(self):
        return self.state()


class FakeSession:
    def __init__(self, responses):
        self.responses, self.sent_tools, self.sent_audio, self.client_content = responses, [], [], []

    async def send_tool_response(self, function_responses):
        self.sent_tools.extend(function_responses)

    async def send_realtime_input(self, audio=None, **_):
        self.sent_audio.append(audio)

    async def send_client_content(self, **kw):
        self.client_content.append(kw)

    async def receive(self):
        for r in self.responses:
            yield r
            await asyncio.sleep(0.05)
        await asyncio.sleep(3)  # the session stays open; the test closes the voice


class FakeClient:
    def __init__(self, session):
        self.session = session
        live = NS(connect=self.connect)
        self.aio = NS(live=live, aclose=self._aclose)

    def connect(self, model, config):
        session = self.session

        class Ctx:
            async def __aenter__(self):
                return session

            async def __aexit__(self, *a):
                return False
        return Ctx()

    async def _aclose(self):
        pass


def heard(text, finished=True):
    return NS(server_content=NS(interrupted=False, input_transcription=NS(text=text, finished=finished), model_turn=None,
                                output_transcription=None, turn_complete=False), tool_call=None)


def tool(name, **args):
    return NS(server_content=None, tool_call=NS(function_calls=[NS(id=f'id-{name}', name=name, args=args)]))


def speech(audio=b'\x01\x00' * 10, text='Okay.'):
    return NS(server_content=NS(interrupted=False, input_transcription=None,
                                model_turn=NS(parts=[NS(inline_data=NS(data=audio))]),
                                output_transcription=NS(text=text), turn_complete=True), tool_call=None)


async def run_voice(bench, responses, seconds=2.0):
    frames, session = [], FakeSession(responses)

    async def emit(f):
        frames.append(f)
    v = BenchVoice(bench, emit, client_factory=lambda: FakeClient(session))
    task = asyncio.create_task(v.run())
    await asyncio.sleep(seconds)
    await v.close()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return frames, session, v


@pytest.mark.asyncio
async def test_spoken_request_goes_to_the_bench_and_gemini_hears_progress_then_the_result():
    bench = FakeBench()
    frames, session, _ = await run_voice(bench, [heard('pour the beaker into the dish'),
                                                 tool('bench_request', text='pour the beaker into the dish'), speech()], 2.5)
    assert bench.requests == ['pour the beaker into the dish']
    updates = [r for r in session.sent_tools if r.name == 'bench_request']
    assert updates[0].will_continue is True and updates[-1].will_continue is False
    assert 'Simulation finished.' in updates[-1].response['result']['bench_said']
    assert {'type': 'transcript', 'role': 'user', 'text': 'pour the beaker into the dish', 'final': True} in frames
    assert any(f['type'] == 'audio' for f in frames) and session.client_content  # greeted, and spoke


@pytest.mark.asyncio
async def test_hearing_stop_stops_the_arm_before_gemini_answers():
    bench = FakeBench(real_arm=True, terminal_confirm=True)
    frames, _, _ = await run_voice(bench, [heard('wait, STOP', finished=False)], 0.5)
    assert bench.stops == 1 and any(f.get('status') == 'stopped' for f in frames)


@pytest.mark.asyncio
async def test_voice_execute_needs_the_students_own_words_and_an_operator_question_on_the_real_arm():
    # The model calling execute without the student saying it runs nothing.
    bench = FakeBench(real_arm=True, terminal_confirm=True)
    _, session, _ = await run_voice(bench, [heard('what happens next'), tool('bench_request', text='execute')], 0.6)
    assert bench.requests == [] and 'Only the student' in session.sent_tools[-1].response['error']
    # Said by the student, with the operator's Yes still to come: it goes through.
    bench = FakeBench(real_arm=True, terminal_confirm=True)
    await run_voice(bench, [heard('go ahead'), tool('bench_request', text='go ahead')], 0.6)
    assert bench.requests == ['go ahead']
    # Page-only confirmation (no operator question after Execute): voice cannot start the real arm.
    bench = FakeBench(real_arm=True, terminal_confirm=False)
    _, session, _ = await run_voice(bench, [heard('execute'), tool('bench_request', text='execute')], 0.6)
    assert bench.requests == [] and 'Press Execute on the screen' in session.sent_tools[-1].response['error']


@pytest.mark.asyncio
async def test_without_a_key_voice_says_so_and_nothing_connects(monkeypatch):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    frames = []

    async def emit(f):
        frames.append(f)
    await BenchVoice(FakeBench(), emit).run()
    assert frames == [{'type': 'status', 'status': 'unavailable', 'message': 'Voice needs GEMINI_API_KEY in agentic/.env. Typing still works.'}]


@pytest.mark.asyncio
async def test_audio_frames_are_checked_and_an_old_backlog_is_dropped():
    v = BenchVoice(FakeBench(), None)
    with pytest.raises(ValueError):
        await v.audio(base64.b64encode(b'\x00' * 7000).decode())
    for _ in range(45):
        await v.audio(base64.b64encode(b'\x00\x00' * 100).decode())
    assert v.incoming.qsize() == 40


def test_what_gemini_is_told_names_the_operator_question_and_whether_execute_is_possible():
    s = {'arm': 'real', 'armed': True, 'busy': 'waiting for the operator', 'log': [{'role': 'assistant', 'text': 'Waiting.'}],
         'question': {'id': 'q1', 'text': 'Arm at HOME, path clear? '},
         'pending': {'summary': 'Pour', 'executable': True, 'sim_block_overridden': True,
                     'preview': {'status': 'blocked', 'blocks': ['The gripper would hit the table.']}}}
    b = bench_brief(s)
    assert b['waiting_for_operator_yes'].startswith('Arm at HOME') and b['can_execute'] is True
    assert b['simulation_problem_is_only_a_warning'] is True and b['bench_said'] == ['Waiting.']


def test_the_voice_socket_is_local_and_says_when_there_is_no_key(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from agentic.openarms_lab.app import create_app
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
    monkeypatch.setenv('OPENARMS_DATA_DIR', str(tmp_path))
    app = create_app(bench=FakeBench())
    with TestClient(app) as client, client.websocket_connect('/api/bench/voice') as ws:
        assert ws.receive_json()['status'] == 'unavailable'
