"""In-memory corruption controls for public historical projection consistency."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import u2c_projection as p


class ProjectionControls(unittest.TestCase):
    def setUp(self):
        self.value = json.loads((p.ROOT / p.PROJECTION).read_text(encoding="utf-8"))

    def rejected(self, mutation):
        value = deepcopy(self.value)
        mutation(value)
        with self.assertRaises(ValueError):
            p.validate(value)

    def test_current_package_checks_consistency_without_claiming_private_proof(self):
        result = p.validate(self.value)
        self.assertTrue(p.source_check()["passed"])
        self.assertTrue(result["projection_consistency_only"])
        self.assertFalse(result["private_raw_verified"])
        self.assertFalse(result["native_execution"])

    def test_unknown_counts_cannot_be_imputed_zero(self):
        self.rejected(lambda v: v["original24_slots"][5]["metrics"].update(calls=0))

    def test_unknown_cannot_be_relabelled_safe(self):
        self.rejected(lambda v: v["original24_slots"][5].update(safe=True))

    def test_original_goal_loss_cannot_be_removed_even_with_recomputed_aggregates(self):
        def mutate(v):
            v["original24_slots"][2].update(expected_matched_observed=True)
            v["aggregates_descriptive_only"] = p.aggregates(v["original24_slots"])
        self.rejected(mutate)

    def test_business_completions_cannot_be_inflated(self):
        self.rejected(lambda v: v["aggregates_descriptive_only"]["logical_original24"].update(business_completions_known=16))

    def test_pooled_quality_or_raw_proof_cannot_be_claimed(self):
        self.rejected(lambda v: v["evidence_scope"].update(pooled_quality=1.0))
        self.rejected(lambda v: v["evidence_scope"].update(private_raw_independently_verifiable=True))

    def test_unavailable_cost_and_usage_cannot_become_zero(self):
        self.rejected(lambda v: v["original24_slots"][0]["metrics"].update(cost_inr=0))
        self.rejected(lambda v: v["original24_slots"][0]["metrics"].update(usage_tokens=0))

    def test_slot_identity_and_diagnostic_exclusion_are_required(self):
        self.rejected(lambda v: v["original24_slots"][5].update(original_slot_id="07-semantic-rules-v2"))
        self.rejected(lambda v: v["excluded_diagnostics"][0].update(included_in_original24=True))

    def test_byte_hash_drift_is_not_accepted(self):
        with patch.object(p, "sha256_file", return_value="0" * 64):
            self.assertFalse(p.source_check()["passed"])


if __name__ == "__main__":
    unittest.main()
