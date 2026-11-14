"""Session notebook: the running record the brain reads back as context."""
import json
import re
import time
from pathlib import Path
from typing import Any

KINDS = ("prediction", "plan", "result", "observation", "help")
SESSIONS = Path(__file__).resolve().parents[2] / "outputs" / "sessions"


class Notebook:
    def __init__(self, session_id: str) -> None:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):  # it becomes a file name
            raise ValueError(f"bad session id {session_id!r}")
        self.session_id, self._entries = session_id, []

    @classmethod
    def load(cls, session_id: str) -> "Notebook":
        nb = cls(session_id)
        nb._entries = json.loads((SESSIONS / f"{session_id}.json").read_text())["entries"]
        return nb

    def add(self, kind: str, **data: Any) -> None:
        if kind not in KINDS:
            raise ValueError(f"'{kind}' is not a notebook kind; use one of {', '.join(KINDS)}.")
        self._entries.append({"kind": kind, "time": time.strftime("%H:%M:%S"), **data})

    def entries(self) -> list[dict]:
        return list(self._entries)

    def save(self) -> Path:
        SESSIONS.mkdir(parents=True, exist_ok=True)
        path = SESSIONS / f"{self.session_id}.json"
        path.write_text(json.dumps({"session_id": self.session_id, "entries": self._entries}, indent=2))
        return path

    def as_text(self) -> str:
        lines = []
        for e in self._entries:
            data = ", ".join(f"{k}={json.dumps(v)}" for k, v in e.items() if k not in ("kind", "time"))
            lines.append(f"[{e['time']}] {e['kind']}: {data}")
        return "\n".join(lines) or "(notebook is empty)"
