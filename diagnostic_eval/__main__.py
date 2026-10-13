"""Diagnostic repeat only; original twenty pending slots have no route here."""
from argparse import ArgumentParser
import json

from .repeat import RepeatLedger
from .source_check import binding, check


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("source-check")
    repeat = commands.add_parser("repeat-dev02")
    repeat.add_argument("--out", required=True)
    repeat.add_argument("--plan-sha256", required=True)
    for command in ("report", "recover"):
        sub = commands.add_parser(command)
        sub.add_argument("--out", required=True)
        if command == "recover": sub.add_argument("--owner-stopped", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source-check":
            result = check()
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        if args.command == "repeat-dev02":
            from fresh_eval.lease import require_lease
            require_lease()
            from .native import evaluate
            result = evaluate(args.out, binding(), args.plan_sha256)
        else:
            ledger = RepeatLedger(args.out, binding())
            result = ledger.recover(owner_stopped=args.owner_stopped) if args.command == "recover" else ledger.write_report()
        print(json.dumps({k: result[k] for k in ("evaluation_scope", "summary_scope", "summary", "accounting_states",
                         "new_unique_tasks", "original_pending_slots", "root_cause_established", "freeze_eligible")}, indent=2))
        # A diagnostic run can return 0 while preserving a business failure. This is not acceptance.
        return 0 if args.command != "repeat-dev02" or all(r["accounting_state"] == "completed" for r in result["rows"]) else 1
    except Exception:
        print(json.dumps({"passed": False, "code": "invalid_or_unauthorized_diagnostic_command", "live_model": False}))
        return 1


if __name__ == "__main__": raise SystemExit(main())
