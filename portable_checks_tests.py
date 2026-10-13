"""Packaging controls; native history remains strict outside the explicit context."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import portable_checks as p


class PackagingControls(unittest.TestCase):
    def test_source_scope_never_claims_historical_or_native_verification(self):
        value = p.source_check()
        self.assertTrue(value["passed"])
        self.assertEqual(value["historical_native_artifact_verification"], "not_performed")
        self.assertFalse(value["native_execution"])

    def test_exact_javascript_controls_and_demo_are_unit_only(self):
        controls = p.collector_controls()
        value = p.demo(controls)
        self.assertEqual(value["baseline"]["tool"], "click")
        self.assertEqual(value["local_double"], {"tool": "handoff", "arguments": {"reason": "insufficient_evidence"}})
        self.assertFalse(value["native_browser"]); self.assertFalse(value["business_completion_claim"])

    def test_source_tampering_is_not_accepted_by_source_only_contract(self):
        with patch.object(p, "normalized_hash", return_value="changed"):
            self.assertFalse(p.source_check()["passed"])

    def test_fixture_context_does_not_patch_checksum_functions_and_restores_paths(self):
        import diagnostic_eval.repeat as diagnostic
        import details_eval.repeat as details
        original, original_function = diagnostic.ORIGINAL, diagnostic.check_original
        controls = p.collector_controls()
        with p.fixture_context(controls) as fixtures:
            self.assertIs(diagnostic.check_original, original_function)
            self.assertNotEqual(diagnostic.ORIGINAL, original)
            self.assertFalse(fixtures["native_evidence"])
            self.assertEqual(len(diagnostic.check_original()["tree"]["files"]), 42)
            self.assertEqual(sorted(len(v["files"]) for v in details.check_history()["artifact_trees"].values()), [22, 42])
            path = fixtures["root"] / "work/u2b-first-slice-accounting-v1/report.json"
            path.write_text("tampered unit fixture")
            with self.assertRaises(ValueError): diagnostic.check_original()
        self.assertEqual(diagnostic.ORIGINAL, original)
        with patch.object(diagnostic, "ORIGINAL", fixtures["root"] / "absent-native-history"):
            with self.assertRaises(ValueError): diagnostic.check_original()


if __name__ == "__main__": unittest.main()
