"""Fictional semantic layout over the unchanged v1 atomic portal contract."""
from __future__ import annotations

from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from portal.server import Handler, escape, hidden, initialize

SEMANTIC_LABELS = {"legal_name": "Registered organisation", "registration_ref": "Business identity reference",
                   "country": "Jurisdiction of operation", "contact_email": "Purchasing correspondence email",
                   "category": "Supply classification", "payment_terms": "Invoice settlement schedule"}
ORDER = ("category", "contact_email", "payment_terms", "registration_ref", "legal_name", "country")


class SemanticHandler(Handler):
    def page(self, title, body, status=200, cookie=None):
        identity = self.config().get("target_identity", "")
        return super().page(title, f'<p data-target-identity="{escape(identity)}">Local-v2 authored fixture</p>' + body, status, cookie)

    def do_GET(self):
        if urlparse(self.path).path != "/vendors/new" or not self.allowed_host():
            return super().do_GET()
        session = self.session()
        if not session:
            return self.redirect("/login")
        body = '<form method="post" action="/vendors/draft">' + hidden("csrf", session["csrf"])
        options = {"country": ("IN", "GB", "US"), "category": ("Office supplies", "IT services"), "payment_terms": ("NET30", "NET60")}
        body += '<fieldset><legend>Supplier onboarding · organisation and purchasing details</legend>'
        for index, field in enumerate(ORDER):
            label = self.config().get("labels", {}).get(field, SEMANTIC_LABELS[field])
            # No field name/id enters provider observations; the browser sees accessible semantics.
            if field in options:
                control = f'<select name="{field}" required><option value="">Choose</option>' + ''.join(f'<option value="{escape(o)}">{escape(o)}</option>' for o in options[field]) + '</select>'
            else:
                control = f'<input name="{field}" required maxlength="120">'
            body += f'<div class="group-{index % 2}"><label>{escape(label)}{control}</label></div>'
        if self.config().get("unsupported_field"):
            body += '<label>Compliance certificate<input name="unsupported" required></label>'
        body += '</fieldset><aside role="note">Review all six immutable request fields before approval.</aside>'
        return self.page("Supplier onboarding", body + '<button>Review vendor</button></form>')


def serve(database):
    initialize(database)
    server = ThreadingHTTPServer(("127.0.0.1", 0), SemanticHandler)
    server.daemon_threads = True
    server.database = database
    print(f"http://127.0.0.1:{server.server_port}", flush=True)
    server.serve_forever(poll_interval=.05)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    serve(parser.parse_args().db)
