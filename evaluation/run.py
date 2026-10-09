"""Sequential offline comparison. Oracle and barriers belong to this harness."""
from argparse import ArgumentParser
import json
from pathlib import Path

from .fixtures import create_run, load_suite
from .freeze import MARKER, check
from .harness import execute
from .verify import write_report


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("development", "heldout"), required=True)
    parser.add_argument("--agents", default="reactive-scripted,fixed-macro")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-heldout", action="store_true", help="Only after separate M3 authorization")
    args = parser.parse_args()
    agents = args.agents.split(",")
    if len(set(agents)) != len(agents) or any(a not in {"reactive-scripted", "fixed-macro"} for a in agents):
        raise SystemExit("Choose distinct documented offline agents")
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit("Evaluation output must be new; failures are preserved")
    manifest = load_suite(args.suite)
    if args.suite == "heldout":
        if not args.allow_heldout:
            raise SystemExit("Held-out scoring requires explicit separate authorization and --allow-heldout")
        if not check()["passed"]:
            raise SystemExit("Frozen source/definition hashes changed")
        MARKER.write_text("Frozen held-out scoring started; do not tune or replace definitions.\n", encoding="utf-8")
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "suite": args.suite, "version": manifest["version"], "seed": manifest["seed"],
              "mode": "scripted_offline_no_live_model", "case_count": len(manifest["cases"]), "agents": agents,
              "results": [], "complete": False}
    for agent in agents:
        for name in manifest["case_order"]:
            case = manifest["cases"][name]
            directory = args.out / agent / name
            create_run(directory, name, args.suite)
            try:
                codes = execute(directory, case, agent)
                result = write_report(directory)
                entry = {"agent": agent, "case": name, "family": case["family"], "expected_outcome": case["outcome"],
                         "run_path": directory.relative_to(args.out).as_posix(), "raw_actor_exits": codes, **result}
            except Exception as exc:
                entry = {"agent": agent, "case": name, "family": case["family"], "expected_outcome": case["outcome"],
                         "passed": False, "safe": False, "error": str(exc)[:500], "missing_evidence": True}
            report["results"].append(entry)
            (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps({"agent": agent, "case": name, "passed": entry["passed"], "safe": entry["safe"]}), flush=True)
    report["complete"] = True
    report["summary"] = {}
    for agent in agents:
        selected = [r for r in report["results"] if r["agent"] == agent]
        by_outcome = {kind: {"passed": sum(r["passed"] for r in selected if r["expected_outcome"] == kind),
                             "denominator": sum(r["expected_outcome"] == kind for r in selected)} for kind in ("created", "existing", "handoff")}
        by_family = {family: {"passed": sum(r["passed"] for r in selected if r["family"] == family),
                              "denominator": sum(r["family"] == family for r in selected)} for family in sorted({r["family"] for r in selected})}
        report["summary"][agent] = {"passed": sum(r["passed"] for r in selected), "denominator": report["case_count"],
                                    "safe": sum(r["safe"] for r in selected), "outcomes": by_outcome, "families": by_family,
                                    "wrong_vendor_rows": sum(r.get("wrong_vendor_rows", 0) for r in selected),
                                    "unauthorized_creations": sum(r.get("unauthorized_creations", 0) for r in selected),
                                    "duplicate_rows": sum(r.get("duplicate_rows", 0) for r in selected),
                                    "reasons": {reason: sum(r.get("reason") == reason for r in selected) for reason in sorted({r.get("reason") for r in selected if r.get("reason")})}}
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return 0 if all(r["safe"] for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
