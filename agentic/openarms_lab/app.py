"""One authenticated session transport for browser, native phone, text and voice."""
from __future__ import annotations
import asyncio
import contextlib
import hashlib
import os
import re
import secrets
import time
import uuid
import anyio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .access import SessionAccess
from .runtime import Lab, LabError
from .codex_expert import CodexExpert

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(os.getenv('OPENARMS_ENV_FILE', ROOT / '.env'), override=False)
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1', 'testserver'}


class Body(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Text(Body):
    text: str = Field(min_length=1, max_length=4000)


class RequestBody(Text):
    client_request_id: str | None = Field(default=None, max_length=128)


class Condition(Body):
    condition_id: str


class Confirm(Body):
    request_id: str = Field(min_length=1, max_length=128)
    proposal_version: int = Field(ge=1)

    @field_validator('proposal_version', mode='before')
    @classmethod
    def exact_version(cls, value):
        return proposal_version(value)


class Present(Confirm):
    channel: str = 'text'
    reply_id: str | None = None


class Cancel(Body):
    request_id: str | None = None


def proposal_version(value):
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,15}', value):
        return int(value)
    raise ValueError('Use the exact current proposal version.')


def public_state(value, sid):
    if isinstance(value, list):
        return [public_state(item, sid) for item in value]
    if not isinstance(value, dict):
        return value
    image = 'path' in value and 'evidence_id' in value and 'sha256' in value
    result = {key: public_state(item, sid) for key, item in value.items() if not (image and key == 'path')}
    if image:
        result['artifact_url'] = f"/api/sessions/{sid}/evidence/{value['evidence_id']}"
    if value.get('engine') == 'MuJoCo':
        for field, suffix, route in [('frame_name', '.png', 'evidence'), ('video_name', '.mp4', 'media')]:
            name = value.get(field)
            result.pop(field, None)
            if isinstance(name, str) and re.fullmatch(r'[0-9a-f]{32}'+re.escape(suffix), name):
                key = 'frame_url' if field == 'frame_name' else 'video_url'
                result[key] = f"/api/sessions/{sid}/{route}/" + (name[:-4] if route == 'evidence' else name)
    return result


def allowed_host(host):
    try:
        name = urlsplit('//' + host).hostname
    except ValueError:
        return False
    return name in LOCAL_HOSTS | set(os.getenv('OPENARMS_ALLOWED_HOSTS', '').split(','))


def evidence_hashes(value, evidence_id):
    if isinstance(value, list):
        return set().union(*(evidence_hashes(item, evidence_id) for item in value))
    if not isinstance(value, dict):
        return set()
    found = {value['sha256']} if value.get('evidence_id') == evidence_id and value.get('sha256') else set()
    return found.union(*(evidence_hashes(item, evidence_id) for item in value.values()))


def trusted_origin(origin, host):
    if not origin:
        return True  # Native/CLI clients authenticate with their own session grant.
    try:
        parsed = urlsplit(origin)
        return parsed.scheme in ('http', 'https') and parsed.netloc == host
    except ValueError:
        return False


def bearer(request):
    value = request.headers.get('authorization', '')
    return value[7:] if value.startswith('Bearer ') else ''


