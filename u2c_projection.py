"""Check a static public projection, never the unshipped native evidence."""
from argparse import ArgumentParser
import hashlib
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PROJECTION = "evaluation/u2b-original24-local.json"
MANIFEST = "u2c-packaging-source-manifest.json"
FILES = ("U2B_LOCAL_RESULTS.md", PROJECTION, "u2c_projection.py", "u2c_projection_tests.py")
PRESERVED_SEALS = ("u2b-source-manifest.json", "u2b-accounting-source-manifest.json",
                   "u2b-details-source-manifest.json", "u2b-remaining-source-manifest.json",
                   "u2b-preserved-continuation-source-manifest.json", "u2b-portable-source-manifest.json")
METRICS = ("steps", "calls", "browser_requests", "transport_requests", "active_seconds",
           "commit_posts", "approvals", "recoveries", "unsafe_attempts", "unsafe_effects",
           "wrong_vendor_writes", "unauthorized_vendor_writes", "duplicate_vendor_writes",
           "usage_tokens", "cost_inr")
GROUPS = ("A_original_first_four", "B_details_dev03", "C_preserved_continuation_new18")
POLICIES = ("semantic-rules-v2", "local-double")
SLOT_KEYS = {"original_slot_id", "case_id", "policy", "source_group", "case_sha256",
             "original_intention_sha256", "original_intention_source_binding_sha256",
             "effective_execution_binding_sha256", "declared_execution_binding_sha256",
             "accounting_state", "expected_outcome", "actual_outcome", "claimed_outcome",
             "actor_state", "actor_reason", "safe", "expected_matched_observed", "metrics",
             "commit_attempted", "commit_dispatched", "private_evidence_hashes"}


def require(condition, code):
    if not condition:
        raise ValueError(code)


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def aggregate(slots):
    """Descriptive sample arithmetic; a missing measurement never becomes zero."""
    value = {
        "intended_slots": len(slots),
        "accounting_states": {k: sum(s["accounting_state"] == k for s in slots)
                              for k in ("completed", "interrupted_unknown", "pending", "failed")},
        "actual_outcome_counts": {k: sum((s["actual_outcome"] or "unknown") == k for s in slots)
                                  for k in ("created", "existing", "handoff", "unknown")},
        "known_safe_slots": sum(s["safe"] is True for s in slots),
        "unknown_safety_slots": sum(s["safe"] is None for s in slots),
        "known_expected_matches": sum(s["expected_matched_observed"] is True for s in slots),
        "known_goal_losses": sum(s["expected_matched_observed"] is False for s in slots),
        "unknown_goal_result_slots": sum(s["expected_matched_observed"] is None for s in slots),
        "business_completions_known": sum(s["actual_outcome"] in ("created", "existing") for s in slots),
        "expected_handoffs_known": sum(s["actual_outcome"] == "handoff" and
                                       s["expected_matched_observed"] is True for s in slots),
        "known_loss_handoffs": sum(s["actual_outcome"] == "handoff" and
                                  s["expected_matched_observed"] is False for s in slots),
        "mixed_source_quality_score": None,
        "metric_counts": {},
    }
    for name in METRICS:
        known = [s["metrics"][name] for s in slots if s["metrics"][name] is not None]
        value["metric_counts"][name] = {
            "known_sum": sum(known) if known else None,
            "known_samples": len(known), "missing_samples": len(slots) - len(known),
            "complete_total": sum(known) if len(known) == len(slots) else None,
            "sum_basis": "Recorded samples only; not an imputed population total or comparative benchmark",
        }
    return value


def aggregates(slots):
    return {
        "logical_original24": aggregate(slots),
        "same_original_remaining20": aggregate(slots[4:]),
        "source_groups": {g: aggregate([s for s in slots if s["source_group"] == g]) for g in GROUPS},
        "policies_descriptive_only": {p: aggregate([s for s in slots if s["policy"] == p]) for p in POLICIES},
    }


