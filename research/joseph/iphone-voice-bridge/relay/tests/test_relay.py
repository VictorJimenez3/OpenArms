import asyncio
import json
import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from audio import Endpoint, MAX_FRAME, command, pcm_wav, validate_wav
from dialogue import Context, MockDialogue
from relay import handler_factory, parser

LOCAL = Path(__file__).resolve().parents[1] / ".local"
LOCAL.mkdir(exist_ok=True)
VOICE = struct.pack("<h", 2500) * 3200
SILENCE = b"\x00" * 6400


class StubSpeech:
    def __init__(self):
        self.text = "I predict the block reaches the target"
        self.received = []
        self.gate = asyncio.Event()
        self.gate.set()
        self.started = asyncio.Event()
        self.cancelled = False
        self.fail = False
        self.tts_gate = asyncio.Event()
        self.tts_gate.set()
        self.tts_cancelled = False

    async def transcribe(self, pcm):
        self.received.append(pcm)
        self.started.set()
        try:
            await self.gate.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.fail:
            raise RuntimeError("test recognition failure")
        return self.text

    async def synthesize(self, text):
        try:
            await self.tts_gate.wait()
        except asyncio.CancelledError:
            self.tts_cancelled = True
            raise
        return pcm_wav(b"\x00" * 3200)


class RelayTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=LOCAL)
        self.logs = Path(self.tmp.name)
        self.speech = StubSpeech()
        self.adapters = []
        self.sessions = []
        self.connections = []
        def make_adapter():
            adapter = MockDialogue()
            self.adapters.append(adapter)
            return adapter
        self.server = await serve(handler_factory(self.speech, self.logs, make_adapter, ack_timeout=0.6), "127.0.0.1", 0, max_size=MAX_FRAME, max_queue=8, close_timeout=0.1)
        self.url = f"ws://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/voice"

    async def asyncTearDown(self):
        for ws in self.connections:
            await ws.close()
        self.server.close()
        await self.server.wait_closed()
        self.tmp.cleanup()

    async def event(self, ws):
        frame = await asyncio.wait_for(ws.recv(), 2)
        self.assertIsInstance(frame, str)
        return json.loads(frame)

    async def state(self, ws, state):
        self.assertEqual(await self.event(ws), {"type": "state", "state": state})

    async def reply(self, ws):
        reply = await self.event(ws)
        self.assertEqual(reply["type"], "reply")
        wav = await asyncio.wait_for(ws.recv(), 2)
        self.assertIsInstance(wav, bytes)
        validate_wav(wav)
        return reply

    async def send(self, ws, **fields):
        await ws.send(json.dumps(fields))

    async def open_session(self, ack=True):
        ws = await connect(self.url, proxy=None)
        self.connections.append(ws)
        session = await self.event(ws)
        self.assertEqual(session["type"], "session")
        self.assertFalse(session["raw_audio"])
        self.sessions.append(session["session_id"])
        await self.state(ws, "processing")
        reply = await self.reply(ws)
        if ack:
            await self.send(ws, type="played", turn_id=reply["turn_id"])
            await self.state(ws, "listening")
        return ws, reply

    async def utterance(self, ws):
        await ws.send(VOICE)
        for _ in range(3):
            await ws.send(SILENCE)

    async def turn(self, ws, text):
        self.speech.text = text
        await self.utterance(ws)
        await self.state(ws, "processing")
        transcript = await self.event(ws)
        self.assertEqual(transcript["type"], "transcript")
        self.assertEqual(transcript["text"], text)
        reply = await self.reply(ws)
        self.assertEqual(transcript["turn_id"], reply["turn_id"])
        await self.send(ws, type="played", turn_id=reply["turn_id"])
        await self.state(ws, "listening")
        return reply

    async def test_dialogue_confirm_cancel_logs_and_fresh_session(self):
        ws, opening = await self.open_session()
        preview = await self.turn(ws, "It reaches the target")
        self.assertEqual(preview["lab_stage"], "preview")
        ambiguous = await self.turn(ws, "do not confirm")
        self.assertEqual(ambiguous["lab_stage"], "confirmation")
        result = await self.turn(ws, "confirm")
        self.assertEqual(result["lab_stage"], "result")
        reflection = await self.turn(ws, "It matched my prediction")
        self.assertEqual(reflection["lab_stage"], "reflection")
        self.assertEqual(len({x["turn_id"] for x in [opening, preview, ambiguous, result, reflection]}), 5)
        await self.send(ws, type="end")
        await ws.wait_closed()
        ws2, _ = await self.open_session()
        self.assertNotEqual(*self.sessions)
        self.assertIsNot(self.adapters[0], self.adapters[1])
        await self.turn(ws2, "Prediction")
        cancelled = await self.turn(ws2, "cancel")
        self.assertEqual(cancelled["lab_stage"], "reflection")
        self.assertIn("cancelled", cancelled["text"])
        await ws2.close()
        self.server.close()
        await self.server.wait_closed()
        self.assertFalse(list(self.logs.rglob("*.wav")))
        for path in self.logs.glob("*/events.jsonl"):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            events = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertTrue(all(e["timestamp"].endswith("+00:00") for e in events))
            self.assertTrue(all("turn_id" in e and e["session_id"] == path.parent.name for e in events))
            self.assertEqual(events[0]["event"], "connection")
            self.assertEqual(events[-1]["event"], "disconnect")
            self.assertEqual({e["role"] for e in events if e["event"] == "transcript"}, {"student", "relay"})
            self.assertTrue(any(e["event"] == "played" and e["duration_ms"] >= 0 for e in events))

    async def test_mute_processing_controls_and_playback_gate(self):
        ws, _ = await self.open_session()
        self.speech.gate.clear()
        await self.utterance(ws)
        await self.state(ws, "processing")
        await asyncio.wait_for(self.speech.started.wait(), 1)
        await self.send(ws, type="mute", muted=True)
        await self.state(ws, "muted")
        await self.send(ws, type="ping")
        self.assertEqual(await self.event(ws), {"type": "pong"})
        await self.send(ws, type="mute", muted=False)
        await self.state(ws, "processing")
        await self.utterance(ws)  # must not create a second recognition job
        await self.send(ws, type="mute", muted=True)
        await self.state(ws, "muted")
        self.speech.gate.set()
        self.assertEqual((await self.event(ws))["type"], "transcript")
        reply = await self.reply(ws)
        await self.send(ws, type="mute", muted=False)
        await self.state(ws, "processing")  # playback still unacknowledged
        await self.send(ws, type="played", turn_id="t-stale")
        self.assertFalse((await self.event(ws))["fatal"])
        await self.state(ws, "processing")
        await self.send(ws, type="mute", muted=True)
        await self.state(ws, "muted")
        await self.send(ws, type="played", turn_id=reply["turn_id"])
        await self.state(ws, "muted")
        await self.utterance(ws)
        await self.send(ws, type="mute", muted=False)
        await self.state(ws, "listening")
        self.assertEqual(len(self.speech.received), 1)

    async def test_mute_discards_partial_utterance(self):
        ws, _ = await self.open_session()
        await ws.send(VOICE)
        await self.send(ws, type="mute", muted=True)
        await self.state(ws, "muted")
        await self.send(ws, type="mute", muted=False)
        await self.state(ws, "listening")
        for _ in range(4):
            await ws.send(SILENCE)
        await self.send(ws, type="ping")
        self.assertEqual(await self.event(ws), {"type": "pong"})
        self.assertEqual(self.speech.received, [])

    async def test_ack_timeout_survives_mute(self):
        ws, _ = await self.open_session(ack=False)
        await self.send(ws, type="mute", muted=True)
        await self.state(ws, "muted")
        error = await self.event(ws)
        self.assertTrue(error["fatal"])
        self.assertIn("timed out", error["message"])
        await ws.wait_closed()
        self.assertEqual(ws.close_code, 1011)

    async def test_end_cancels_recognition(self):
        ws, _ = await self.open_session()
        self.speech.gate.clear()
        await self.utterance(ws)
        await self.state(ws, "processing")
        await self.speech.started.wait()
        await self.send(ws, type="end")
        await ws.wait_closed()
        self.server.close()
        await self.server.wait_closed()
        self.assertTrue(self.speech.cancelled)

    async def test_empty_recognition_and_bad_controls_recover(self):
        ws, _ = await self.open_session()
        for bad in ("[]", "{", '{"type":"mute","muted":"yes"}'):
            await ws.send(bad)
            self.assertFalse((await self.event(ws))["fatal"])
            await self.state(ws, "listening")
        await ws.send(b"x")
        self.assertFalse((await self.event(ws))["fatal"])
        await self.state(ws, "listening")
        self.speech.text = ""
        await self.utterance(ws)
        await self.state(ws, "processing")
        self.assertFalse((await self.event(ws))["fatal"])
        await self.state(ws, "listening")

    async def test_processing_failure_closes_session(self):
        ws, _ = await self.open_session()
        self.speech.fail = True
        await self.utterance(ws)
        await self.state(ws, "processing")
        self.assertTrue((await self.event(ws))["fatal"])
        await ws.wait_closed()
        self.assertEqual(ws.close_code, 1011)

    async def test_transport_frame_limit_and_path(self):
        ws, _ = await self.open_session()
        await ws.send(b"\x00" * (MAX_FRAME + 2))
        with self.assertRaises(ConnectionClosed):
            await ws.recv()
        self.assertEqual(ws.close_code, 1009)
        wrong = await connect(self.url + "-wrong", proxy=None)
        self.connections.append(wrong)
        await wrong.wait_closed()
        self.assertEqual(wrong.close_code, 1008)

    async def test_opening_tts_mute_and_disconnect_cleanup(self):
        self.speech.tts_gate.clear()
        ws = await connect(self.url, proxy=None)
        self.connections.append(ws)
        self.assertEqual((await self.event(ws))["type"], "session")
        await self.state(ws, "processing")
        await self.send(ws, type="mute", muted=True)
        await self.state(ws, "muted")
        await self.send(ws, type="mute", muted=False)
        await self.state(ws, "processing")
        await self.send(ws, type="ping")
        self.assertEqual(await self.event(ws), {"type": "pong"})
        await ws.close()
        self.server.close()
        await self.server.wait_closed()
        self.assertTrue(self.speech.tts_cancelled)

    async def test_duplicate_ack_cannot_skip_next_turn(self):
        ws, opening = await self.open_session()
        await self.send(ws, type="played", turn_id=opening["turn_id"])
        self.assertFalse((await self.event(ws))["fatal"])
        await self.state(ws, "listening")
        reply = await self.turn(ws, "Prediction")
        self.assertEqual(reply["lab_stage"], "preview")

    async def test_raw_capture_is_explicit(self):
        async with serve(handler_factory(self.speech, self.logs, raw=True), "127.0.0.1", 0) as raw_server:
            async with connect(f"ws://127.0.0.1:{raw_server.sockets[0].getsockname()[1]}/voice", proxy=None) as ws:
                self.assertTrue((await self.event(ws))["raw_audio"])
                await self.state(ws, "processing")
                reply = await self.reply(ws)
                await self.send(ws, type="played", turn_id=reply["turn_id"])
                await self.state(ws, "listening")
                await self.turn(ws, "prediction")
        files = list(self.logs.rglob("*.wav"))
        self.assertEqual(len(files), 3)
        for path in files:
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            validate_wav(path.read_bytes())


