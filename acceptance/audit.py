"""Reinspect all retained task databases against frozen definitions, read-only."""
from argparse import ArgumentParser
import json
from pathlib import Path
import sqlite3

from evaluation.verify import inspect as inspect_domain
from .stress import expected_pairs

ROOT = Path(__file__).resolve().parents[1]
AGENTS = {"reactive-scripted": "scripted:reactive-ui-v2", "fixed-macro": "fixed-macro:canonical-v1"}


def identities(report, manifest, stress=False):
    expected = ([("reactive-scripted", name, repeat) for repeat, name in expected_pairs(manifest)] if stress
                else [(agent, name, None) for agent in AGENTS for name in manifest["case_order"]])
    actual = [(entry.get("agent"), entry.get("case"), entry.get("repeat")) for entry in report["results"]]
    metadata = (report.get("complete") is True and report.get("suite") == "heldout" and report.get("version") == manifest["version"]
                and report.get("seed") == manifest["seed"] and report.get("mode") == "scripted_offline_no_live_model"
                and report.get("case_count") == (6 if stress else 30)
                and report.get("agents") == (["reactive-scripted"] if stress else list(AGENTS))
                and (not stress or (report.get("kind") == "stress_recovery" and report.get("repeat_count") == 3)))
    return metadata and actual == expected


def inspect_tasks(root, manifest, stress=False):
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if not identities(report, manifest, stress):
        return {"passed": False, "error": "Missing, duplicate, reordered or incorrect task denominator/metadata", "tasks": []}
    tasks = []
    for entry in report["results"]:
        name, agent = entry["case"], entry["agent"]
        relative = f"repeat-{entry['repeat']}/{name}" if stress else f"{agent}/{name}"
        directory = root / relative
        case = manifest["cases"][name]
        checks = {}
        try:
            oracle = json.loads((directory / "oracle.json").read_text(encoding="utf-8"))
            checks["oracle_is_frozen_definition"] = oracle == {"schema_version": 1, "scenario": name, **case}
            checks["case_metadata_and_path"] = entry["run_path"] == relative and entry["expected_outcome"] == case["outcome"] and entry["family"] == case["family"]
            independent = inspect_domain(directory)
            checks["report_matches_read_only_database_verifier"] = all(entry.get(key) == value for key, value in independent.items())
            checks["expected_provider_identity"] = independent["provider_mode"] == AGENTS[agent]
            checks["safe"] = independent["safe"]
            checks["reactive_expected_postcondition"] = agent != "reactive-scripted" or independent["passed"]
            harness = json.loads((directory / "harness.json").read_text(encoding="utf-8"))
            exits = entry["raw_actor_exits"]
            checks["restart_receipt_and_bounded_attempts"] = harness["raw_actor_exits"] == exits and harness["restart_count"] == len(exits) - 1 and 1 <= len(exits) <= 2 and all(code in {0, 11, 20, 30} for code in exits)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            checks["complete_readable_evidence"] = False
            independent = {"error": str(exc)[:500]}
        tasks.append({"agent": agent, "case": name, "repeat": entry.get("repeat"), "passed": all(checks.values()),
                      "checks": checks, "observed": independent})
    return {"passed": all(task["passed"] for task in tasks), "task_count": len(tasks), "distinct_cases": 6 if stress else 30,
            "assertions": sum(len(task["checks"]) for task in tasks), "tasks": tasks}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--heldout-out", type=Path, required=True)
    parser.add_argument("--stress-out", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((ROOT / "evaluation/heldout.json").read_text(encoding="utf-8"))
    comparison = inspect_tasks(args.heldout_out, manifest)
    stress = inspect_tasks(args.stress_out, manifest, stress=True)
    result = {"passed": comparison["passed"] and stress["passed"], "comparison": comparison, "stress": stress}
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
