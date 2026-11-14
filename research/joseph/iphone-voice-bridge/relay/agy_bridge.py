"""Bridge between relay dialogue and headless agy Gemini 3.8 Flash High with MCP."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import uuid


MCP_CONFIG_PATH = Path.home() / ".gemini" / "config" / "mcp_config.json"


class ScopedMcpServer:
    """Context manager for temporary, isolated MCP server registration."""

    def __init__(self, name: str, command: str, args: list[str]):
        self.name = name
        self.command = command
        self.args = args

    def __enter__(self):
        self._add_server()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._remove_server()

    def _add_server(self):
        MCP_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        data = {"mcpServers": {}}
        if MCP_CONFIG_PATH.exists():
            try:
                data = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
            except Exception as exc:
                raise ValueError("Refusing to overwrite invalid existing MCP configuration") from exc
        servers = data.setdefault("mcpServers", {})
        servers[self.name] = {
            "command": self.command,
            "args": self.args,
            "disabled": False,
        }
        self._atomic_write(data)

    def _remove_server(self):
        if not MCP_CONFIG_PATH.exists():
            return
        try:
            data = json.loads(MCP_CONFIG_PATH.read_text(encoding="utf-8"))
            servers = data.get("mcpServers", {})
            if self.name in servers:
                del servers[self.name]
                self._atomic_write(data)
        except Exception as exc:
            raise RuntimeError("Failed to remove temporary MCP registration") from exc

    def _atomic_write(self, data: dict):
        content = json.dumps(data, indent=2) + "\n"
        with tempfile.NamedTemporaryFile("w", dir=MCP_CONFIG_PATH.parent, delete=False) as tf:
            tf.write(content)
            temp_name = tf.name
        os.replace(temp_name, MCP_CONFIG_PATH)


async def submit(
    transcript: str,
    state_dir: Path | str,
    timeout: float = 60.0,
    server_script: Path | str | None = None,
) -> dict:
    """Invoke headless agy with Gemini 3.8 Flash High and return authoritative plan.json.

    Never infers tool calls from prose. Requires real MCP execution to write plan.json.
    """
    state_path = Path(state_dir).resolve()
    state_path.mkdir(parents=True, exist_ok=True, mode=0o700)

    # Clean previous plan if present to prevent stale read
    plan_path = state_path / "plan.json"
    if plan_path.exists():
        plan_path.unlink()

    script_path = (
        Path(server_script).resolve()
        if server_script is not None
        else (Path(__file__).parent / "mcp_server.py").resolve()
    )
    if not script_path.is_file():
        raise FileNotFoundError(f"MCP server script not found: {script_path}")

    server_name = f"mandarin_plan_{uuid.uuid4().hex[:8]}"

    prompt = (
        "You interpret a student's intent for an OpenArms mock demo. Student text: " + json.dumps(transcript) + "\n"
        "Interpret natural phrasing, synonyms, disfluencies and speech-recognition errors; do not demand a fixed sentence. "
        "If the intent is to transfer the mandarin (a small orange) from station A to B, "
        "use call_mcp_tool to call submit_plan on server " + server_name +
        " with object='mandarin', source='A', destination='B'. This creates a placeholder preview only. "
        "Never submit a plan for negated, uncertain, unrelated, or unsupported destinations, objects, or instructions. "
        "If unclear, finish briefly asking for clarification without calling a tool. "
        "Do not use shell, files, browser or other tools. Never execute motion or claim physical results. "
        "After the tool returns, finish immediately."
    )

    cmd = [
        "agy",
        "--model",
        "gemini-3.8-flash-high",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--disable-slash-commands",
        "--print",
        prompt,
    ]

    with ScopedMcpServer(
        name=server_name,
        command=sys.executable,
        args=[str(script_path), str(state_path)],
    ):
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            cwd=str(state_path),
        )

        try:
            async with asyncio.timeout(timeout):
                stdout_bytes, stderr_bytes = await proc.communicate()
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Graceful termination to process group
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

            try:
                async with asyncio.timeout(2.0):
                    await proc.wait()
            except (asyncio.TimeoutError, asyncio.CancelledError):
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
            raise

    evidence = Path.home()/"Library/Logs/OpenArmsVoiceRelay/agent"/server_name
    evidence.mkdir(parents=True,exist_ok=True,mode=0o700)
    (evidence/"agent.jsonl").write_bytes(stdout_bytes or b"")
    (evidence/"stderr.log").write_bytes(stderr_bytes or b"")
    if proc.returncode:
        raise RuntimeError(f"agy exited {proc.returncode}")
    if not plan_path.exists():
        return {'status':'no_plan'}

    try:
        plan_data = json.loads(plan_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Failed to parse plan.json from {plan_path}: {exc}") from exc

    # Validate fixed schema
    if (
        plan_data.get("object") != "mandarin"
        or plan_data.get("source") != "A"
        or plan_data.get("destination") != "B"
    ):
        raise ValueError(
            f"Invalid plan format in {plan_path}: object must be 'mandarin', source 'A', destination 'B'. Got: {plan_data}"
        )

    calls = state_path/"mcp-calls.jsonl"
    if not calls.is_file():
        raise RuntimeError("No authoritative MCP call log")
    (evidence/"mcp-calls.jsonl").write_text(calls.read_text())
    (evidence/"plan.json").write_text(json.dumps(plan_data,indent=2))
    return plan_data
