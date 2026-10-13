"""One owned transport child per inference; zero retries, monotonic deadline."""
from __future__ import annotations

import base64
import subprocess
import sys
import time
from pathlib import Path

from backoffice.domain import canonical
from .protocol import Halt, MAX_REPLY, strict_json


def exchange(config, body, deadline, cancelled, *, credential=None):
    config.validate()
    if config.mode == "gateway":
        # U1 has zero allocation. No environment/key/store is consulted by this code.
        raise Halt("live_dispatch_disabled", sent=False)
    if credential is not None:
        raise Halt("double_must_not_receive_credentials", sent=False)
    if cancelled():
        raise Halt("cancelled", sent=False)
    if time.monotonic() >= deadline:
        raise Halt("transport_deadline", sent=False)
    wire = canonical({"endpoint": config.endpoint, "body": base64.b64encode(body).decode(),
                      "timeout": min(config.attempt_seconds, deadline - time.monotonic())}).encode()
    process = subprocess.Popen([sys.executable, "-m", "industry_backoffice.transport_worker"],
                               cwd=Path(__file__).resolve().parents[1], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    # Once launched, even a parent timeout is conservatively ambiguous; never replay.
    first = True
    try:
        while True:
            if cancelled():
                raise Halt("cancelled", sent=None)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Halt("transport_deadline", sent=None)
            try:
                output, _ = process.communicate(wire if first else None, timeout=min(.05, remaining))
                break
            except subprocess.TimeoutExpired:
                first = False
        if process.returncode != 0:
            raise Halt("transport_child_failed", sent=None)
        reply = strict_json(output, MAX_REPLY * 2)
        if reply.get("error"):
            raise Halt("transport_io", sent=reply.get("sent"))
        status = reply.get("status")
        if type(status) is not int:
            raise Halt("transport_envelope", sent=None)
        if status != 200:
            code = ("gateway_auth" if status in {401, 403} else "gateway_quota" if status == 402 else
                    "gateway_rate_limit" if status == 429 else "gateway_server" if status >= 500 else
                    "gateway_http")
            raise Halt(code, sent=True)
        try:
            result = base64.b64decode(reply["body"], validate=True)
        except (ValueError, KeyError, TypeError) as exc:
            raise Halt("transport_envelope", sent=True) from exc
        if len(result) > MAX_REPLY:
            raise Halt("response_size", sent=True)
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                process.kill()  # Exact owned Popen child; no PID discovery or subtree kill.
                process.wait(timeout=.5)
        for pipe in (process.stdin, process.stdout):
            pipe.close()
