"""Freeze/check normalized source and held-out definition SHA-256 before scoring."""
from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evaluation/heldout-freeze.json"
MARKER = ROOT / "evaluation/heldout-evaluated.marker"


def snapshot():
    paths = sorted(p for directory in ("backoffice", "portal", "evaluation", "tests") for p in (ROOT / directory).rglob("*.py"))
    paths += [ROOT / "evaluation/cases.json", ROOT / "evaluation/heldout.json", ROOT / "requirements.lock"]
    paths += sorted((ROOT / "fixtures/requests").glob("*.json"))
    result = {}
    for path in paths:
        normalized = path.read_bytes().replace(b"\r\n", b"\n")
        result[path.relative_to(ROOT).as_posix()] = hashlib.sha256(normalized).hexdigest()
    return dict(sorted(result.items()))


def check():
    frozen = json.loads(MANIFEST.read_text())
    current = snapshot()
    changed = sorted(k for k in set(current) | set(frozen["files"]) if current.get(k) != frozen["files"].get(k))
    return {"passed": not changed, "changed_files": changed, "frozen_files": len(current),
            "heldout_scoring_started": MARKER.exists()}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("heldout",), required=True)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--replace-before-scoring", action="store_true")
    args = parser.parse_args()
    if args.check:
        result = check()
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    if MARKER.exists():
        raise SystemExit("Held-out scoring has started; preserve this freeze and report failures")
    if MANIFEST.exists() and not args.replace_before_scoring:
        raise SystemExit("Already frozen; explicit replacement allowed only before scoring")
    manifest = json.loads((ROOT / "evaluation/heldout.json").read_text())
    counts = {kind: sum(c["outcome"] == kind for c in manifest["cases"].values()) for kind in ("created", "existing", "handoff")}
    if counts != {"created": 19, "existing": 2, "handoff": 9} or len(manifest["cases"]) != 30:
        raise SystemExit("Held-out definition counts differ from the accepted contract")
    files = snapshot()
    MANIFEST.write_text(json.dumps({"schema_version": 1, "suite": "heldout", "version": manifest["version"],
                        "hash_normalization": "CRLF to LF bytes", "counts": counts, "files": files}, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"frozen": True, "files": len(files), "counts": counts, "scored": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
