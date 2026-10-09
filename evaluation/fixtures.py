"""Fixture construction belongs to the demo harness, outside acting tools."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import uuid

from backoffice.domain import validate_request
from backoffice.store import Store
from portal.server import initialize

ROOT = Path(__file__).resolve().parents[1]


def load_suite(suite="development"):
    if suite not in {"development", "heldout"}:
        raise ValueError("Unknown suite")
    filename = "cases.json" if suite == "development" else "heldout.json"
    return json.loads((ROOT / "evaluation" / filename).read_text(encoding="utf-8"))


def create_run(run_dir: Path, scenario: str, suite="development"):
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError("Run directory is nonempty; choose a new directory or use resume")
    run_dir.mkdir(parents=True, exist_ok=True)
    cases = load_suite(suite)["cases"]
    if scenario not in cases:
        raise ValueError("Unknown scenario in the selected authored suite")
    case = cases[scenario]
    request = validate_request(case["request"])
    if set(case.get("config", {}).get("order", request)) != set(request):
        raise ValueError("Fixture field order must contain all six fields")
    initialize(run_dir / "portal.db")
    with closing(sqlite3.connect(run_dir / "portal.db")) as con, con:
        con.execute("INSERT INTO settings(key,value) VALUES('fixture',?)", (json.dumps(case.get("config", {})),))
        for row in case["before"]:
            fields = ("legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms")
            con.execute("INSERT INTO vendors(legal_name,registration_ref,country,contact_email,category,payment_terms) VALUES(?,?,?,?,?,?)", tuple(row[f] for f in fields))
    # Oracle files are not passed to the provider and no actor file-read tool exists.
    (run_dir / "oracle.json").write_text(json.dumps({"schema_version": 1, "scenario": scenario, **case}, indent=2), encoding="utf-8")
    store = Store(run_dir)
    try:
        store.initialize(request, uuid.uuid4().hex)
        store.export()
    finally:
        store.close()
