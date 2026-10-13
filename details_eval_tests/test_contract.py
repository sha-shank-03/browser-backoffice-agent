from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from types import SimpleNamespace
import uuid
from unittest.mock import patch

from backoffice.domain import digest
from diagnostic_eval.browser import DiagnosticBrowser
from durable_eval.ledger import ROOT, execute_first_slice
from fresh_eval.baseline import SemanticRules
from fresh_eval.browser import EvaluationBrowser, SELECTOR
from fresh_eval.cases import load, BUDGETS
from fresh_eval.freeze import validate_development
from industry_backoffice.double import semantic_decision
from industry_backoffice.protocol import Halt
from supplier_contract_tests.pure_support import PureTestCase
from details_eval import VERSION
from details_eval.browser import DetailsBrowser, EXTRACTOR
from details_eval.repeat import VerificationLedger, create, make_plan, future_development_plan, check_history


class DetailsControls(PureTestCase):
    def setUp(self):
        super().setUp()
        def no_sql(*args, **kwargs):
            self.forbidden_calls.append("forbidden_sql")
            raise AssertionError("Pure DETAILS control attempted SQL")
        self.safety.enter_context(patch("sqlite3.connect", side_effect=no_sql))
        self.out = ROOT / "work/details-pure-controls" / uuid.uuid4().hex
        self.binding = {"collector_version": "synthetic-pure-details-control"}
        self.controls = [self.control(0, "Organisation details"), self.control(4, "Purchasing details"), self.control(8, "Review vendor")]
        self.indices, self.selectors, self.extractors, self.events = [], [], [], []

    def control(self, index, label, role="button"):
        return {"index": index, "visible": True, "enabled": True, "role": role, "label": label, "value": "",
                "options": [], "description": "", "context": "", "required": False}

    def browser(self):
        store = SimpleNamespace(run_dir=self.out, data={"evaluation_browser_requests": 0, "state": "READY", "commit_attempted": False,
                                 "commit_dispatched": False, "approval": None}, save=lambda kind, event: self.events.append((kind, event)))
        browser = DetailsBrowser("http://127.0.0.1:1", store)
        class Locator:
            def evaluate_all(inner, code):
                self.extractors.append(code)
                return deepcopy(self.controls)
            def nth(inner, index):
                self.indices.append(index)
                return SimpleNamespace(index=index)
        def locator(selector):
            self.selectors.append(selector)
            return Locator()
        browser.page = SimpleNamespace(url="http://127.0.0.1:1/vendors/new", locator=locator)
        browser.refs = {f"c{c['index']}": deepcopy(c) for c in self.controls}
        browser.signature = digest({"url": browser.page.url, "controls": self.controls})
        return browser

    def policy_context(self):
        result = json.loads((ROOT / "work/details-pure-controls/v8-result.json").read_text(encoding="utf-8-sig"))
        self.assertTrue(result["passed"])
        case = next(c for c in load("development-v2")["cases"] if c["id"] == "u2b-dev-02")
        return {"request": case["request"], "observation": {"id": "pure-current", "path": "/vendors/new", "title": "Supplier onboarding",
                "text": "", "controls": result["closed_policy_controls"], "records": []},
                "state": {"approval_state": "READY", "search_complete": True, "commit_dispatched": False, "commit_uncertain": False}}

    def completed(self, case, agent, row, deadline):
        row["verification"] = {"status": "mismatch", "safe": True, "expected_matched": False,
                               "evidence_kind": "pure_mocked_orchestration", "actual_outcome": "handoff",
                               "unsafe_attempts": 0, "unsafe_effects": 0, "cost_inr": None, "usage_tokens": None}
        return row

    def test_collector_uses_same_selector_and_exact_candidate_javascript(self):
        self.assertEqual(self.browser()._controls(), self.controls)
        self.assertEqual(self.selectors, [SELECTOR])
        self.assertEqual(self.extractors, [EXTRACTOR])

    def test_filtered_controls_resolve_original_index_not_filtered_position(self):
        locator, item = self.browser().resolve("c4")
        self.assertEqual(locator.index, 4)
        self.assertEqual(item["label"], "Purchasing details")
        self.assertEqual(self.indices, [4])

    def test_opening_details_invalidates_preopening_reference_signature(self):
        browser = self.browser()
        self.controls.insert(1, self.control(2, "Legal name", "textbox"))
        with self.assertRaises(Halt) as caught: browser.resolve("c4")
        self.assertEqual(caught.exception.code, "stale_observation")
        self.assertEqual(self.indices, [])

    def test_closing_details_invalidates_exposed_input_reference(self):
        self.controls.insert(1, self.control(2, "Legal name", "textbox"))
        browser = self.browser()
        self.controls.pop(1)
        with self.assertRaises(Halt) as caught: browser.resolve("c2")
        self.assertEqual(caught.exception.code, "stale_observation")

    def test_url_drift_and_unknown_refs_still_fail_stale_observation(self):
        browser = self.browser(); browser.page.url += "?different"
        with self.assertRaises(Halt) as caught: browser.resolve("c0")
        self.assertEqual(caught.exception.code, "stale_observation")
        browser = self.browser()
        with self.assertRaises(Halt): browser.resolve("c999")

    def test_duplicate_current_semantics_remain_ambiguous(self):
        self.controls.append(self.control(9, "Organisation details"))
        browser = self.browser()
        with self.assertRaises(Halt) as caught: browser.resolve("c0")
        self.assertEqual(caught.exception.code, "ambiguous_current_control")

    def test_reference_routing_approval_and_diagnostic_methods_are_inherited(self):
        for name in ("resolve", "_route", "read_review", "refresh_review", "arm_and_submit", "__enter__", "__exit__"):
            self.assertIs(getattr(DetailsBrowser, name), getattr(EvaluationBrowser, name))
        self.assertIs(DetailsBrowser.interact, DiagnosticBrowser.interact)

    def test_external_route_remains_blocked_without_browser_or_http(self):
        browser = self.browser(); calls = []
        route = SimpleNamespace(abort=lambda reason: calls.append(reason), continue_=lambda: calls.append("continued"))
        browser._route(route, SimpleNamespace(url="https://outside.invalid/vendors", method="GET"))
        self.assertEqual(calls, ["blockedbyclient"])
        self.assertEqual(self.events[-1][1]["reason"], "outside_owned_origin")

    def test_commit_without_ticket_and_approval_remains_blocked(self):
        browser = self.browser(); calls = []
        route = SimpleNamespace(abort=lambda reason: calls.append(reason), continue_=lambda: calls.append("continued"))
        browser._route(route, SimpleNamespace(url="http://127.0.0.1:1/vendors/commit", method="POST", post_data="legal_name=fictional"))
        self.assertEqual(calls, ["blockedbyclient"])
        self.assertFalse(browser.store.data["commit_dispatched"])
        self.assertEqual(self.events[-1][1]["reason"], "commit_not_armed_or_body_changed")

    def test_owned_read_route_remains_allowed(self):
        browser = self.browser(); calls = []
        route = SimpleNamespace(abort=lambda reason: calls.append(reason), continue_=lambda: calls.append("continued"))
        browser._route(route, SimpleNamespace(url="http://127.0.0.1:1/vendors", method="GET"))
        self.assertEqual(calls, ["continued"])

    def test_unchanged_semantic_rules_explicitly_choose_visible_summary(self):
        decision = SemanticRules().decide(self.policy_context())
        self.assertEqual(decision.tool, "click")
        self.assertEqual(decision.arguments, {"ref": "c0"})

    def test_unchanged_local_double_missing_section_handoff_is_not_tuned_away(self):
        tool, arguments = semantic_decision(self.policy_context())
        self.assertEqual((tool, arguments), ("handoff", {"reason": "insufficient_evidence"}))

    def test_same_corrected_collector_binding_is_used_for_each_policy_and_restored(self):
        from fresh_eval import native
        from details_eval.native import bind_collector
        for agent in ("semantic-rules-v2", "local-double"):
            with bind_collector(): self.assertIs(native.EvaluationBrowser, DetailsBrowser)
            self.assertIs(native.EvaluationBrowser, EvaluationBrowser)
        with self.assertRaises(RuntimeError):
            with bind_collector(): raise RuntimeError("synthetic")
        self.assertIs(native.EvaluationBrowser, EvaluationBrowser)

    def test_verification_pair_has_new_identity_and_keeps_unknown_costs(self):
        ledger = create(self.out, self.binding, execution_kind="pure_mocked_orchestration")
        report = execute_first_slice(ledger, self.completed)
        self.assertEqual(len(report["rows"]), 2)
        self.assertEqual(report["new_unique_tasks"], 0)
        self.assertEqual(report["collector_version"], VERSION)
        self.assertEqual(report["original_pending_slots"], 20)
        self.assertFalse(report["freeze_eligible"])
        self.assertFalse(report["native_collector_fix_verified"])
        self.assertEqual(report["configuration"]["budgets"], BUDGETS)
        for agent in report["summary"]["agents"].values(): self.assertIsNone(agent["actual_cost_inr"])
        with self.assertRaises(ValueError): validate_development(report, self.binding)

    def test_interruption_is_durable_and_verification_cannot_replay(self):
        ledger = create(self.out, self.binding, execution_kind="pure_mocked_orchestration")
        def actor(*args): raise KeyboardInterrupt("synthetic")
        with self.assertRaises(KeyboardInterrupt): execute_first_slice(ledger, actor)
        report = VerificationLedger(self.out, self.binding).recover(owner_stopped=True)
        self.assertEqual(report["accounting_states"]["interrupted_unknown"], 1)
        self.assertEqual(report["accounting_states"]["pending"], 1)
        with self.assertRaises(ValueError): execute_first_slice(ledger, self.completed)

    def test_original_and_diagnostic_outputs_and_descendants_are_refused(self):
        for path in ("work/u2b-first-slice-accounting-v1", "work/u2b-first-slice-accounting-v1/extra",
                     "work/u2b-dev02-diagnostic-repeat-v1", "work/u2b-dev02-diagnostic-repeat-v1/extra"):
            with self.assertRaises(ValueError): make_plan(self.binding, output_relative=path)

    def test_new_cohort_plan_does_not_pool_old_or_verification_results(self):
        plan = future_development_plan(self.binding)
        self.assertEqual(len(plan["slots"]), 24)
        self.assertTrue(all(s["initial_state"] == "pending" for s in plan["slots"]))
        self.assertEqual(sum(s["migration_phase"] == "separate_pending_gate" for s in plan["slots"]), 20)
        self.assertEqual(len(plan["pending_migration_task_ids"]), 10)
        self.assertEqual(len({s["execution_id"] for s in plan["slots"]}), 24)
        self.assertEqual([task for batch in plan["pending_migration_batches"] for task in batch], plan["pending_migration_task_ids"])
        self.assertTrue(all(len(batch) <= 2 for batch in plan["pending_migration_batches"]))
        self.assertFalse(plan["execution_authorized"])
        self.assertFalse(plan["import_prior_results"])
        self.assertFalse(plan["import_verification_repeat_results"])
        self.assertEqual(plan["original_frozen_pending_remain_unchanged"], 20)

    def test_unleased_cli_and_runner_create_no_output(self):
        from details_eval.native import evaluate
        from details_eval.__main__ import main
        with patch.dict(os.environ, {"BB_U2B_EVALUATION_LEASE": ""}):
            with self.assertRaises(ValueError): evaluate(self.out, self.binding, "synthetic")
            with redirect_stdout(io.StringIO()): self.assertEqual(main(["verify-dev02", "--out", str(self.out), "--plan-sha256", "synthetic"]), 1)
        self.assertFalse(self.out.exists())

    def test_unreviewed_plan_hash_cannot_create_output(self):
        from details_eval.native import evaluate
        with patch("details_eval.native.require_lease"), patch("details_eval.source_check.binding", return_value=self.binding):
            with self.assertRaises(ValueError): evaluate(self.out, self.binding, "changed")
        self.assertFalse(self.out.exists())

    def test_all_original_and_diagnostic_artifacts_remain_pinned(self):
        counts = {key: len(value["files"]) for key, value in check_history()["artifact_trees"].items()}
        self.assertEqual(sorted(counts.values()), [22, 42])
