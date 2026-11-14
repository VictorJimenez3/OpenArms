"""Synthetic voice client for a running mandarin relay; never drives hardware.

Use the relay's uv environment. Generates speech with say, sends PCM through the
actual WebSocket/VAD/Whisper/AGY path, validates reply WAVs and acknowledges them.
Acknowledgement here is a test stand-in for playback, not evidence of audibility.
"""
import argparse
import asyncio
import io
import json
from pathlib import Path
import sys
import tempfile
import wave

async def run(args):
    sys.path.insert(0, str(args.relay_dir.resolve()))
    from audio import MacSpeech, validate_wav
    from websockets.asyncio.client import connect
    evidence = []
    with tempfile.TemporaryDirectory() as scratch:
        speech = MacSpeech(Path('/unused'), Path('/unused'), Path(scratch), None)
        async def reply(ws):
            messages = []
            while True:
                event = await asyncio.wait_for(ws.recv(), 240)
                if isinstance(event, bytes):
                    validate_wav(event)
                    response = next(x for x in reversed(messages) if x['type'] == 'reply')
                    await ws.send(json.dumps({'type':'played','turn_id':response['turn_id']}))
                    while True:
                        state = json.loads(await asyncio.wait_for(ws.recv(), 10))
                        if state.get('state') == 'listening':
                            break
                    return response
                data = json.loads(event)
                messages.append(data)
                if data['type'] == 'error':
                    raise AssertionError(data)
        async def utter(ws, text):
            wav = await speech.synthesize(text)
            with wave.open(io.BytesIO(wav)) as f:
                pcm = f.readframes(f.getnframes())
            pcm = bytes(6400) + pcm + bytes(32000)
            for offset in range(0, len(pcm), 3200):
                await ws.send(pcm[offset:offset+3200])
                await asyncio.sleep(.003)
            result = await reply(ws)
            evidence.append({'synthetic_input':text, 'reply':result})
            print(json.dumps(evidence[-1]), flush=True)
            return result
        for command, outcome in [('Confirm.', 'result'), ('Cancel.', 'reflection')]:
            async with connect(args.url, max_size=4*1024*1024) as ws:
                await reply(ws)
                preview = await utter(ws, args.command)
                assert preview.get('lab_stage') == 'preview', preview
                assert 'mandarin' in preview['text'].lower(), preview
                result = await utter(ws, command)
                if command.startswith('Confirm'):
                    assert result.get('lab_stage') == 'result', result
                else:
                    assert 'cancel' in result['text'].lower(), result
                    assert 'A' in result['text'], result
                await ws.send(json.dumps({'type':'mute','muted':True}))
                state = json.loads(await ws.recv())
                assert state.get('state') == 'muted', state
                await ws.send(json.dumps({'type':'mute','muted':False}))
                state = json.loads(await ws.recv())
                assert state.get('state') == 'listening', state
                await ws.send(json.dumps({'type':'end'}))
    args.output.write_text(json.dumps({'kind':'synthetic voice over loopback; playback acknowledgement simulated','turns':evidence,'passed':True}, indent=2)+'\n')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--relay-dir', type=Path, required=True)
    p.add_argument('--url', default='ws://127.0.0.1:8765/voice')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--command', default='Move the mandarin from point A to point B.')
    asyncio.run(run(p.parse_args()))
