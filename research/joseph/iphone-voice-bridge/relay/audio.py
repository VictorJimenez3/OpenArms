"""Bounded PCM endpointing and cancellable local Mac speech commands."""
import asyncio
import io
import math
import os
import struct
import tempfile
import wave
from pathlib import Path

RATE = 16000
MAX_FRAME = 6400  # 200 ms PCM; client may send shorter frames
MAX_WAV = 4 * 1024 * 1024


def pcm_wav(pcm: bytes) -> bytes:
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm)
    return out.getvalue()


def validate_wav(data: bytes) -> None:
    if len(data) > MAX_WAV:
        raise ValueError("Reply audio exceeds size limit")
    with wave.open(io.BytesIO(data), "rb") as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, RATE, "NONE"):
            raise ValueError("Reply audio must be mono PCM16 WAV at 16000 Hz")
        frames = wav.getnframes()
        if not frames or len(wav.readframes(frames)) != frames * 2:
            raise ValueError("Empty or truncated reply WAV")


class Endpoint:
    """20 ms analysis windows; duration depends on samples, never packet count.

    Retains 200 ms pre-roll, requires 120 ms voiced audio, ends after 600 ms
    silence, and cuts at 15 s including pre-roll. At most one utterance per feed.
    """
    window = 640
    preroll_bytes = 6400
    max_bytes = RATE * 2 * 15
    min_voiced = RATE * 2 * 120 // 1000
    silence_bytes = RATE * 2 * 600 // 1000

    def __init__(self, threshold: float = 600):
        self.threshold = threshold
        self.reset()

    def reset(self):
        self.pending = bytearray()
        self.pre = bytearray()
        self.audio = bytearray()
        self.voiced = 0
        self.silent = 0
        self.active = False

    def feed(self, frame: bytes) -> bytes | None:
        if not frame or len(frame) % 2 or len(frame) > MAX_FRAME:
            self.reset()
            raise ValueError("PCM frames must contain 1 to 3200 complete int16 samples")
        self.pending.extend(frame)
        while len(self.pending) >= self.window:
            chunk = bytes(self.pending[:self.window])
            del self.pending[:self.window]
            samples = struct.unpack("<320h", chunk)
            loud = math.sqrt(sum(s * s for s in samples) / len(samples)) >= self.threshold
            if not self.active:
                if not loud:
                    self.pre.extend(chunk)
                    del self.pre[:-self.preroll_bytes]
                    continue
                self.active = True
                self.audio.extend(self.pre)
                self.pre.clear()
            self.audio.extend(chunk)
            self.voiced += len(chunk) if loud else 0
            self.silent = 0 if loud else self.silent + len(chunk)
            if self.silent >= self.silence_bytes or len(self.audio) >= self.max_bytes:
                result = bytes(self.audio) if self.voiced >= self.min_voiced else None
                self.reset()
                return result
        return None


async def command(*args: str, timeout: float = 90) -> None:
    # Do not pipe diagnostic output: tools may echo private spoken text, and an
    # unbounded pipe could consume memory. Failures identify the executable.
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(timeout):
            code = await proc.wait()
        if code:
            raise RuntimeError(f"{Path(args[0]).name} exited with code {code}")
    finally:
        if proc.returncode is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            try:
                await asyncio.wait_for(proc.wait(), 2)
            except TimeoutError:
                proc.kill()
                await proc.wait()


class MacSpeech:
    def __init__(self, whisper_cli: Path, model: Path, scratch: Path, voice: str | None = None):
        self.whisper_cli = whisper_cli
        self.model = model
        self.scratch = scratch
        self.voice = voice

    async def transcribe(self, pcm: bytes) -> str:
        with tempfile.TemporaryDirectory(prefix="stt-", dir=self.scratch) as tmp:
            root = Path(tmp)
            source = root / "input.wav"
            source.write_bytes(pcm_wav(pcm))
            source.chmod(0o600)
            output = root / "transcript"
            await command(str(self.whisper_cli), "-m", str(self.model), "-f", str(source), "-l", "en", "-otxt", "-of", str(output), "-nt")
            text_file = output.with_suffix(".txt")
            if text_file.stat().st_size > 16384:
                raise ValueError("Recognition output exceeds limit")
            return text_file.read_text().strip()

    async def synthesize(self, text: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="tts-", dir=self.scratch) as tmp:
            root = Path(tmp)
            source, target = root / "reply.aiff", root / "reply.wav"
            text_path = root / "reply.txt"
            text_path.write_text(text)
            text_path.chmod(0o600)
            voice = ["-v", self.voice] if self.voice else []
            await command("/usr/bin/say", *voice, "-f", str(text_path), "-o", str(source))
            await command("/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", str(source), str(target))
            if target.stat().st_size > MAX_WAV:
                raise ValueError("Reply audio exceeds size limit")
            data = target.read_bytes()
            validate_wav(data)
            return data
