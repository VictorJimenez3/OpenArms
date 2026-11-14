"""Explicit local tool smoke check; generated audio only, no microphone."""
import argparse
import asyncio
import io
import os
from pathlib import Path
import tempfile
import wave

from audio import MacSpeech, validate_wav
from relay import private_dir


async def check(args):
    scratch = private_dir(Path(__file__).parent / ".local" / "smoke")
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        speech = MacSpeech(args.whisper_cli, args.model, Path(tmp), args.voice)
        wav = await speech.synthesize("Confirm.")
        validate_wav(wav)
        print(f"PASS: say + afconvert generated mono PCM16/16000 Hz WAV ({len(wav)} bytes)")
        if not args.tts_only:
            with wave.open(io.BytesIO(wav), "rb") as source:
                pcm = source.readframes(source.getnframes())
            text = await speech.transcribe(pcm)
            print(f"Synthetic test transcript: {text!r}")
            if "confirm" not in text.lower():
                raise AssertionError("Expected 'confirm' in recognition of generated test speech")
            print("PASS: local whisper.cpp recognized generated speech")
    print("PASS: temporary test audio and transcripts removed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tts-only", action="store_true")
    parser.add_argument("--whisper-cli", type=lambda p: Path(p).expanduser().resolve())
    parser.add_argument("--model", type=lambda p: Path(p).expanduser().resolve())
    parser.add_argument("--voice")
    args = parser.parse_args()
    if not args.tts_only and (args.whisper_cli is None or args.model is None):
        parser.error("Real recognition requires --whisper-cli and --model")
    os.umask(0o077)
    asyncio.run(check(args))
