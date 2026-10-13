"""Private bounded pipe worker; no proxy, redirects, logs or retry machinery."""
import base64
import http.client
import sys
from urllib.parse import urlparse

from backoffice.domain import canonical
from .protocol import MAX_REPLY, MAX_WIRE, ModelConfig, strict_json


def main():
    sent = False
    connection = None
    try:
        wire = strict_json(sys.stdin.buffer.read(MAX_WIRE * 2 + 1), MAX_WIRE * 2)
        ModelConfig("local_double", "fixture/local-double-v1", wire["endpoint"]).validate()
        body = base64.b64decode(wire["body"], validate=True)
        if len(body) > MAX_WIRE or not 0 < wire["timeout"] <= 30:
            raise ValueError()
        parsed = urlparse(wire["endpoint"])
        connection = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=wire["timeout"])
        connection.connect()
        sent = None  # A partial send may have reached the service.
        connection.request("POST", parsed.path, body=body, headers={"Content-Type": "application/json"})
        sent = True
        response = connection.getresponse()
        # Error bodies may echo credentials/prompt text; deliberately do not read or return them.
        payload = response.read(MAX_REPLY + 1) if response.status == 200 else b""
        if len(payload) > MAX_REPLY:
            raise ValueError()
        result = {"status": response.status, "body": base64.b64encode(payload).decode(), "sent": sent}
    except Exception:
        result = {"error": "io", "sent": sent}
    finally:
        if connection:
            connection.close()
    sys.stdout.write(canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
