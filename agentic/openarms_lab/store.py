"""Durable notebook and passive session snapshots. No device imports or startup hooks."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

class Store:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, snapshot TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, session_id TEXT, time REAL, kind TEXT, data TEXT)')
        self.db.commit()

    def save(self, snapshot):
        self.db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)', (snapshot['session_id'], json.dumps(snapshot)))
        self.db.commit()

    def load(self, sid):
        row = self.db.execute('SELECT snapshot FROM sessions WHERE id=?', (sid,)).fetchone()
        return json.loads(row[0]) if row else None

    def event(self, sid, kind, **data):
        timestamp = time.time()
        e = {**{key: data.get(key) for key in ('turn_id', 'task_id', 'trial_id', 'request_id',
                                               'skill_id', 'skill_version', 'evidence_ids',
                                               'revision', 'sequence', 'provenance')},
             'event_id': str(uuid.uuid4()), 'session_id': sid, 'time': timestamp,
             'timestamp': timestamp, 'kind': kind, 'data': data}
        self.db.execute('INSERT INTO events VALUES (?,?,?,?,?)', (e['event_id'], sid, e['time'], kind, json.dumps(data)))
        self.db.commit()
        return e

    def list_sessions(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT snapshot FROM sessions ORDER BY rowid DESC LIMIT 50')]

    def close(self):
        self.db.close()
