"""Run with Python 3.13: uv run python relay.py --help."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import time
import uuid

from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from audio import Endpoint, MAX_FRAME, MacSpeech, pcm_wav, validate_wav
from dialogue import Context, MockDialogue


def uid(prefix):
    return f"{prefix}-{uuid.uuid4().hex}"


def private_dir(path: Path) -> Path:
    path = path.expanduser().absolute()
    # Refuse symlink components; logs must not redirect into an unrelated place.
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError("Private data directory cannot contain symlinks")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


class SessionLog:
    def __init__(self, root: Path, session_id: str, raw: bool):
        self.session_id = session_id
        self.path = private_dir(root / session_id)
        self.raw = raw
        fd = os.open(self.path / "events.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.file = os.fdopen(fd, "w", buffering=1)

    def event(self, event, turn_id=None, **fields):
        self.file.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), "session_id": self.session_id, "turn_id": turn_id, "event": event, **fields}) + "\n")

    def audio(self, turn_id: str, role: str, wav: bytes):
        if self.raw:
            fd = os.open(self.path / f"{turn_id}-{role}.wav", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(wav)

    def close(self):
        self.file.close()


class Session:
    def __init__(self, websocket, speech, adapter, log_root, *, raw=False, ack_timeout=45, processing_timeout=120):
        self.ws = websocket
        self.speech = speech
        self.adapter = adapter
        self.id = uid("s")
        self.log = SessionLog(log_root, self.id, raw)
        if hasattr(adapter, "set_event_sink"):
            adapter.set_event_sink(lambda name, **fields: self.log.event(name, self.turn_id, **fields))
        self.raw = raw
        self.ack_timeout = ack_timeout
        self.processing_timeout = processing_timeout
        self.endpoint = Endpoint()
        self.muted = False
        self.phase = "processing"  # independent from microphone state
        self.turn_id = None
        self.lock = asyncio.Lock()
        self.worker = None
        self.ack_task = None
        self.playback_started = None
        self.closed = False

    async def send(self, message):
        await self.ws.send(json.dumps(message))
        self.log.event("sent", self.turn_id, message=message)

    async def state(self):
        # Protocol has no playback state. Remain non-listening until matching ack.
        state = "muted" if self.muted else ("listening" if self.phase == "listening" else "processing")
        await self.send({"type": "state", "state": state})

    async def error(self, message, fatal=False):
        self.log.event("error", self.turn_id, message=message, fatal=fatal)
        await self.send({"type": "error", "message": message, "fatal": fatal})
        if fatal:
            self.closed = True
            await self.ws.close(code=1011, reason=message[:100])
        else:
            await self.state()

    async def run(self):
        self.log.event("connection", peer=str(self.ws.remote_address), raw_audio=self.raw,
                       speech_backend=type(self.speech).__name__, dialogue_backend=type(self.adapter).__name__)
        try:
            async with self.lock:
                await self.send({"type": "session", "session_id": self.id, "mode": getattr(getattr(self.adapter, "runner", None), "mode", "mock"), "logging": True, "raw_audio": self.raw})
                await self.start_turn(None)
            async for message in self.ws:
                async with self.lock:
                    if self.closed:
                        break
                    await self.receive(message)
        except ConnectionClosed as exc:
            self.log.event("connection_closed", self.turn_id, detail=str(exc))
        except Exception as exc:
            self.log.event("internal_error", self.turn_id, error=type(exc).__name__, detail=str(exc))
            await self.ws.close(code=1011, reason="Relay error; see local session log")
        finally:
            self.closed = True
            for task in (self.worker, self.ack_task):
                if task:
                    task.cancel()
            await asyncio.gather(*(task for task in (self.worker, self.ack_task) if task), return_exceptions=True)
            try:
                async with asyncio.timeout(5):
                    await self.adapter.close()
            except Exception as exc:
                self.log.event("adapter_cleanup_error", self.turn_id, error=str(exc))
            finally:
                self.endpoint.reset()
                self.log.event("disconnect", self.turn_id)
                self.log.close()

    async def start_turn(self, pcm):
        self.phase = "processing"
        self.turn_id = uid("t")
        self.endpoint.reset()
        await self.state()
        self.worker = asyncio.create_task(self.process(pcm, self.turn_id))

    async def process(self, pcm, turn_id):
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.processing_timeout):
                text = None
                if pcm is not None:
                    self.log.audio(turn_id, "student", pcm_wav(pcm))
                    stt_start = time.monotonic()
                    text = (await self.speech.transcribe(pcm)).strip()
                    self.log.event("recognition", turn_id, duration_ms=round((time.monotonic() - stt_start) * 1000), audio_ms=len(pcm) / 32)
                    if text.upper() in {"[BLANK_AUDIO]", "[SILENCE]", "[NO_SPEECH]"}:
                        text = ""
                    if len(text) > 4096:
                        raise ValueError("Transcript exceeds limit")
                    if not text:
                        async with self.lock:
                            self.phase = "listening"
                            await self.error("No speech recognized. Please try again.")
                        return
                    self.log.event("transcript", turn_id, role="student", text=text)
                    async with self.lock:
                        await self.send({"type": "transcript", "role": "student", "turn_id": turn_id, "text": text})
                reply = await self.adapter.respond(Context(self.id, turn_id), text)
                if not reply.text or len(reply.text) > 4096:
                    raise ValueError("Reply text is empty or exceeds limit")
                self.log.event("transcript", turn_id, role="relay", text=reply.text, lab_stage=reply.lab_stage)
                tts_start = time.monotonic()
                wav = await self.speech.synthesize(reply.text)
                validate_wav(wav)
                self.log.audio(turn_id, "relay", wav)
                self.log.event("synthesis", turn_id, duration_ms=round((time.monotonic() - tts_start) * 1000), bytes=len(wav))
                async with self.lock:
                    self.phase = "playback"
                    await self.send({"type": "reply", "turn_id": turn_id, "text": reply.text, "lab_stage": reply.lab_stage})
                    await self.ws.send(wav)
                    self.playback_started = time.monotonic()
                    self.log.event("reply_audio", turn_id, bytes=len(wav), total_ms=round((time.monotonic() - started) * 1000))
                    self.ack_task = asyncio.create_task(self.expire_ack(turn_id))
        except asyncio.CancelledError:
            self.log.event("processing_cancelled", turn_id)
            raise
        except ConnectionClosed:
            pass
        except Exception as exc:
            async with self.lock:
                self.log.event("processing_error", turn_id, error=type(exc).__name__, detail=str(exc))
                # A failed adapter/TTS may have advanced dialogue state: close
                # rather than retrying an ambiguous half-completed turn.
                await self.error("Speech processing failed; start a new session.", fatal=True)

    async def expire_ack(self, turn_id):
        await asyncio.sleep(self.ack_timeout)
        try:
            async with self.lock:
                if self.phase == "playback" and self.turn_id == turn_id:
                    await self.error("Playback acknowledgement timed out.", fatal=True)
        except ConnectionClosed:
            pass

    async def receive(self, message):
        if isinstance(message, bytes):
            if self.phase != "listening" or self.muted:
                self.log.event("audio_discarded", self.turn_id, bytes=len(message), phase=self.phase, muted=self.muted)
                return
            try:
                pcm = self.endpoint.feed(message)
            except ValueError as exc:
                await self.error(str(exc))
                return
            if pcm is not None:
                await self.start_turn(pcm)
            return
        if len(message) > 2048:
            await self.error("Control message exceeds limit")
            return
        try:
            control = json.loads(message)
            if not isinstance(control, dict) or not isinstance(control.get("type"), str):
                raise ValueError
        except (ValueError, TypeError):
            await self.error("Expected a JSON control object")
            return
        kind = control["type"]
        # Log only validated fields, not arbitrary unsolicited payloads.
        self.log.event("control", self.turn_id, type=kind[:64])
        if kind == "ping":
            await self.send({"type": "pong"})
        elif kind == "end":
            self.closed = True
            await self.ws.close(code=1000, reason="Session ended")
        elif kind == "mute":
            if type(control.get("muted")) is not bool:
                await self.error("muted must be a boolean")
                return
            self.muted = control["muted"]
            self.log.event("mute", self.turn_id, muted=self.muted, phase=self.phase)
            self.endpoint.reset()
            await self.state()
        elif kind == "played":
            if self.phase != "playback" or control.get("turn_id") != self.turn_id:
                await self.error("Unexpected playback acknowledgement")
                return
            if self.ack_task:
                self.ack_task.cancel()
            self.log.event("played", self.turn_id, duration_ms=round((time.monotonic() - self.playback_started) * 1000))
            self.phase = "listening"
            self.endpoint.reset()
            await self.state()
        else:
            await self.error("Unknown control type")


def handler_factory(speech, log_root, adapter_factory=MockDialogue, **options):
    async def handler(ws):
        if ws.request.path != "/voice":
            await ws.close(code=1008, reason="Use /voice")
            return
        session = Session(ws, speech, adapter_factory(), log_root, **options)
        await session.run()
    return handler


def parser():
    out = argparse.ArgumentParser(description=__doc__)
    bind = out.add_mutually_exclusive_group()
    bind.add_argument("--host", help="Explicit bind address; default 127.0.0.1")
    bind.add_argument("--lan", action="store_true", help="Explicitly bind 0.0.0.0 on a trusted LAN")
    out.add_argument("--port", type=int, default=8765)
    out.add_argument("--whisper-cli", type=Path, required=True)
    out.add_argument("--model", type=Path, required=True, help="Explicit local whisper.cpp model file; no download")
    out.add_argument("--voice", help="Optional installed macOS say voice")
    out.add_argument("--log-dir", type=Path, default=Path.home() / "Library/Logs/OpenArmsVoiceRelay")
    out.add_argument("--raw-audio", action="store_true", help="Opt in to retaining utterance and reply WAVs")
    out.add_argument("--runner", help="Optional robotics module:factory implementing the documented TransferRunner contract")
    out.add_argument("--dialogue", choices=("mock", "agy"), default="mock")
    out.add_argument("--ack-timeout", type=float, default=45)
    out.add_argument("--processing-timeout", type=float, default=120,
                     help="Deadline in seconds for recognition, dialogue and reply synthesis")
    return out


async def main(args):
    if any(not math.isfinite(value) or value <= 0 for value in (args.ack_timeout, args.processing_timeout)):
        raise ValueError("Timeouts must be finite positive numbers")
    if not 0 <= args.port <= 65535:
        raise ValueError("Port must be between 0 and 65535")
    cli, model = args.whisper_cli.expanduser().resolve(), args.model.expanduser().resolve()
    if not cli.is_file() or not os.access(cli, os.X_OK):
        raise ValueError("--whisper-cli must be an existing executable")
    if not model.is_file():
        raise ValueError("--model must be an existing whisper.cpp model")
    for executable in ("/usr/bin/say", "/usr/bin/afconvert"):
        if not os.access(executable, os.X_OK):
            raise ValueError(f"Missing Mac executable: {executable}")
    log_root = args.log_dir.expanduser().absolute()
    # Refuse all Git working trees, including other repositories. Default data
    # location is outside Git. An ignored path is allowed only for tests.
    if any((part / ".git").exists() for part in [log_root, *log_root.parents]):
        raise ValueError("--log-dir must be outside Git working trees")
    log_root = private_dir(log_root)
    scratch = private_dir(log_root / "scratch")
    speech = MacSpeech(cli, model, scratch, args.voice)
    host = args.host or ("0.0.0.0" if args.lan else "127.0.0.1")
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    if args.runner and args.dialogue != "agy":
        raise ValueError("--runner requires --dialogue agy")
    adapter_factory = MockDialogue
    if args.dialogue == "agy":
        from mandarin import MandarinDialogue
        if args.runner:
            import importlib
            module, separator, factory = args.runner.partition(":")
            if not separator:
                raise ValueError("--runner must be module:factory")
            make_runner = getattr(importlib.import_module(module), factory)
            adapter_factory = lambda: MandarinDialogue(runner=make_runner())
        else:
            adapter_factory = MandarinDialogue
    async with serve(handler_factory(speech, log_root, adapter_factory=adapter_factory, raw=args.raw_audio, ack_timeout=args.ack_timeout,
                                    processing_timeout=args.processing_timeout), host, args.port,
                     max_size=MAX_FRAME, max_queue=8, compression=None, ping_interval=20, ping_timeout=20, close_timeout=2) as server:
        print(f"Voice relay listening on {host}:{server.sockets[0].getsockname()[1]}/voice; logs: {log_root}", flush=True)
        await stop.wait()


if __name__ == "__main__":
    # Private transient CLI output inherits this mask too.
    os.umask(0o077)
    cli_parser = parser()
    try:
        asyncio.run(main(cli_parser.parse_args()))
    except ValueError as exc:
        cli_parser.error(str(exc))
