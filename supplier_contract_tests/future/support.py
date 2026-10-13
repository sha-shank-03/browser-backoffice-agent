"""Test-only loopback server. Never imported by the adapter or pure suite."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from threading import Thread
from urllib.parse import urlsplit

LEASE_VALUE = "u2a-local-double-and-browser-explicit-main-lease"


def require_lease():
    if os.environ.get("BB_U2A_LOCAL_DOUBLE_LEASE") != LEASE_VALUE:
        raise RuntimeError("Future local-double tests require their separate main lease")


@contextmanager
def loopback_server(*, replies=(), html=None):
    require_lease() # Before socket or thread creation.
    seen,blocked = [],[]
    queue = list(replies)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            pass

        def do_GET(self):
            seen.append(self.path)
            if html is not None and self.path == "/fixture":
                body,kind,status = html,"text/html; charset=utf-8",200
            elif queue:
                reply = queue.pop(0)
                expected = urlsplit(reply.expected_url)
                expected_path = expected.path + ("?"+expected.query if expected.query else "")
                body,kind,status = (reply.body,"application/json",reply.status) if self.path == expected_path else (b'{}',"application/json",409)
            else:
                body,kind,status = b'{}',"application/json",404
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            blocked.append("POST")
            self.send_error(405)

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

    server = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    server.daemon_threads = True
    server.timeout = 2
    thread = Thread(target=server.serve_forever,kwargs={"poll_interval":0.05},daemon=True)
    thread.start()
    try:
        yield {"origin":f"http://127.0.0.1:{server.server_port}","seen":seen,"blocked_writes":blocked,"remaining":queue}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        if thread.is_alive():
            raise RuntimeError("Owned loopback server did not stop")
