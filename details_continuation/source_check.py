"""Small additive continuation seal; every main-reviewed repo pin stays fixed."""
import ast
import hashlib
import json
from durable_eval.ledger import ROOT
from . import VERSION
from .continuation import check_provenance

MANIFEST = ROOT / "u2b-details-continuation-source-manifest.json"
ASSETS = ("details_continuation_tests.py", "details_continuation_data/provenance.json",
          "details_continuation_data/future_one_slot.json", "docs/U2B_DETAILS_CONTINUATION.md")


def snapshot():
    paths = sorted((ROOT / "details_continuation").rglob("*.py")) + [ROOT / name for name in ASSETS]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths}


def check():
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = snapshot()
    changed = sorted(k for k in set(actual) | set(frozen["files"]) if actual.get(k) != frozen["files"].get(k))
    for name in actual:
        if name.endswith(".py"): ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
    profile, _ = check_provenance()
    return {"passed": not changed, "version": VERSION, "files": len(actual),
            "python_files_parsed": sum(n.endswith(".py") for n in actual), "changed_files": changed,
            "prior_repo_pins_unchanged": len(profile["prior_repo_pins"]), "partial_files_unchanged": len(profile["partial_tree"]["files"]),
            "retained_unknown": 1, "retained_pending": 1, "new_native_execution": False,
            "native_collector_fix_verified": False, "quality_acceptance": False}


def binding():
    from details_eval.source_check import binding as prior_binding
    if not check()["passed"]: raise ValueError("continuation_source_manifest_drift")
    return {**prior_binding(), "continuation_version": VERSION,
            "continuation_source_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
