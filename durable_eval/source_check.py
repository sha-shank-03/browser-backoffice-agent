"""Read-only additive seal; every previous source checker must still pass."""
import ast
import hashlib
import json
from pathlib import Path

from . import VERSION

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "u2b-accounting-source-manifest.json"
ASSETS = ("docs/U2B_DURABLE_ACCOUNTING.md", "durable_eval_data/first_slice_proposal.json")


def snapshot():
    paths = sorted(p for directory in ("durable_eval", "durable_eval_tests") for p in (ROOT / directory).rglob("*.py"))
    paths += [ROOT / name for name in ASSETS]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths}


def check():
    from fresh_eval.source_check import check as prior_check
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = snapshot()
    changed = sorted(k for k in set(actual) | set(frozen["files"]) if actual.get(k) != frozen["files"].get(k))
    for name in actual:
        if name.endswith(".py"):
            ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
    preserved = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
                 for name, digest in frozen["preserved_manifests"].items()}
    prior = prior_check()
    return {"passed": not changed and all(preserved.values()) and prior["passed"], "accounting_version": VERSION,
            "changed_files": changed, "files": len(actual), "python_files_parsed": sum(n.endswith(".py") for n in actual),
            "preserved_manifests": preserved, "prior_u2b": prior, "native_execution": False,
            "quality_acceptance": False, "scoring_freeze": False}


def binding():
    from fresh_eval.source_check import binding as prior_binding
    if not check()["passed"]:
        raise ValueError("accounting_source_manifest_drift")
    return {**prior_binding(), "accounting_version": VERSION,
            "accounting_source_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest()}
