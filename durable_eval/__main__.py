"""Bounded development only. Full freeze and capability are unavailable here."""
from argparse import ArgumentParser
import json

from .ledger import Ledger
from .source_check import binding, check


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("source-check")
    evaluate = commands.add_parser("evaluate-first-slice")
    evaluate.add_argument("--out", required=True)
    evaluate.add_argument("--plan-sha256", required=True)
    evaluate.add_argument("--paired-tasks", type=int, choices=(1, 2), default=2)
    evaluate.add_argument("--phase-seconds", type=int, choices=(900, 1800), default=900)
    for command in ("report", "recover"):
        sub = commands.add_parser(command)
        sub.add_argument("--out", required=True)
        if command == "recover":
            sub.add_argument("--owner-stopped", action="store_true", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source-check":
            result = check()
            print(json.dumps(result, indent=2))
            return 0 if result["passed"] else 1
        if args.command == "evaluate-first-slice":
            from fresh_eval.lease import require_lease
            require_lease()  # Before creating output or importing the actor runtime.
            from .native import evaluate_first_slice
            result = evaluate_first_slice(args.out, binding(), expected_plan_sha256=args.plan_sha256,
                                          paired_tasks=args.paired_tasks, phase_seconds=args.phase_seconds)
            selected = [r for r in result["rows"] if r["case_id"] in result["first_slice_case_ids"]]
            print(json.dumps({"summary": result["summary"], "accounting_states": result["accounting_states"],
                              "freeze_eligible": False, "capability_eligible": False}, indent=2))
            return 0 if all(r["accounting_state"] == "completed" and r["verification"].get("safe") is True for r in selected) else 1
        ledger = Ledger(args.out, binding())
        result = ledger.recover(owner_stopped=args.owner_stopped) if args.command == "recover" else ledger.write_report()
        print(json.dumps({"summary": result["summary"], "accounting_states": result["accounting_states"],
                          "execution_complete": result["execution_complete"], "freeze_eligible": False}, indent=2))
        return 0
    except Exception:
        print(json.dumps({"passed": False, "code": "invalid_or_unauthorized_accounting_command",
                          "live_model": False, "external_site_verified": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
