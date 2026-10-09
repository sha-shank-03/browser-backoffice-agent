"""Run state and ordered events, separate from the portal database."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

from .domain import WorkflowError, canonical, digest


@contextmanager
def run_lock(run_dir: Path):
    path = run_dir / "run.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise WorkflowError("Run already owned; inspect a stale lock manually after a crash") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


class Store:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.connection = sqlite3.connect(run_dir / "workflow.db", timeout=2)
        self.connection.execute("CREATE TABLE IF NOT EXISTS run (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)")
        row = self.connection.execute("SELECT data FROM run WHERE id=1").fetchone()
        self.data = json.loads(row[0]) if row else {}
        if self.data and self.data.get("schema_version") != 1:
            self.close()
            raise WorkflowError("Unsupported workflow schema version")
        if self.data:
            for key, value in {"generated_tokens": 0, "protocol_errors": 0, "reauth_attempts": 0,
                               "session_opened": False, "last_result": None, "live_provider": False}.items():
                self.data.setdefault(key, value)

    def initialize(self, request: dict, task_id: str):
        if self.data:
            raise WorkflowError("Run already exists; use resume")
        self.data = {"schema_version": 1, "task_id": task_id, "request": request,
                     "request_hash": digest(request), "state": "CREATED", "steps": 0,
                     "active_seconds": 0.0, "version": 0, "provider": "scripted",
                     "review": None, "approval": None, "commit_attempted": False,
                     "outcome": None, "reason": None, "resume_path": "/login"}
        self.save("run_created", {"request_hash": self.data["request_hash"]})

    def save(self, kind: str, event: dict | None = None):
        self.data["version"] += 1
        with self.connection:
            self.connection.execute("INSERT INTO run(id,data) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (canonical(self.data),))
            self.connection.execute("INSERT INTO events(at,kind,data) VALUES(?,?,?)", (time.time(), kind, canonical(event or {})))

    def export(self):
        records = self.connection.execute("SELECT seq,at,kind,data FROM events ORDER BY seq").fetchall()
        with (self.run_dir / "events.jsonl").open("w", encoding="utf-8") as output:
            for seq, at, kind, data in records:
                output.write(canonical({"seq": seq, "at": at, "kind": kind, "data": json.loads(data)}) + "\n")
        (self.run_dir / "actor-result.json").write_text(json.dumps({k: self.data.get(k) for k in
            ("schema_version", "task_id", "state", "outcome", "reason", "steps", "provider", "commit_attempted",
             "active_seconds", "generated_tokens", "usage_unavailable_calls", "protocol_errors", "reauth_attempts")}, indent=2), encoding="utf-8")

    def close(self):
        self.connection.close()
