"""Live Gemini voice check: speak synthesized student audio to the running app and follow the whole loop.

Usage: voice_check.py [base_url] ["request sentence"] ["confirmation sentence"]
Audio comes from macOS `say` at 16 kHz mono PCM, streamed in real time like a microphone. Each spoken
reply is acknowledged as played when Gemini finishes it (the browser does this after playback). Consent is
whatever Gemini and the app accept from the spoken confirmation; nothing is confirmed by this script.
"""
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8011'
REQUEST = sys.argv[2] if len(sys.argv) > 2 else 'Please pour the beaker at A into the container at C, then put it back and go home.'
CONFIRM = sys.argv[3] if len(sys.argv) > 3 else 'Yes, I confirm. Go ahead.'
FRAME = 3200  # 100 ms of 16 kHz 16-bit mono


def speech(text):
    with tempfile.TemporaryDirectory() as folder:
        wav = Path(folder) / 'speech.wav'
        subprocess.run(['say', '-o', str(wav), '--file-format=WAVE', '--data-format=LEI16@16000', text], check=True)
        data = wav.read_bytes()
    return data[data.index(b'data') + 8:]


def post(path, body=None):
    request = urllib.request.Request(BASE + path, data=json.dumps(body or {}).encode(),
                                     headers={'Content-Type': 'application/json'}, method='POST')
    return json.load(urllib.request.urlopen(request, timeout=30))


async def main():
    session = post('/api/sessions')
    sid, token = session['session_id'], session['access_token']
    log, marks, started = [], {}, time.monotonic()
    state = {'pending': None, 'task': None, 'generation': 0, 'listening': asyncio.Event(), 'done': asyncio.Event()}

    def mark(name):
        marks.setdefault(name, round(time.monotonic() - started, 2))

    async with websockets.connect(BASE.replace('http', 'ws') + f'/api/sessions/{sid}/live', max_size=2**24) as ws:
        await ws.send(json.dumps({'type': 'hello', 'protocol_version': 1, 'access_token': token}))

        async def reader():
            async for raw in ws:
                msg = json.loads(raw)
                kind = msg.get('type')
                if kind == 'hello':
                    state['generation'] = msg.get('generation', 0)
                elif kind == 'status':
                    log.append(('status', msg.get('status'), msg.get('message')))
                    if msg.get('status') == 'listening':
                        state['listening'].set()
                elif kind == 'transcript' and msg.get('final'):
                    log.append((msg['role'], msg['text']))
                    print(f"[{time.monotonic()-started:6.1f}s] {msg['role']}: {msg['text']}", flush=True)
                elif kind == 'reply_end':
                    await asyncio.sleep(0.2)
                    await ws.send(json.dumps({'type': 'played', 'reply_id': msg['reply_id']}))
                elif kind == 'error':
                    log.append(('error', msg.get('code'), msg.get('message')))
                    print(f"[{time.monotonic()-started:6.1f}s] error: {msg.get('message')}", flush=True)
                snapshot = msg.get('state') if kind == 'state' else (msg if 'tasks' in msg else None)
                if snapshot:
                    state['generation'] = snapshot.get('generation', state['generation'])
                    pending = snapshot.get('pending')
                    if pending:
                        mark('proposal')
                        if pending.get('presented'):
                            mark('presented_by_voice')
                    state['pending'] = pending
                    tasks = snapshot.get('tasks') or []
                    if tasks:
                        task = tasks[-1]
                        state['task'] = task
                        if task['status'] in ('executing', 'observing') and (pending or {}).get('student_confirmed', True) and \
                                any(r.get('student_confirmed') for r in snapshot.get('requests') or []):
                            mark('confirmed_and_running')
                        if task['status'] in ('completed', 'failed', 'cancelled', 'needs_clarification'):
                            mark('task_' + task['status'])

        async def pinger():
            seq = 0
            while True:
                seq += 1
                await ws.send(json.dumps({'type': 'ping', 'seq': seq}))
                await asyncio.sleep(2)

        async def say(text):
            audio = speech(text)
            silence = bytes(FRAME)
            for chunk in [audio[i:i + FRAME] for i in range(0, len(audio), FRAME)] + [silence] * 15:
                chunk += bytes(FRAME - len(chunk)) if len(chunk) < FRAME else b''
                await ws.send(json.dumps({'type': 'audio', 'data': base64.b64encode(chunk).decode(),
                                          'epoch': state['generation']}))
                await asyncio.sleep(0.1)

        tasks = [asyncio.create_task(reader()), asyncio.create_task(pinger())]
        await ws.send(json.dumps({'type': 'start_voice'}))
        await asyncio.wait_for(state['listening'].wait(), 30)
        mark('voice_ready')
        await asyncio.sleep(2)
        print(f'student says: {REQUEST}', flush=True)
        await say(REQUEST)
        mark('request_spoken')
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline and not (state['pending'] or {}).get('presented'):
            if state['task'] and state['task']['status'] in ('failed', 'needs_clarification'):
                break
            await asyncio.sleep(0.25)
        if (state['pending'] or {}).get('presented'):
            await asyncio.sleep(1)
            print(f'student says: {CONFIRM}', flush=True)
            await say(CONFIRM)
            mark('confirmation_spoken')
            if os.environ.get('VOICE_STOP_DURING_MOTION'):
                while 'confirmed_and_running' not in marks and time.monotonic() < deadline + 120:
                    await asyncio.sleep(0.1)
                await asyncio.sleep(1.5)
                print('student says: Stop!', flush=True)
                await say('Stop!')
                mark('stop_spoken')
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline and not any(k.startswith('task_') for k in marks):
                await asyncio.sleep(0.25)
            await asyncio.sleep(12)  # let Gemini speak the result
        for task in tasks:
            task.cancel()
    task = state['task'] or {}
    observation = (task.get('observations') or [{}])[-1]
    print(json.dumps({'marks_s': marks, 'task_status': task.get('status'), 'route': task.get('route'),
                      'simulation': {k: (task.get('execution') or [{}])[-1].get('simulation', {}).get(k)
                                     for k in ('status', 'dose_count', 'home_reached')},
                      'executions': len(task.get('execution') or []), 'observation': observation.get('status'),
                      'observed_text': observation.get('text'),
                      'assistant_lines': [t for r, *t in log if r == 'assistant'],
                      'errors': [e for e in log if e[0] == 'error']}, indent=2))


asyncio.run(main())
