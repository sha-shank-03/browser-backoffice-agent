"""Read-only normalized U1 review-manifest check; not a quality/held-out freeze."""
from argparse import ArgumentParser
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "u1-source-manifest.json"


def source_snapshot():
    paths = sorted(p for folder in ("industry_backoffice", "upgrade_tests") for p in (ROOT / folder).rglob("*.py"))
    paths += [ROOT / "upgrade_tests/integration_batch.ps1", ROOT / "config/local-double-v2.json", ROOT / "docs/U1_LOCAL_V2.md"]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest() for p in paths}


def check():
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    actual = source_snapshot()
    changed = sorted(k for k in set(actual) | set(frozen["files"]) if actual.get(k) != frozen["files"].get(k))
    parsed = []
    for name in actual:
        if name.endswith(".py"):
            ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
            parsed.append(name)
    return {"passed": not changed, "changed_files": changed, "python_files_parsed": len(parsed),
            "files": len(actual), "quality_acceptance": False, "integration_executed": False}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.parse_args()
    result = check()
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
