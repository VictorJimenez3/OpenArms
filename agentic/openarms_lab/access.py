"""Session-scoped bearer grants. Only hashes are persisted; tokens never enter URLs."""
from __future__ import annotations
import hashlib
import secrets
import sqlite3
from pathlib import Path


class SessionAccess:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS grants (session TEXT PRIMARY KEY, digest TEXT NOT NULL)')
        self.db.commit()
        path.chmod(0o600)

    @staticmethod
    def digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def issue(self, sid: str) -> str:
        token = secrets.token_urlsafe(32)
        self.db.execute('INSERT OR REPLACE INTO grants VALUES (?,?)', (sid, self.digest(token)))
        self.db.commit()
        return token

    def permits(self, sid: str, token: str) -> bool:
        row = self.db.execute('SELECT digest FROM grants WHERE session=?', (sid,)).fetchone()
        return bool(row and token and secrets.compare_digest(row[0], self.digest(token)))

    def close(self):
        self.db.close()
