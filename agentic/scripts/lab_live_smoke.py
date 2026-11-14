"""Real, non-motion Gemini Live proxy rehearsal. Run against the MOCK app only."""
import argparse,asyncio,base64,json,time
from pathlib import Path
import httpx,websockets

async def run(base_url,out):
    async with httpx.AsyncClient(base_url=base_url,timeout=45) as http:
        health=(await http.get('/api/health')).json()
        assert health['backend']=='mock','This rehearsal is mock-only.'
        s=(await http.post('/api/sessions')).json();sid=s['session_id']
        await http.post(f'/api/sessions/{sid}/prediction',json={'text':'Sample A should float because it is less dense than water.'})
        evidence={'session_id':sid,'model':health['live_model'],'messages':[],'audio_bytes':0,'started':time.time()}
        url=base_url.replace('http://','ws://').replace('https://','wss://')
        async with websockets.connect(f'{url}/api/sessions/{sid}/live',origin=base_url) as ws:
            async def receive():
                sent=False
                while True:
                    msg=json.loads(await ws.recv())
                    if msg['type']=='audio':evidence['audio_bytes']+=len(base64.b64decode(msg['data']))
                    else:evidence['messages'].append(msg)
                    if msg.get('status')=='connected' and not sent:
                        await ws.send(json.dumps({'type':'text','text':'Please call request_action with exactly this text: test sample at A in B. My prediction is already recorded. Ask me to review the proposal; never execute.'}));sent=True
                    if msg.get('status')=='listening':
                        snap=(await http.get(f'/api/sessions/{sid}')).json()
                        if snap['pending'] and evidence['audio_bytes']:
                            evidence['proposal']=snap['pending']
                            assert not any(r['status']=='executing' for r in snap['requests'])
                            await ws.send(json.dumps({'type':'close'}));return
                    if msg['type']=='error':raise RuntimeError(msg['message'])
            try:await asyncio.wait_for(receive(),65)
            except Exception as exc:evidence['error']=type(exc).__name__;raise
            finally:
                evidence['ended']=time.time()
                out.parent.mkdir(parents=True,exist_ok=True)
                out.write_text(json.dumps(evidence,indent=2))
        assert evidence['audio_bytes']>0 and evidence.get('proposal')
        print(json.dumps({'live_model':health['live_model'],'audio_bytes':evidence['audio_bytes'],'proposal':True,'executed':False,'evidence':str(out)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8000');p.add_argument('--output',type=Path,default=Path('outputs/lab-evidence/live-proxy.json'));args=p.parse_args()
    asyncio.run(run(args.url.rstrip('/'),args.output))
