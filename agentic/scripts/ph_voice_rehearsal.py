"""Real Gemini speech -> real Codex expert -> simulated observed outcome.

Generated student speech and acknowledged PCM playback are test inputs. --audible
plays returned audio on the Mac; neither mode verifies a physical iPhone.
"""
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

async def run(base, output, audible=False):
    output.mkdir(parents=True, exist_ok=False)
    async with httpx.AsyncClient(base_url=base, timeout=20) as http:
        response = await http.post('/api/sessions')
        response.raise_for_status()
        state = response.json()
        sid, token = state['session_id'], state.pop('access_token')
        url = base.replace('http://', 'ws://').replace('https://', 'wss://') + f'/api/sessions/{sid}/live'
        events, replies, interrupted, transcripts = [], {}, set(), []
        playback = asyncio.Queue()
        ready = asyncio.Event()
        playback_count = 0
        async with websockets.connect(url, max_size=16*1024*1024) as ws:
            async def reader():
                nonlocal state
                async for raw in ws:
                    event = json.loads(raw)
                    kind = event['type']
                    if kind == 'state': state = event['state']
                    if kind == 'hello': ready.set()
                    if kind == 'audio':
                        replies.setdefault(event['reply_id'], bytearray()).extend(base64.b64decode(event['data']))
                    else:
                        events.append({'at': time.time(), **event})
                    if kind == 'interrupted': interrupted.add(event.get('reply_id'))
                    if kind == 'reply_end': await playback.put(event['reply_id'])
                    if kind == 'transcript' and event.get('final'):
                        transcripts.append({'role': event['role'], 'text': event['text']})
                        print(json.dumps(transcripts[-1]), flush=True)
            async def player():
                nonlocal playback_count
                while True:
                    rid = await playback.get()
                    try:
                        if rid in interrupted: continue
                        data = replies.pop(rid, b'')
                        path = output/(rid+'.wav')
                        with wave.open(str(path), 'wb') as wav:
                            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000); wav.writeframes(data)
                        if audible and data:
                            await asyncio.to_thread(subprocess.run, ['afplay', str(path)], check=True)
                        if rid not in interrupted:
                            await ws.send(json.dumps({'type':'played', 'reply_id':rid}))
                            playback_count += 1
                    finally:
                        playback.task_done()
            async def heartbeat():
                while True:
                    await asyncio.sleep(5)
                    await ws.send(json.dumps({'type':'ping','seq':int(time.monotonic())}))
            tasks = [asyncio.create_task(reader()), asyncio.create_task(player()), asyncio.create_task(heartbeat())]
            async def wait_for(predicate, timeout=240):
                async with asyncio.timeout(timeout):
                    while not predicate():
                        for task in tasks:
                            if task.done(): await task
                        failures = [e for e in events if e['type']=='status' and e.get('status')=='unavailable']
                        if failures: raise RuntimeError(failures[-1].get('message'))
                        await asyncio.sleep(.1)
            async def speak(text, index):
                await playback.join()
                aiff, pcm = output/f'input-{index}.aiff', output/f'input-{index}.pcm'
                await asyncio.to_thread(subprocess.run, ['say','-r','165','-o',str(aiff),text],check=True)
                await asyncio.to_thread(subprocess.run, ['ffmpeg','-v','error','-y','-i',str(aiff),'-ar','16000','-ac','1','-f','s16le',str(pcm)],check=True)
                data = pcm.read_bytes()+bytes(32000)
                for pos in range(0,len(data),3200):
                    await ws.send(json.dumps({'type':'audio','data':base64.b64encode(data[pos:pos+3200]).decode(),'epoch':state.get('generation',0)}))
                    await asyncio.sleep(.1)
                await ws.send(json.dumps({'type':'audio_end'}))
            try:
                await ws.send(json.dumps({'type':'hello','protocol_version':1,'connection_id':str(uuid.uuid4()),'access_token':token}))
                await ready.wait()
                await ws.send(json.dumps({'type':'start_voice'}))
                await wait_for(lambda: playback_count>0, 50)
                await speak('Please test the prepared vinegar sample and check the cabbage indicator color.', 0)
                await wait_for(lambda:bool(state.get('tasks')))
                start_phase = state['tasks'][-1]['status']
                before = len(transcripts)
                if start_phase in ('queued','running'):
                    await speak('What are you checking while the expert works?',1)
                    await wait_for(lambda:any(t['role']=='assistant' for t in transcripts[before:]),50)
                await wait_for(lambda:bool(state.get('pending')) or state['tasks'][-1]['status'] in ('failed','needs_clarification'))
                assert state.get('pending'), state['tasks'][-1].get('summary')
                # Do not fabricate a text presentation: this verifies exact audio
                # preview plus the client's completed-playback acknowledgment.
                await wait_for(lambda:bool((state.get('pending') or {}).get('presented')),90)
                assert state['pending']['presentation']['channel']=='audio'
                await speak('Confirm.',2)
                await wait_for(lambda:state['tasks'][-1]['status'] in ('completed','failed','needs_clarification','cancelled'))
                assert state['tasks'][-1]['status']=='completed', state['tasks'][-1].get('summary')
                await wait_for(lambda:any(t['role']=='assistant' and 'simulation' in t['text'].lower() and 'pink' in t['text'].lower() for t in transcripts),60)
                assert state['observations'][-1]['provenance']=='SYNTHETIC'
                await playback.join()
                result={'passed':True,'session_id':sid,'evidence_type':'generated-speech real-provider integration',
                        'expert_provider':'openai_codex_cli','expert_model':'gpt-6.1-sol','expert_effort':'medium',
                        'voice_model':'gemini-3.8-live','followup_during_expert':start_phase in ('queued','running'),
                        'audio_proposal_presented':True,'completed_trials':len(state['observations']),
                        'mac_output_played':audible,'physical_iphone_verified':False,'transcripts':transcripts}
                (output/'result.json').write_text(json.dumps(result,indent=2))
                print(json.dumps(result,indent=2),flush=True)
            finally:
                (output/'events.json').write_text(json.dumps(events,indent=2))
                (output/'final-state.json').write_text(json.dumps(state,indent=2))
                try: await ws.send(json.dumps({'type':'close'}))
                except Exception: pass
                for task in tasks: task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--url',default='http://127.0.0.1:8010')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--audible',action='store_true')
    args=parser.parse_args()
    asyncio.run(run(args.url.rstrip('/'),args.output,args.audible))
