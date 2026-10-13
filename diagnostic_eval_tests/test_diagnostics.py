from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import uuid
from unittest.mock import patch

from backoffice.domain import Decision
from durable_eval.ledger import ROOT, execute_first_slice
from fresh_eval.browser import EvaluationBrowser
from fresh_eval.freeze import validate_development
from industry_backoffice.protocol import Halt
from playwright.sync_api import TimeoutError as BrowserTimeout
from supplier_contract_tests.pure_support import PureTestCase
from diagnostic_eval.browser import DiagnosticBrowser
from diagnostic_eval.diagnostics import NAME, MAX_RECORDS, Writer, descriptor, error_category, probe_control
from diagnostic_eval.repeat import RepeatLedger, create, make_plan, check_original


class DiagnosticControls(PureTestCase):
    def setUp(self):
        super().setUp()
        def no_sql(*args, **kwargs):
            self.forbidden_calls.append("forbidden_sql")
            raise AssertionError("Pure diagnostic control attempted SQL")
        self.safety.enter_context(patch("sqlite3.connect", side_effect=no_sql))
        self.out = ROOT / "work/diagnostic-pure-controls" / uuid.uuid4().hex
        self.binding = {"version": "synthetic-pure-diagnostic-control"}

    def browser(self, probe=None):
        self.out.mkdir(parents=True)
        browser = DiagnosticBrowser("http://127.0.0.1:1", SimpleNamespace(run_dir=self.out))
        self.evaluations = []
        class Locator:
            def nth(inner, index):
                self.assertEqual(index, 2)
                return inner
            def evaluate(inner, code, *, timeout):
                self.evaluations.append(timeout)
                if isinstance(probe, Exception): raise probe
                return probe
        browser.page = SimpleNamespace(url="http://127.0.0.1:1/vendors/new?secret=DO_NOT_EXPORT", locator=lambda _: Locator())
        browser.refs = {"c2": {"index": 2, "role": "textbox", "label": "DO_NOT_EXPORT", "value": "DO_NOT_EXPORT"}}
        return browser

    def decision(self):
        return Decision("fill_from_request", {"ref": "c2", "field": "legal_name"})

    def successful(self, case, agent, row, deadline):
        row["verification"] = {"status": "mismatch", "safe": True, "expected_matched": False,
                               "evidence_kind": "pure_mocked_orchestration", "actual_outcome": "handoff",
                               "unsafe_attempts": 0, "unsafe_effects": 0, "cost_inr": None, "usage_tokens": None}
        return row

    def test_exact_exception_object_is_rethrown_with_fixed_classification(self):
        browser = self.browser({"tag": "INPUT", "closed_details_content": True, "has_client_rects": True,
                                "style_visibility_hidden": False, "check_visibility": False})
        error = BrowserTimeout("secret error message DO_NOT_EXPORT")
        with patch.object(EvaluationBrowser, "interact", side_effect=error) as original:
            with self.assertRaises(BrowserTimeout) as caught:
                browser.interact(self.decision(), {"legal_name": "DO_NOT_EXPORT"})
        self.assertIs(caught.exception, error)
        original.assert_called_once()
        rows = [json.loads(line) for line in (self.out / NAME).read_text().splitlines()]
        self.assertEqual([r["stage"] for r in rows], ["before_interact", "interaction_error"])
        self.assertEqual(rows[-1]["exception_category"], "playwright_timeout")
        self.assertTrue(rows[-1]["control_probe"]["closed_details_content"])
        self.assertEqual(self.evaluations, [200])
        self.assertNotIn("DO_NOT_EXPORT", (self.out / NAME).read_text())

    def test_success_return_arguments_and_collector_remain_unchanged(self):
        browser = self.browser()
        decision, request = self.decision(), {"legal_name": "fictional"}
        sentinel = object()
        with patch.object(EvaluationBrowser, "interact", return_value=sentinel) as original:
            self.assertIs(browser.interact(decision, request), sentinel)
        original.assert_called_once_with(decision, request)
        self.assertEqual(self.evaluations, [])
        self.assertIs(DiagnosticBrowser._controls, EvaluationBrowser._controls)
        self.assertIs(DiagnosticBrowser.resolve, EvaluationBrowser.resolve)
        self.assertIs(DiagnosticBrowser._route, EvaluationBrowser._route)

    def test_exception_string_is_never_evaluated(self):
        class PoisonError(Exception):
            def __str__(self): raise AssertionError("must not stringify")
        browser = self.browser()
        error = PoisonError()
        with patch.object(EvaluationBrowser, "interact", side_effect=error):
            with self.assertRaises(PoisonError): browser.interact(self.decision(), {})
        self.assertIn("unclassified_exception", (self.out / NAME).read_text())

    def test_probe_failure_stays_unknown_and_does_not_mask_error(self):
        browser = self.browser(RuntimeError("DO_NOT_EXPORT"))
        error = ValueError("original")
        with patch.object(EvaluationBrowser, "interact", side_effect=error):
            with self.assertRaises(ValueError) as caught: browser.interact(self.decision(), {})
        self.assertIs(caught.exception, error)
        final = json.loads((self.out / NAME).read_text().splitlines()[-1])
        self.assertEqual(final["control_probe"]["probe_status"], "unavailable")
        self.assertIsNone(final["control_probe"]["closed_details_content"])

    def test_interruption_does_not_start_a_dom_probe(self):
        browser = self.browser()
        with patch.object(EvaluationBrowser, "interact", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): browser.interact(self.decision(), {})
        self.assertEqual(self.evaluations, [])
        self.assertIn('"exception_category": "interruption"', (self.out / NAME).read_text())

    def test_diagnostic_write_failure_does_not_mask_original_action_error(self):
        browser = self.browser()
        error = RuntimeError("original")
        with patch.object(Writer, "emit", return_value=False), patch.object(EvaluationBrowser, "interact", side_effect=error):
            with self.assertRaises(RuntimeError) as caught: browser.interact(self.decision(), {})
        self.assertIs(caught.exception, error)

    def test_writer_bounds_record_count_and_never_replaces_an_existing_trace(self):
        self.out.mkdir(parents=True)
        writer = Writer(self.out)
        metadata = {"path": "/vendors/new", "tool": "fill_from_request", "request_field": "legal_name", "control_index": 2, "control_role": "textbox"}
        for _ in range(MAX_RECORDS): self.assertTrue(writer.emit("before_interact", metadata))
        self.assertFalse(writer.emit("before_interact", metadata))
        before = (self.out / NAME).read_bytes()
        self.assertFalse(Writer(self.out).emit("before_interact", metadata))
        self.assertEqual((self.out / NAME).read_bytes(), before)

    def test_probe_discards_unknown_tags_text_and_nonboolean_values(self):
        browser = self.browser({"tag": "SECRET_TAG", "closed_details_content": "secret", "text": "DO_NOT_EXPORT"})
        probe = probe_control(browser, 2)
        self.assertIsNone(probe["tag"])
        self.assertIsNone(probe["closed_details_content"])
        self.assertNotIn("text", probe)

    def test_typical_error_categories_contain_no_arbitrary_class_name_or_message(self):
        for error, category in ((Halt("DO_NOT_EXPORT"), "typed_halt"), (ValueError("secret"), "value_error"),
                                (OSError("secret"), "os_error"), (TimeoutError("secret"), "builtin_timeout")):
            self.assertEqual(error_category(error), category)

    def test_repeat_plan_has_distinct_execution_and_original_slot_references(self):
        ledger = create(self.out, self.binding, execution_kind="pure_mocked_orchestration")
        self.assertEqual(len(ledger.plan["slots"]), 2)
        self.assertEqual({s["case_id"] for s in ledger.plan["slots"]}, {"u2b-dev-02"})
        self.assertEqual([s["original_slot_id"] for s in ledger.plan["slots"]], ["03-semantic-rules-v2", "04-local-double"])
        report = execute_first_slice(ledger, self.successful)
        self.assertEqual(report["new_unique_tasks"], 0)
        self.assertEqual(report["original_pending_slots"], 20)
        self.assertFalse(report["full_development_complete"])
        self.assertFalse(report["freeze_eligible"])
        self.assertEqual(report["summary"]["agents"]["semantic-rules-v2"]["expected_postconditions"]["n"], 0)
        with self.assertRaises(ValueError): validate_development(report, self.binding)

    def test_repeat_interrupt_retains_both_intended_rows(self):
        ledger = create(self.out, self.binding, execution_kind="pure_mocked_orchestration")
        def actor(*args): raise KeyboardInterrupt("synthetic")
        with self.assertRaises(KeyboardInterrupt): execute_first_slice(ledger, actor)
        report = RepeatLedger(self.out, self.binding).recover(owner_stopped=True)
        self.assertEqual(len(report["rows"]), 2)
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(report["accounting_states"]["pending"], 1)
        with self.assertRaises(ValueError): execute_first_slice(ledger, self.successful)

    def test_repeat_plan_cannot_target_original_output(self):
        for path in ("work/u2b-first-slice-accounting-v1", "work/u2b-first-slice-accounting-v1/extra-repeat"):
            with self.assertRaises(ValueError): make_plan(self.binding, output_relative=path)

    def test_repeat_plan_relocation_is_rejected(self):
        create(self.out, self.binding, execution_kind="pure_mocked_orchestration")
        other = ROOT / "work/diagnostic-pure-controls" / uuid.uuid4().hex
        other.mkdir(parents=True)
        (other / "plan.json").write_bytes((self.out / "plan.json").read_bytes())
        with self.assertRaises(ValueError): RepeatLedger(other, self.binding)

    def test_diagnostic_evidence_hash_is_bound_and_changes_are_visible(self):
        ledger = create(self.out, self.binding, execution_kind="pure_mocked_orchestration")
        def actor(case, agent, row, deadline):
            run = Path(row["run_dir"])
            run.mkdir(parents=True)
            Writer(run).emit("before_interact", {"path": "/vendors/new"})
            return self.successful(case, agent, row, deadline)
        report = execute_first_slice(ledger, actor)
        self.assertTrue(all(r["diagnostic_receipt_unchanged"] for r in report["rows"]))
        first = Path(report["rows"][0]["run_dir"]) / NAME
        first.write_text("changed")
        self.assertFalse(ledger.report()["rows"][0]["diagnostic_receipt_unchanged"])

    def test_runtime_browser_substitution_is_restored_after_exception(self):
        from fresh_eval import native
        from diagnostic_eval.native import bind_browser
        with self.assertRaises(RuntimeError):
            with bind_browser():
                self.assertIs(native.EvaluationBrowser, DiagnosticBrowser)
                raise RuntimeError("synthetic")
        self.assertIs(native.EvaluationBrowser, EvaluationBrowser)

    def test_unleased_repeat_and_cli_create_no_output(self):
        from diagnostic_eval.native import evaluate
        from diagnostic_eval.__main__ import main
        with patch.dict(os.environ, {"BB_U2B_EVALUATION_LEASE": ""}):
            with self.assertRaises(ValueError): evaluate(self.out, self.binding, "synthetic")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["repeat-dev02", "--out", str(self.out), "--plan-sha256", "synthetic"]), 1)
        self.assertFalse(self.out.exists())

    def test_unreviewed_plan_hash_cannot_start_repeat(self):
        from diagnostic_eval.native import evaluate
        with patch("diagnostic_eval.native.require_lease"), patch("diagnostic_eval.source_check.binding", return_value=self.binding):
            with self.assertRaises(ValueError): evaluate(self.out, self.binding, "changed")
        self.assertFalse(self.out.exists())

    def test_original_four_attempts_and_twenty_pending_still_match(self):
        self.assertEqual(len(check_original()["tree"]["files"]), 42)

    def test_writer_is_a_redaction_boundary_for_extra_or_malformed_fields(self):
        self.out.mkdir(parents=True)
        writer = Writer(self.out)
        self.assertTrue(writer.emit("interaction_error", {"path": "SECRET", "tool": "SECRET", "value": "SECRET",
                                    "control_index": "SECRET", "request_field": ["SECRET"]}, error=ValueError("SECRET"),
                                    probe={"probe_status": "SECRET", "tag": "SECRET", "text": "SECRET", "closed_details_content": "SECRET"}))
        self.assertNotIn("SECRET", (self.out / NAME).read_text())
