"""Read-only U2-A source receipt plus preservation checks; not quality acceptance."""
from argparse import ArgumentParser
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "u2a-source-manifest.json"
ASSETS = ("sandbox_profiles/erpnext-v15-supplier.profile.example.json",
          "sandbox_profiles/erpnext-v15-sources.json", "supplier_contract_tests/future_batch.json",
          "docs/U2A_SUPPLIER_CONTRACT.md")


def source_snapshot():
    paths = sorted(p for folder in ("supplier_sandbox","supplier_contract_tests") for p in (ROOT/folder).rglob("*.py"))
    paths += [ROOT/name for name in ASSETS]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b"\r\n",b"\n")).hexdigest() for p in paths}


def check():
    from evaluation.freeze import check as v1_check
    from upgrade_tests.source_check import check as u1_check
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = source_snapshot()
    changed = sorted(k for k in set(actual)|set(frozen["files"]) if actual.get(k) != frozen["files"].get(k))
    parsed = 0
    for name in actual:
        if name.endswith(".py"):
            ast.parse((ROOT/name).read_text(encoding="utf-8"),filename=name)
            parsed += 1
    preserved = {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected
                 for name,expected in frozen["preserved_manifests"].items()}
    legacy,prior = v1_check(),u1_check()
    passed = not changed and all(preserved.values()) and legacy["passed"] and prior["passed"]
    return {"passed":passed,"changed_files":changed,"files":len(actual),"python_files_parsed":parsed,
            "preserved_manifests":preserved,"v1":legacy,"u1":prior,
            "quality_acceptance":False,"future_batch_executed":False,"external_site_verified":False}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--check",action="store_true",required=True)
    parser.parse_args()
    result = check()
    print(json.dumps(result,indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
