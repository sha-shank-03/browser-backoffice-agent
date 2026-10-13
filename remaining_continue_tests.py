"""Focused preserved-boundary controls using the existing memory fixtures only."""
from contextlib import ExitStack, contextmanager, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
import unittest
from unittest.mock import patch

from durable_eval import ledger as old_ledger
from fresh_eval.cases import sha
import remaining_eval_tests as fixtures
import remaining_eval as engine
import remaining_continue as c


class PreservedContinuationControls(unittest.TestCase):
    def setUp(self):
        self.base = fixtures.RemainingControls("runTest")
        self.base.setUp()  # Installs existing socket/process/browser/SQL/Path.open guards.
        self.safety = ExitStack()
        self.addCleanup(self.base.doCleanups)
        self.addCleanup(self.safety.close)
        self.addCleanup(lambda: self.assertEqual(self.base.forbidden_calls, []))
        self.fs, self.out, self.root = self.base.fs, self.base.out, self.base.root
        self.old = self.base.ledger()
        first, unknown = self.old.plan["slots"][:2]
        self.old._dispatch_slots = (first["slot_id"], unknown["slot_id"])
        self.old.start(first)
        row = old_ledger.unknown_row(self.old, first, "memory_actor")
        row = self.base.actor(self.base.full["cases"][2], first["agent"], row, 900)
        row["verification"].update(status="verified", expected_matched=True, actual_outcome="created")
        # Fake bytes with the preserved capture's names: SQLite is never opened.
        for name in ("actor-result-v2.json", "evaluation-diagnostic.jsonl", "evaluation-oracle.json", "independent-evaluation.json",
                     "portal-eval-stderr.log", "portal-v2.db", "review-v2.json", "reviewer-decision.json", "workflow-v2.db"):
            self.fs.put(self.out / first["run_dir"] / name, b"memory_baseline_bytes")
        self.old.terminal(first, "completed", row, "memory_actor")
        self.old.start(unknown)
        for name in ("evaluation-diagnostic.jsonl", "evaluation-oracle.json", "portal-eval-stderr.log", "portal-v2.db", "workflow-v2.db", "workflow-v2.db-journal"):
            self.fs.put(self.out / unknown["run_dir"] / name, b"memory_unknown_hot_bytes")
        self.old._dispatch_slots = ()
        self.old.write_report()
        self.base.calls.clear()
        preserved = c.tree(self.out)
        self.assertEqual(len(preserved["files"]), 21)
        self.boundary = {"plan_sha256": self.old.plan["plan_sha256"], "engine_source_binding_sha256": sha(self.base.binding),
                         "starting_state_sha256": engine.state_sha256(self.old), "preserved_tree": preserved,
                         "completed_slot_id": first["slot_id"], "unknown_slot_id": unknown["slot_id"],
                         "allowed_slot_ids": [slot["slot_id"] for slot in self.old.plan["slots"][2:]]}
        self.seal = {"boundary": self.boundary, "boundary_sha256": sha(self.boundary)}
        self.actual = {**self.base.binding, "continuation_version": c.VERSION,
                       "continuation_source_manifest_sha256": "memory_only_new_source",
                       "preserved_boundary_sha256": self.seal["boundary_sha256"]}
        self.safety.enter_context(patch.object(c, "seal_data", side_effect=lambda: deepcopy(self.seal)))
        self.safety.enter_context(patch.object(c, "actual_binding", side_effect=lambda: deepcopy(self.actual)))
        self.safety.enter_context(patch.object(c, "replace_projection", side_effect=self.fs.projection))
        self.safety.enter_context(patch.dict(os.environ, {engine.LEASE_ENV: "browser-main-remaining-u2b-dev-04"}))
        self.ledger = c.ContinuationLedger(self.out)

    def dispatch(self, case="u2b-dev-04", actor=None, **kwargs):
        return c.dispatch(self.ledger, case, self.ledger.plan["plan_sha256"], self.actual["preserved_boundary_sha256"],
                          self.actual["continuation_source_manifest_sha256"], c.state_sha256(self.ledger), actor or self.base.actor, **kwargs)

    def preserved_unchanged(self):
        for name, digest in self.boundary["preserved_tree"]["files"].items():
            self.assertEqual(hashlib.sha256((self.out / name).read_bytes()).hexdigest(), digest)
        self.assertFalse((self.out / "slots/06-local-double/TERMINAL.json").exists())

    def test_only_pinned_boundary_is_crossed_and_original_selector_still_blocks(self):
        with self.assertRaises(ValueError): engine.next_pair(self.old, "u2b-dev-04")
        self.assertEqual([s["slot_id"] for s in c.next_pair(self.ledger, "u2b-dev-04")], ["07-semantic-rules-v2", "08-local-double"])
        for case in ("u2b-dev-03", "u2b-dev-05", "repeat-02-local-double"):
            with self.assertRaises(ValueError): c.next_pair(self.ledger, case)
        self.preserved_unchanged()

    def test_twenty_and_twenty_four_denominators_keep_unknown_without_pooled_quality(self):
        result = self.ledger.report()
        self.assertEqual(len(result["rows"]), 20); self.assertEqual(len(result["logical_inventory"]), 24)
        self.assertEqual(result["accounting_states"], {"completed": 1, "interrupted_unknown": 1, "pending": 18, "failed": 0})
        self.assertEqual(result["policy_accounting_denominators"], {agent: 10 for agent in engine.AGENTS})
        self.assertIsNone(result["summary"]); self.assertIsNone(result["mixed_source_quality_summary"])
        self.assertIsNone(result["source_binding"])
        for metrics in result["per_source_summary"]["summary"]["agents"].values(): self.assertEqual(metrics["attempted"]["N"], 9)
        unknown = result["rows"][1]
        for key in ("safe", "actual_outcome", "transport_requests", "cost_inr", "usage_tokens"): self.assertIsNone(unknown["verification"].get(key))
        self.assertEqual(result["included_diagnostic_or_alias_rows"], 0)
        for key in ("execution_complete", "full_development_complete", "freeze_eligible", "capability_eligible", "quality_acceptance", "native_collector_fix_verified"):
            self.assertFalse(result[key])

    def test_two_single_dispatches_preserve_all_old_bytes_then_only_next_pair(self):
        result = self.dispatch()
        self.assertEqual(self.base.calls, [("u2b-dev-04", "semantic-rules-v2"), ("u2b-dev-04", "local-double")])
        self.assertEqual(result["accounting_states"]["completed"], 3); self.assertEqual(result["accounting_states"]["pending"], 16)
        with self.assertRaises(ValueError): self.dispatch()
        self.assertEqual([s["slot_id"] for s in c.next_pair(self.ledger, "u2b-dev-05")], ["09-semantic-rules-v2", "10-local-double"])
        self.preserved_unchanged()

    def test_supplementary_hashes_bind_both_new_receipts_and_old_envelopes_unchanged(self):
        self.dispatch()
        for slot in self.ledger.plan["slots"][2:4]:
            for name in ("STARTED.json", "TERMINAL.json"):
                record = json.loads((self.ledger.slot_path(slot) / name).read_text())
                self.assertEqual(record["continuation_source_binding_sha256"], sha(self.actual))
                self.assertEqual(record["preserved_boundary_sha256"], self.actual["preserved_boundary_sha256"])
        for slot in self.ledger.plan["slots"][:2]:
            self.assertEqual(self.ledger.envelope(slot), self.old.envelope(slot))
        slot = self.ledger.plan["slots"][2]
        path = self.ledger.slot_path(slot) / "STARTED.json"
        record = json.loads(path.read_text()); del record["preserved_boundary_sha256"]
        record["receipt_sha256"] = sha({k: v for k, v in record.items() if k != "receipt_sha256"})
        self.fs.put(path, json.dumps(record).encode())
        with self.assertRaisesRegex(ValueError, "receipt_binding_drift"): self.ledger.report()

    def test_any_new_unknown_stops_companion_and_all_later_pairs(self):
        def interrupted(*args): raise KeyboardInterrupt("memory_unknown")
        with self.assertRaises(KeyboardInterrupt): self.dispatch(actor=interrupted)
        result = self.ledger.report()
        self.assertEqual(result["accounting_states"]["interrupted_unknown"], 2); self.assertEqual(result["accounting_states"]["pending"], 17)
        for case in ("u2b-dev-04", "u2b-dev-05"):
            with patch.dict(os.environ, {engine.LEASE_ENV: f"browser-main-remaining-{case}"}):
                with self.assertRaises(ValueError): self.dispatch(case)
        self.preserved_unchanged()

    def test_new_unsafe_or_incomplete_result_cannot_use_preserved_exception(self):
        def unsafe(*args):
            row = self.base.actor(*args); row["verification"]["safe"] = False; return row
        self.dispatch(actor=unsafe)
        self.assertEqual(len(self.base.calls), 1)
        with self.assertRaises(ValueError): c.next_pair(self.ledger, "u2b-dev-05")
        self.preserved_unchanged()

    def test_incomplete_new_actor_evidence_stops_companion_and_later_pairs(self):
        def incomplete(*args):
            row = self.base.actor(*args); row["verification"].update(status="unknown", safe=None); return row
        self.dispatch(actor=incomplete)
        self.assertEqual(len(self.base.calls), 1)
        self.assertEqual(self.ledger.report()["accounting_states"]["pending"], 17)
        with self.assertRaises(ValueError): c.next_pair(self.ledger, "u2b-dev-05")
        self.preserved_unchanged()

    def test_completed_pending_new_partial_pair_cannot_replay_or_skip(self):
        moments = iter((0, 0, 880))
        self.dispatch(clock=lambda: next(moments))
        self.assertEqual(len(self.base.calls), 1)
        for case in ("u2b-dev-04", "u2b-dev-05"):
            with self.assertRaises(ValueError): c.next_pair(self.ledger, case)

    def test_boundary_raw_hot_journal_and_old_projection_tampering_are_rejected(self):
        for name in ("slots/05-semantic-rules-v2/TERMINAL.json", "slots/06-local-double/STARTED.json",
                     "runs/local-double/u2b-dev-03/workflow-v2.db-journal", "report.json"):
            path = self.out / name; saved = path.read_bytes()
            self.fs.put(path, b"changed")
            with self.assertRaises(ValueError): self.ledger.report()
            self.fs.put(path, saved)
        self.preserved_unchanged()

    def test_preserved_terminal_creation_replay_alias_and_unexpected_path_are_forbidden(self):
        for slot in self.ledger.plan["slots"][:2]:
            with self.assertRaises(ValueError): self.ledger.start(slot)
            with self.assertRaises(ValueError): self.ledger.terminal(slot, "completed", {}, "invented")
        self.fs.put(self.out / "slots/06-local-double/TERMINAL.json", b"{}")
        with self.assertRaises(ValueError): self.ledger.report()
        del self.fs.files[str(self.out / "slots/06-local-double/TERMINAL.json")]
        self.fs.put(self.out / "runs/local-double/u2b-dev-03/new-alias.json", b"{}")
        with self.assertRaises(ValueError): self.ledger.report()
        with self.assertRaises(ValueError): c.ContinuationLedger("work/other-sidecar")
        with self.assertRaises(ValueError): self.ledger.recover(owner_stopped=True)

    def test_exact_plan_boundary_source_state_named_lease_and_source_drift_guard_dispatch(self):
        expected = [self.ledger.plan["plan_sha256"], self.actual["preserved_boundary_sha256"],
                    self.actual["continuation_source_manifest_sha256"], c.state_sha256(self.ledger)]
        for index in range(4):
            changed = list(expected); changed[index] = "changed"
            with self.assertRaises(ValueError): c.dispatch(self.ledger, "u2b-dev-04", *changed, self.base.actor)
        with patch.dict(os.environ, {engine.LEASE_ENV: "wrong-lease"}):
            with self.assertRaises(ValueError): self.dispatch()
        with patch.object(engine, "require_lease", side_effect=ValueError("unleased")):
            with self.assertRaises(ValueError): self.dispatch()
        with patch.object(c, "actual_binding", return_value={"source_changed": True}):
            with self.assertRaises(ValueError): self.dispatch()
        self.assertEqual(self.base.calls, []); self.assertFalse((self.out / c.PROJECTION).exists())

    def test_disposable_projection_does_not_change_state_or_frozen_root_report(self):
        state = c.state_sha256(self.ledger); frozen = (self.out / "report.json").read_bytes()
        self.ledger.write_report()
        self.assertTrue((self.out / c.PROJECTION).exists())
        self.assertEqual(c.state_sha256(self.ledger), state)
        self.fs.put(self.out / c.PROJECTION, b"disposable_changed_bytes")
        self.assertEqual(c.state_sha256(self.ledger), state)
        self.assertEqual((self.out / "report.json").read_bytes(), frozen)
        self.preserved_unchanged()

    def test_actual_per_row_source_attribution_and_tampered_new_raw_tree(self):
        self.dispatch(); result = self.ledger.report()
        self.assertEqual(result["rows"][0]["execution_source_binding"], self.base.binding)
        self.assertEqual(result["rows"][1]["execution_source_binding"], self.base.binding)
        self.assertTrue(all(row["execution_source_binding"] == self.actual for row in result["rows"][2:]))
        self.assertEqual([row["execution_source_binding_status"] for row in result["rows"][2:]], ["executed"] * 2 + ["planned"] * 16)
        self.fs.put(self.out / "runs/semantic-rules-v2/u2b-dev-04/unexpected-raw.json", b"changed")
        self.assertEqual(self.ledger.report()["accounting_states"]["interrupted_unknown"], 2)
        with self.assertRaises(ValueError): c.next_pair(self.ledger, "u2b-dev-05")

    def test_runtime_reuses_same_collector_full_cases_and_supplementary_actor_binding(self):
        from fresh_eval import native
        from details_eval import native as collector_native
        entries, calls = [], []
        @contextmanager
        def collector(): entries.append("collector"); yield
        def actor(case, agent, row, binding, full, deadline): calls.append((case, agent, binding, full)); return row
        def memory_dispatch(ledger, case_id, *args):
            executor = args[-1]
            for agent in engine.AGENTS:
                executor(self.base.full["cases"][3], agent, {}, 900)
            return ledger.report()
        values = (self.ledger.plan["plan_sha256"], self.actual["preserved_boundary_sha256"], self.actual["continuation_source_manifest_sha256"], c.state_sha256(self.ledger))
        with patch.object(collector_native, "bind_collector", collector), patch.object(native, "run_one", actor), patch.object(c, "dispatch", memory_dispatch):
            c.evaluate(self.out, "u2b-dev-04", *values)
        self.assertEqual(entries, ["collector", "collector"])
        self.assertEqual([call[2]["original_slot_id"] for call in calls], ["07-semantic-rules-v2", "08-local-double"])
        for case, agent, binding, full in calls:
            self.assertEqual(full, self.base.full); self.assertEqual(binding["continuation_source_binding_sha256"], sha(self.actual))
            self.assertEqual(binding["preserved_boundary_sha256"], self.actual["preserved_boundary_sha256"])
        self.preserved_unchanged()

    def test_unleased_entry_does_not_write_projection_or_claim_and_derivation_is_read_only(self):
        before = deepcopy(c.tree(self.out))
        with patch.object(engine, "require_lease", side_effect=ValueError("unleased")), redirect_stdout(io.StringIO()):
            self.assertEqual(c.main(["run-next", "--out", str(self.out), "--case-id", "u2b-dev-04", "--plan-sha256", "x", "--boundary-sha256", "x", "--source-sha256", "x", "--state-sha256", "x"]), 1)
        with redirect_stdout(io.StringIO()) as output: self.assertEqual(c.main(["derive-dev04"]), 0)
        value = json.loads(output.getvalue())
        self.assertEqual(value["selected_original_slot_ids"], ["07-semantic-rules-v2", "08-local-double"])
        self.assertFalse(value["sidecar_mutated"]); self.assertEqual(c.tree(self.out), before)

    def test_source_history_and_boundary_seal_drift_in_memory(self):
        source = b"# memory continuation source\n"
        self.seal["files"] = {name: hashlib.sha256(source).hexdigest() for name in c.SOURCES}
        for name in c.SOURCES: self.fs.put(self.root / name, source)
        self.seal["preserved_repo_files"] = {}
        for ordinal in range(250):
            name = f"frozen/{ordinal}"; self.fs.put(self.root / name, b"frozen")
            self.seal["preserved_repo_files"][name] = hashlib.sha256(b"frozen").hexdigest()
        self.seal["history_trees"] = {}
        for root, count in (("old/a", 42), ("old/b", 22), ("old/c", 7), ("old/d", 12)):
            for ordinal in range(count): self.fs.put(self.root / root / str(ordinal), b"history")
            self.seal["history_trees"][root] = c.tree(self.root / root)
        self.assertTrue(c.source_check()["passed"])
        self.fs.put(self.root / c.SOURCES[0], b"# changed\n"); self.assertFalse(c.source_check()["passed"])
        self.fs.put(self.root / c.SOURCES[0], source)
        self.fs.put(self.root / "frozen/0", b"changed"); self.assertFalse(c.source_check()["passed"])
        self.fs.put(self.root / "frozen/0", b"frozen")
        (self.root / "old/c/unexpected-empty-directory").mkdir(); self.assertFalse(c.source_check()["passed"])
        self.fs.dirs.remove(str(self.root / "old/c/unexpected-empty-directory"))
        self.seal["boundary"]["allowed_slot_ids"].pop(); self.assertFalse(c.source_check()["passed"])
