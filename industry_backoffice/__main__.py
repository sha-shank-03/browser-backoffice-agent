"""Explicit local-double CLI. Actor exits and independent verification differ."""
from argparse import ArgumentParser
from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import uuid

from backoffice.domain import canonical, digest, validate_request
from backoffice.store import run_lock
from portal.server import initialize
from .double import LocalDouble
from .protocol import Halt, ModelConfig, strict_json
from .runner import execute, EXITS
from .state import ActiveClock, Store, approve


def load_config(path):
    raw = strict_json(path.read_bytes(), 4096)
    if not isinstance(raw, dict) or set(raw) != {"mode", "model", "endpoint", "max_output_tokens", "attempt_seconds"}:
        raise Halt("config_schema")
    return ModelConfig(**raw).validate()


def initialize_run(run_dir, request, config, *, existing=False, fixture_options=None):
    """Trusted fictional fixture preparation, outside provider capabilities."""
    if run_dir.exists():
        raise Halt("run_directory_exists")
    config.validate()
    if config.mode != "local_double":
        raise Halt("live_dispatch_disabled", sent=False)
    run_dir.mkdir(parents=True)
    target = "local-v2-" + uuid.uuid4().hex
    database = run_dir / "portal-v2.db"
    initialize(database)
    with closing(sqlite3.connect(database)) as con, con:
        options = {**(fixture_options or {}), "target_identity": target}
        con.execute("INSERT INTO settings VALUES('fixture',?)", (canonical(options),))
        if existing:
            con.execute("INSERT INTO vendors(legal_name,registration_ref,country,contact_email,category,payment_terms) VALUES(?,?,?,?,?,?)", tuple(request[f] for f in ("legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms")))
        rows = [dict(zip([column[0] for column in cursor.description], row)) for cursor in [con.execute("SELECT * FROM vendors ORDER BY id")] for row in cursor.fetchall()]
    oracle = {"schema_version": 2, "target_identity": target, "expected_request": request,
              "before_rows": rows, "baseline_hash": digest(rows)}
    (run_dir / "verification-input.json").write_text(json.dumps(oracle, indent=2) + "\n", encoding="utf-8")
    store = Store(run_dir)
    try:
        store.initialize(request, uuid.uuid4().hex, target, config)
        store.export()
    finally:
        store.close()


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo")
    demo.add_argument("--request", type=Path, required=True)
    demo.add_argument("--config", type=Path, required=True)
    demo.add_argument("--existing", action="store_true")
    resume = commands.add_parser("resume")
    resume.add_argument("--config", type=Path, required=True)
    commands.add_parser("review")
    approval = commands.add_parser("approve")
    approval.add_argument("--digest", required=True, help="Digest read and explicitly accepted by the operator")
    commands.add_parser("cancel")
    for command in commands.choices.values():
        command.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            config = load_config(args.config)
            request = validate_request(strict_json(args.request.read_bytes(), 4096))
            initialize_run(args.run_dir, request, config, existing=args.existing)
        elif args.command == "cancel":
            if not (args.run_dir / "workflow-v2.db").exists():
                raise Halt("missing_run")
            (args.run_dir / "cancel.request").touch(exist_ok=True)
            print('{"cancel_requested":true,"rollback_promised":false}')
            return 0
        if not (args.run_dir / "workflow-v2.db").exists():
            raise Halt("missing_run")
        with run_lock(args.run_dir):
            store = Store(args.run_dir)
            try:
                if args.command == "review":
                    if not store.data["review"]:
                        raise Halt("no_review")
                    print(json.dumps({"review": store.data["review"], "digest": digest(store.data["review"])}, indent=2))
                    return 0
                if args.command == "approve":
                    approve(store, args.digest)
                    store.export()
                    print('{"approved":true,"next_command":"resume"}')
                    return 0
                config = load_config(args.config)
                if config.mode != "local_double":
                    raise Halt("live_dispatch_disabled", sent=False)
                if store.data["state"] in EXITS:
                    result = EXITS[store.data["state"]]
                else:
                    clock = ActiveClock(store)
                    try:
                        if (store.run_dir / "cancel.request").exists():
                            result = execute(store, config, clock=clock)
                        else:
                            with LocalDouble() as double:
                                result = execute(store, replace(config, endpoint=double.endpoint), clock=clock)
                    finally:
                        # Includes double startup/shutdown; human approval CLI/wait stays excluded.
                        clock.persist()
                        store.export()
                print(json.dumps({"actor_exit": result, "state": store.data["state"],
                                  "verified": False, "mode": "local_double"}))
                return result
            finally:
                store.close()
    except Exception as exc:
        print(json.dumps({"halt": exc.code if isinstance(exc, Halt) else "local_command_failure", "verified": False}))
        return 30


if __name__ == "__main__":
    raise SystemExit(main())
