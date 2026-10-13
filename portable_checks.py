"""Standalone upgrade unit package; synthetic histories are NEVER native evidence.

Frozen tests are loaded unchanged in an explicit temporary fixture context. Native
entrypoints are not exposed here and their original history/lease gates remain.
"""
from argparse import ArgumentParser
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import hashlib
import importlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
VERSION = "standalone-unit-packaging.1"
MANIFEST = ROOT / "u2b-portable-source-manifest.json"
NEW_FILES = ("portable_checks.py", "portable_checks_tests.py", "PORTABLE_CHECKS.md", ".github/workflows/u2b-portable.yml")
SUITES = ("upgrade_tests.unit", "supplier_contract_tests.pure", "fresh_eval_tests", "durable_eval_tests",
          "diagnostic_eval_tests", "details_eval_tests", "details_continuation_tests", "remaining_eval_tests", "remaining_continue_tests")


def normalized_hash(path): return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def source_check():
    """Source-only contract, not the historical native artifact-integrity check."""
    frozen = json.loads(MANIFEST.read_text(encoding="utf-8"))
    changed = [name for name, digest in frozen["preserved_shipping_files"].items()
               if not (ROOT / name).is_file() or hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest]
    changed += [name for name, digest in frozen["files"].items()
                if not (ROOT / name).is_file() or normalized_hash(ROOT / name) != digest]
    return {"passed": not changed, "version": VERSION, "changed_files": changed,
            "preserved_shipping_files": len(frozen["preserved_shipping_files"]), "new_files": len(frozen["files"]),
            "scope": "Exact old shipping bytes plus normalized new correction files; no saved evaluation required",
            "historical_native_artifact_verification": "not_performed", "native_execution": False,
            "quality_acceptance": False, "historical_manifests_rewritten": False}


def collector_controls():
    """Exact frozen JS tests in Playwright's already installed bundled Node; no browser."""
    import playwright
    node = Path(playwright.__file__).resolve().parent / "driver" / ("node.exe" if os.name == "nt" else "node")
    if not node.is_file(): raise ValueError("existing_pinned_playwright_node_required_no_install")
    completed = subprocess.run([str(node), str(ROOT / "details_eval_tests/test_collector.js")], cwd=ROOT,
                               capture_output=True, timeout=20, check=True)
    if len(completed.stdout) > 32768: raise ValueError("collector_unit_result_size")
    result = json.loads(completed.stdout)
    if result.get("passed") is not True or (result.get("tests"), result.get("assertions")) != (16, 22):
        raise ValueError("exact_collector_controls_required")
    return result


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output: output.write(json.dumps(value, sort_keys=True, indent=2) + "\n")


