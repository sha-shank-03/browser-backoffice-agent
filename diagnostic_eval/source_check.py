"""Additive diagnostic seal and byte-preservation of all original attempts."""
import ast
import hashlib
import json
from pathlib import Path

from . import VERSION
from .repeat import check_original

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "u2b-diagnostics-source-manifest.json"
ASSETS = ("diagnostic_eval_data/original_evidence_profile.json", "diagnostic_eval_data/future_repeat.json",
          "docs/U2B_FAILURE_DIAGNOSTICS.md")


def snapshot():
    paths = sorted(p for directory in ("diagnostic_eval", "diagnostic_eval_tests") for p in (ROOT / directory).rglob("*.py"))
    paths += [ROOT / name for name in ASSETS]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths}


def check():
    from durable_eval.source_check import check as prior_check
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = snapshot()
    changed = sorted(k for k in set(actual) | set(frozen["files"]) if actual.get(k) != frozen["files"].get(k))
    for name in actual:
        if name.endswith(".py"): ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
    preserved = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
                 for name, value in frozen["preserved_manifests"].items()}
    profile = check_original()
    prior = prior_check()
    return {"passed": not changed and all(preserved.values()) and prior["passed"], "diagnostic_version": VERSION,
            "files": len(actual), "python_files_parsed": sum(n.endswith(".py") for n in actual), "changed_files": changed,
            "preserved_manifests": preserved, "prior_accounting": prior,
            "original_attempt_files_unchanged": len(profile["tree"]["files"]), "original_terminal_slots": 4,
            "original_pending_slots": 20, "new_native_execution": False, "root_cause_established": False,
            "quality_acceptance": False}


def binding():
    from durable_eval.source_check import binding as prior_binding
    if not check()["passed"]: raise ValueError("diagnostic_source_manifest_drift")
    return {**prior_binding(), "diagnostic_version": VERSION,
            "diagnostic_source_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
