"""Run a generated-speech conversation through the real local voice gateway.

Use a new mock or MuJoCo session. The default run leaves all proposals unapproved.
The output records audio and correlated events without including credentials.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import time
import uuid
import wave
from pathlib import Path

import httpx
import websockets

OPENING = 'Please test the prepared vinegar sample and check the indicator color.'
PROGRESS = 'What are you checking right now?'
SCIENCE = 'What is the water control for?'
CORRECTION = 'Actually, use water instead.'
STOP = 'Emergency stop.'
AFTER_STOP = 'What happened to the test?'
CONFIRM = 'Confirm.'
OUTCOME = 'What did the observer actually see?'
WATER_OPENING = 'Will you pour one premeasured portion of water from cup A into cup C?'
CAPABILITIES = 'What can you do with the two cups?'
REPEAT = 'Can you repeat the plan?'
TURNS = (OPENING, PROGRESS, SCIENCE, CORRECTION, STOP, AFTER_STOP, CONFIRM, OUTCOME)
WATER_TURNS = (WATER_OPENING, PROGRESS, CAPABILITIES, REPEAT, CONFIRM, OUTCOME, STOP, AFTER_STOP)
TERMINAL = {'completed', 'cancelled', 'failed', 'needs_clarification'}


def write_wave(path, data):
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(data)


def generate_student_audio(output, turns):
    samples = {}
    for index, line in enumerate(turns):
        aiff = output / f'input-{index}.aiff'
        subprocess.run(['say', '-r', '185', '-o', str(aiff), line], check=True)
        samples[line] = subprocess.check_output([
            'ffmpeg', '-loglevel', 'error', '-i', str(aiff), '-ar', '16000',
            '-ac', '1', '-f', 's16le', 'pipe:1',
        ]) + bytes(25600)
        aiff.unlink()
    return samples


class Rehearsal:
    def __init__(self, websocket, output, state, samples, audible):
        self.ws = websocket
        self.output = output
        self.state = state
        self.samples = samples
        self.audible = audible
        self.started = time.monotonic()
        self.events = []
        self.turns = []
        self.audio = {}
        self.playback = {}
        self.played = []
        self.player = None
        self.workers = []

    def elapsed(self):
        return round((time.monotonic() - self.started) * 1000)

    async def send(self, kind, **fields):
        await self.ws.send(json.dumps({'type': kind, **fields}))

    async def receive(self):
        async for raw in self.ws:
            frame = json.loads(raw)
            kind = frame['type']
            if kind == 'state':
                self.state = frame['state']
                continue
            if kind == 'audio':
                self.audio.setdefault(frame['reply_id'], bytearray()).extend(base64.b64decode(frame['data']))
                continue
            self.events.append({'ms': self.elapsed(), **frame})
            if kind == 'reply_end':
                rid = frame['reply_id']
                data = self.audio.pop(rid, b'')
                if data:
                    self.playback[rid] = asyncio.create_task(self.play(rid, data))
            if kind == 'interrupted':
                rid = frame.get('reply_id')
                for key in tuple(self.audio):
                    if rid in (None, key):
                        del self.audio[key]
                for key, task in self.playback.items():
                    if rid in (None, key):
                        task.cancel()

    async def play(self, rid, data):
        path = self.output / f'reply-{len(list(self.output.glob("reply-*.wav"))):02d}.wav'
        write_wave(path, data)
        if self.audible:
            player = await asyncio.create_subprocess_exec('afplay', str(path))
            try:
                await player.wait()
            finally:
                if player.returncode is None:
                    player.terminate()
                    await player.wait()
        else:
            await asyncio.sleep(len(data) / 48000)
        await self.send('played', reply_id=rid)
        self.played.append(rid)

    async def heartbeat(self):
        while True:
            await asyncio.sleep(4)
            await self.send('ping', seq=self.elapsed())

    async def wait(self, predicate, label, timeout=55):
        deadline = time.monotonic() + timeout
        while not predicate():
            for event in reversed(self.events):
                if event.get('status') == 'unavailable':
                    raise RuntimeError(f"Voice unavailable during {label} (code {event.get('code', 'unspecified')})")
            for worker in self.workers:
                if worker.done():
                    worker.result()
                    raise RuntimeError(f'Gateway connection ended during {label}.')
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Timed out waiting for {label}.')
            await asyncio.sleep(.035)

    def transcripts(self, role, since=0):
        return [event for event in self.events[since:] if event['type'] == 'transcript'
                and event.get('role') == role and event.get('final')]

    async def speak(self, line):
        since = len(self.events)
        pending = self.state.get('pending') or {}
        task = self.state['tasks'][-1] if self.state.get('tasks') else {}
        turn = {'input': line, 'input_start_ms': self.elapsed(), 'task_count_before': len(self.state['tasks']),
                'status_at_input': task.get('status'), 'proposal_at_input': pending.get('proposal_version')}
        self.turns.append(turn)
        data = self.samples[line]
        for position in range(0, len(data), 3200):
            await self.send('audio', data=base64.b64encode(data[position:position + 3200]).decode(),
                            epoch=self.state['generation'])
            await asyncio.sleep(.1)
        await self.send('audio_end')
        await self.wait(lambda: self.transcripts('user', since), f'transcription for {line!r}', timeout=25)
        student = self.transcripts('user', since)[0]
        turn.update(transcript=student['text'], user_final_ms=student['ms'], turn_id=student['turn_id'])
        return since, turn

    async def response(self, marker, *, check=None):
        since, turn = marker

        def matching():
            return [event for event in self.transcripts('assistant', since)
                    if check is None or check(event['text'].casefold())]

        await self.wait(matching, f'an answer to {turn["input"]!r}')
        reply = matching()[0]
        turn['reply'] = reply['text']
        turn['reply_final_ms'] = reply['ms']
        turn['first_audio_start_ms'] = next((event['ms'] for event in self.events[since:]
                                             if event.get('reply_id') == reply['turn_id']
                                             and event['type'] == 'reply_start'), None)
        turn['task_count_after'] = len(self.state['tasks'])
        await self.wait(lambda: reply['turn_id'] in self.played, 'reply playback acknowledgment')

    async def phase(self, label, *, timeout=150):
        def done():
            return self.state.get('pending') or (self.state['tasks'] and self.state['tasks'][-1]['status'] in TERMINAL)
        await self.wait(done, label, timeout=timeout)
        pending = self.state.get('pending')
        if pending is None:
            task = self.state['tasks'][-1]
            raise RuntimeError(f'{label}: {task["status"]} — {task.get("summary")}')
        return pending

    async def run(self, token, confirm_outcome, water_only):
        await self.send('hello', protocol_version=1, connection_id=str(uuid.uuid4()), access_token=token)
        self.workers = [asyncio.create_task(self.receive()), asyncio.create_task(self.heartbeat())]
        await self.wait(lambda: any(e['type'] == 'hello' for e in self.events), 'connection')
        await self.send('start_voice')
        await self.wait(lambda: self.played, 'spoken greeting')
        await self.speak(WATER_OPENING if water_only else OPENING)
        await self.wait(lambda: self.state['tasks'], 'first background task')
        first_task = self.state['tasks'][-1]['task_id']
        progress = await self.speak(PROGRESS)
        await self.response(progress, check=lambda text: any(word in text for word in (
            'check', 'plan', 'scene', 'sample', 'ready', 'confirm', 'prepar', 'expert')))
        assert len(self.state['tasks']) == 1 and self.state['tasks'][0]['task_id'] == first_task, 'Follow-up changed the task.'
        first = await self.phase('first proposal')
        await self.wait(lambda: (self.state.get('pending') or {}).get('presented'), 'exact first spoken preview', timeout=75)
        if water_only:
            await self.response(await self.speak(CAPABILITIES),
                                check=lambda text: 'pour' in text and ('water' in text or 'portion' in text))
            assert self.state['pending']['request_id'] == first['request_id'], 'Question replaced the water proposal.'
            exact = lambda text: ' '.join(''.join(c if c.isalnum() else ' ' for c in text.casefold()).split())
            await self.response(await self.speak(REPEAT), check=lambda text: exact(first['summary']) in exact(text))
            assert self.state['pending']['request_id'] == first['request_id'], 'Repeating the plan replaced the proposal.'
            assert len(self.state['tasks']) == 1
        else:
            await self.response(await self.speak(SCIENCE),
                                check=lambda text: any(word in text for word in ('compar', 'neutral', 'baseline', 'reference')))
            assert self.state['pending']['request_id'] == first['request_id'], 'Science discussion changed the proposal.'
            assert self.state['trial']['condition_id'] == first['condition_id'], 'Science discussion changed the sample.'
            await self.speak(CORRECTION)
            await self.wait(lambda: len(self.state['tasks']) == 2, 'corrected background task')
            second = await self.phase('corrected proposal')
            assert second['condition_id'] == 'water' and second['proposal_version'] > first['proposal_version']
            original = next(r for r in self.state['requests'] if r['request_id'] == first['request_id'])
            assert original['status'] == 'cancelled' and not original['student_confirmed']
            await self.wait(lambda: (self.state.get('pending') or {}).get('presented'), 'exact corrected spoken preview', timeout=75)
        assert self.state['pending']['presentation']['channel'] == 'audio'
        if confirm_outcome:
            await self.speak(CONFIRM)
            await self.wait(lambda: self.state['tasks'][-1]['status'] in TERMINAL, 'observed execution', timeout=150)
            assert self.state['tasks'][-1]['status'] == 'completed'
            observations = self.state['tasks'][-1]['observations']
            assert observations and observations[-1]['provenance'] in ('SIMULATED', 'SYNTHETIC', 'UNKNOWN')
            if water_only:
                observed = observations[-1]
                assert observed['provenance'] == 'SIMULATED' and observed['status'] == 'observed', observed.get('text')
                assert observed['checks'] and all(observed['checks'].values()), observed.get('text')
                await self.response(await self.speak(OUTCOME),
                                    check=lambda text: 'simulation' in text and ('receiver' in text or 'water' in text))
            else:
                await self.response(await self.speak(OUTCOME),
                                    check=lambda text: 'simulation' in text or 'unknown' in text or 'couldn' in text)
        generation = self.state['generation']
        _, stop_turn = await self.speak(STOP)
        await self.wait(lambda: self.state['generation'] > generation,
                        f'spoken STOP after ASR {stop_turn["transcript"]!r}', timeout=15)
        assert self.state['pending'] is None
        if confirm_outcome:
            await self.response(await self.speak(AFTER_STOP),
                                check=lambda text: any(word in text for word in ('idle', 'already', 'finish', 'completed',
                                                                                'nothing was', 'no action was')))
        else:
            await self.response(await self.speak(AFTER_STOP), check=lambda text: 'cancel' in text or 'stop' in text)
        assert len(self.state['tasks']) == (1 if water_only else 2) and self.state['pending'] is None
        assert sum(bool(r['student_confirmed']) for r in self.state['requests']) == int(confirm_outcome)

    async def close(self):
        tasks = [*self.workers, *self.playback.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run(base, output, audible, confirm_outcome, water_only):
    output.mkdir(parents=True, exist_ok=False)
    confirm_outcome |= water_only
    report = {'passed': False, 'input': 'generated student audio', 'mac_output_played': audible,
              'physical_iphone_verified': False, 'confirmed_outcome': confirm_outcome, 'water_only': water_only}
    try:
        samples = await asyncio.to_thread(generate_student_audio, output, WATER_TURNS if water_only else TURNS)
        async with httpx.AsyncClient(base_url=base, timeout=40) as http:
            response = await http.get('/api/health')
            response.raise_for_status()
            health = response.json()
            assert health['backend'] in ('mock', 'mujoco') and health['live_configured'], health['backend']
            report['voice_model'] = health['live_model']
            report['execution_backend'] = health['backend']
            response = await http.post('/api/sessions')
            response.raise_for_status()
            state = response.json()
            token = state.pop('access_token')
            assert (state['experiment']['id'] == 'two_vessel_water') == water_only, state['experiment']['id']
            report['experiment'] = state['experiment']['id']
            report['session_id'] = state['session_id']
            url = base.replace('http', 'ws', 1) + f'/api/sessions/{state["session_id"]}/live'
        async with websockets.connect(url, max_size=16 * 1024 * 1024) as ws:
            rehearsal = Rehearsal(ws, output, state, samples, audible)
            try:
                await rehearsal.run(token, confirm_outcome, water_only)
                report['passed'] = True
            finally:
                report['turns'] = rehearsal.turns
                report['tasks'] = rehearsal.state.get('tasks', [])
                report['observations'] = rehearsal.state.get('observations', [])
                report['requests'] = rehearsal.state.get('requests', [])
                report['task_events'] = [event for event in rehearsal.state.get('notebook', [])
                                         if event['kind'] in ('request_proposed', 'request_cancelled', 'proposal_presented',
                                                              'student_confirmed', 'stop_requested', 'task_cancelled',
                                                              'task_status', 'execution_progress', 'execution_result')]
                (output / 'events.json').write_text(json.dumps(rehearsal.events, indent=2))
                await rehearsal.close()
    except Exception as exc:
        report['failure'] = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        for task in report.get('tasks', []):
            # Keep requested and actual provider identity without local images/tool payloads.
            task.pop('images', None)
            task.pop('evidence', None)
            task.pop('feedback', None)
            for expert_run in task.get('expert_runs', []):
                expert_run.pop('tool_receipts', None)
        (output / 'result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps({'passed': report['passed'], 'evidence': str(output / 'result.json'),
                          'failure': report.get('failure')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8879')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--audible', action='store_true')
    parser.add_argument('--confirm-outcome', action='store_true', help='Confirm the corrected simulation proposal and discuss its observation.')
    parser.add_argument('--water-only', action='store_true', help='Rehearse the two-vessel water simulation, including consent and observation.')
    args = parser.parse_args()
    asyncio.run(run(args.url.rstrip('/'), args.output, args.audible, args.confirm_outcome, args.water_only))
