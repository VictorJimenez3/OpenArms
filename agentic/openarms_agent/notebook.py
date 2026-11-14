"""Session notebook: the running record the brain reads back as context."""
import json
import os
import tempfile
from copy import deepcopy
import re
import time
from pathlib import Path
from typing import Any

KINDS = ("prediction", "plan", "result", "observation", "help", "control", "skill")
SESSIONS = Path(__file__).resolve().parents[2] / "outputs" / "sessions"


class Notebook:
    def __init__(self, session_id: str, directory: Path | None = None) -> None:
        if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", session_id):  # it becomes a file name
            raise ValueError(f"bad session id {session_id!r}")
        self.session_id, self._entries = session_id, []
        self.directory = SESSIONS if directory is None else Path(directory)

    @classmethod
    def load(cls, session_id: str, directory: Path | None = None) -> "Notebook":
        nb = cls(session_id, directory)
        nb._entries = json.loads((nb.directory / f"{session_id}.json").read_text())["entries"]
        return nb

    def add(self, kind: str, **data: Any) -> None:
        if kind not in KINDS:
            raise ValueError(f"'{kind}' is not a notebook kind; use one of {', '.join(KINDS)}.")
        self._entries.append({"kind": kind, "time": time.strftime("%H:%M:%S"), **data})

    def entries(self) -> list[dict]:
        return deepcopy(self._entries)

    def save(self) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{self.session_id}.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, delete=False) as handle:
            temp = Path(handle.name)
            try:
                json.dump({"session_id": self.session_id, "entries": self._entries}, handle, indent=2)
                handle.close()
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
        return path

    def as_text(self) -> str:
        lines = []
        for e in self._entries:
            data = ", ".join(f"{k}={json.dumps(v)}" for k, v in e.items() if k not in ("kind", "time"))
            lines.append(f"[{e['time']}] {e['kind']}: {data}")
        return "\n".join(lines) or "(notebook is empty)"
