"""Run: python -m agentic.openarms_lab (local-first, one server worker)."""
from __future__ import annotations
import asyncio
import anyio
from contextlib import asynccontextmanager
import os
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from dotenv import load_dotenv
from .runtime import Lab,LabError
from .voice_controls import MUTATING_TOOLS

ROOT=Path(__file__).resolve().parents[2]
# Explicit external env file supports bridging an existing checkout without copying secrets.
load_dotenv(os.getenv('OPENARMS_ENV_FILE',ROOT/'.env'),override=False)

class Text(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=4000)
class RequestBody(Text):
    client_request_id:str|None=Field(default=None,max_length=128)
class Confirm(BaseModel):
    request_id:str=Field(min_length=1,max_length=128)
class Cancel(BaseModel):
    request_id:str|None=None
class Experiment(BaseModel):
    experiment_id:str
class Answer(BaseModel):
    question_id:str
    answer:str=Field(min_length=1,max_length=4000)
class Compose(BaseModel):
    instruction:str=Field(min_length=1,max_length=4000)
class Promote(BaseModel):
    evidence_id:str

def allowed_host(host):
    try:hostname=urlsplit('//'+host).hostname
    except ValueError:return False
    return hostname in ({'localhost','127.0.0.1','::1','testserver'}|set(os.getenv('OPENARMS_ALLOWED_HOSTS','').split(',')))

def trusted_origin(origin,host):
    if not origin:return True  # CLI clients; browser clients always send Origin for WS/mutations
    try:
        u=urlsplit(origin)
        return u.scheme in ('http','https') and u.netloc==host
    except ValueError:return False

