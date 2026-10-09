from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
import time
import unittest

from backoffice.domain import ProtocolError, TOOLS, WorkflowError
from backoffice.ollama import OllamaProvider
from evaluation.fixtures import load_suite


def context():
    return {"schema_version": 1, "request": load_suite()["cases"]["happy"]["request"], "state": "CREATED", "remaining_steps": 40,
            "last_result": None, "observation": {"id": "obs", "url": "http://127.0.0.1:8000/login", "title": "Operator session",
            "text": "Fictional session", "records": [], "controls": [{"ref": "c0", "role": "button", "label": "Open fictional operator session", "value": "", "options": []}]}}


def response(tool="click", arguments=None, **extra):
    return {"done": True, "message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": tool, "arguments": arguments if arguments is not None else {"ref": "c0"}}}]}, **extra}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.server.requests.append({"path": self.path, "body": json.loads(self.rfile.read(int(self.headers["Content-Length"]))),
                                     "content_type": self.headers["Content-Type"]})
        spec = self.server.responses.pop(0)
        time.sleep(spec.get("delay", 0))
        body = spec.get("body", response())
        encoded = json.dumps(body).encode() if not isinstance(body, bytes) else body
        self.send_response(spec.get("status", 200))
        if "location" in spec:
            self.send_header("Location", spec["location"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            if spec.get("chunk_delay"):
                size = max(1, len(encoded) // 6)
                for offset in range(0, len(encoded), size):
                    self.wfile.write(encoded[offset:offset + size])
                    self.wfile.flush()
                    time.sleep(spec["chunk_delay"])
            else:
                self.wfile.write(encoded)
        except ConnectionError:
            pass


@contextmanager
def double(responses):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = False
    server.requests, server.responses = [], list(responses)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}/api/chat"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


class OllamaContracts(unittest.TestCase):
    def test_round_trip_schemas_usage_and_tool_result_feedback(self):
        with double([{"body": response(eval_count=12, prompt_eval_count=31, total_duration=123)},
                     {"body": response("observe", {})}]) as (server, endpoint):
            provider = OllamaProvider("local-protocol-double", endpoint, allow_live=True)
            first = provider.next_decision(context(), TOOLS)
            self.assertEqual(first, {"tool": "click", "arguments": {"ref": "c0"}})
            self.assertEqual(provider.last_usage["eval_count"], 12)
            current = context()
            current["last_result"] = {"status": "completed", "tool": "click"}
            provider.next_decision(current, TOOLS)
            request = server.requests[0]
            self.assertEqual(request["path"], "/api/chat")
            self.assertEqual(request["content_type"], "application/json")
            self.assertFalse(request["body"]["stream"])
            self.assertEqual(request["body"]["options"], {"temperature": 0, "num_predict": 512})
            schemas = request["body"]["tools"]
            self.assertEqual({s["function"]["name"] for s in schemas}, set(TOOLS))
            self.assertTrue(all(s["function"]["parameters"]["additionalProperties"] is False for s in schemas))
            messages = server.requests[1]["body"]["messages"]
            tool = next(m for m in messages if m["role"] == "tool")
            self.assertEqual(tool["tool_name"], "click")
            self.assertEqual(json.loads(tool["content"]), current["last_result"])
            self.assertEqual([m["role"] for m in messages], ["system", "user", "assistant", "tool", "user"])
            self.assertIsNone(provider.last_usage["eval_count"])

    def test_malformed_multiple_unknown_calls_and_usage_are_rejected(self):
        multiple = response()
        multiple["message"]["tool_calls"] *= 2
        examples = [b"not json", response(done=False), multiple, response("fetch", {"url": "https://unsafe.example"}),
                    response(eval_count=True), response(eval_count=513), response(eval_count=-1),
                    {"done": True, "message": {"role": "assistant", "content": "success"}}]
        for value in examples:
            with self.subTest(value=value), double([{"body": value}]) as (_, endpoint):
                with self.assertRaises(ProtocolError):
                    OllamaProvider("local-protocol-double", endpoint, allow_live=True).next_decision(context(), TOOLS)

    def test_endpoint_opt_in_loopback_and_timeout_bounds(self):
        with self.assertRaises(WorkflowError):
            OllamaProvider("model")
        for endpoint in ("https://127.0.0.1:1/api/chat", "http://localhost:1/api/chat", "http://example.com:1/api/chat",
                         "http://127.0.0.1:1/api/chat?x=1", "http://user:pass@127.0.0.1:1/api/chat", "http://127.0.0.1:1/other"):
            with self.subTest(endpoint=endpoint), self.assertRaises(WorkflowError):
                OllamaProvider("model", endpoint, allow_live=True)
        with self.assertRaises(WorkflowError):
            OllamaProvider("model", allow_live=True, timeout=31)

    def test_oversized_response_context_redirect_error_and_timeout(self):
        specs = [{"body": b"x" * (16 * 1024 + 1)}, {"status": 303, "location": "http://127.0.0.1:9/api/chat"},
                 {"status": 503}, {"delay": 0.15}]
        for spec in specs:
            with self.subTest(spec=spec.get("status", "bounded")), double([spec]) as (server, endpoint):
                with self.assertRaises(WorkflowError):
                    OllamaProvider("double", endpoint, allow_live=True, timeout=0.03).next_decision(context(), TOOLS)
                self.assertEqual(len(server.requests), 1)
        with double([]) as (server, endpoint):
            provider = OllamaProvider("double", endpoint, allow_live=True)
            huge = {**context(), "last_result": "x" * (64 * 1024)}
            with self.assertRaises(ProtocolError):
                provider.next_decision(huge, TOOLS)
            self.assertFalse(server.requests)

    def test_total_deadline_stops_trickled_response(self):
        with double([{"chunk_delay": 0.02}]) as (_, endpoint):
            provider = OllamaProvider("double", endpoint, allow_live=True, timeout=0.055)
            started = time.monotonic()
            with self.assertRaises(WorkflowError):
                provider.next_decision(context(), TOOLS)
            self.assertLess(time.monotonic() - started, 0.2)