class AudioTests(unittest.TestCase):
    def test_sample_duration_and_preroll_independent_of_packets(self):
        data = SILENCE * 2 + VOICE * 2 + SILENCE * 3
        outputs = []
        for size in (320, 640, 960, 6400):
            endpoint = Endpoint()
            captured = None
            for start in range(0, len(data), size):
                result = endpoint.feed(data[start:start + size])
                if result is not None:
                    captured = result
            outputs.append(captured)
        self.assertTrue(all(out == outputs[0] for out in outputs))
        self.assertEqual(outputs[0], SILENCE + VOICE * 2 + SILENCE * 3)

    def test_continuous_speech_is_bounded_and_short_noise_is_ignored(self):
        endpoint = Endpoint()
        for _ in range(74):
            self.assertIsNone(endpoint.feed(VOICE))
        self.assertEqual(len(endpoint.feed(VOICE)), endpoint.max_bytes)
        self.assertFalse(endpoint.active)
        endpoint.feed(VOICE[:640])
        for _ in range(3):
            self.assertIsNone(endpoint.feed(SILENCE))
        self.assertFalse(endpoint.active)

    def test_silence_and_invalid_frames_are_bounded(self):
        endpoint = Endpoint()
        for _ in range(100):
            endpoint.feed(SILENCE)
        self.assertLessEqual(len(endpoint.pre), 6400)
        self.assertEqual(len(endpoint.audio), 0)
        for frame in (b"", b"a", b"\x00" * 6402):
            with self.assertRaises(ValueError):
                endpoint.feed(frame)
        with self.assertRaises(Exception):
            validate_wav(b"invalid")

    def test_cli_loopback_and_raw_defaults(self):
        args = parser().parse_args(["--whisper-cli", "/fake/whisper", "--model", "/fake/model"])
        self.assertIsNone(args.host)
        self.assertFalse(args.lan)
        self.assertFalse(args.raw_audio)


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_reaps_subprocess(self):
        with tempfile.TemporaryDirectory(dir=LOCAL) as tmp:
            pidfile = Path(tmp) / "pid"
            script = "import os,time,pathlib; pathlib.Path(" + repr(str(pidfile)) + ").write_text(str(os.getpid())); time.sleep(30)"
            with self.assertRaises(TimeoutError):
                await command(sys.executable, "-c", script, timeout=0.3)
            pid = int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)


if __name__ == "__main__":
    unittest.main()
