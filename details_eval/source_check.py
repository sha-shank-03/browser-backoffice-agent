"""Read-only candidate seal, retaining every earlier source and native artifact."""
import ast
import hashlib
import json
from pathlib import Path
from . import VERSION
from .repeat import check_history

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "u2b-details-source-manifest.json"
ASSETS = ("details_eval/collector.js", "details_eval_tests/test_collector.js", "details_eval_data/lineage.json",
          "details_eval_data/future_verification.json", "docs/U2B_DETAILS_COLLECTOR.md")


def snapshot():
    paths = sorted(p for directory in ("details_eval", "details_eval_tests") for p in (ROOT / directory).rglob("*.py"))
    paths += [ROOT / name for name in ASSETS]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths}


def check():
    from diagnostic_eval.source_check import check as prior_check
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = snapshot()
    changed = sorted(k for k in set(actual) | set(frozen["files"]) if actual.get(k) != frozen["files"].get(k))
    for name in actual:
        if name.endswith(".py"): ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
    preserved = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
                 for name, value in frozen["preserved_manifests"].items()}
    history = check_history()
    prior = prior_check()
    return {"passed": not changed and all(preserved.values()) and prior["passed"], "collector_version": VERSION,
            "files": len(actual), "python_files_parsed": sum(n.endswith(".py") for n in actual), "changed_files": changed,
            "preserved_manifests": preserved, "prior_diagnostics": prior,
            "history_files_unchanged": {key: len(value["files"]) for key, value in history["artifact_trees"].items()},
            "new_native_execution": False, "native_collector_fix_verified": False, "quality_acceptance": False}


def binding():
    from diagnostic_eval.source_check import binding as prior_binding
    if not check()["passed"]: raise ValueError("details_source_manifest_drift")
    return {**prior_binding(), "collector_version": VERSION,
            "collector_source_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
