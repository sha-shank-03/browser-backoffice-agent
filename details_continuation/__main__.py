"""Only one fixed never-started local-double slot; no baseline/recovery/cohort CLI."""
from argparse import ArgumentParser
import json
from .continuation import ContinuationLedger, evaluate
from .source_check import binding, check


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("source-check")
    for command in ("run-local-double", "report"):
        sub = commands.add_parser(command)
        sub.add_argument("--out", required=True)
        if command == "run-local-double": sub.add_argument("--plan-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source-check":
            result = check(); print(json.dumps(result, indent=2)); return 0 if result["passed"] else 1
        if args.command == "run-local-double":
            from fresh_eval.lease import require_lease
            require_lease()
            result = evaluate(args.out, binding(), args.plan_sha256)
        else:
            result = ContinuationLedger(args.out, binding()).report()  # Read-only; no projection rewrite.
        print(json.dumps(result, indent=2))
        local = next(r for r in result["rows"] if r["agent"] == "local-double")
        return 0 if args.command == "report" or local["accounting_state"] == "completed" and local["verification"].get("safe") is True else 1
    except Exception:
        print(json.dumps({"passed": False, "code": "invalid_or_unauthorized_one_slot_continuation", "live_model": False})); return 1


if __name__ == "__main__": raise SystemExit(main())
