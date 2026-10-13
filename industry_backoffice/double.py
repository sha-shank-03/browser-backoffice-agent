"""Authored semantic deterministic baseline exposed as a LOCAL HTTP double."""
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import uuid

from backoffice.domain import FIELDS, canonical
from .protocol import MAX_WIRE, strict_json

PHRASES = {
    "legal_name": ("legal name", "business name", "registered organisation"),
    "registration_ref": ("registration reference", "business identity reference", "vendor reference"),
    "country": ("country", "jurisdiction of operation"),
    "contact_email": ("contact email", "correspondence email", "vendor email"),
    "category": ("category", "supply classification"),
    "payment_terms": ("payment terms", "invoice terms", "settlement schedule"),
}


def semantic_decision(context):
    """Only public current observation/request/state; no case id or evaluator oracle."""
    observation, request, state = context["observation"], context["request"], context["state"]
    controls = observation["controls"]
    def action(name, **args):
        return name, args
    def named(label):
        matches = [c for c in controls if c["label"] == label and c["role"] in {"button", "link"}]
        return matches[0] if len(matches) == 1 else None
    def click(label):
        control = named(label)
        return action("click", ref=control["ref"]) if control else action("handoff", reason="unexpected_ui")
    path = observation["path"]
    if path == "/login":
        return click("Open fictional operator session")
    if path == "/vendors":
        search = [c for c in controls if c["role"] == "textbox" and c["label"] == "Registration reference search"]
        if len(search) != 1:
            return action("handoff", reason="unexpected_ui")
        if not state["search_complete"]:
            if search[0]["value"] != request["registration_ref"]:
                return action("fill_from_request", ref=search[0]["ref"], field="registration_ref")
            return click("Search")
        records = observation["records"]
        if records:
            if len(records) == 1 and records[0] == request:
                return action("finish", outcome="existing")
            return action("handoff", reason="conflicting_existing")
        return click("Register a vendor")
    if path == "/vendors/new":
        mapped = {}
        for control in controls:
            if control["role"] not in {"textbox", "combobox"}:
                continue
            candidates = [field for field, phrases in PHRASES.items()
                          if any(phrase in control["label"].lower() for phrase in phrases)]
            if len(candidates) != 1 or candidates[0] in mapped:
                return action("handoff", reason="unsupported_required_field")
            mapped[candidates[0]] = control
        if set(mapped) != set(FIELDS):
            return action("handoff", reason="insufficient_evidence")
        for field in FIELDS:
            control = mapped[field]
            if control["value"] != request[field]:
                return action("choose_from_request" if control["role"] == "combobox" else "fill_from_request",
                              ref=control["ref"], field=field)
        return click("Review vendor")
    if path == "/vendors/validation":
        return click("Continue to review") if named("Continue to review") else action("handoff", reason="validation_rejected")
    if path == "/vendors/review":
        return action("submit_approved" if state["approval_state"] == "APPROVED" else "request_review",
                      observation_id=observation["id"])
    if path == "/vendors/detail" and observation["records"] == [request]:
        return action("finish", outcome="created")
    return action("handoff", reason="insufficient_evidence")


class DoubleHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != "/v1/chat/completions" or self.headers.get("Authorization"):
            self.send_error(400)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_WIRE:
                raise ValueError()
            body = strict_json(self.rfile.read(size), MAX_WIRE)
            if body["model"] != "fixture/local-double-v1" or body["parallel_tool_calls"] is not False:
                raise ValueError()
            name, arguments = semantic_decision(strict_json(body["messages"][-1]["content"], MAX_WIRE))
            payload = canonical({"model": body["model"], "choices": [{"index": 0, "finish_reason": "tool_calls",
                       "message": {"role": "assistant", "content": None, "tool_calls": [
                       {"id": "call_" + uuid.uuid4().hex, "type": "function",
                        "function": {"name": name, "arguments": canonical(arguments)}}]}}],
                       "usage": None}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception:
            self.send_error(400)


class LocalDouble(AbstractContextManager):
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), DoubleHandler)
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        self.thread.start()
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
