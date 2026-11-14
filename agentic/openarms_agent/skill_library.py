"""A small persistent registry for reviewed, reusable plan skills.

The registry stores exact phrases and their plan-action steps. It deliberately
does not infer aliases or fill parameters. A caller must decide when a cold
candidate is safe to promote, and the normal validator must still check the
resolved steps against live state before execution.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .catalog import expand
from .types import Step


MAX_SKILL_STEPS = 6
MAX_TEXT_LENGTH = 240


def _normalize(phrase: str, *, allow_empty: bool = False, label: str = "Skill phrases") -> str:
    if not isinstance(phrase, str):
        raise ValueError(f"{label} must be text.")
    if len(phrase) > MAX_TEXT_LENGTH:
        raise ValueError(f"{label} cannot exceed {MAX_TEXT_LENGTH} characters.")
    normalized = re.sub(r"\s+", " ", phrase).strip().casefold()
    if not normalized and not allow_empty:
        raise ValueError(f"{label} cannot be empty.")
    return normalized


class SkillLibrary:
    """Versioned exact-match skills backed by one JSON file.

    The file uses a single-writer convention. Writes go to a temporary file in
    the destination directory and then replace the destination atomically, so
    a restart observes either the old complete store or the new complete store.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def resolve(self, text: str, *, scope: str = "") -> list[Step] | None:
        key = _normalize(text)
        scope_key = _normalize(scope, allow_empty=True, label="Skill scopes")
        store = self._load()
        entry = store["skills"].get(scope_key, {}).get(key)
        if entry is None:
            return None
        versions = entry["versions"]
        version = entry["active_version"]
        selected = next((item for item in versions if item["version"] == version), None)
        if selected is None:
            raise ValueError(f"Skill {key!r} has no active version {version}.")
        return copy.deepcopy(selected["steps"])

    def promote(self, phrase: str, steps: list[Step], *, scope: str = "") -> int:
        key = _normalize(phrase)
        scope_key = _normalize(scope, allow_empty=True, label="Skill scopes")
        checked = self._validate_steps(steps)
        store = self._load()
        entries = store["skills"].setdefault(scope_key, {})
        entry = entries.get(key)
        if entry is None:
            entry = {"active_version": 0, "versions": []}
            entries[key] = entry
        versions = entry["versions"]
        version = entry["active_version"] + 1
        if version != len(versions) + 1:
            raise ValueError(f"Skill {key!r} has non-sequential versions.")
        versions.append({"version": version, "steps": checked})
        entry["active_version"] = version
        self._write(store)
        return version

    @staticmethod
    def _validate_steps(steps: list[Step]) -> list[Step]:
        if not isinstance(steps, list):
            raise ValueError("Skill steps must be a list.")
        if not 1 <= len(steps) <= MAX_SKILL_STEPS:
            raise ValueError(f"Skill steps must contain 1 to {MAX_SKILL_STEPS} actions.")
        if not all(isinstance(step, dict) for step in steps):
            raise ValueError("Skill steps must be objects.")
        candidate = copy.deepcopy(steps)
        # `expand` is the catalog's schema gate. Store the original macro
        # actions because they are the stable, reviewable skill representation.
        try:
            expand({"plan_id": "skill-validation", "student_instruction": "", "steps": candidate})
        except (TypeError, KeyError, ValueError) as exc:
            raise ValueError(f"Invalid skill steps: {exc}") from exc
        return candidate

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"skills": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read skill library {self.path}: {exc}") from exc
        if not isinstance(data, dict) or not isinstance(data.get("skills"), dict):
            raise ValueError("Skill library must contain a skills object.")
        for scope, entries in data["skills"].items():
            if not isinstance(scope, str) or not isinstance(entries, dict):
                raise ValueError("Skill library scopes must contain objects keyed by phrase.")
            for key, entry in entries.items():
                if not isinstance(key, str) or not isinstance(entry, dict):
                    raise ValueError("Skill library entries must be objects keyed by phrase.")
                if not isinstance(entry.get("active_version"), int) or not isinstance(entry.get("versions"), list):
                    raise ValueError(f"Skill {key!r} has an invalid version record.")
                for expected, item in enumerate(entry["versions"], start=1):
                    if (
                        not isinstance(item, dict)
                        or item.get("version") != expected
                        or not isinstance(item.get("steps"), list)
                    ):
                        raise ValueError(f"Skill {key!r} has an invalid version {expected}.")
                if entry["active_version"] < 1 or entry["active_version"] > len(entry["versions"]):
                    raise ValueError(f"Skill {key!r} has an invalid active version.")
        return data

    def _write(self, data: dict[str, Any]) -> None:
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=parent, prefix=f".{self.path.name}.", delete=False
            ) as handle:
                temporary = Path(handle.name)
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
