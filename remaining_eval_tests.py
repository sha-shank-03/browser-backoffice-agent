"""Focused controls with a memory filesystem; no real sidecar or SQL/browser I/O."""
from contextlib import contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from durable_eval import ledger as old_ledger
from fresh_eval.cases import load, sha
from supplier_contract_tests.pure_support import PureTestCase
import remaining_eval as r


class MemoryPath:
    def __init__(self, fs, name): self.fs, self.name = fs, str(name).replace("\\", "/").rstrip("/")
    def __str__(self): return self.name
    def __truediv__(self, value): return MemoryPath(self.fs, self.name + "/" + str(value))
    def __lt__(self, other): return self.name < str(other)
    @property
    def name_only(self): return self.name.rsplit("/", 1)[-1]
    def relative_to(self, root): return PurePosixPath(self.name[len(str(root).rstrip("/")) + 1:])
    def exists(self): return self.name in self.fs.files or self.name in self.fs.dirs
    def is_file(self): return self.name in self.fs.files
    def is_dir(self): return self.name in self.fs.dirs
    def is_symlink(self): return False
    def read_bytes(self): return self.fs.files[self.name]
    def read_text(self, encoding="utf-8"): return self.read_bytes().decode(encoding)
    def open(self, mode):
        if mode != "rb": raise AssertionError("Only memory byte reads expected")
        return io.BytesIO(self.read_bytes())
    def mkdir(self, parents=False, exist_ok=False):
        if self.exists() and not exist_ok: raise FileExistsError(self.name)
        if parents:
            pieces = self.name.split("/")
            for size in range(2, len(pieces) + 1): self.fs.dirs.add("/".join(pieces[:size]))
        else: self.fs.dirs.add(self.name)
    def iterdir(self):
        if not self.is_dir(): raise FileNotFoundError(self.name)
        prefix = self.name + "/"
        names = {name for name in self.fs.dirs | set(self.fs.files) if name.startswith(prefix) and "/" not in name[len(prefix):]}
        return iter([MemoryEntry(self.fs, name) for name in sorted(names)])
    def rglob(self, pattern):
        prefix = self.name + "/"
        return [MemoryEntry(self.fs, name) for name in sorted(self.fs.dirs | set(self.fs.files)) if name.startswith(prefix)]


class MemoryEntry(MemoryPath):
    # pathlib's .name is used by the inherited immutable layout validator.
    @property
    def name(self): return self._path.rsplit("/", 1)[-1]
    @name.setter
    def name(self, value): self._path = value
    def __str__(self): return self._path
    def relative_to(self, root): return PurePosixPath(self._path[len(str(root).rstrip("/")) + 1:])
    def is_file(self): return self._path in self.fs.files
    def is_dir(self): return self._path in self.fs.dirs
    def read_bytes(self): return self.fs.files[self._path]


class MemoryFS:
    def __init__(self): self.files, self.dirs = {}, {"/memory"}
    def path(self, value):
        name = str(value)
        return MemoryPath(self, name if name.startswith("/memory") else "/memory/" + name)
    def put(self, path, data):
        name = str(path)
        parent = MemoryPath(self, name.rsplit("/", 1)[0]); parent.mkdir(parents=True, exist_ok=True)
        self.files[name] = data
    def exclusive(self, path, value):
        if path.exists(): raise FileExistsError(str(path))
        self.put(path, old_ledger.encoded(value))
    def projection(self, path, value): self.put(path, old_ledger.encoded(value))


