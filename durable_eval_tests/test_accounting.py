from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import uuid
from unittest.mock import patch

from fresh_eval.cases import BUDGETS, sha
from fresh_eval.freeze import validate_development
from supplier_contract_tests.pure_support import PureTestCase
from durable_eval.ledger import ROOT, Ledger, create_plan, execute_first_slice, make_plan, unknown_row


class AccountingControls(PureTestCase):
    def setUp(self):
        super().setUp()
        def no_sql(*args, **kwargs):
            self.forbidden_calls.append("forbidden_sql")
            raise AssertionError("Pure accounting test attempted SQL")
        self.safety.enter_context(patch("sqlite3.connect", side_effect=no_sql))
        self.binding = {"source_manifest_sha256": "synthetic-source-control", "accounting_version": "synthetic"}
        # Retain bounded test artifacts in the assigned repository, including failures.
        self.out = ROOT / "work/accounting-pure-controls" / uuid.uuid4().hex

    def ledger(self, **options):
        return create_plan(self.out, self.binding, execution_kind="pure_mocked_orchestration", **options)

    def successful(self, case, agent, row, deadline):
        row["verification"] = {"status": "verified", "safe": True, "expected_matched": True,
                               "evidence_kind": "pure_mocked_orchestration", "cost_inr": None, "usage_tokens": None,
                               "unsafe_attempts": 0, "unsafe_effects": 0}
        row["wall_seconds"] = 1
        return row

    def saved(self):
        return json.loads((self.out / "report.json").read_text())

    def edit(self, path, mutate):
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")

    def test_all_intentions_and_bindings_exist_before_first_actor(self):
        ledger = self.ledger()
        seen = []
        def actor(case, agent, row, deadline):
            plan = json.loads((self.out / "plan.json").read_text())
            self.assertEqual(len(plan["slots"]), 24)
            self.assertEqual(len(self.saved()["rows"]), 24)
            self.assertEqual(plan["configuration"]["budgets"], BUDGETS)
            started = list((self.out / "slots").glob("*/STARTED.json"))
            self.assertEqual(len(started), len(seen) + 1)
            self.assertTrue(all(s["case_sha256"] and s["source_binding_sha256"] and s["configuration_sha256"] for s in plan["slots"]))
            seen.append((case["id"], agent))
            return self.successful(case, agent, row, deadline)
        report = execute_first_slice(ledger, actor)
        self.assertEqual(len(seen), 4)
        self.assertEqual(report["accounting_states"], {"pending": 20, "completed": 4, "failed": 0, "interrupted_unknown": 0})

    def test_keyboard_interrupt_first_invocation_retains_all_denominators(self):
        ledger = self.ledger()
        calls = []
        def actor(*args):
            calls.append(1)
            raise KeyboardInterrupt("synthetic orchestration only")
        with self.assertRaises(KeyboardInterrupt):
            execute_first_slice(ledger, actor)
        report = self.saved()
        self.assertEqual(calls, [1])
        self.assertEqual(len(report["rows"]), 24)
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(report["accounting_states"]["pending"], 23)
        metrics = report["summary"]["agents"]["semantic-rules-v2"]
        self.assertEqual(metrics["attempted"], {"n": 1, "N": 12, "rate": 1 / 12})
        for field in ("actual_cost_inr", "cost_per_expected_success_inr", "unsafe_attempts", "unsafe_effects"):
            self.assertIsNone(metrics[field])
        self.assertIsNone(report["rows"][0]["verification"]["safe"])
        self.assertFalse(report["summary"]["complete"])

    def test_start_without_terminal_recovers_after_projection_loss(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        ledger.start(slot)
        start_path = ledger.slot_path(slot) / "STARTED.json"
        start_hash = hashlib.sha256(start_path.read_bytes()).hexdigest()
        (self.out / "report.json").unlink()
        reopened = Ledger(self.out, self.binding)
        self.assertEqual(reopened.report()["accounting_states"]["interrupted_unknown"], 1)
        report = reopened.recover(owner_stopped=True)
        self.assertEqual(len(report["rows"]), 24)
        self.assertEqual(hashlib.sha256(start_path.read_bytes()).hexdigest(), start_hash)
        self.assertTrue((ledger.slot_path(slot) / "TERMINAL.json").exists())
        with self.assertRaises(ValueError):
            execute_first_slice(reopened, self.successful)

    def test_system_exit_is_interrupted_unknown(self):
        ledger = self.ledger()
        def actor(*args):
            raise SystemExit(7)
        with self.assertRaises(SystemExit):
            execute_first_slice(ledger, actor)
        self.assertEqual(self.saved()["accounting_states"]["interrupted_unknown"], 1)

    def test_ordinary_exception_is_failed_with_unknown_safety_and_cost(self):
        ledger = self.ledger()
        def actor(*args):
            raise RuntimeError("synthetic")
        with self.assertRaises(RuntimeError):
            execute_first_slice(ledger, actor)
        report = self.saved()
        self.assertEqual(report["accounting_states"]["failed"], 1)
        self.assertEqual(report["accounting_states"]["pending"], 23)
        self.assertIsNone(report["rows"][0]["verification"]["safe"])

    def test_unknown_actor_evidence_stops_with_one_failed_slot(self):
        ledger = self.ledger()
        report = execute_first_slice(ledger, lambda case, agent, row, deadline: row)
        self.assertEqual(report["accounting_states"]["failed"], 1)
        self.assertEqual(report["accounting_states"]["pending"], 23)

    def test_first_slice_cannot_pass_freeze_or_capability(self):
        report = execute_first_slice(self.ledger(), self.successful)
        self.assertFalse(report["execution_complete"])
        self.assertFalse(report["freeze_eligible"])
        self.assertFalse(report["capability_eligible"])
        self.assertEqual(report["summary"]["paired_attempted"], 2)
        with self.assertRaises(ValueError):
            validate_development(report, self.binding)

    def test_one_pair_still_uses_complete_full_plan(self):
        report = execute_first_slice(self.ledger(paired_tasks=1), self.successful)
        self.assertEqual(len(report["rows"]), 24)
        self.assertEqual(report["accounting_states"]["completed"], 2)
        self.assertEqual(report["accounting_states"]["pending"], 22)

    def test_invalid_task_limits_fail_before_output_creation(self):
        for value in (0, 3, 12, True):
            with self.assertRaises(ValueError):
                self.ledger(paired_tasks=value)
        self.assertFalse(self.out.exists())

    def test_reinvocation_never_dispatches_existing_attempts(self):
        ledger = self.ledger()
        execute_first_slice(ledger, self.successful)
        calls = []
        with self.assertRaises(ValueError):
            execute_first_slice(ledger, lambda *args: calls.append(1))
        self.assertEqual(calls, [])
        with self.assertRaises(ValueError):
            ledger.start(ledger.plan["slots"][0])

    def test_terminal_receipt_is_never_replaced(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        ledger.start(slot)
        row = unknown_row(ledger, slot, "synthetic")
        ledger.terminal(slot, "failed", row, "synthetic")
        old = (ledger.slot_path(slot) / "TERMINAL.json").read_bytes()
        with self.assertRaises(FileExistsError):
            ledger.terminal(slot, "failed", row, "replacement")
        self.assertEqual((ledger.slot_path(slot) / "TERMINAL.json").read_bytes(), old)

    def test_existing_directory_is_never_reinitialized(self):
        self.ledger()
        with self.assertRaises(FileExistsError):
            self.ledger()

    def test_omitted_intended_slot_rejected_even_with_recomputed_plan_hash(self):
        self.ledger()
        def omit(value):
            value["slots"].pop()
            value["plan_sha256"] = sha({k: v for k, v in value.items() if k != "plan_sha256"})
        self.edit(self.out / "plan.json", omit)
        with self.assertRaises(ValueError):
            Ledger(self.out, self.binding)

    def test_duplicate_intended_slot_is_rejected(self):
        self.ledger()
        self.edit(self.out / "plan.json", lambda value: value["slots"].append(value["slots"][0]))
        with self.assertRaises(ValueError):
            Ledger(self.out, self.binding)

    def test_source_binding_drift_is_rejected(self):
        self.ledger()
        with self.assertRaises(ValueError):
            Ledger(self.out, {**self.binding, "source_manifest_sha256": "changed"})

    def test_dataset_and_configuration_drift_are_rejected(self):
        for field in ("dataset_sha256", "configuration"):
            ledger = self.ledger()
            if field == "dataset_sha256":
                self.edit(self.out / "plan.json", lambda value: value.update(dataset_sha256="changed"))
            else:
                self.edit(self.out / "plan.json", lambda value: value["configuration"]["model_config"].update(max_output_tokens=129))
            with self.assertRaises(ValueError):
                Ledger(self.out, self.binding)
            self.out = ROOT / "work/accounting-pure-controls" / uuid.uuid4().hex

    def test_start_receipt_binding_drift_is_rejected(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        ledger.start(slot)
        self.edit(ledger.slot_path(slot) / "STARTED.json", lambda value: value.update(dataset_sha256="changed"))
        with self.assertRaises(ValueError):
            ledger.write_report()

    def test_terminal_row_policy_or_case_drift_is_rejected(self):
        ledger = self.ledger()
        execute_first_slice(ledger, self.successful)
        slot = ledger.plan["slots"][0]
        self.edit(ledger.slot_path(slot) / "TERMINAL.json", lambda value: value["row"].update(agent="foreign"))
        with self.assertRaises(ValueError):
            ledger.report()

    def test_raw_state_files_are_hashed_without_sql_or_contents_export(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        ledger.start(slot)
        run = self.out / slot["run_dir"]
        run.mkdir(parents=True)
        payload = b"synthetic raw state; this is not a SQL database"
        (run / "workflow-v2.db").write_bytes(payload)
        terminal = ledger.terminal(slot, "interrupted_unknown", unknown_row(ledger, slot, "synthetic"), "synthetic")
        evidence = terminal["raw_evidence"]
        self.assertFalse(evidence["sql_read"])
        self.assertEqual(evidence["files"], [{"name": "workflow-v2.db", "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}])
        self.assertNotIn("synthetic raw state", json.dumps(terminal))

    def test_partial_start_is_spent_and_never_replayed(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        (ledger.slot_path(slot) / "STARTED.json").write_bytes(b'{"schema_version":')
        self.assertEqual(ledger.report()["accounting_states"]["interrupted_unknown"], 1)
        ledger.recover(owner_stopped=True)
        with self.assertRaises(ValueError):
            ledger.start(slot)
        with self.assertRaises(ValueError):
            execute_first_slice(ledger, self.successful)

    def test_partial_terminal_is_unknown_and_is_not_replaced(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        ledger.start(slot)
        path = ledger.slot_path(slot) / "TERMINAL.json"
        path.write_bytes(b"{")
        report = ledger.recover(owner_stopped=True)
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(path.read_bytes(), b"{")

    def test_omitted_start_receipt_with_terminal_is_rejected(self):
        ledger = self.ledger()
        execute_first_slice(ledger, self.successful)
        (ledger.slot_path(ledger.plan["slots"][0]) / "STARTED.json").unlink()
        with self.assertRaises(ValueError):
            ledger.report()

    def test_terminal_without_start_is_rejected(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        with self.assertRaises(ValueError):
            ledger.terminal(slot, "failed", unknown_row(ledger, slot, "synthetic"), "synthetic")

    def test_duplicate_slot_record_is_rejected(self):
        ledger = self.ledger()
        (ledger.slot_path(ledger.plan["slots"][0]) / "STARTED-copy.json").write_text("{}")
        with self.assertRaises(ValueError):
            Ledger(self.out, self.binding)

    def test_cached_report_is_disposable_and_not_trusted(self):
        ledger = self.ledger()
        (self.out / "report.json").write_text('{"rows": [], "summary": {"complete": true}}')
        report = Ledger(self.out, self.binding).write_report()
        self.assertEqual(len(report["rows"]), 24)
        self.assertEqual(report["accounting_states"]["pending"], 24)
        self.assertFalse(report["summary"]["complete"])

    def test_recovery_requires_stopped_owner_declaration(self):
        ledger = self.ledger()
        ledger.start(ledger.plan["slots"][0])
        with self.assertRaises(ValueError):
            ledger.recover()
        self.assertFalse((ledger.slot_path(ledger.plan["slots"][0]) / "TERMINAL.json").exists())

    def test_phase_stop_retains_all_pending_slots(self):
        ledger = self.ledger()
        ticks = iter([0] + [1000] * 24)
        calls = []
        report = execute_first_slice(ledger, lambda *args: calls.append(1), clock=lambda: next(ticks))
        self.assertEqual(calls, [])
        self.assertEqual(report["accounting_states"]["pending"], 24)

    def test_unleased_native_wrapper_and_cli_do_not_create_output(self):
        from durable_eval.native import evaluate_first_slice
        from durable_eval.__main__ import main
        with patch.dict(os.environ, {"BB_U2B_EVALUATION_LEASE": ""}):
            with self.assertRaises(ValueError):
                evaluate_first_slice(self.out, self.binding)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["evaluate-first-slice", "--out", str(self.out), "--plan-sha256", "synthetic"]), 1)
        self.assertFalse(self.out.exists())

    def test_actor_foreign_row_becomes_unknown_failed_receipt(self):
        ledger = self.ledger()
        def actor(case, agent, row, deadline):
            row["case_id"] = "foreign"
            return self.successful(case, agent, row, deadline)
        with self.assertRaises(ValueError):
            execute_first_slice(ledger, actor)
        self.assertEqual(self.saved()["accounting_states"]["failed"], 1)

    def test_unknown_success_cost_is_not_zero_and_score_semantics_are_unchanged(self):
        report = execute_first_slice(self.ledger(), self.successful)
        for agent in report["summary"]["agents"].values():
            self.assertEqual(agent["expected_postconditions"]["N"], 12)
            self.assertEqual(agent["attempted"]["n"], 2)
            self.assertIsNone(agent["actual_cost_inr"])
            self.assertIsNone(agent["cost_per_expected_success_inr"])

    def test_historical_run_directory_cannot_be_dispatched(self):
        ledger = self.ledger()
        slot = ledger.plan["slots"][0]
        (self.out / slot["run_dir"]).mkdir(parents=True)
        with self.assertRaises(ValueError):
            ledger.start(slot)

    def test_absent_terminal_record_is_visible_as_interrupted_unknown(self):
        ledger = self.ledger()
        execute_first_slice(ledger, self.successful)
        (ledger.slot_path(ledger.plan["slots"][0]) / "TERMINAL.json").unlink()
        report = ledger.write_report()
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(report["accounting_states"]["completed"], 3)

    def test_native_claim_without_raw_sql_evidence_fails_unknown(self):
        ledger = create_plan(self.out, self.binding)
        report = execute_first_slice(ledger, self.successful)
        self.assertEqual(report["accounting_states"]["failed"], 1)
        self.assertIsNone(report["rows"][0]["verification"]["safe"])
        self.assertFalse(report["native_execution"])

    def test_receipt_metric_tampering_is_rejected(self):
        ledger = self.ledger()
        execute_first_slice(ledger, self.successful)
        slot = ledger.plan["slots"][0]
        self.edit(ledger.slot_path(slot) / "TERMINAL.json", lambda value: value["row"]["verification"].update(cost_inr=0))
        with self.assertRaises(ValueError):
            ledger.report()

    def test_raw_state_changed_after_completed_receipt_is_unknown(self):
        ledger = self.ledger()
        def actor(case, agent, row, deadline):
            run = Path(row["run_dir"])
            run.mkdir(parents=True)
            (run / "actor-result-v2.json").write_text('{"synthetic": true}')
            return self.successful(case, agent, row, deadline)
        execute_first_slice(ledger, actor)
        (self.out / ledger.plan["slots"][0]["run_dir"] / "actor-result-v2.json").write_text("changed")
        report = ledger.write_report()
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertIsNone(report["rows"][0]["verification"]["safe"])

    def test_unreviewed_full_plan_hash_cannot_create_native_output(self):
        from durable_eval.native import evaluate_first_slice
        with patch("durable_eval.native.require_lease"), patch("durable_eval.source_check.binding", return_value=self.binding):
            with self.assertRaises(ValueError):
                evaluate_first_slice(self.out, self.binding, expected_plan_sha256="changed")
        self.assertFalse(self.out.exists())

    def test_native_wrapper_mocked_first_invocation_preserves_receipts(self):
        from durable_eval.native import evaluate_first_slice
        plan = make_plan(self.binding, output_relative=self.out.relative_to(ROOT).as_posix())
        with patch("durable_eval.native.require_lease"), patch("durable_eval.source_check.binding", return_value=self.binding), \
                patch("fresh_eval.native.run_one", side_effect=KeyboardInterrupt("synthetic coordinator interruption")) as actor:
            with self.assertRaises(KeyboardInterrupt):
                evaluate_first_slice(self.out, self.binding, expected_plan_sha256=plan["plan_sha256"])
        report = self.saved()
        self.assertEqual(actor.call_count, 1)
        self.assertEqual(report["accounting_states"], {"pending": 23, "completed": 0, "failed": 0, "interrupted_unknown": 1})
        self.assertFalse(report["native_execution"])
        probe = {"kind": "mocked first run_one interruption; no actor/browser/SQL/server/model/process termination",
                 "run_one_invocations": actor.call_count, "intended_runs": len(report["rows"]),
                 "accounting_states": report["accounting_states"], "native_execution": report["native_execution"],
                 "plan_sha256": plan["plan_sha256"], "report_source_binding": report["source_binding"],
                 "source_binding_kind": "synthetic pure control", "unsafe_attempts": report["summary"]["agents"]["semantic-rules-v2"]["unsafe_attempts"],
                 "actual_cost_inr": report["summary"]["agents"]["semantic-rules-v2"]["actual_cost_inr"],
                 "files": sorted(p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file())}
        (self.out / "mocked-interruption-probe.json").write_text(json.dumps(probe, indent=2) + "\n")

    def test_safe_quality_loss_remains_visible_and_does_not_stop_slice(self):
        ledger = self.ledger()
        def actor(case, agent, row, deadline):
            self.successful(case, agent, row, deadline)
            if case["id"] == ledger.plan["first_slice_case_ids"][0] and agent == "semantic-rules-v2":
                row["verification"].update(status="mismatch", expected_matched=False, actual_outcome="handoff")
            return row
        report = execute_first_slice(ledger, actor)
        self.assertEqual(report["accounting_states"]["completed"], 4)
        self.assertEqual(report["summary"]["agents"]["semantic-rules-v2"]["expected_postconditions"]["n"], 1)
        self.assertEqual(report["summary"]["pairs"][0]["winner"], "local-double")
        self.assertEqual(report["summary"]["failures"][0]["actual_outcome"], "handoff")

    def test_reviewed_plan_cannot_reexecute_under_another_output_directory(self):
        from durable_eval.native import evaluate_first_slice
        plan = make_plan(self.binding, output_relative=self.out.relative_to(ROOT).as_posix())
        other = ROOT / "work/accounting-pure-controls" / uuid.uuid4().hex
        with patch("durable_eval.native.require_lease"), patch("durable_eval.source_check.binding", return_value=self.binding):
            with self.assertRaises(ValueError):
                evaluate_first_slice(other, self.binding, expected_plan_sha256=plan["plan_sha256"])
        self.assertFalse(other.exists())

    def test_relocated_plan_is_rejected(self):
        self.ledger()
        other = ROOT / "work/accounting-pure-controls" / uuid.uuid4().hex
        other.mkdir(parents=True)
        (other / "plan.json").write_bytes((self.out / "plan.json").read_bytes())
        with self.assertRaises(ValueError):
            Ledger(other, self.binding)
