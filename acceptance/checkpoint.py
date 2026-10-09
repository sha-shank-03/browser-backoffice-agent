"""Hash the additive M3 harness without replacing the original 32-file freeze."""
from argparse import ArgumentParser
import hashlib
import json
from pathlib import Path

from evaluation.freeze import MARKER, check as original_check

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "acceptance/checkpoint.json"


def file_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def snapshot():
    return {path.relative_to(ROOT).as_posix(): file_hash(path) for path in sorted((ROOT / "acceptance").rglob("*.py"))}


def check():
    original = original_check()
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current = snapshot()
    changed = sorted(name for name in set(current) | set(frozen["files"]) if current.get(name) != frozen["files"].get(name))
    original_manifest_matches = frozen["original_freeze_sha256"] == file_hash(ROOT / "evaluation/heldout-freeze.json")
    return {"passed": original["passed"] and original_manifest_matches and not changed,
            "original_freeze": original, "original_manifest_matches": original_manifest_matches,
            "additive_files": len(current), "changed_additive_files": changed}


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    if args.check == args.write:
        parser.error("Choose exactly one of --check or --write")
    if args.check:
        result = check()
        print(json.dumps(result, indent=2))
        return 0 if result["passed"] else 1
    if MARKER.exists() or MANIFEST.exists():
        raise SystemExit("Checkpoint creation is one-time before held-out scoring; preserve existing evidence")
    if not original_check()["passed"]:
        raise SystemExit("Original policy/definition freeze differs; do not replace it")
    data = {"schema_version": 1, "version": "additive-m3-v1", "hash_normalization": "CRLF to LF bytes",
            "original_freeze_sha256": file_hash(ROOT / "evaluation/heldout-freeze.json"), "files": snapshot()}
    MANIFEST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"checkpoint_written": True, "additive_files": len(data["files"]), "original_freeze_replaced": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