@contextmanager
def fixture_context(controls, *, scratch_parent=None):
    """Actual strict checksum functions run against labelled authored unit inputs.

    Only module path constants are scoped. No integrity/scoring function is patched
    and no fixture is written into the real work/, source profiles or index.
    """
    import diagnostic_eval.repeat as diagnostic
    import details_eval.repeat as details
    import details_continuation.continuation as continuation
    from durable_eval import ledger
    from diagnostic_eval.diagnostics import Writer
    from fresh_eval.cases import sha

    scratch_parent = Path(scratch_parent) if scratch_parent else ROOT / "work/portable-unit-scratch"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="browser-unit-package-", dir=scratch_parent) as temporary, ExitStack() as scope:
        root = Path(temporary)
        if not root.resolve().is_relative_to(scratch_parent.resolve()): raise ValueError("unit_scratch_scope")
        shipping = json.loads(MANIFEST.read_text(encoding="utf-8"))["preserved_shipping_files"]
        for name in shipping:
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, target)
        source_roots = (ledger, diagnostic, details, continuation,
                        importlib.import_module("diagnostic_eval.source_check"), importlib.import_module("details_eval.source_check"),
                        importlib.import_module("details_continuation.source_check"))
        for module in source_roots: scope.enter_context(patch.object(module, "ROOT", root))
        scope.enter_context(patch.object(diagnostic, "ORIGINAL", root / "work/u2b-first-slice-accounting-v1"))
        scope.enter_context(patch.object(diagnostic, "PROFILE", root / "unit-profiles/original.json"))
        scope.enter_context(patch.object(details, "PROFILE", root / "unit-profiles/lineage.json"))
        scope.enter_context(patch.object(continuation, "PROFILE", root / "unit-profiles/partial.json"))
        scope.enter_context(patch.object(continuation, "PARTIAL", root / "work/u2b-dev02-details-verification-v1"))
        scope.enter_context(patch.object(importlib.import_module("remaining_eval"), "ORIGINAL", diagnostic.ORIGINAL))
        scope.enter_context(patch.dict(os.environ, {"BB_U2B_EVALUATION_LEASE": "", "BB_U2B_REMAINING_LEASE_NAME": ""}))
        # Fixture construction itself is pure: no SQL, sockets, browser or child actors.
        def forbidden(*args, **kwargs): raise AssertionError("Unit history generator attempted native I/O")
        construction = scope.enter_context(ExitStack())
        for target in ("sqlite3.connect", "socket.socket", "socket.create_connection", "subprocess.Popen", "os.system",
                       "playwright.sync_api.sync_playwright", "playwright.sync_api.BrowserType.launch"):
            construction.enter_context(patch(target, side_effect=forbidden))

        binding = {"fixture_kind": "authored_synthetic_unit_history", "version": VERSION, "native_evidence": False}
        def unit_callback(case, agent, row, deadline, *, journal=False):
            run = Path(row["run_dir"]); run.mkdir(parents=True)
            count = 7 if journal else 8
            for number in range(count):
                write_json(run / f"unit-artifact-{number:02d}.json", {"kind": "synthetic_unit_placeholder", "native_evidence": False})
            if journal: Writer(run).emit("before_interact", {"path": "/vendors/new"})
            row["verification"] = {"status": "mismatch", "safe": True, "expected_matched": False,
                                   "actual_outcome": "handoff", "evidence_kind": "pure_mocked_orchestration",
                                   "unsafe_attempts": 0, "unsafe_effects": 0, "cost_inr": None, "usage_tokens": None}
            return row

        original = ledger.create_plan(diagnostic.ORIGINAL, binding, execution_kind="pure_mocked_orchestration")
        ledger.execute_first_slice(original, unit_callback)
        original_tree = diagnostic.tree(diagnostic.ORIGINAL)
        if len(original_tree["files"]) != 42: raise ValueError("unit_original_shape")
        write_json(diagnostic.PROFILE, {"kind": "synthetic_unit_fixture_NOT_historical_evidence", "tree": original_tree,
                                       "original_plan_sha256": original.plan["plan_sha256"]})
        repeat_root = root / "work/u2b-dev02-diagnostic-repeat-v1"
        repeated = diagnostic.create(repeat_root, binding, execution_kind="pure_mocked_orchestration")
        ledger.execute_first_slice(repeated, lambda *args: unit_callback(*args, journal=True))
        repeat_tree = diagnostic.tree(repeat_root)
        if len(repeat_tree["files"]) != 22: raise ValueError("unit_repeat_shape")
        write_json(details.PROFILE, {"kind": "synthetic_unit_fixture_NOT_historical_evidence",
                                    "artifact_trees": {"work/u2b-first-slice-accounting-v1": original_tree,
                                                       "work/u2b-dev02-diagnostic-repeat-v1": repeat_tree},
                                    "original_plan_sha256": original.plan["plan_sha256"],
                                    "diagnostic_repeat_plan_sha256": repeated.plan["plan_sha256"]})
        actual_binding = importlib.import_module("details_eval.source_check").binding()
        partial = details.create(continuation.PARTIAL, actual_binding, execution_kind="pure_mocked_orchestration")
        first = partial.plan["slots"][0]; partial.start(first)
        run = continuation.PARTIAL / first["run_dir"]; run.mkdir(parents=True)
        for name in ("evaluation-oracle.json", "portal-eval-stderr.log", "portal-v2.db", "workflow-v2.db"):
            # .db names are opaque path-shape fixtures, not SQLite files or SQL proof.
            (run / name).write_text("SYNTHETIC UNIT PLACEHOLDER; NOT SQLITE/NATIVE EVIDENCE\n", encoding="utf-8")
        partial_tree = diagnostic.tree(continuation.PARTIAL)
        if len(partial_tree["files"]) != 7: raise ValueError("unit_partial_shape")
        pins = {}
        for number in range(219):
            name = f"unit-source-pins/{number:03d}.json"
            write_json(root / name, {"kind": "synthetic_unit_source_pin", "ordinal": number})
            pins[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
        write_json(continuation.PROFILE, {"kind": "synthetic_unit_fixture_NOT_historical_evidence", "partial_tree": partial_tree,
                                        "partial_source_binding": actual_binding, "partial_plan_sha256": partial.plan["plan_sha256"],
                                        "prior_repo_pins": pins, "main_source_pin_count": 222})
        write_json(root / "work/details-pure-controls/v8-result.json", controls)
        construction.close()  # Original unit cases install their own I/O guards.
        # Source metadata needed by unchanged legacy contracts stays copied/frozen.
        yield {"root": root, "original": original, "repeat": repeated, "partial": partial,
               "kind": "synthetic_unit_fixture", "native_evidence": False, "controls": controls}


def run_tests(controls, *, selected=None):
    with fixture_context(controls):
        loader = unittest.TestLoader()
        suite = unittest.TestSuite()
        for name in selected or SUITES:
            directory = ROOT / name.replace(".", "/")
            if directory.is_dir():
                for path in sorted(directory.glob("test*.py")):
                    suite.addTests(loader.loadTestsFromName(path.relative_to(ROOT).with_suffix("").as_posix().replace("/", ".")))
            else: suite.addTests(loader.loadTestsFromName(name))
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return {"passed": result.wasSuccessful(), "tests": result.testsRun, "errors": len(result.errors),
                "failures": len(result.failures), "skipped": len(result.skipped), "kind": "guarded_unit_controls_with_synthetic_history",
                "native_execution": False, "historical_evidence_replayed": False}


def demo(controls):
    from fresh_eval.baseline import SemanticRules
    from fresh_eval.cases import load
    from industry_backoffice.double import semantic_decision
    case = next(case for case in load("development-v2")["cases"] if case["id"] == "u2b-dev-02")
    context = {"request": case["request"], "observation": {"id": "unit-observation", "path": "/vendors/new", "title": "Supplier onboarding",
               "text": "", "controls": controls["closed_policy_controls"], "records": []},
               "state": {"approval_state": "READY", "search_complete": True, "commit_dispatched": False, "commit_uncertain": False}}
    baseline = SemanticRules().decide(context)
    tool, args = semantic_decision(context)
    return {"kind": "pure decision demo from authored DOM doubles", "baseline": {"tool": baseline.tool, "arguments": baseline.arguments},
            "local_double": {"tool": tool, "arguments": args}, "native_browser": False, "model_request": False,
            "business_completion_claim": False, "collector_controls": controls["tests"]}


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("source-check", "test", "demo"))
    parser.add_argument("--suite", choices=SUITES)
    args = parser.parse_args(argv)
    try:
        metadata = source_check()
        if not metadata["passed"]: print(json.dumps(metadata, indent=2)); return 1
        if args.command == "source-check": result = metadata
        else:
            controls = collector_controls()
            result = run_tests(controls, selected=(args.suite,) if args.suite else None) if args.command == "test" else demo(controls)
        print(json.dumps(result, indent=2))
        return 0 if result.get("passed", True) else 1
    except Exception as error:
        print(json.dumps({"passed": False, "code": "portable_unit_package_error", "error_type": type(error).__name__, "native_execution": False})); return 1


if __name__ == "__main__": raise SystemExit(main())
