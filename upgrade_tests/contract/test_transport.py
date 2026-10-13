"""UNEXECUTED U1 lease batch: sockets and owned child-process transport."""
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import subprocess
from threading import Event, Thread
import time
import unittest
from unittest.mock import patch

from industry_backoffice.double import LocalDouble
from industry_backoffice.protocol import Halt, ModelConfig, parse_reply, request_body
from industry_backoffice.transport import exchange
from upgrade_tests.unit.test_protocol import REQUEST, OBS


class FaultHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        self.server.received += 1
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.authorization = self.headers.get("Authorization")
        try:
            if self.server.mode == "slow_headers":
                time.sleep(.8)
            payload = b"SECRET-ERROR-ECHO" if self.server.status != 200 else b"x" * self.server.size
            self.send_response(self.server.status)
            self.send_header("Content-Length", str(len(payload)))
            if self.server.status == 302:
                self.send_header("Location", "http://127.0.0.1:1/not-allowed")
            self.end_headers()
            if self.server.mode == "slow_body":
                time.sleep(.8)
            self.wfile.write(payload)
        except OSError:
            pass


@contextmanager
def fault_server(status=200, mode="normal", size=2):
    server = ThreadingHTTPServer(("127.0.0.1", 0), FaultHandler)
    server.daemon_threads = True
    server.status, server.mode, server.size, server.received = status, mode, size, 0
    server.authorization = None
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


class TransportTests(unittest.TestCase):
    def config(self, server):
        return ModelConfig("local_double", "fixture/local-double-v1", f"http://127.0.0.1:{server.server_port}/v1/chat/completions", attempt_seconds=2)

    def test_real_http_function_round_trip(self):
        with LocalDouble() as double:
            config = ModelConfig("local_double", "fixture/local-double-v1", double.endpoint)
            # A complete semantic field set is required by the authored baseline.
            context = {"approval_state": "READY", "search_complete": False}
            observation = {**OBS, "path": "/login", "controls": [{"ref": "open", "role": "button", "label": "Open fictional operator session", "value": "", "options": []}]}
            raw = exchange(config, request_body(config, REQUEST, observation, context, []), time.monotonic() + 3, lambda: False)
            decision, message, usage = parse_reply(raw, observation, 512)
            self.assertEqual((decision.tool, decision.arguments), ("click", {"ref": "open"}))
            self.assertIsNone(usage)

    def test_status_halts_exactly_one_received_request(self):
        for status, code in ((401, "gateway_auth"), (402, "gateway_quota"), (403, "gateway_auth"),
                             (429, "gateway_rate_limit"), (500, "gateway_server"), (503, "gateway_server"),
                             (302, "gateway_http")):
            with self.subTest(status=status), fault_server(status=status) as server:
                with self.assertRaises(Halt) as caught:
                    exchange(self.config(server), b"{}", time.monotonic() + 3, lambda: False)
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(server.received, 1)  # No automatic retry or redirect.
                self.assertIsNone(server.authorization)
                self.assertNotIn("SECRET-ERROR-ECHO", str(caught.exception))

    def test_total_deadline_covers_headers_and_body(self):
        for mode in ("slow_headers", "slow_body"):
            with self.subTest(mode=mode), fault_server(mode=mode) as server:
                started = time.monotonic()
                with self.assertRaises(Halt) as caught:
                    exchange(self.config(server), b"{}", started + .4, lambda: False)
                self.assertEqual(caught.exception.code, "transport_deadline")
                self.assertLess(time.monotonic() - started, 1.6)
                self.assertLessEqual(server.received, 1)

    def test_cancel_during_send_or_read(self):
        with fault_server(mode="slow_body") as server:
            cancel = Event()
            trigger = Thread(target=lambda: (time.sleep(.35), cancel.set()), daemon=True)
            trigger.start()
            started = time.monotonic()
            with self.assertRaises(Halt) as caught:
                exchange(self.config(server), b"{}", started + 2, cancel.is_set)
            self.assertEqual(caught.exception.code, "cancelled")
            self.assertLess(time.monotonic() - started, 1.6)
            self.assertLessEqual(server.received, 1)
            trigger.join(timeout=1)

    def test_oversized_reply_halts(self):
        with fault_server(size=32769) as server:
            with self.assertRaises(Halt):
                exchange(self.config(server), b"{}", time.monotonic() + 2, lambda: False)
            self.assertEqual(server.received, 1)

    def test_proxy_environment_not_used(self):
        with fault_server(status=429) as server, patch.dict(os.environ, {"HTTP_PROXY": "http://127.0.0.1:1", "HTTPS_PROXY": "http://127.0.0.1:1"}):
            with self.assertRaises(Halt) as caught:
                exchange(self.config(server), b"{}", time.monotonic() + 3, lambda: False)
            self.assertEqual(caught.exception.code, "gateway_rate_limit")
            self.assertEqual(server.received, 1)

    def test_owned_transport_child_reaped_on_timeout(self):
        owned = []
        original = subprocess.Popen
        def capture(*args, **kwargs):
            process = original(*args, **kwargs)
            owned.append(process)
            return process
        with fault_server(mode="slow_body") as server, patch("industry_backoffice.transport.subprocess.Popen", capture):
            with self.assertRaises(Halt):
                exchange(self.config(server), b"{}", time.monotonic() + .4, lambda: False)
        self.assertEqual(len(owned), 1)
        self.assertIsNotNone(owned[0].poll())
        self.assertTrue(owned[0].stdin.closed)
        self.assertTrue(owned[0].stdout.closed)
