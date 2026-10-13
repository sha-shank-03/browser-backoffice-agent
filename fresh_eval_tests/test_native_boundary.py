from dataclasses import asdict
import contextlib
import io

from supplier_contract_tests.pure_support import PureTestCase
from industry_backoffice.protocol import ModelConfig,Halt,parse_reply,request_body
from fresh_eval.baseline import SemanticRules
from fresh_eval.cases import load
from fresh_eval.lease import require_lease
from fresh_eval.native import baseline_reply,vendor_values,evaluate
from fresh_eval.__main__ import main,require_native_freeze_proof
from fresh_eval.freeze import validate_development
from fresh_eval_tests.test_contract import report_fixture
from fresh_eval_tests.simulator import DevelopmentDouble


class NativeBoundaryTests(PureTestCase):
    def test_unleased_native_evaluation_fails_before_any_creation(self):
        with self.assertRaises(ValueError):require_lease()
        with self.assertRaises(ValueError):evaluate("development-v2","work/forbidden-pure",{},phase_seconds=900)
        self.assertEqual(self.forbidden_calls,[])

    def test_cli_native_request_refuses_without_lease(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result=main(["evaluate","--suite","development-v2","--out","work/forbidden-pure","--phase-seconds","900"])
        self.assertEqual(result,1)
        self.assertIn("invalid_or_unauthorized",output.getvalue())

    def test_baseline_round_trip_uses_the_same_function_protocol_and_fresh_ref_guard(self):
        sim=DevelopmentDouble(load("development-v2")["cases"][0])
        observation=sim.observe()
        state={"approval_state":"READY","search_complete":False,"commit_dispatched":False,"commit_uncertain":False}
        config=ModelConfig("local_double","fixture/local-double-v1","http://127.0.0.1:1/v1/chat/completions",max_output_tokens=128)
        body=request_body(config,sim.request,observation,state,[])
        raw=baseline_reply(SemanticRules(),body)
        decision,_,tokens=parse_reply(raw,observation,128)
        self.assertEqual(decision.tool,"click")
        self.assertIsNone(tokens)
        changed={**observation,"controls":[]}
        with self.assertRaises(Halt):parse_reply(raw,changed,128)

    def test_seed_column_order_is_independent_of_sorted_dataset_object_keys(self):
        request=load("development-v2")["cases"][0]["request"]
        self.assertEqual(list(request),sorted(request))
        self.assertEqual(vendor_values(request),(request["legal_name"],request["registration_ref"],request["country"],request["contact_email"],request["category"],request["payment_terms"]))

    def test_shape_only_freeze_without_scoped_native_report_is_rejected(self):
        fixture=report_fixture()
        for row in fixture["rows"]:row["verification"]["evidence_kind"]="native_local_browser_full_sql"
        frozen=validate_development(fixture,fixture["source_binding"])
        with self.assertRaises((KeyError,ValueError)):
            require_native_freeze_proof(frozen,fixture["source_binding"])
        frozen["development_report_path"]="C:/outside-authorized-evidence/report.json"
        with self.assertRaises(ValueError):require_native_freeze_proof(frozen,fixture["source_binding"])
