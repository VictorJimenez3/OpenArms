"""Async lifecycle for a MuJoCo renderer and its video encoder."""
from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
from contextlib import suppress


async def run_worker(folder, command, on_progress=None):
    # Own the whole process group: VideoRecorder starts a separate ffmpeg process.
    launch = asyncio.create_task(asyncio.create_subprocess_exec(
        sys.executable, '-m', 'agentic.openarms_lab.mujoco_worker', str(folder), json.dumps(command),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
    ))
    process = None
    result = None
    try:
        process = await asyncio.shield(launch)
        while line := await process.stdout.readline():
            message = json.loads(line)
            if message['kind'] == 'progress' and on_progress:
                await on_progress(message)
            else:
                result = message
        if await process.wait() or result is None:
            reason = (result or {}).get('reason', 'MuJoCo worker exited before producing evidence.')
            raise RuntimeError(reason)
        return result
    finally:
        if process is None:
            # Cancellation can arrive while the OS is still creating the process.
            process = await launch
        if process.returncode is None:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            await process.communicate()
