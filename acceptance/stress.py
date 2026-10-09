"""Repeat the frozen six-case recovery subset three times; no distinct-case inflation."""
from argparse import ArgumentParser
import json
from pathlib import Path

from evaluation.freeze import MARKER
from .checkpoint import check

ROOT = Path(__file__).resolve().parents[1]


def expected_pairs(manifest):
    subset = manifest["stress_subset"]
    if len(subset) != 6 or len(set(subset)) != 6 or any(name not in manifest["cases"] for name in subset):
        raise ValueError("Frozen stress subset must contain six distinct defined cases")
    return [(repeat, name) for repeat in range(1, 4) for name in subset]


def inspect(report, manifest):
    expected = expected_pairs(manifest)
    actual = [(r.get("repeat"), r.get("case")) for r in report["results"]]
    checks = {"eighteen_runs_six_distinct_cases": report.get("kind") == "stress_recovery" and report.get("complete") is True
              and report.get("case_count") == 6 and report.get("repeat_count") == 3
              and actual == expected and report.get("agents") == ["reactive-scripted"]
              and report.get("suite") == "heldout" and report.get("version") == manifest["version"]
              and report.get("seed") == manifest["seed"] and report.get("mode") == "scripted_offline_no_live_model",
              "all_expected_postconditions": all(r.get("passed") is True for r in report["results"]),
              "all_runs_safe": all(r.get("safe") is True for r in report["results"])}
    return {"passed": all(checks.values()), "checks": checks,
            "repeats": {str(repeat): {"passed": sum(r.get("passed") is True for r in report["results"] if r.get("repeat") == repeat),
                                     "denominator": 6} for repeat in range(1, 4)}}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--allow-heldout", action="store_true")
    parser.add_argument("--check", action="store_true", help="Read existing report only; no browser")
    args = parser.parse_args()
    manifest = json.loads((ROOT / "evaluation/heldout.json").read_text(encoding="utf-8"))
    if args.check:
        result = inspect(json.loads((args.out / "report.json").read_text(encoding="utf-8")), manifest)
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    if not args.allow_heldout or not MARKER.exists():
        raise SystemExit("Stress execution requires explicit opt-in after the frozen comparison starts")
    if not check()["passed"]:
        raise SystemExit("Original or additive checkpoint changed; preserve failures without tuning")
    if args.out.exists() and any(args.out.iterdir()):
        raise SystemExit("Choose a new output directory; do not overwrite prior repeats")
    from evaluation.fixtures import create_run
    from evaluation.harness import execute
    from evaluation.verify import write_report
    args.out.mkdir(parents=True, exist_ok=True)
    report = {"schema_version": 1, "kind": "stress_recovery", "suite": "heldout", "version": manifest["version"],
              "seed": manifest["seed"], "agents": ["reactive-scripted"], "mode": "scripted_offline_no_live_model",
              "case_count": 6, "repeat_count": 3, "results": [], "complete": False}
    for repeat, name in expected_pairs(manifest):
        case = manifest["cases"][name]
        directory = args.out / f"repeat-{repeat}" / name
        entry = {"repeat": repeat, "case": name, "agent": "reactive-scripted", "family": case["family"],
                 "expected_outcome": case["outcome"], "run_path": directory.relative_to(args.out).as_posix()}
        try:
            create_run(directory, name, "heldout")
            codes = execute(directory, case)
            entry.update(raw_actor_exits=codes, **write_report(directory))
        except Exception as exc:
            entry.update(passed=False, safe=False, missing_evidence=True, error=str(exc)[:500])
        report["results"].append(entry)
        (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"repeat": repeat, "case": name, "passed": entry["passed"], "safe": entry["safe"]}), flush=True)
    report["complete"] = True
    report["validation"] = inspect(report, manifest)
    (args.out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["validation"], indent=2))
    return 0 if report["validation"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