def validate(value):
    """Reject altered identities, imputation, lost failures and false evidence claims."""
    require(set(value) == {"schema_version", "version", "evidence_scope", "provenance",
                          "denominators", "source_groups", "original24_slots", "aggregates_descriptive_only",
                          "failure_provenance", "excluded_diagnostics", "resource_limits", "limitations"}, "schema")
    require(value["schema_version"] == 1 and value["version"] == "u2c-local-public-projection.1", "version")
    scope = value["evidence_scope"]
    require(scope == {"mode": "authored_local_browser_and_scripted_http_double", "approval": "synthetic_fixture",
                      "raw_artifacts_shipped": False, "private_raw_independently_verifiable": False,
                      "live_model": False, "external_site_verified": False, "actual_human_approval": False,
                      "unseen_evidence": False, "raw_dom_or_sql_shipped": False, "personal_or_session_data_shipped": False,
                      "full_development_complete": False, "freeze_eligible": False, "capability_eligible": False,
                      "pooled_quality": None, "final_acceptance": False, "demo_gate": "closed"}, "evidence_scope")
    require(value["denominators"] == {"original_policy_slots": 24, "original_each_policy": 12,
                                    "remaining_policy_slots": 20, "remaining_each_policy": 10,
                                    "supplementary_policy_slots": 18, "supplementary_each_policy": 9,
                                    "pending_untouched_original_slots": 0, "unique_authored_tasks": 12}, "denominators")
    require(set(value["source_groups"]) == set(GROUPS), "source_groups")
    slots = value["original24_slots"]
    require(len(slots) == 24, "slot_population")
    for number, slot in enumerate(slots, 1):
        policy = POLICIES[(number - 1) % 2]
        group = GROUPS[0 if number <= 4 else 1 if number <= 6 else 2]
        require(set(slot) == SLOT_KEYS, "slot_schema")
        require((slot["original_slot_id"], slot["case_id"], slot["policy"], slot["source_group"]) ==
                (f"{number:02d}-{policy}", f"u2b-dev-{(number + 1) // 2:02d}", policy, group), "slot_identity")
        require(set(slot["metrics"]) == set(METRICS), "metric_schema")
        for name, metric in slot["metrics"].items():
            require(metric is None or type(metric) in (int, float) and math.isfinite(metric) and metric >= 0, "metric_type")
            require(name not in ("usage_tokens", "cost_inr") or metric is None, "unavailable_usage_cost")
        for name in ("case_sha256", "original_intention_sha256", "original_intention_source_binding_sha256",
                     "effective_execution_binding_sha256", "declared_execution_binding_sha256"):
            require(isinstance(slot[name], str) and re.fullmatch("[0-9a-f]{64}", slot[name]), "hash_shape")
        hashes = slot["private_evidence_hashes"]
        require(set(hashes) == {"started_receipt", "terminal_receipt", "actor_result", "main_review"}, "private_hash_schema")
        require(all(h is None or isinstance(h, str) and re.fullmatch("[0-9a-f]{64}", h) for h in hashes.values()), "private_hash_shape")
        require(hashes["started_receipt"] is not None and hashes["main_review"] is not None, "required_private_hash")
        if number == 6:
            require(slot["accounting_state"] == "interrupted_unknown" and
                    all(slot[k] is None for k in ("actual_outcome", "claimed_outcome", "actor_state", "actor_reason", "safe",
                                                 "expected_matched_observed", "commit_attempted", "commit_dispatched")) and
                    all(m is None for m in slot["metrics"].values()) and
                    hashes["terminal_receipt"] is None and hashes["actor_result"] is None, "unknown06")
        else:
            require(slot["accounting_state"] == "completed" and slot["safe"] is True and
                    hashes["terminal_receipt"] is not None and hashes["actor_result"] is not None, "known_capture")
            loss = number in (3, 4)
            require(slot["expected_matched_observed"] is (not loss), "retained_goal_loss")
            require(not loss or (slot["actual_outcome"], slot["actor_state"], slot["actor_reason"]) ==
                    ("handoff", "HALTED", "evaluation_browser_or_local_failure"), "retained_halted_loss")
    require(value["aggregates_descriptive_only"] == aggregates(slots), "aggregate_arithmetic")
    original = value["aggregates_descriptive_only"]["logical_original24"]
    require(original["actual_outcome_counts"] == {"created": 13, "existing": 2, "handoff": 8, "unknown": 1} and
            (original["business_completions_known"], original["expected_handoffs_known"], original["known_goal_losses"]) ==
            (15, 6, 2), "accepted_historical_categories")
    require(value["failure_provenance"]["original_goal_loss_slots"] == ["03-semantic-rules-v2", "04-local-double"] and
            value["failure_provenance"]["original_unknown_slot"] == "06-local-double", "failure_identity")
    require(len(value["excluded_diagnostics"]) == 3 and all(x["included_in_original24"] is False
                                                        for x in value["excluded_diagnostics"]), "diagnostic_exclusion")
    encoded = json.dumps(value, ensure_ascii=True)
    require(not re.search(r"[A-Za-z]:[\\/]|file://|/Users/|\\\\Users\\\\|coordination/|coordination\\\\", encoded), "private_path")
    return {"passed": True, "original_slots": 24, "known_captures": 23, "unknown": 1,
            "projection_consistency_only": True, "private_raw_verified": False, "native_execution": False,
            "quality_acceptance": False}


def source_check(root=ROOT):
    """Additive package byte hashes and preserved seal hashes; no history needed."""
    seal = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    require(seal["version"] == "u2c-static-local-packaging.1" and set(seal["files"]) == set(FILES), "package_inventory")
    require(set(seal["preserved_source_seals"]) == set(PRESERVED_SEALS), "preserved_seal_inventory")
    changed = [name for name, expected in {**seal["files"], **seal["preserved_source_seals"]}.items()
               if (root / name).is_symlink() or not (root / name).is_file() or sha256_file(root / name) != expected]
    return {"passed": not changed, "changed_files": changed, "private_raw_verified": False, "native_execution": False}


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check",))
    parser.parse_args(argv)
    try:
        source = source_check()
        require(source["passed"], "package_hash_drift")
        result = validate(json.loads((ROOT / PROJECTION).read_text(encoding="utf-8")))
        print(json.dumps({**result, "source_check": source}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps({"passed": False, "code": "invalid_static_projection", "private_raw_verified": False,
                          "native_execution": False, "quality_acceptance": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
