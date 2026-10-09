"""HTML form-only fixture. No acting-agent API or direct database tools."""
from __future__ import annotations

import html
from contextlib import contextmanager, closing
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
import socket
import time
from urllib.parse import parse_qs, urlparse
import uuid

FIELDS = ("legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms")
LABELS = ("Legal name", "Registration reference", "Country", "Contact email", "Category", "Payment terms")


def initialize(db: Path):
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE IF NOT EXISTS vendors (id INTEGER PRIMARY KEY, legal_name TEXT NOT NULL, registration_ref TEXT UNIQUE NOT NULL, country TEXT NOT NULL, contact_email TEXT NOT NULL, category TEXT NOT NULL, payment_terms TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, public_id TEXT NOT NULL, csrf TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS drafts (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS faults (name TEXT PRIMARY KEY)")


def escape(value):
    return html.escape(str(value), quote=True)


def hidden(key, value):
    return f'<input type="hidden" name="{escape(key)}" value="{escape(value)}">'


def record_view(record):
    return '<dl data-vendor-record>' + ''.join(f'<dt>{label}</dt><dd data-vendor-field="{field}">{escape(record[field])}</dd>' for field, label in zip(FIELDS, LABELS)) + '</dl>'


class Handler(BaseHTTPRequestHandler):
    server_version = "FictionalPortal/0.1"

    def log_message(self, *args):
        pass

    @contextmanager
    def database_connection(self):
        con = sqlite3.connect(self.server.database, timeout=2)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def audit(self, kind, data):
        with self.database_connection() as con:
            con.execute("INSERT INTO audit(at,kind,data) VALUES(?,?,?)", (time.time(), kind, json.dumps(data, sort_keys=True)))

    def config(self):
        with self.database_connection() as con:
            row = con.execute("SELECT value FROM settings WHERE key='fixture'").fetchone()
        return json.loads(row[0]) if row else {}

    def once(self, name):
        with self.database_connection() as con:
            cursor = con.execute("INSERT OR IGNORE INTO faults(name) VALUES(?)", (name,))
        return cursor.rowcount == 1

    def session(self):
        try:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            token = cookie["fictional_session"].value if "fictional_session" in cookie else ""
        except Exception:
            token = ""
        with self.database_connection() as con:
            row = con.execute("SELECT * FROM sessions WHERE token=?", (token,)).fetchone()
        return dict(row) if row else None

    def allowed_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def page(self, title, body, status=200, cookie=None):
        document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{escape(title)}</title>
<style>body{{font:17px system-ui;max-width:850px;margin:40px auto;background:#f6f8fa;color:#13273b}}main{{background:white;padding:28px;border:1px solid #ddd}}label{{display:block;margin:12px 0}}input,select,button{{font:inherit;padding:7px}}dt{{font-weight:bold;margin-top:10px}}dd{{margin:3px 0}}a{{color:#075a9d}}</style></head>
<body><main><p>Fictional local procurement portal · authored demonstration</p><h1>{escape(title)}</h1>{body}</main></body></html>'''
        payload = document.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, target, cookie=None):
        self.send_response(303)
        self.send_header("Location", target)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self.allowed_host():
            return self.page("Rejected host", "", 403)
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/login":
            return self.page("Operator session", '<form method="post" action="/session/open"><button>Open fictional operator session</button></form>')
        session = self.session()
        if not session:
            return self.redirect("/login")
        config = self.config()
        if url.path == config.get("expire_once_on") and self.once("session_expiry"):
            with self.database_connection() as con:
                con.execute("DELETE FROM sessions WHERE public_id=?", (session["public_id"],))
            self.audit("fixture_session_expired", {"path": url.path})
            return self.redirect("/login?expired=1")
        if url.path == "/vendors":
            term = query.get("q", [""])[0]
            with self.database_connection() as con:
                records = con.execute("SELECT * FROM vendors WHERE registration_ref=?", (term,)).fetchall() if term else []
            search = f'<form method="get" action="/vendors"><label>Registration reference search<input name="q" value="{escape(term)}"></label><button>Search</button></form>'
            body = search + '<a href="/vendors/new">Register a vendor</a>' + ''.join(record_view(dict(r)) for r in records)
            if len(records) == 1:
                body += f'<a href="/vendors/detail?id={records[0]["id"]}">Inspect matching vendor</a>'
            if term and not records:
                body += '<p>No matching vendors</p>'
            return self.page("Vendor search", body)
        if url.path == "/vendors/new":
            body = '<form method="post" action="/vendors/draft">' + hidden("csrf", session["csrf"])
            options = {"country": ("IN", "GB", "US"), "category": ("Office supplies", "IT services"), "payment_terms": ("NET30", "NET60")}
            labels = dict(zip(FIELDS, LABELS))
            labels.update(config.get("labels", {}))
            for field in config.get("order", FIELDS):
                label = labels[field]
                if field in options:
                    control = f'<select id="{field}" name="{field}" required><option value="">Choose</option>' + ''.join(f'<option value="{escape(o)}">{escape(o)}</option>' for o in options[field]) + '</select>'
                else:
                    control = f'<input id="{field}" name="{field}" required maxlength="120">'
                body += f'<label for="{field}">{escape(label)}</label>{control}'
            if config.get("unsupported_field"):
                body += '<label>Tax certificate<input name="tax_certificate" required></label>'
            if config.get("notice"):
                body += f'<aside role="note">{escape(config["notice"])}</aside>'
            return self.page("Register vendor", body + '<p><button>Review vendor</button></p></form>')
        if url.path in {"/vendors/review", "/vendors/validation"}:
            draft_id = query.get("draft", [""])[0]
            with self.database_connection() as con:
                draft = con.execute("SELECT * FROM drafts WHERE id=? AND session_id=?", (draft_id, session["public_id"])).fetchone()
            if not draft:
                return self.page("Missing draft", "Draft is unavailable", 404)
            values = json.loads(draft["payload"])
            if url.path == "/vendors/validation":
                body = '<section role="dialog" aria-modal="true" aria-labelledby="validation-title"><h2 id="validation-title">Vendor validation</h2>'
                body += record_view(values)
                if config.get("validation_rejected"):
                    return self.page("Vendor validation", body + '<p role="alert">Vendor requires an unsupported certificate. Ask an operator.</p></section>')
                body += '<p role="status">Six vendor fields passed validation. Review before final submission.</p>'
                body += '<form method="post" action="/vendors/ack">' + hidden("csrf", session["csrf"]) + hidden("draft_id", draft_id)
                return self.page("Vendor validation", body + '<button>Continue to review</button></form></section>')
            body = f'<section data-review data-draft-id="{escape(draft_id)}" data-revision="{draft["revision"]}" data-session-id="{session["public_id"]}">' + record_view(values) + '</section>'
            body += '<p>No vendor is created until the final approved submission.</p><form method="post" action="/vendors/commit">'
            for key, value in {**values, "draft_id": draft_id, "revision": draft["revision"], "csrf": session["csrf"]}.items():
                body += hidden(key, value)
            return self.page("Review vendor", body + '<button>Submit vendor</button></form>')
        if url.path == "/vendors/detail":
            with self.database_connection() as con:
                row = con.execute("SELECT * FROM vendors WHERE id=?", (query.get("id", [""])[0],)).fetchone()
            if row:
                return self.page("Vendor registered", '<p role="status">Registration completed</p>' + record_view(dict(row)))
            return self.page("Missing vendor", "No such vendor", 404)
        return self.page("Not found", "", 404)

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self.allowed_host() or self.headers.get("Origin") != origin:
            return self.page("Rejected origin", "", 403)
        if self.headers.get("Content-Type", "").split(";")[0] != "application/x-www-form-urlencoded":
            return self.page("Unsupported body", "", 415)
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 <= size <= 8192:
                raise ValueError()
            pairs = parse_qs(self.rfile.read(size).decode(), keep_blank_values=True, strict_parsing=True)
            if any(len(values) != 1 for values in pairs.values()):
                raise ValueError()
            form = {key: values[0] for key, values in pairs.items()}
        except (ValueError, UnicodeError):
            return self.page("Malformed form", "", 400)
        path = urlparse(self.path).path
        self.audit("http_post", {"path": path})
        if path == "/session/open" and not form:
            token, public_id, csrf = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
            with self.database_connection() as con:
                con.execute("INSERT INTO sessions VALUES(?,?,?)", (token, public_id, csrf))
            return self.redirect("/vendors", f"fictional_session={token}; HttpOnly; SameSite=Strict; Path=/")
        session = self.session()
        if not session or form.get("csrf") != session["csrf"]:
            return self.page("Session rejected", "", 403)
        if path == "/vendors/draft":
            if set(form) != set(FIELDS) | {"csrf"} or any(not form[f] or len(form[f]) > 120 for f in FIELDS):
                return self.page("Invalid vendor", "Complete the six fields", 400)
            if form["country"] not in {"IN", "GB", "US"} or form["category"] not in {"Office supplies", "IT services"} or form["payment_terms"] not in {"NET30", "NET60"}:
                return self.page("Invalid option", "", 400)
            draft_id = uuid.uuid4().hex
            payload = json.dumps({f: form[f] for f in FIELDS}, sort_keys=True)
            with self.database_connection() as con:
                con.execute("INSERT INTO drafts VALUES(?,?,?,?)", (draft_id, session["public_id"], 1, payload))
            target = "/vendors/validation" if self.config().get("validation_modal") else "/vendors/review"
            return self.redirect(f"{target}?draft={draft_id}")
        if path == "/vendors/ack":
            if set(form) != {"csrf", "draft_id"} or self.config().get("validation_rejected"):
                return self.page("Validation rejected", "", 409)
            with self.database_connection() as con:
                draft = con.execute("SELECT id FROM drafts WHERE id=? AND session_id=?", (form["draft_id"], session["public_id"])).fetchone()
            if not draft:
                return self.page("Missing draft", "", 404)
            return self.redirect(f'/vendors/review?draft={form["draft_id"]}')
        if path == "/vendors/commit":
            if set(form) != set(FIELDS) | {"csrf", "draft_id", "revision"}:
                return self.page("Invalid commit", "", 400)
            with self.database_connection() as con:
                draft = con.execute("SELECT * FROM drafts WHERE id=? AND session_id=?", (form["draft_id"], session["public_id"])).fetchone()
                values = {f: form[f] for f in FIELDS}
                if not draft or str(draft["revision"]) != form["revision"] or json.loads(draft["payload"]) != values:
                    return self.page("Stale draft", "", 409)
                existing = con.execute("SELECT * FROM vendors WHERE registration_ref=?", (values["registration_ref"],)).fetchone()
                if existing:
                    if {f: existing[f] for f in FIELDS} == values:
                        return self.redirect(f'/vendors/detail?id={existing["id"]}')
                    return self.page("Conflicting vendor", "Existing vendor was not changed", 409)
                cursor = con.execute("INSERT INTO vendors(legal_name,registration_ref,country,contact_email,category,payment_terms) VALUES(?,?,?,?,?,?)", tuple(values[f] for f in FIELDS))
                con.execute("INSERT INTO audit(at,kind,data) VALUES(?,?,?)", (time.time(), "vendor_created", json.dumps({"vendor_id": cursor.lastrowid, "draft_id": form["draft_id"], "revision": int(form["revision"]), "values": values}, sort_keys=True)))
                vendor_id = cursor.lastrowid
            if self.config().get("response_loss") and self.once("commit_response_loss"):
                self.audit("fixture_response_lost", {"after": "atomic_vendor_commit"})
                self.close_connection = True
                self.connection.shutdown(socket.SHUT_RDWR)
                return
            return self.redirect(f"/vendors/detail?id={vendor_id}")
        return self.page("Not found", "", 404)


def serve(db: Path):
    initialize(db)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.database = db
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever()
