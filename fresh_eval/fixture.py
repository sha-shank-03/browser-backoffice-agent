"""Future leased local HTML fixture; host names never enter acting observations."""
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from portal.server import escape,hidden,initialize
from industry_backoffice.fixture import SemanticHandler
from .lease import require_lease

FIELDS=("legal_name","registration_ref","country","contact_email","category","payment_terms")
OPTIONS={"country":("IN","GB","US"),"category":("Office supplies","IT services"),"payment_terms":("NET30","NET60")}


class EvaluationHandler(SemanticHandler):
    def do_POST(self):
        opening=urlparse(self.path).path=="/session/open"
        if opening:
            with self.database_connection() as con:before={r[0] for r in con.execute("SELECT public_id FROM sessions")}
        super().do_POST()
        if opening:
            with self.database_connection() as con:after={r[0] for r in con.execute("SELECT public_id FROM sessions")}
            for public_id in after-before:self.audit("fixture_session_opened",{"public_id":public_id})

    def do_GET(self):
        path=urlparse(self.path).path
        if path!="/vendors/new" or not self.allowed_host():return super().do_GET()
        session=self.session()
        if not session:return self.redirect("/login")
        config=self.config()
        if path==config.get("expire_once_on") and self.once("session_expiry"):
            with self.database_connection() as con:con.execute("DELETE FROM sessions WHERE public_id=?",(session["public_id"],))
            self.audit("fixture_session_expired",{"path":path})
            return self.redirect("/login")
        body='<form method="post" action="/vendors/draft">'+hidden("csrf",session["csrf"])
        groups=(("Organisation details",{"legal_name","registration_ref","country"}),("Purchasing details",{"contact_email","category","payment_terms"}))
        layout=config["layout"]
        for group,fields in groups if layout!="flat" else (("Supplier onboarding",set(FIELDS)),):
            if layout=="tabs":body+=f'<details><summary>{escape(group)}</summary>'
            body+=f'<fieldset><legend>{escape(group)}</legend>'
            for field in config["order"]:
                if field not in fields:continue
                description=config["descriptions"][field]
                attrs=f'name="{field}" required aria-description="{escape(description)}"'
                if field in OPTIONS:
                    control=f'<select {attrs}><option value="">Choose</option>'
                    for value in OPTIONS[field]:
                        label={"IN":"India","GB":"United Kingdom","US":"United States","NET30":"Due after thirty days","NET60":"Due after sixty days"}.get(value,value) if config["option_labels"] else value
                        control+=f'<option value="{escape(value)}">{escape(label)}</option>'
                    control+='</select>'
                else:control=f'<input {attrs} maxlength="120">'
                body+=f'<div class="field"><label><span>{escape(config["labels"][field])}</span>{control}</label><small>{escape(description)}</small></div>'
            body+='</fieldset>'
            if layout=="tabs":body+='</details>'
        if config["decoy"]:body+='<label>Newsletter delivery<input aria-description="Optional mailing preferences"></label>'
        if config["unsupported_field"]:body+='<label>Compliance certificate<input name="unsupported" required></label>'
        if config["ambiguous"]:body+=f'<label>{escape(config["labels"]["legal_name"])}<input name="ambiguous" aria-description="{escape(config["descriptions"]["legal_name"])}" required></label>'
        if config["notice"]:body+=f'<aside role="note">{escape(config["notice"])}</aside>'
        return self.page("Supplier onboarding",body+'<button>Review vendor</button></form>')


def serve(database):
    require_lease(browser=False)
    initialize(database)
    server=ThreadingHTTPServer(("127.0.0.1",0),EvaluationHandler)
    server.daemon_threads=True
    server.database=database
    print(f"http://127.0.0.1:{server.server_port}",flush=True)
    server.serve_forever(poll_interval=.05)


if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db",type=Path,required=True)
    serve(parser.parse_args().db)
