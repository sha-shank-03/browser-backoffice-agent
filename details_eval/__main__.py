"""At most one dev02 verification pair; original pending cohort has no route."""
from argparse import ArgumentParser
import json
from .repeat import VerificationLedger
from .source_check import binding, check


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("source-check")
    verify = commands.add_parser("verify-dev02")
    verify.add_argument("--out", required=True)
    verify.add_argument("--plan-sha256", required=True)
    for command in ("report", "recover"):
        sub = commands.add_parser(command)
        sub.add_argument("--out", required=True)
        if command == "recover": sub.add_argument("--owner-stopped", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source-check":
            result = check(); print(json.dumps(result, indent=2)); return 0 if result["passed"] else 1
        if args.command == "verify-dev02":
            from fresh_eval.lease import require_lease
            require_lease()
            from .native import evaluate
            result = evaluate(args.out, binding(), args.plan_sha256)
        else:
            ledger = VerificationLedger(args.out, binding())
            result = ledger.recover(owner_stopped=args.owner_stopped) if args.command == "recover" else ledger.write_report()
        print(json.dumps({key: result[key] for key in ("evaluation_scope", "summary_scope", "summary", "accounting_states",
                         "new_unique_tasks", "original_pending_slots", "collector_version", "freeze_eligible")}, indent=2))
        return 0 if args.command != "verify-dev02" or all(r["accounting_state"] == "completed" and r["verification"].get("safe") is True for r in result["rows"]) else 1
    except Exception:
        print(json.dumps({"passed": False, "code": "invalid_or_unauthorized_details_command", "live_model": False})); return 1


if __name__ == "__main__": raise SystemExit(main())
