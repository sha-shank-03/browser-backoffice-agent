"""Validate denominators, safety and reactive expected postconditions."""
from argparse import ArgumentParser
import json
from pathlib import Path

from .fixtures import load_suite


def inspect(report, require_cases, require_safe):
    manifest = load_suite(report["suite"])
    expected = {(agent, name) for agent in ("reactive-scripted", "fixed-macro") for name in manifest["case_order"]}
    actual = [(r["agent"], r["case"]) for r in report["results"]]
    checks = {"complete_expected_denominators": report.get("complete") is True and len(manifest["cases"]) == require_cases
              and report["case_count"] == require_cases and len(actual) == len(expected) and set(actual) == expected,
              "reactive_expected_postconditions": all(r["passed"] for r in report["results"] if r["agent"] == "reactive-scripted"),
              "canonical_baseline_succeeds": report["suite"] != "development" or any(r["agent"] == "fixed-macro" and r["case"] == "happy" and r["passed"] for r in report["results"])}
    if require_safe:
        checks["all_runs_safe"] = all(r.get("safe") is True for r in report["results"])
    return {"passed": all(checks.values()), "checks": checks, "summary": report.get("summary")}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--require-cases", type=int, required=True)
    parser.add_argument("--require-safe", action="store_true")
    args = parser.parse_args()
    result = inspect(json.loads(args.report.read_text()), args.require_cases, args.require_safe)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
