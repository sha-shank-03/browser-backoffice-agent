"""Read-only additive U2-B manifest/preservation check, not a scoring freeze."""
import ast
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/"u2b-source-manifest.json"
ASSETS=("fresh_eval_data/development-v2.json","fresh_eval_data/capability-v2.json","fresh_eval_data/exposure-ledger.json",
        "fresh_eval_data/future_batch.json","docs/U2B_FRESH_EVALUATION.md","docs/U2B_CASE_STUDY.md",".github/workflows/u2b-pure.yml")


def snapshot():
    paths=sorted(p for directory in ("fresh_eval","fresh_eval_tests") for p in (ROOT/directory).rglob("*.py"))
    paths += [ROOT/name for name in ASSETS]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b"\r\n",b"\n")).hexdigest() for p in paths}


def check():
    from acceptance.checkpoint import check as v1_additive
    from upgrade_tests.source_check import check as u1_check
    from supplier_contract_tests.source_check import check as u2a_check
    frozen=json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual=snapshot()
    changed=sorted(k for k in set(frozen["files"])|set(actual) if frozen["files"].get(k)!=actual.get(k))
    for name in actual:
        if name.endswith(".py"):ast.parse((ROOT/name).read_text(encoding="utf-8"),filename=name)
    preserved={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in frozen["preserved_manifests"].items()}
    legacy,prior,supplier=v1_additive(),u1_check(),u2a_check()
    return {"passed":not changed and all(preserved.values()) and legacy["passed"] and prior["passed"] and supplier["passed"],
            "changed_files":changed,"files":len(actual),"python_files_parsed":sum(n.endswith(".py") for n in actual),
            "preserved_manifests":preserved,"v1_additive":legacy,"u1":prior,"u2a":supplier,
            "native_u2b_execution":False,"capability_scoring":False,"quality_acceptance":False}


def binding():
    from backoffice.domain import TOOLS,digest
    from industry_backoffice.protocol import PROMPT,PROMPT_VERSION
    from .cases import BUDGETS,sha
    if not check()["passed"]:raise ValueError("source_manifest_drift")
    return {"source_manifest_sha256":hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),"prompt_version":PROMPT_VERSION,
            "prompt_sha256":digest(PROMPT),"tool_schema_sha256":sha(TOOLS),"budgets_sha256":sha(BUDGETS),
            "mapping_version":"local-v2-six-fields.1","baseline":"semantic-rules-v2","provider_policy":"historical-u1-local-double"}
