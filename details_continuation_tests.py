"""Focused source/filesystem controls; all native/SQL/network creation is guarded."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
import shutil
import uuid
from unittest.mock import patch

from durable_eval.ledger import ROOT
from supplier_contract_tests.pure_support import PureTestCase
from details_continuation import continuation as c


class ContinuationControls(PureTestCase):
    def setUp(self):
        super().setUp()
        def no_sql(*args, **kwargs):
            self.forbidden_calls.append("forbidden_sql")
            raise AssertionError("Pure continuation control attempted SQL")
        self.safety.enter_context(patch("sqlite3.connect", side_effect=no_sql))
        self.relative = "work/details-continuation-pure/" + uuid.uuid4().hex
        self.safety.enter_context(patch.object(c, "OUTPUT", self.relative))
        self.out = ROOT / self.relative
        self.binding = {"continuation_version": "synthetic-pure-control"}
        self.calls = []

    def ledger(self):
        return c.create(self.out, self.binding, execution_kind="pure_mocked_orchestration")

    def actor(self, case, agent, row, deadline):
        self.calls.append((case["id"], agent))
        run = self.out / f"runs/{agent}/{case['id']}"
        run.mkdir(parents=True)
        (run / "events-v2.jsonl").write_text('{"kind":"synthetic_pure_control"}\n', encoding="utf-8")
        row["verification"] = {"status": "mismatch", "safe": True, "expected_matched": False,
                               "actual_outcome": "handoff", "evidence_kind": "pure_mocked_orchestration",
                               "unsafe_attempts": 0, "unsafe_effects": 0, "cost_inr": None, "usage_tokens": None}
        return row

    def test_two_intentions_keep_unknown_and_pending_denominators(self):
        ledger = self.ledger()
        report = ledger.report()
        self.assertEqual(report["accounting_states"], {"pending": 1, "completed": 0, "failed": 0, "interrupted_unknown": 1})
        self.assertEqual(len(report["rows"]), 2)
        unknown, pending = report["rows"]
        self.assertIsNone(unknown["verification"].get("actual_outcome"))
        self.assertIsNone(unknown["verification"]["safe"])
        self.assertIsNone(unknown["provider_requests"])
        self.assertFalse(pending["attempted"])
        self.assertEqual(report["summary"]["intended_paired_runs"], 2)
        for metrics in report["summary"]["agents"].values():
            self.assertEqual(metrics["expected_postconditions"]["N"], 1)
        self.assertIsNone(report["summary"]["pairs"][0]["winner"])
        self.assertFalse(report["summary"]["complete"])
        self.assertEqual(report["new_unique_tasks"], 0)
        self.assertEqual(report["original_pending_slots"], 20)
        for key in ("native_collector_fix_verified", "quality_acceptance", "freeze_eligible", "capability_eligible"):
            self.assertFalse(report[key])

    def test_unknown_attempted_and_output_aliases_are_rejected(self):
        ledger = self.ledger()
        with self.assertRaises(ValueError): ledger.start(ledger.index[c.RETAINED])
        for change in ({"agent": "semantic-rules-v2"}, {"partial_slot_id": "details-01-semantic-rules-v2"},
                       {"source_binding_sha256": "changed"}, {"case_id": "u2b-dev-01"}):
            with self.assertRaises(ValueError): ledger.start({**ledger.index[c.TARGET], **change})
        for relative in ("work/u2b-first-slice-accounting-v1", "work/u2b-dev02-diagnostic-repeat-v1/alias",
                         "work/u2b-dev02-details-verification-v1", self.relative + "/alias"):
            with self.assertRaises(ValueError): c.make_plan(self.binding, output_relative=relative)
        self.assertEqual(self.calls, [])

    def test_only_local_double_dispatches_once_with_same_existing_ledger_seam(self):
        ledger = self.ledger()
        before = c.tree(c.PARTIAL)
        report = c.execute_pending(ledger, self.actor)
        self.assertEqual(self.calls, [("u2b-dev-02", "local-double")])
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(report["accounting_states"]["completed"], 1)
        self.assertEqual(report["retained_partial_accounting_states"]["pending"], 1)
        self.assertEqual(c.tree(c.PARTIAL), before)
        (self.out / "runs/local-double/u2b-dev-02/events-v2.jsonl").write_text("synthetic changed raw file")
        self.assertEqual(ledger.report()["accounting_states"]["interrupted_unknown"], 2)
        with self.assertRaises(ValueError): c.execute_pending(ledger, self.actor)
        with self.assertRaises(FileExistsError): self.ledger()
        with self.assertRaises(ValueError): ledger.recover(owner_stopped=True)
        self.assertEqual(len(self.calls), 1)

    def test_new_interruption_is_spent_without_replaying_either_policy(self):
        ledger = self.ledger()
        def interrupted(*args): raise KeyboardInterrupt("synthetic pure interruption")
        with self.assertRaises(KeyboardInterrupt): c.execute_pending(ledger, interrupted)
        report = c.ContinuationLedger(self.out, self.binding).report()
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 2)
        with self.assertRaises(ValueError): c.execute_pending(ledger, self.actor)
        self.assertEqual(self.calls, [])

    def test_omitted_unknown_or_pending_plan_rows_and_source_drift_fail(self):
        ledger = self.ledger()
        original = deepcopy(ledger.plan)
        for removed in (c.RETAINED, c.TARGET):
            altered = deepcopy(original)
            altered["slots"] = [s for s in altered["slots"] if s["slot_id"] != removed]
            (self.out / "plan.json").write_text(json.dumps(altered), encoding="utf-8")
            with self.assertRaises(ValueError): c.ContinuationLedger(self.out, self.binding)
        (self.out / "plan.json").write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaises(ValueError): c.ContinuationLedger(self.out, {**self.binding, "source_changed": True})
        from details_continuation import source_check
        with patch.object(source_check, "snapshot", return_value={}):
            self.assertFalse(source_check.check()["passed"])
            with self.assertRaises(ValueError): source_check.binding()

    def test_retained_raw_tampering_or_new_claim_is_detected_on_a_copy(self):
        for mode in ("raw", "claim", "directory"):
            copy = ROOT / (self.relative + "-" + mode)
            shutil.copytree(c.PARTIAL, copy)
            if mode == "raw": (copy / "runs/semantic-rules-v2/u2b-dev-02/portal-v2.db").write_bytes(b"synthetic tamper")
            elif mode == "claim": (copy / "slots/details-02-local-double/STARTED.json").write_text("{}")
            else: (copy / "unexpected-empty-directory").mkdir()
            with patch.object(c, "PARTIAL", copy):
                with self.assertRaisesRegex(ValueError, "partial_raw_claim_state_or_directory_drift"): c.check_provenance()

    def test_actor_source_and_retained_state_drift_block_before_dispatch(self):
        ledger = self.ledger()
        with patch.object(c, "prior_binding", return_value={"changed": True}):
            with self.assertRaisesRegex(ValueError, "retained_actor_collector_source_drift"): c.execute_pending(ledger, self.actor)
        with patch.object(c.VerificationLedger, "report", return_value={"plan_sha256": ledger.plan["partial_plan_sha256"],
                   "accounting_states": {"pending": 0, "completed": 1, "failed": 0, "interrupted_unknown": 1}}):
            with self.assertRaisesRegex(ValueError, "only_original_unknown_and_never_started_pair_allowed"): c.execute_pending(ledger, self.actor)
        self.assertEqual(self.calls, [])
        self.assertFalse((ledger.slot_path(ledger.index[c.TARGET]) / "STARTED.json").exists())

    def test_unleased_and_unreviewed_native_entry_creates_no_output(self):
        from details_continuation.__main__ import main
        with patch.dict(os.environ, {"BB_U2B_EVALUATION_LEASE": ""}):
            with self.assertRaises(ValueError): c.evaluate(self.out, self.binding, "synthetic")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["run-local-double", "--out", str(self.out), "--plan-sha256", "synthetic"]), 1)
        with patch("fresh_eval.lease.require_lease"), patch("details_continuation.source_check.binding", return_value=self.binding):
            with self.assertRaisesRegex(ValueError, "reviewed_one_slot_continuation_plan_required"):
                c.evaluate(self.out, self.binding, "unreviewed")
        self.assertFalse(self.out.exists())

    def test_launcher_aware_proposal_keeps_other_resource_limits_and_history(self):
        proposal = json.loads((ROOT / "details_continuation_data/future_one_slot.json").read_text(encoding="utf-8"))
        bounds = proposal["bounds"]
        self.assertEqual(bounds["max_owned_python_processes"], 4)
        self.assertEqual(bounds["max_python_including_main_recorder"], 5)
        self.assertEqual(bounds["max_owned_processes"], 16)
        self.assertEqual((bounds["ram_mib"], bounds["additional_disk_mib"], bounds["max_owned_loopback_listeners"]), (1536, 256, 2))
        self.assertFalse(proposal["executed"])
        self.assertFalse(proposal["resource_increase_granted"])
        self.assertEqual(proposal["maximum_new_actor_starts"], 1)
        profile, _ = c.check_provenance()
        self.assertEqual(len(profile["partial_tree"]["files"]), 7)
        self.assertEqual(len(profile["prior_repo_pins"]), 219)
        self.assertEqual(profile["main_source_pin_count"], 222)
