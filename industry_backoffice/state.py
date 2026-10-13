"""Persisted U1 counters, ReviewV2 and explicit human approval."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
import sqlite3
import time

from backoffice.domain import canonical, digest, review_contract
from . import VERSION
from .protocol import Halt, PROMPT_VERSION

MAPPING_VERSION = "local-v2-six-fields.1"
REVIEW_KEYS = {"schema_version", "task_id", "request_hash", "action", "draft_id", "revision",
               "session_id", "values", "source_values", "target_identity", "mapping_version", "payload_hash"}
LIMITS = {"decisions": 40, "calls": 40, "output_tokens": 8192, "active_seconds": 300.0}
EVENT_KEYS = {"request_hash", "target_identity", "mode", "model", "prompt_version", "code_version",
              "config_hash", "tool", "call_id", "observation_hash", "decision_hash", "usage_tokens",
              "usage_known", "cost_inr", "sent", "code", "status", "review_digest", "approval_digest",
              "expires_at", "body_hash", "method", "path", "reason", "outcome", "manual", "phase"}


def make_review(task_id, request, draft, target_identity, payload_hash):
    base = review_contract(task_id, request, draft)
    base.update(schema_version=2, source_values=dict(request), target_identity=target_identity,
                mapping_version=MAPPING_VERSION, payload_hash=payload_hash)
    validate_review(base, request, task_id, target_identity)
    return base


def validate_review(review, request, task_id, target_identity):
    if not isinstance(review, dict) or set(review) != REVIEW_KEYS:
        raise Halt("review_schema")
    if (review["schema_version"] != 2 or review["task_id"] != task_id
            or review["request_hash"] != digest(request) or review["action"] != "create_vendor"
            or review["values"] != request or review["source_values"] != request
            or review["target_identity"] != target_identity or review["mapping_version"] != MAPPING_VERSION
            or not isinstance(review["payload_hash"], str) or not re.fullmatch(r"[0-9a-f]{64}", review["payload_hash"])):
        raise Halt("review_binding")
    review_contract(task_id, request, review)
    return review


class Store:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.connection = sqlite3.connect(run_dir / "workflow-v2.db", timeout=2)
        self.connection.execute("CREATE TABLE IF NOT EXISTS run (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
        self.connection.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)")
        row = self.connection.execute("SELECT data FROM run WHERE id=1").fetchone()
        self.data = json.loads(row[0]) if row else {}
        if self.data and self.data.get("schema_version") != 2:
            self.close()
            raise Halt("workflow_schema")

    def initialize(self, request, task_id, target_identity, config):
        if self.data:
            raise Halt("run_exists")
        self.data = {"schema_version": 2, "task_id": task_id, "request": dict(request),
                     "request_hash": digest(request), "target_identity": target_identity,
                     "code_version": VERSION, "prompt_version": PROMPT_VERSION, "config": asdict(config),
                     "config_hash": digest(asdict(config)), "state": "READY", "steps": 0, "calls": 0,
                     "active_seconds": 0.0, "version": 0, "provider": config.mode,
                     "generated_tokens": 0, "reserved_output_tokens": 0, "usage_unavailable_calls": 0,
                     "cost_inr": None, "pending_transport": None, "history": [], "call_ids": [],
                     "review": None, "approval": None, "commit_attempted": False, "commit_dispatched": False,
                     "outcome": None, "reason": None, "resume_path": "/login", "last_result": None,
                     "approval_wait_excluded": True}
        self.save("run_created", {k: self.data[k] for k in ("request_hash", "target_identity", "prompt_version", "code_version", "config_hash")})

    def save(self, kind, event=None):
        event = event or {}
        if set(event) - EVENT_KEYS:
            raise Halt("event_field_not_allowlisted")
        if len(canonical(event).encode()) > 4096:
            raise Halt("event_size")
        self.data["version"] += 1
        with self.connection:
            self.connection.execute("INSERT INTO run VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data", (canonical(self.data),))
            self.connection.execute("INSERT INTO events(at,kind,data) VALUES(?,?,?)", (time.time(), kind, canonical(event)))

    def export(self):
        with (self.run_dir / "events-v2.jsonl").open("w", encoding="utf-8") as output:
            for seq, at, kind, raw in self.connection.execute("SELECT seq,at,kind,data FROM events ORDER BY seq"):
                output.write(canonical({"seq": seq, "at": at, "kind": kind, "data": json.loads(raw)}) + "\n")
        summary = {k: self.data[k] for k in ("schema_version", "task_id", "state", "outcome", "reason", "steps", "calls", "active_seconds", "provider", "generated_tokens", "reserved_output_tokens", "usage_unavailable_calls", "cost_inr", "commit_attempted", "commit_dispatched", "approval_wait_excluded")}
        (self.run_dir / "actor-result-v2.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        if self.data["review"]:
            (self.run_dir / "review-v2.json").write_text(json.dumps(self.data["review"], indent=2) + "\n", encoding="utf-8")

    def close(self):
        self.connection.close()


class ActiveClock:
    """Human wait is excluded; every actor invocation uses remaining persisted budget."""
    def __init__(self, store, monotonic=time.monotonic):
        self.store, self.monotonic = store, monotonic
        self.base = store.data["active_seconds"]
        self.started = monotonic()

    def elapsed(self):
        return self.base + self.monotonic() - self.started

    def remaining(self):
        return LIMITS["active_seconds"] - self.elapsed()

    def checkpoint(self):
        self.store.data["active_seconds"] = self.elapsed()
        if (self.store.run_dir / "cancel.request").exists():
            raise Halt("cancelled")
        if self.remaining() <= 0:
            raise Halt("active_budget")

    def persist(self):
        self.store.data["active_seconds"] = self.elapsed()
        self.store.save("active_accounted")


def reserve_call(store, config, clock):
    clock.checkpoint()
    data = store.data
    if data["pending_transport"]:
        raise Halt("ambiguous_inference_requires_operator")
    if data["calls"] >= LIMITS["calls"] or data["steps"] >= LIMITS["decisions"]:
        raise Halt("decision_budget")
    if data["reserved_output_tokens"] + config.max_output_tokens > LIMITS["output_tokens"]:
        raise Halt("token_budget")
    data["calls"] += 1
    data["reserved_output_tokens"] += config.max_output_tokens
    data["pending_transport"] = {"reserved_tokens": config.max_output_tokens,
                                 "reserved_seconds": min(config.attempt_seconds, clock.remaining())}
    store.save("inference_reserved", {"mode": config.mode, "model": config.model, "cost_inr": None})


def settle_call(store, tokens, sent):
    reservation = store.data["pending_transport"]
    if tokens is None:
        store.data["usage_unavailable_calls"] += 1
    else:
        store.data["generated_tokens"] += tokens
        store.data["reserved_output_tokens"] -= reservation["reserved_tokens"] - tokens
    store.data["pending_transport"] = None
    store.save("inference_settled", {"usage_tokens": tokens, "usage_known": tokens is not None,
                                    "cost_inr": None, "sent": sent})


def approve(store, supplied_digest, now=None):
    now = time.time() if now is None else now
    data = store.data
    if data["state"] != "AWAITING_APPROVAL" or data["commit_attempted"] or data["approval"]:
        raise Halt("approval_state")
    validate_review(data["review"], data["request"], data["task_id"], data["target_identity"])
    if supplied_digest != digest(data["review"]):
        raise Halt("approval_digest")
    if (store.run_dir / "cancel.request").exists():
        raise Halt("cancelled")
    data["approval"] = {"digest": supplied_digest, "expires_at": now + 300,
                        "consumed": False, "manual": True}
    data["state"] = "APPROVED"
    store.save("manual_approval", {"approval_digest": supplied_digest, "expires_at": now + 300, "manual": True})


def consume_approval(store, fresh_review, now=None):
    now = time.time() if now is None else now
    data = store.data
    approval = data["approval"] or {}
    validate_review(fresh_review, data["request"], data["task_id"], data["target_identity"])
    if (data["state"] != "APPROVED" or approval.get("consumed") or not approval.get("manual")
            or approval.get("expires_at", 0) < now or approval.get("digest") != digest(fresh_review)
            or digest(data["review"]) != digest(fresh_review) or data["commit_attempted"]
            or (store.run_dir / "cancel.request").exists()):
        raise Halt("approval_freshness")
    approval["consumed"] = True
    data["commit_attempted"] = True
    data["state"] = "SUBMITTING"
    store.save("approval_consumed", {"approval_digest": approval["digest"], "body_hash": fresh_review["payload_hash"]})
