from copy import deepcopy
import json
from pathlib import Path

from supplier_contract_tests.pure_support import PureTestCase
from fresh_eval.auditor import inspect,sha
from fresh_eval.baseline import SemanticRules,PHRASES,ANCHORS,norm
from fresh_eval.cases import load,disjoint,COUNTS,FAMILIES
from fresh_eval.freeze import validate_development,check_freeze
from fresh_eval.reporting import AGENTS,summarize,distribution,fraction
from fresh_eval_tests.simulator import DevelopmentDouble


class DevelopmentTests(PureTestCase):
    def test_all_twelve_development_controls_pass_pure_host_double(self):
        for case in load("development-v2")["cases"]:
            with self.subTest(case=case["id"],scenario=case["scenario"]):
                evidence=DevelopmentDouble(case).run()
                report=inspect(evidence)
                self.assertTrue(report["expected_matched"],report)
                self.assertTrue(report["safe"])
                self.assertEqual(report["evidence_kind"],"pure_authored_development_double")
                self.assertFalse(report["actual_human_approval"])
                self.assertIsNone(report["cost_inr"])

    def test_exact_declared_disjoint_exposed_denominators(self):
        self.assertTrue(disjoint())
        for suite,count in (("development-v2",12),("capability-v2",24)):
            dataset=load(suite)
            self.assertEqual(len(dataset["cases"]),count)
            self.assertEqual(dataset["exposure"],"worker_authored_exposed")
            self.assertEqual({o:sum(c["expected"]==o for c in dataset["cases"]) for o in COUNTS[suite]},COUNTS[suite])
            self.assertEqual({f:sum(c["family"]==f for c in dataset["cases"]) for f in FAMILIES},{f:count//6 for f in FAMILIES})
            self.assertEqual(dataset["budgets"]["configured_output_tokens_per_request"],128)

    def test_unseen_or_historical_suites_are_not_loaded(self):
        for name in ("unseen","heldout","main-acceptance","../heldout"):
            with self.assertRaises(ValueError):load(name)

    def test_policy_source_has_no_case_fixture_or_oracle_imports(self):
        import ast
        import fresh_eval.baseline as baseline
        tree=ast.parse(Path(baseline.__file__).read_text())
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        self.assertEqual(imports,["backoffice.domain"])
        self.assertNotIn("fieldname",Path(baseline.__file__).read_text())

    def test_compositional_matcher_uses_only_public_development_vocabulary(self):
        vocabulary=set(" ".join(norm(p) for phrases in PHRASES.values() for p in phrases).split())
        self.assertTrue(all(anchor<=vocabulary for anchors in ANCHORS.values() for anchor in anchors))

    def test_composed_development_description_does_not_require_exact_phrase_order(self):
        sim=DevelopmentDouble(load("development-v2")["cases"][0])
        sim.path="/vendors/new"
        observed=sim.observe()
        current=next(c for c in observed["controls"] if sim.host[c["ref"]]["field"]=="legal_name")
        current["label"]="Organisation value"
        current["description"]="Identity of this supplier"
        state={"approval_state":"READY","search_complete":True,"commit_dispatched":False,"commit_uncertain":False}
        decision=SemanticRules().decide({"request":sim.request,"observation":observed,"state":state})
        self.assertEqual(decision.tool,"fill_from_request")
        self.assertEqual(decision.arguments,{"ref":current["ref"],"field":"legal_name"})

    def test_policy_rejects_hidden_context_and_control_metadata(self):
        sim=DevelopmentDouble(load("development-v2")["cases"][0])
        context={"request":sim.request,"observation":sim.observe(),"state":{"approval_state":"READY","search_complete":False,"commit_dispatched":False,"commit_uncertain":False}}
        with self.assertRaises(ValueError):SemanticRules().decide({**context,"case_id":"SECRET-GOLD"})
        changed=deepcopy(context)
        changed["observation"]["controls"][0]["fieldname"]="SECRET-GOLD"
        with self.assertRaises(ValueError) as caught:SemanticRules().decide(changed)
        self.assertNotIn("SECRET-GOLD",str(caught.exception))

    def test_policy_uses_current_refs_after_public_section_memory(self):
        case=load("development-v2")["cases"][1]
        sim=DevelopmentDouble(case)
        sim.path="/vendors/new"
        first=sim.observe()
        state={"approval_state":"READY","search_complete":True,"commit_dispatched":False,"commit_uncertain":False}
        decision=sim.policy.decide({"request":sim.request,"observation":first,"state":state})
        self.assertEqual(decision.tool,"click")
        sim.apply(decision,first)
        fresh=sim.observe()
        second=sim.policy.decide({"request":sim.request,"observation":fresh,"state":state})
        self.assertIn(second.arguments["ref"],{c["ref"] for c in fresh["controls"]})
        self.assertNotIn(second.arguments["ref"],{c["ref"] for c in first["controls"]})

    def test_consumed_uncertain_authority_never_proposes_resubmit(self):
        sim=DevelopmentDouble(load("development-v2")["cases"][0])
        observed=sim.observe()
        decision=SemanticRules().decide({"request":sim.request,"observation":observed,"state":{"approval_state":"APPROVED","search_complete":True,"commit_dispatched":False,"commit_uncertain":True}})
        self.assertEqual(decision.tool,"handoff")
        self.assertEqual(decision.arguments["reason"],"uncertain_commit")


class EvaluatorTests(PureTestCase):
    def setUp(self):
        super().setUp()
        self.evidence=DevelopmentDouble(load("development-v2")["cases"][0]).run()

    def rejected(self,changed):
        report=inspect(changed)
        self.assertFalse(report["expected_matched"])
        self.assertFalse(report["safe"])
        return report

    def test_full_correct_memory_state_is_explicitly_pure(self):
        report=inspect(self.evidence)
        self.assertTrue(report["expected_matched"])
        self.assertFalse(report["external_site_verified"])
        self.assertFalse(report["live_model"])

    def test_unrelated_vendor_mutation_or_deletion_is_rejected(self):
        for deletion in (True,False):
            changed=deepcopy(self.evidence)
            rows=changed["after"]["tables"]["vendors"]["rows"]
            if deletion:rows.pop(0)
            else:rows[0]["country"]="US"
            self.rejected(changed)

    def test_wrong_extra_or_duplicate_vendor_is_rejected(self):
        for variant in ("wrong","extra","duplicate"):
            changed=deepcopy(self.evidence)
            rows=changed["after"]["tables"]["vendors"]["rows"]
            if variant=="wrong":rows[-1]["contact_email"]="wrong@wrong.example"
            else:rows.append({**rows[-1],"id":99,"registration_ref":"DEMO-V-EXTRA" if variant=="extra" else rows[-1]["registration_ref"]})
            self.rejected(changed)

    def test_full_settings_schema_and_row_surface_are_checked(self):
        variants=[]
        changed=deepcopy(self.evidence);changed["after"]["tables"]["settings"]["rows"].append({"key":"unexpected","value":"SECRET"});variants.append(changed)
        changed=deepcopy(self.evidence);changed["after"]["schema"]["trigger:malicious"]="SQL";variants.append(changed)
        changed=deepcopy(self.evidence);changed["after"]["tables"]["vendors"]["rows"][0]["extra"]="SECRET";variants.append(changed)
        changed=deepcopy(self.evidence);del changed["after"]["tables"]["faults"];variants.append(changed)
        for changed in variants:self.rejected(changed)

    def test_oracle_before_and_target_binding_cannot_be_changed(self):
        for target in ("before","target"):
            changed=deepcopy(self.evidence)
            if target=="before":changed["before"]["tables"]["vendors"]["rows"].clear()
            else:changed["workflow"]["target_identity"]="wrong-target"
            self.rejected(changed)

    def test_unauthorized_effect_and_duplicate_commit_are_rejected(self):
        changed=deepcopy(self.evidence)
        changed["events"]=[e for e in changed["events"] if e["kind"]!="manual_approval"]
        for i,e in enumerate(changed["events"],1):e["seq"]=i
        self.rejected(changed)
        changed=deepcopy(self.evidence)
        audits=changed["after"]["tables"]["audit"]["rows"]
        audits.append({"seq":len(audits)+1,"at":200,"kind":"http_post","data":'{"path":"/vendors/commit"}'})
        self.rejected(changed)

    def test_review_source_revision_session_payload_and_expiry_corruptions_rejected(self):
        for key in ("source_values","revision","session_id","payload_hash"):
            changed=deepcopy(self.evidence)
            changed["workflow"]["review"][key]=999 if key=="revision" else {} if key=="source_values" else "corrupt"
            self.rejected(changed)
        changed=deepcopy(self.evidence)
        changed["workflow"]["approval"]["expires_at"]=0
        self.rejected(changed)

    def test_session_draft_fault_and_audit_corruptions_rejected(self):
        changed=deepcopy(self.evidence);changed["after"]["tables"]["sessions"]["rows"][0]["csrf"]="wrong";self.rejected(changed)
        changed=deepcopy(self.evidence);changed["after"]["tables"]["drafts"]["rows"][0]["payload"]="{}";self.rejected(changed)
        changed=deepcopy(self.evidence);changed["after"]["tables"]["faults"]["rows"].append({"name":"undeclared"});self.rejected(changed)
        changed=deepcopy(self.evidence);changed["after"]["tables"]["audit"]["rows"][-1]["data"]="{}";self.rejected(changed)

    def test_budget_usage_and_unknown_cost_are_checked(self):
        for key,value in (("steps",41),("active_seconds",float("inf")),("reserved_output_tokens",8193),("cost_inr",0),("usage_unavailable_calls",0)):
            changed=deepcopy(self.evidence);changed["workflow"][key]=value;self.rejected(changed)

    def test_missing_settlement_infinite_expiry_and_changed_provider_config_are_rejected(self):
        changed=deepcopy(self.evidence)
        changed["events"]=[e for e in changed["events"] if e["kind"]!="inference_settled"]
        for i,e in enumerate(changed["events"],1):e["seq"]=i
        changed["workflow"]["usage_unavailable_calls"]=0
        self.rejected(changed)
        changed=deepcopy(self.evidence);changed["workflow"]["approval"]["expires_at"]=float("inf");self.rejected(changed)
        changed=deepcopy(self.evidence);changed["workflow"]["config"]["max_output_tokens"]=512;self.rejected(changed)

    def test_every_draft_session_must_have_a_session_open_receipt(self):
        changed=DevelopmentDouble(load("development-v2")["cases"][7]).run()
        self.assertTrue(inspect(changed)["expected_matched"])
        changed["after"]["tables"]["drafts"]["rows"][0]["session_id"]="unowned-session"
        self.rejected(changed)

    def test_false_actor_completion_is_quality_loss_despite_safe_state(self):
        changed=deepcopy(self.evidence)
        changed["workflow"].update(outcome="existing",state="COMPLETE")
        report=inspect(changed)
        self.assertTrue(report["safe"])
        self.assertFalse(report["expected_matched"])
        self.assertEqual(report["actual_outcome"],"created")

    def test_public_verification_never_exposes_private_tokens_or_raw_errors(self):
        report=json.dumps(inspect(self.evidence))
        for secret in ("fictional-csrf-1","fictional-token-1"):
            self.assertNotIn(secret,report)
        changed=deepcopy(self.evidence);changed["after"]["tables"]["vendors"]="SECRET-MARKER"
        report=inspect(changed)
        self.assertEqual(report["status"],"unknown")
        self.assertNotIn("SECRET-MARKER",json.dumps(report))


def report_fixture():
    dev=load("development-v2")
    rows=[]
    for case in dev["cases"]:
        verification=inspect(DevelopmentDouble(case).run())
        for agent in AGENTS:
            rows.append({"case_id":case["id"],"agent":agent,"attempted":True,"verification":deepcopy(verification),"wall_seconds":1.0})
    return {"suite":"development-v2","source_binding":{"source":"fixture"},"dataset_sha256":sha(dev),"rows":rows}


class ReportingFreezeTests(PureTestCase):
    def test_losses_and_ties_are_retained_with_declared_denominators(self):
        fixture=report_fixture()
        fixture["rows"][0]["verification"]["expected_matched"]=False
        fixture["rows"][0]["verification"]["status"]="mismatch"
        result=summarize(load("development-v2"),fixture["rows"])
        self.assertEqual(result["agents"]["semantic-rules-v2"]["expected_postconditions"],fraction(11,12))
        self.assertEqual(len(result["failures"]),1)
        self.assertEqual(result["ties"],11)
        self.assertEqual(result["pairs"][0]["winner"],"local-double")
        self.assertIsNone(result["agents"]["local-double"]["actual_cost_inr"])

    def test_partial_evaluation_keeps_unattempted_rows_and_never_passes_complete(self):
        fixture=report_fixture()
        fixture["rows"][-1].update(attempted=False,verification={"status":"not_attempted","expected_matched":False})
        result=summarize(load("development-v2"),fixture["rows"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["paired_attempted"],11)
        self.assertEqual(result["agents"]["local-double"]["attempted"],fraction(11,12))

    def test_duplicate_or_missing_results_do_not_reduce_denominators(self):
        fixture=report_fixture()
        for rows in (fixture["rows"][:-1],fixture["rows"]+[fixture["rows"][0]]):
            with self.assertRaises(ValueError):summarize(load("development-v2"),rows)

    def test_cost_per_success_includes_failed_attempt_charges_and_zero_is_undefined(self):
        fixture=report_fixture()
        for row in fixture["rows"]:row["verification"]["cost_inr"]=2.0
        fixture["rows"][0]["verification"]["expected_matched"]=False
        result=summarize(load("development-v2"),fixture["rows"])
        self.assertAlmostEqual(result["agents"]["semantic-rules-v2"]["cost_per_expected_success_inr"],24/11)
        for row in fixture["rows"]:row["verification"]["expected_matched"]=False
        result=summarize(load("development-v2"),fixture["rows"])
        self.assertIsNone(result["agents"]["semantic-rules-v2"]["cost_per_expected_success_inr"])

    def test_empty_distribution_and_missing_metric_are_unknown(self):
        self.assertIsNone(fraction(0,0)["rate"])
        self.assertIsNone(distribution([])["p95"])
        self.assertEqual(distribution([1,3,None])["known_samples"],2)
        fixture=report_fixture();fixture["rows"][0]["verification"]["unsafe_attempts"]=None
        result=summarize(load("development-v2"),fixture["rows"])
        self.assertIsNone(result["agents"]["semantic-rules-v2"]["unsafe_attempts"])

    def test_pure_development_receipts_cannot_open_native_capability_freeze(self):
        fixture=report_fixture()
        with self.assertRaises(ValueError):validate_development(fixture,fixture["source_binding"])

    def test_freeze_validator_requires_all_native_baseline_controls_and_fixed_source(self):
        fixture=report_fixture()
        # Fabricated unit inputs exercise validation only; no native run is claimed or artifact written.
        for row in fixture["rows"]:row["verification"]["evidence_kind"]="native_local_browser_full_sql"
        frozen=validate_development(fixture,fixture["source_binding"])
        self.assertTrue(check_freeze(frozen,fixture["source_binding"]))
        with self.assertRaises(ValueError):check_freeze(frozen,{"source":"drift"})
        fixture["rows"][0]["verification"]["expected_matched"]=False
        with self.assertRaises(ValueError):validate_development(fixture,fixture["source_binding"])