class RemainingControls(PureTestCase):
    def setUp(self):
        super().setUp()
        # Read-only authored fixture metadata before installing the no-disk guard.
        self.full = load("development-v2")
        self.old = json.loads((r.ORIGINAL / "plan.json").read_text(encoding="utf-8"))
        self.binding = {"collector_version": "fresh-local-u2b-details.1", "remaining_version": r.VERSION,
                        "remaining_source_manifest_sha256": "synthetic-memory-only"}
        self.fs = MemoryFS(); self.root = self.fs.path("/memory"); self.out = self.root / r.OUTPUT
        self.calls = []
        self.original = [{"case_id": slot["case_id"], "agent": slot["agent"], "attempted": True,
                          "accounting_state": "completed", "original_slot_id": slot["slot_id"],
                          "execution_source_binding": deepcopy(self.old["source_binding"]),
                          "verification": {"safe": True, "expected_matched": ordinal < 2},
                          "provenance": "immutable_original_receipt"} for ordinal, slot in enumerate(self.old["slots"][:4])]
        def no_io(*args, **kwargs):
            self.forbidden_calls.append("forbidden_file_or_sql_io")
            raise AssertionError("Pure memory control attempted real file or SQL I/O")
        for target in ("sqlite3.connect", "pathlib.Path.open"):
            self.safety.enter_context(patch(target, side_effect=no_io))
        self.safety.enter_context(patch.object(r, "ROOT", self.root))
        self.safety.enter_context(patch.object(r, "scoped_path", side_effect=self.fs.path))
        self.safety.enter_context(patch.object(r, "source_binding", side_effect=lambda: deepcopy(self.binding)))
        self.safety.enter_context(patch.object(r, "original_plan", side_effect=lambda: deepcopy(self.old)))
        self.safety.enter_context(patch.object(r, "original_rows", side_effect=lambda: deepcopy(self.original)))
        self.safety.enter_context(patch.object(r, "load", side_effect=lambda suite: deepcopy(self.full)))
        self.safety.enter_context(patch.object(r, "require_lease"))
        self.safety.enter_context(patch.dict(os.environ, {r.LEASE_ENV: "browser-main-remaining-u2b-dev-03"}))
        self.safety.enter_context(patch.object(r, "exclusive_receipt", side_effect=self.fs.exclusive))
        self.safety.enter_context(patch.object(old_ledger, "exclusive_receipt", side_effect=self.fs.exclusive))
        self.safety.enter_context(patch.object(old_ledger, "replace_projection", side_effect=self.fs.projection))

    def ledger(self, kind="pure_mocked_orchestration"):
        plan = r.make_plan(self.binding, execution_kind=kind)
        self.out.mkdir(parents=True)
        self.fs.exclusive(self.out / "plan.json", plan)
        (self.out / "slots").mkdir()
        for slot in plan["slots"]: (self.out / "slots" / slot["slot_id"]).mkdir()
        return r.RemainingLedger(self.out, self.binding)

    def actor(self, case, agent, row, deadline):
        self.calls.append((case["id"], agent))
        run = self.fs.path(row["run_dir"])
        self.fs.put(run / "events-v2.jsonl", b'{"kind":"memory_control"}\n')
        row["verification"] = {"status": "mismatch", "safe": True, "expected_matched": False,
                               "actual_outcome": "handoff", "evidence_kind": "pure_mocked_orchestration",
                               "unsafe_attempts": 0, "unsafe_effects": 0, "cost_inr": None, "usage_tokens": None}
        return row

    def dispatch(self, ledger, case="u2b-dev-03", actor=None, **kwargs):
        return r.dispatch(ledger, case, ledger.plan["plan_sha256"], r.state_sha256(ledger), actor or self.actor, **kwargs)

    def test_fixed_twenty_intentions_and_mixed_source_twenty_four_inventory(self):
        ledger = self.ledger(); report = ledger.report()
        self.assertEqual([s["slot_id"] for s in ledger.plan["slots"]], [s["slot_id"] for s in self.old["slots"][4:]])
        self.assertEqual(len(report["rows"]), 20); self.assertEqual(report["accounting_states"]["pending"], 20)
        self.assertEqual(len(report["logical_inventory"]), 24)
        self.assertEqual(report["logical_inventory"][:4], self.original)
        self.assertTrue(all(row["execution_source_binding"] == self.binding for row in report["rows"]))
        self.assertTrue(all(row["execution_source_binding_status"] == "planned" for row in report["rows"]))
        self.assertEqual(report["included_diagnostic_or_alias_rows"], 0)
        self.assertIsNone(report["mixed_source_quality_summary"])
        self.assertEqual(report["new_unique_tasks"], 0)
        for metrics in report["summary"]["agents"].values():
            self.assertEqual(metrics["attempted"]["N"], 10); self.assertIsNone(metrics["actual_cost_inr"])
        for key in ("freeze_eligible", "capability_eligible", "full_development_complete", "native_collector_fix_verified", "quality_acceptance"):
            self.assertFalse(report[key])

    def test_initial_state_prediction_matches_memory_initialization_without_report_bytes(self):
        ledger = self.ledger()
        self.assertEqual(r.initial_state_sha256(ledger.plan), r.state_sha256(ledger))
        ledger.write_report()
        self.assertEqual(r.initial_state_sha256(ledger.plan), r.state_sha256(ledger))

    def test_exact_next_pair_source_plan_state_and_named_lease_are_required(self):
        ledger = self.ledger(); initial = r.state_sha256(ledger)
        for case in ("u2b-dev-01", "u2b-dev-02", "u2b-dev-04", "repeat-02-local-double"):
            with patch.dict(os.environ, {r.LEASE_ENV: f"browser-main-remaining-{case}"}):
                with self.assertRaises(ValueError): self.dispatch(ledger, case)
        for plan, state in (("changed", initial), (ledger.plan["plan_sha256"], "changed")):
            with self.assertRaises(ValueError): r.dispatch(ledger, "u2b-dev-03", plan, state, self.actor)
        with patch.dict(os.environ, {r.LEASE_ENV: "other-main-lease"}):
            with self.assertRaisesRegex(ValueError, "exact_main_remaining_pair_lease_name_required"): self.dispatch(ledger)
        with patch.object(r, "require_lease", side_effect=ValueError("missing-main-lease")):
            with self.assertRaises(ValueError): self.dispatch(ledger)
        with patch.object(r, "source_binding", return_value={"changed": True}):
            with self.assertRaises(ValueError): self.dispatch(ledger)
        self.assertEqual(self.calls, []); self.assertEqual(ledger.report()["accounting_states"]["pending"], 20)

    def test_two_single_use_actor_dispatches_then_only_next_case_is_eligible(self):
        ledger = self.ledger(); before = deepcopy(self.old)
        report = self.dispatch(ledger)
        self.assertEqual(self.calls, [("u2b-dev-03", "semantic-rules-v2"), ("u2b-dev-03", "local-double")])
        self.assertEqual(report["accounting_states"]["completed"], 2); self.assertEqual(report["accounting_states"]["pending"], 18)
        self.assertEqual([row["execution_source_binding_status"] for row in report["rows"]], ["executed"] * 2 + ["planned"] * 18)
        self.assertEqual(self.old, before); self.assertEqual(report["logical_inventory"][:4], self.original)
        with self.assertRaises(ValueError): self.dispatch(ledger)
        self.assertEqual([s["slot_id"] for s in r.next_pair(ledger, "u2b-dev-04")], ["07-semantic-rules-v2", "08-local-double"])
        with self.assertRaises(ValueError): ledger.start(ledger.plan["slots"][2])
        with self.assertRaises(ValueError): ledger.recover(owner_stopped=True)

    def test_unknown_interruption_stops_companion_and_all_later_pairs(self):
        ledger = self.ledger()
        def interrupted(*args): raise KeyboardInterrupt("memory-only interruption")
        with self.assertRaises(KeyboardInterrupt): self.dispatch(ledger, actor=interrupted)
        report = ledger.report()
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(report["accounting_states"]["pending"], 19)
        for case in ("u2b-dev-03", "u2b-dev-04"):
            with patch.dict(os.environ, {r.LEASE_ENV: f"browser-main-remaining-{case}"}):
                with self.assertRaises(ValueError): self.dispatch(ledger, case)
        self.assertEqual(self.calls, [])

    def test_completed_pending_partial_pair_is_not_replayed_or_skipped(self):
        ledger = self.ledger(); moments = iter((0, 0, 880))
        report = self.dispatch(ledger, clock=lambda: next(moments))
        self.assertEqual(len(self.calls), 1); self.assertEqual(report["accounting_states"]["pending"], 19)
        for case in ("u2b-dev-03", "u2b-dev-04"):
            with patch.dict(os.environ, {r.LEASE_ENV: f"browser-main-remaining-{case}"}):
                with self.assertRaises(ValueError): self.dispatch(ledger, case)

    def test_partial_claim_and_unsafe_terminal_block_later_dispatch(self):
        ledger = self.ledger()
        self.fs.put(ledger.slot_path(ledger.plan["slots"][0]) / "STARTED.json", b"{")
        with self.assertRaises(ValueError): self.dispatch(ledger)
        self.assertEqual(ledger.report()["accounting_states"]["interrupted_unknown"], 1)
        # A separate all-memory test state exercises a known but unsafe terminal.
        self.fs.files.clear(); self.fs.dirs = {"/memory"}
        ledger = self.ledger()
        def unsafe(*args):
            row = self.actor(*args); row["verification"]["safe"] = False; return row
        self.dispatch(ledger, actor=unsafe)
        self.assertEqual(ledger.report()["accounting_states"]["pending"], 19)
        with self.assertRaises(ValueError): self.dispatch(ledger)

    def test_raw_and_receipt_tampering_cannot_be_relabelled_as_safe_completion(self):
        ledger = self.ledger(); self.dispatch(ledger)
        self.fs.put(self.out / "runs/semantic-rules-v2/u2b-dev-03/events-v2.jsonl", b"changed")
        with self.assertRaises(ValueError): self.dispatch(ledger, "u2b-dev-04")
        self.assertEqual(ledger.report()["accounting_states"]["interrupted_unknown"], 1)
        path = ledger.slot_path(ledger.plan["slots"][1]) / "TERMINAL.json"
        record = json.loads(path.read_text()); record["row"]["verification"]["expected_matched"] = True
        self.fs.put(path, json.dumps(record).encode())
        with self.assertRaisesRegex(ValueError, "receipt_content_drift"): ledger.report()

    def test_missing_intention_source_data_or_fixed_output_alias_is_rejected(self):
        ledger = self.ledger(); saved = deepcopy(ledger.plan)
        for removed in (0, 19):
            changed = deepcopy(saved); del changed["slots"][removed]
            self.fs.put(self.out / "plan.json", old_ledger.encoded(changed))
            with self.assertRaises(ValueError): r.RemainingLedger(self.out, self.binding)
        self.fs.put(self.out / "plan.json", old_ledger.encoded(saved))
        with self.assertRaises(ValueError): r.RemainingLedger(self.out, {"changed": True})
        changed_old = deepcopy(self.old); changed_old["dataset_sha256"] = "changed"
        with patch.object(r, "original_plan", return_value=changed_old):
            with self.assertRaises(ValueError): r.make_plan()
        for output in ("work/u2b-first-slice-accounting-v1", "work/u2b-dev02-details-local-continuation-v1", r.OUTPUT + "/alias"):
            with self.assertRaises(ValueError): r.fixed_output(output)

    def test_unreviewed_initial_plan_state_and_lease_create_no_memory_sidecar(self):
        plan = r.make_plan()
        with patch.object(r, "require_lease", side_effect=ValueError("unleased")):
            with self.assertRaises(ValueError): r.evaluate(self.out, "u2b-dev-03", plan["plan_sha256"], r.initial_state_sha256(plan))
        for plan_hash, state_hash, case in (("changed", r.initial_state_sha256(plan), "u2b-dev-03"),
              (plan["plan_sha256"], "changed", "u2b-dev-03"), (plan["plan_sha256"], r.initial_state_sha256(plan), "u2b-dev-04")):
            with patch.dict(os.environ, {r.LEASE_ENV: f"browser-main-remaining-{case}"}):
                with self.assertRaises(ValueError): r.evaluate(self.out, case, plan_hash, state_hash)
        self.assertFalse(self.out.exists())
        with redirect_stdout(io.StringIO()), patch.object(r, "require_lease", side_effect=ValueError("unleased")):
            self.assertEqual(r.main(["run-next", "--out", str(self.out), "--case-id", "u2b-dev-03", "--plan-sha256", "changed", "--state-sha256", "changed"]), 1)

    def test_runtime_reuses_same_collector_run_one_full_data_and_per_slot_source(self):
        from fresh_eval import native
        from details_eval import native as collector_native
        entries, calls = [], []
        @contextmanager
        def collector(): entries.append("entered"); yield
        def actor(case, agent, row, binding, manifest, deadline):
            calls.append((agent, binding, manifest)); return row
        def pure_dispatch(ledger, case_id, plan, state, executor):
            case = self.full["cases"][2]
            for agent in r.AGENTS:
                row = {"run_dir": str(self.out / f"runs/{agent}/{case_id}")}
                executor(case, agent, row, 900)
            return ledger.report()
        plan = r.make_plan()
        with patch.object(collector_native, "bind_collector", collector), patch.object(native, "run_one", actor), patch.object(r, "dispatch", pure_dispatch):
            r.evaluate(self.out, "u2b-dev-03", plan["plan_sha256"], r.initial_state_sha256(plan))
        self.assertEqual(entries, ["entered", "entered"])
        self.assertEqual([call[0] for call in calls], list(r.AGENTS))
        self.assertEqual([call[1]["original_slot_id"] for call in calls], ["05-semantic-rules-v2", "06-local-double"])
        for agent, actual, manifest in calls:
            self.assertEqual(manifest, self.full); self.assertEqual(actual["collector_version"], self.binding["collector_version"])
            self.assertEqual(actual["remaining_source_manifest_sha256"], self.binding["remaining_source_manifest_sha256"])

    def test_source_seal_rejects_source_history_directory_and_data_drift_in_memory(self):
        seal_path = self.root / "u2b-remaining-source-manifest.json"
        source = b"# authored memory source control\n"
        for name in r.SOURCES: self.fs.put(self.root / name, source)
        preserved = {}
        for ordinal in range(247):
            name = f"frozen/{ordinal}"; self.fs.put(self.root / name, b"frozen"); preserved[name] = hashlib.sha256(b"frozen").hexdigest()
        trees = {}
        for name, count in (("work/u2b-first-slice-accounting-v1", 42), ("work/u2b-dev02-diagnostic-repeat-v1", 22),
                            ("work/u2b-dev02-details-verification-v1", 7), ("work/u2b-dev02-details-local-continuation-v1", 12)):
            for ordinal in range(count): self.fs.put(self.root / name / str(ordinal), b"retained")
            trees[name] = r.tree(self.root / name)
        seal = {"files": {name: hashlib.sha256(source).hexdigest() for name in r.SOURCES},
                "preserved_repo_files": preserved, "history_trees": trees, "dataset_sha256": sha(self.full)}
        self.fs.put(seal_path, json.dumps(seal).encode())
        with patch.object(r, "SEAL", seal_path):
            self.assertTrue(r.source_check()["passed"])
            self.fs.put(self.root / r.SOURCES[0], b"# changed\n"); self.assertFalse(r.source_check()["passed"])
            self.fs.put(self.root / r.SOURCES[0], source)
            self.fs.put(self.root / "frozen/0", b"changed"); self.assertFalse(r.source_check()["passed"])
            self.fs.put(self.root / "frozen/0", b"frozen")
            (self.root / "work/u2b-dev02-details-verification-v1/new-empty-dir").mkdir()
            self.assertFalse(r.source_check()["passed"])
            self.fs.dirs.remove(str(self.root / "work/u2b-dev02-details-verification-v1/new-empty-dir"))
            changed = deepcopy(self.full); changed["cases"][2]["expected"] = "handoff"
            with patch.object(r, "load", return_value=changed): self.assertFalse(r.source_check()["passed"])