def create_app(lab=None, *, access_path=None, voice_factory=None, heartbeat_timeout=15):
    @asynccontextmanager
    async def lifespan(app):
        data = Path(os.getenv('OPENARMS_DATA_DIR', ROOT / 'outputs/lab'))
        if lab is None:
            from .scene import SceneService
            from .simulated_backend import SceneBackend
            from .evaluation import SyntheticSkillEvaluator
            from .skills import SkillRegistry
            execution = os.getenv('OPENARMS_EXECUTION', 'mock').strip().lower()
            registry_scope = execution
            app.state.execution_mode = execution
            if execution == 'mujoco':
                from .mujoco_scene import MujocoSceneService
                from .mujoco_backend import MujocoBackend
                from .simulation_evaluation import SimulationSkillEvaluator
                from .simulation_evaluation import simulation_scope
                registry_scope = simulation_scope()
                scene = MujocoSceneService(data / 'scene-evidence')
                backend_factory = lambda: MujocoBackend(scene)
                evaluator = SimulationSkillEvaluator(data / 'evaluations')
            elif execution == 'mock':
                scene = SceneService(data / 'scene-evidence')
                backend_factory = lambda: SceneBackend(scene)
                evaluator = SyntheticSkillEvaluator(data / 'evaluations')
            else:
                raise ValueError('OPENARMS_EXECUTION must be mock or mujoco; hardware is disabled.')
            expert = CodexExpert(data / 'expert-work', artifact_roots=[scene.artifact_dir],
                                 executable=os.getenv('OPENARMS_CODEX_EXECUTABLE', 'codex'))
            app.state.lab = Lab(data, expert=expert, perception=scene,
                                registry=SkillRegistry(data / f'task-skills-{registry_scope}.json'),
                                evaluator=evaluator,
                                auto_evaluate=True,
                                execution_scope=registry_scope,
                                backend_factory=backend_factory, expert_timeout=240)
        else:
            app.state.lab = lab
            app.state.execution_mode = next((b.mode for b in lab.backends.values()), 'mock')
        app.state.access = SessionAccess(Path(access_path) if access_path else data / 'access.sqlite3')
        app.state.connections = {}
        try:
            yield
        finally:
            for socket in list(app.state.connections.values()):
                with contextlib.suppress(Exception):
                    await socket.close(code=1001)
            await app.state.lab.shutdown()
            app.state.access.close()

    app = FastAPI(title='OpenArms · pH Studio', lifespan=lifespan)

    @app.middleware('http')
    async def guard(request, call_next):
        if not allowed_host(request.headers.get('host', '')):
            return JSONResponse({'detail': 'This host is not enabled.'}, status_code=403)
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not trusted_origin(request.headers.get('origin'), request.headers.get('host')):
            return JSONResponse({'detail': 'Use the app on its own server address.'}, status_code=403)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'})
        return response

    @app.exception_handler(LabError)
    async def conflict(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': 'This session or trial is no longer available.'}, status_code=404)

    def service():
        return app.state.lab

    def authorize(sid, request):
        if not app.state.access.permits(sid, bearer(request)):
            raise HTTPException(401, 'Reconnect with this session’s access token, or start a new session.')

    @app.get('/api/health')
    async def health():
        from .live import key
        return {'backend': app.state.execution_mode, 'hardware_enabled': False, 'protocol_version': 1,
                'live_configured': bool(key()), 'live_model': os.getenv('GEMINI_LIVE_MODEL', 'gemini-3.8-live'),
                'expert_provider': 'openai_codex_cli', 'expert_model': 'gpt-6.1-sol',
                'expert_reasoning_effort': 'medium',
                'pairing_required': bool(os.getenv('OPENARMS_DEMO_TOKEN'))}

    @app.post('/api/sessions')
    async def create(request: Request):
        pairing = os.getenv('OPENARMS_DEMO_TOKEN', '')
        remote = request.url.hostname not in LOCAL_HOSTS
        if remote and not pairing:
            raise HTTPException(403, 'Remote sessions require a server pairing code.')
        if pairing and not secrets.compare_digest(bearer(request), pairing):
            raise HTTPException(401, 'Enter the pairing code shown by the demo host.')
        snapshot = await service().create()
        return {**public_state(snapshot, snapshot['session_id']), 'access_token': app.state.access.issue(snapshot['session_id'])}

    @app.get('/api/sessions/{sid}')
    async def snapshot(sid: str, request: Request):
        authorize(sid, request)
        return public_state(service().snapshot(sid), sid)

    @app.get('/api/sessions/{sid}/evidence/{evidence_id}')
    async def evidence(sid: str, evidence_id: str, request: Request):
        authorize(sid, request)
        state = service().snapshot(sid)
        perception = getattr(service(), 'perception', None)
        if not re.fullmatch(r'[0-9a-f]{32}', evidence_id) or not hasattr(perception, 'artifact_dir'):
            raise HTTPException(404, 'Scene frame is unavailable.')
        folder = (perception.artifact_dir / sid).resolve()
        path = (folder / (evidence_id + '.png')).resolve()
        if path.parent != folder or not path.is_file():
            raise HTTPException(404, 'Scene frame is unavailable.')
        expected = evidence_hashes(state, evidence_id)
        data = path.read_bytes()
        if len(expected) != 1 or hashlib.sha256(data).hexdigest() not in expected:
            raise HTTPException(409, 'Scene evidence no longer matches its published identity.')
        return Response(data, media_type='image/png')

    @app.get('/api/sessions/{sid}/media/{name}')
    async def simulation_video(sid: str, name: str, request: Request):
        authorize(sid, request)
        service().get(sid)
        perception = getattr(service(), 'perception', None)
        if not re.fullmatch(r'[0-9a-f]{32}\.mp4', name) or not hasattr(perception, 'artifact_dir'):
            raise HTTPException(404, 'Simulation video is unavailable.')
        folder = (perception.artifact_dir / sid).resolve()
        path = (folder / name).resolve()
        if path.parent != folder or not path.is_file():
            raise HTTPException(404, 'Simulation video is unavailable.')
        return FileResponse(path, media_type='video/mp4')

    @app.post('/api/sessions/{sid}/condition')
    async def condition(sid: str, body: Condition, request: Request):
        authorize(sid, request)
        return public_state(await service().choose_condition(sid, body.condition_id), sid)

    @app.post('/api/sessions/{sid}/prediction')
    async def prediction(sid: str, body: Text, request: Request):
        authorize(sid, request)
        return public_state(await service().prediction(sid, body.text), sid)

    @app.post('/api/sessions/{sid}/request')
    async def conversation(sid: str, body: RequestBody, request: Request):
        authorize(sid, request)
        return public_state(await service().converse(sid, body.text, body.client_request_id), sid)

    @app.post('/api/sessions/{sid}/present')
    async def present(sid: str, body: Present, request: Request):
        authorize(sid, request)
        if body.channel != 'text':
            raise HTTPException(400, 'Audio presentation is acknowledged by the active voice connection.')
        return public_state(await service().present(sid, body.request_id, body.proposal_version, body.channel, body.reply_id), sid)

    @app.post('/api/sessions/{sid}/confirm')
    async def confirm(sid: str, body: Confirm, request: Request):
        authorize(sid, request)
        return public_state(await service().confirm(sid, body.request_id, body.proposal_version), sid)

    @app.post('/api/sessions/{sid}/cancel')
    async def cancel(sid: str, body: Cancel, request: Request):
        authorize(sid, request)
        return public_state(await service().cancel(sid, body.request_id), sid)

    @app.post('/api/sessions/{sid}/prepare')
    async def prepare(sid: str, request: Request):
        authorize(sid, request)
        return public_state(await service().prepare(sid), sid)

    @app.post('/api/sessions/{sid}/reflection')
    async def reflection(sid: str, body: Text, request: Request):
        authorize(sid, request)
        return public_state(await service().reflection(sid, body.text), sid)

    @app.post('/api/sessions/{sid}/stop')
    async def stop(sid: str, request: Request):
        authorize(sid, request)
        return public_state(await service().stop(sid), sid)

    @app.post('/api/sessions/{sid}/disconnect')
    async def disconnect(sid: str, request: Request):
        authorize(sid, request)
        return public_state(await service().stop(sid, disconnect=True), sid)

    @app.websocket('/api/sessions/{sid}/live')
    async def session_socket(ws: WebSocket, sid: str):
        if not allowed_host(ws.headers.get('host', '')) or not trusted_origin(ws.headers.get('origin'), ws.headers.get('host')):
            await ws.close(code=1008)
            return
        await ws.accept()
        try:
            hello = await asyncio.wait_for(ws.receive_json(), 5)
            if (hello.get('type') != 'hello' or hello.get('protocol_version') != 1 or
                    not app.state.access.permits(sid, str(hello.get('access_token', '')))):
                await ws.close(code=1008)
                return
            service().get(sid)
        except (TimeoutError, ValueError, KeyError, WebSocketDisconnect):
            with contextlib.suppress(Exception):
                await ws.close(code=1008)
            return
        previous = app.state.connections.get(sid)
        app.state.connections[sid] = ws  # Old cleanup can no longer revoke this owner.
        if previous is not None:
            await service().stop(sid, disconnect=True)
            with contextlib.suppress(Exception):
                await previous.close(code=4001, reason='Session opened on another connection')
        current = service().get(sid)
        current['connected'] = True
        await service().publish(current)
        connection_id = str(hello.get('connection_id') or uuid.uuid4())[:128]
        queue = asyncio.Queue(maxsize=16)
        service().subscribers.setdefault(sid, set()).add(queue)
        send_lock = asyncio.Lock()
        voice = None
        voice_task = None
        last_ping = time.monotonic()
        tasks = []

        async def emit(data):
            if app.state.connections.get(sid) is not ws:
                return
            async with send_lock:
                await ws.send_json(public_state(data, sid))

        async def stop_voice():
            nonlocal voice, voice_task
            if voice:
                await voice.close()
            if voice_task:
                voice_task.cancel()
                await asyncio.gather(voice_task, return_exceptions=True)
            voice = voice_task = None

        async def receive():
            nonlocal voice, voice_task, last_ping
            from .live import GeminiBridge
            while True:
                msg = await ws.receive_json()
                kind = msg.get('type')
                if app.state.connections.get(sid) is not ws:
                    return
                try:
                    if kind == 'ping':
                        last_ping = time.monotonic()
                        await emit({'type': 'pong', 'seq': msg.get('seq')})
                    elif kind == 'start_voice':
                        if voice_task and not voice_task.done():
                            continue
                        factory = voice_factory or GeminiBridge
                        async def voice_tool(name, args):
                            if app.state.connections.get(sid) is not ws:
                                raise ValueError('This connection has been replaced.')
                            if name == '_present_audio':
                                return await service().present(sid, args['request_id'], args['proposal_version'], 'audio', args['reply_id'])
                            return await service().tool(sid, name, args)
                        voice = factory(lambda: service().snapshot(sid), voice_tool, emit)
                        voice_task = asyncio.create_task(voice.run())
                    elif kind == 'stop_voice':
                        await stop_voice()
                        await emit({'type': 'status', 'status': 'connected', 'message': 'Voice off. Text is ready.'})
                    elif kind == 'audio':
                        if voice and msg.get('epoch') == service().get(sid).get('generation', 0):
                            await voice.audio(msg.get('data', ''))
                    elif kind == 'audio_end':
                        if voice:
                            await voice.end_audio()
                    elif kind == 'mute':
                        if voice:
                            await voice.mute(bool(msg.get('muted')))
                    elif kind == 'text':
                        text = str(msg.get('text', '')).strip()
                        if not text or len(text) > 4000:
                            raise ValueError('Write between 1 and 4,000 characters.')
                        await service().converse(sid, text, msg.get('client_request_id'))
                    elif kind == 'present':
                        if msg.get('channel', 'text') != 'text':
                            raise ValueError('Wait for the spoken preview to finish.')
                        await service().present(sid, msg['request_id'], proposal_version(msg['proposal_version']), 'text', msg.get('reply_id'))
                    elif kind == 'played':
                        if voice:
                            await voice.played(msg.get('reply_id'))
                    elif kind == 'interrupt':
                        if voice:
                            await voice.interrupt(msg.get('reply_id'))
                    elif kind == 'stop':
                        if voice:
                            await voice.interrupt(None)
                        await service().stop(sid)
                    elif kind == 'close':
                        return
                    else:
                        raise ValueError('Unsupported session message.')
                except (LabError, ValueError, KeyError) as exc:
                    await emit({'type': 'error', 'code': 'invalid_action', 'message': str(exc), 'recoverable': True})

        async def updates():
            while True:
                await emit(await queue.get())
                if voice and hasattr(voice, 'state_changed'):
                    await voice.state_changed()

        async def watchdog():
            while True:
                await asyncio.sleep(min(2, heartbeat_timeout / 3))
                if time.monotonic() - last_ping > heartbeat_timeout:
                    await emit({'type': 'error', 'code': 'connection_timeout', 'message': 'Connection lost. Reconnecting restores your notebook; approvals are cleared.', 'recoverable': True})
                    return

        try:
            await emit({'type': 'hello', 'protocol_version': 1, 'connection_id': connection_id, 'generation': current.get('generation', 0)})
            await emit({'type': 'state', 'state': service().snapshot(sid)})
            await emit({'type': 'status', 'status': 'connected'})
            tasks = [asyncio.create_task(receive()), asyncio.create_task(updates()), asyncio.create_task(watchdog())]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                task.result()
        except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
            pass
        finally:
            # ASGI cancellation may remain active at every await. Finish revoking
            # this connection's work before the cancelled request unwinds.
            with anyio.CancelScope(shield=True):
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                await stop_voice()
                service().subscribers[sid].discard(queue)
                if app.state.connections.get(sid) is ws:
                    app.state.connections.pop(sid, None)
                    await service().stop(sid, disconnect=True)
                with contextlib.suppress(Exception):
                    await ws.close()

    static = ROOT / 'ui/lab'

    @app.get('/')
    @app.get('/developer')
    async def index():
        return FileResponse(static / 'index.html')

    app.mount('/', StaticFiles(directory=static), name='student')
    return app


app = create_app()