def create_app(lab=None):
    @asynccontextmanager
    async def lifespan(app):
        from .sim_preview import from_env
        from .free_plan import from_env as free_from_env
        app.state.lab=lab or Lab(Path(os.getenv('OPENARMS_DATA_DIR',ROOT/'outputs/lab')),previewer=from_env(),free_plans=free_from_env())
        yield
        await app.state.lab.shutdown()
    app=FastAPI(title='OpenArms Student Lab',lifespan=lifespan)
    if lab is not None: app.state.lab=lab
    @app.middleware('http')
    async def origin_guard(request,call_next):
        if request.method not in ('GET','HEAD','OPTIONS') and not trusted_origin(request.headers.get('origin'),request.headers.get('host')):
            return JSONResponse({'detail':'Cross-origin control requests are not allowed.'},status_code=403)
        # Local-first server; explicit host whitelist prevents DNS rebinding.
        hostname=request.url.hostname
        allowed={'localhost','127.0.0.1','::1','testserver'}|set(os.getenv('OPENARMS_ALLOWED_HOSTS','').split(','))
        if hostname not in allowed:
            return JSONResponse({'detail':'Host not allowed; configure OPENARMS_ALLOWED_HOSTS for your private host.'},status_code=403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Cache-Control']='no-store'
        return response
    @app.exception_handler(LabError)
    async def lab_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=409)
    @app.exception_handler(ValueError)
    async def value_error(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)
    @app.exception_handler(KeyError)
    async def key_error(request,exc):return JSONResponse({'detail':'Unknown session, skill or parameter.'},status_code=404)
    def service():return app.state.lab
    @app.get('/api/health')
    async def health():
        key=bool(os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY'))
        return {'backend':os.getenv('OPENARMS_BACKEND','mock'),'preview':'mujoco' if service().previewer else None,'free_plans':bool(service().free),'live_configured':key,
                'live_model':os.getenv('GEMINI_LIVE_MODEL','gemini-3.8-live'),
                'expert_configured':key,'expert_model':os.getenv('OPENARMS_EXPERT_MODEL','gemini-3.8-flash')}
    @app.get('/api/experiments')
    async def experiments():
        from .learning import EXPERIMENTS
        return EXPERIMENTS
    @app.get('/api/previews/{name}')
    async def preview_video(name:str):
        # Simulation preview videos only; the name is checked against the previewer's own pattern.
        previewer=service().previewer
        path=previewer.video_path(name) if previewer else None
        if path is None:return JSONResponse({'detail':'Preview not found.'},status_code=404)
        return FileResponse(path,media_type='video/mp4')
    @app.post('/api/sessions')
    async def create():return await service().create()
    @app.get('/api/sessions')
    async def history():
        return [{'session_id':s['session_id'],'experiment':s['experiment'],'backend':s['backend'],
                 'entries':len(s['notebook'])} for s in service().store.list_sessions()]
    @app.get('/api/sessions/{sid}')
    async def snapshot(sid):return service().snapshot(sid)
    @app.post('/api/sessions/{sid}/experiment')
    async def experiment(sid,b:Experiment):return await service().select_experiment(sid,b.experiment_id)
    @app.post('/api/sessions/{sid}/prediction')
    async def predict(sid,b:Text):return await service().prediction(sid,b.text)
    @app.post('/api/sessions/{sid}/request')
    async def request_action(sid,b:RequestBody):return await service().converse(sid,b.text,b.client_request_id)
    @app.post('/api/sessions/{sid}/confirm')
    async def confirm(sid,b:Confirm):return await service().confirm(sid,b.request_id)
    @app.post('/api/sessions/{sid}/cancel')
    async def cancel(sid,b:Cancel):return await service().cancel(sid,b.request_id)
    @app.post('/api/sessions/{sid}/stop')
    async def stop(sid):return await service().stop(sid)
    @app.post('/api/sessions/{sid}/disconnect')
    async def disconnect(sid):return await service().stop(sid,disconnect=True)
    @app.post('/api/sessions/{sid}/prepare')
    async def prepare(sid):return await service().prepare(sid)
    @app.post('/api/sessions/{sid}/answer')
    async def answer(sid,b:Answer):return await service().answer(sid,b.question_id,b.answer)
    @app.get('/api/skills')
    async def skills():return service().registry.list()
    @app.post('/api/skills/compose')
    async def compose(b:Compose):
        try:return await asyncio.wait_for(service().registry.compose(b.instruction),timeout=45)
        except TimeoutError:return JSONResponse({'detail':'Expert planning timed out. The existing skill catalog remains usable.'},status_code=504)
        except (ValueError,KeyError):raise
        except Exception as exc:return JSONResponse({'detail':f'Expert provider unavailable ({type(exc).__name__}). Retry later or use approved skills.'},status_code=503)
    @app.post('/api/skills/{skill_id}/test')
    async def test_candidate(skill_id):return service().registry.test_candidate(skill_id)
    @app.post('/api/skills/{skill_id}/promote')
    async def promote(skill_id,b:Promote):return service().registry.promote(skill_id,b.evidence_id)
    @app.websocket('/api/sessions/{sid}/events')
    async def events(ws:WebSocket,sid:str):
        if not allowed_host(ws.headers.get('host','')) or not trusted_origin(ws.headers.get('origin'),ws.headers.get('host')):
            await ws.close(code=1008);return
        await ws.accept()
        lab=service()
        try: lab.get(sid)
        except KeyError: await ws.close(code=1008);return
        q=asyncio.Queue(maxsize=8)
        lab.subscribers.setdefault(sid,set()).add(q)
        async def send():
            await ws.send_json({'type':'state','state':lab.snapshot(sid)})
            while True:
                try: item=await asyncio.wait_for(q.get(),timeout=20)
                except TimeoutError: item={'type':'heartbeat'}
                await ws.send_json(item)
        async def receive():
            while True: await ws.receive_text()
        sender=asyncio.create_task(send());receiver=asyncio.create_task(receive())
        try:
            done,_=await asyncio.wait((sender,receiver),return_when=asyncio.FIRST_COMPLETED)
            for t in done: t.result()
        except (WebSocketDisconnect,RuntimeError,asyncio.CancelledError):pass
        finally:
            # ASGI servers may cancel the connection scope during close; cleanup must finish.
            with anyio.CancelScope(shield=True):
                sender.cancel();receiver.cancel()
                await asyncio.gather(sender,receiver,return_exceptions=True)
                lab.subscribers[sid].discard(q)
                if not lab.subscribers[sid]:await lab.stop(sid,disconnect=True)
    @app.websocket('/api/sessions/{sid}/live')
    async def live(ws:WebSocket,sid:str):
        if not allowed_host(ws.headers.get('host','')) or not trusted_origin(ws.headers.get('origin'),ws.headers.get('host')):
            await ws.close(code=1008);return
        await ws.accept()
        lab=service()
        try:lab.get(sid)
        except KeyError:await ws.close(code=1008);return
        from .live import serve_live
        generation=lab.get(sid).get('generation',0)
        async def guarded(name,args):
            if name in MUTATING_TOOLS and lab.get(sid).get('generation',0)!=args.pop('_voice_generation',generation):
                raise LabError('This voice turn was revoked by STOP/disconnect. Reconnect before proposing another action.')
            return await lab.tool(sid,name,args)
        await serve_live(ws,lambda:lab.snapshot(sid),guarded,lambda:lab.stop(sid,disconnect=True))
    static=ROOT/'ui/lab'
    if static.is_dir():
        @app.get('/')
        async def index():return FileResponse(static/'index.html')
        app.mount('/',StaticFiles(directory=static),name='student')
    return app

app=create_app()
