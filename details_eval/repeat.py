"""Distinct corrected-source verification repeat, retaining both old cohorts."""
from copy import deepcopy
import hashlib
import json

from durable_eval.ledger import ROOT, Ledger, exclusive_receipt, scoped_path
from diagnostic_eval.repeat import RepeatLedger, check_original, tree
from fresh_eval.cases import BUDGETS, load, sha
from fresh_eval.reporting import AGENTS
from . import VERSION

PROFILE = ROOT / "details_eval_data/lineage.json"
EXECUTION = "dev02-details-verification-01"


def check_history():
    check_original()
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    for relative, pinned in profile["artifact_trees"].items():
        if tree(ROOT / relative) != pinned: raise ValueError("original_or_diagnostic_history_changed")
    return profile


def make_plan(binding, *, output_relative="work/u2b-dev02-details-verification-v1", execution_kind="native_local_browser"):
    path = scoped_path(ROOT / output_relative)
    profile = check_history()
    if path.relative_to(ROOT).as_posix() != output_relative or any(path.is_relative_to((ROOT / name).resolve()) for name in profile["artifact_trees"]):
        raise ValueError("distinct_canonical_details_output_required")
    if execution_kind not in {"native_local_browser", "pure_mocked_orchestration"}: raise ValueError("execution_kind")
    full = load("development-v2")
    case = next(c for c in full["cases"] if c["id"] == "u2b-dev-02")
    config = {"output_relative": output_relative, "phase_seconds": 900, "paired_task_limit": 1, "budgets": deepcopy(BUDGETS),
              "automatic_retries": 0, "collector_version": VERSION,
              "model_config": {"mode": "local_double", "model": "fixture/local-double-v1", "max_output_tokens": 128,
                               "attempt_seconds": 20, "endpoint": "fresh_loopback_local_double_or_unused_baseline_endpoint"}}
    slots = [{"slot_id": f"details-{i + 1:02d}-{agent}", "case_id": case["id"], "agent": agent, "case_sha256": sha(case),
              "run_dir": f"runs/{agent}/{case['id']}", "initial_state": "pending", "dataset_sha256": sha(full),
              "source_binding_sha256": sha(binding), "configuration_sha256": sha(config), "execution_id": f"{EXECUTION}/{agent}",
              "attempt_kind": "changed_collector_repeat_of_same_exposed_task", "original_slot_id": f"{i + 3:02d}-{agent}",
              "diagnostic_repeat_slot_id": f"repeat-{i + 1:02d}-{agent}"} for i, agent in enumerate(AGENTS)]
    body = {"schema_version": 1, "suite": "development-v2", "execution_kind": execution_kind, "collector_version": VERSION,
            "execution_id": EXECUTION, "source_binding": deepcopy(binding), "dataset_sha256": sha(full), "configuration": config,
            "slots": slots, "first_slice_case_ids": [case["id"]], "original_plan_sha256": profile["original_plan_sha256"],
            "diagnostic_repeat_plan_sha256": profile["diagnostic_repeat_plan_sha256"],
            "lineage_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(), "new_unique_tasks": 0, "repeat_task_ids": 1,
            "original_policy_slots": 24, "original_terminal_slots": 4, "original_pending_slots": 20}
    return {**body, "plan_sha256": sha(body)}


class VerificationLedger(RepeatLedger):
    def __init__(self, out, binding):
        self.out = scoped_path(out)
        self.plan = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        expected = make_plan(binding, output_relative=self.out.relative_to(ROOT).as_posix(), execution_kind=self.plan["execution_kind"])
        if self.plan != expected: raise ValueError("immutable_details_verification_plan_drift")
        self.full_manifest = load("development-v2")
        self.manifest = {**self.full_manifest, "cases": [c for c in self.full_manifest["cases"] if c["id"] == "u2b-dev-02"]}
        self.binding = deepcopy(binding)
        self.index = {s["slot_id"]: s for s in self.plan["slots"]}
        self.validate_layout()

    def report(self):
        check_history()
        result = super().report()
        result.update(collector_version=VERSION, execution_id=EXECUTION, evaluation_scope="changed_collector_verification_repeat",
                      summary_scope="Dev02 repeat under changed source; neither original cohort nor diagnostic repeat metrics are replaced",
                      diagnostic_repeat_plan_sha256=self.plan["diagnostic_repeat_plan_sha256"],
                      native_collector_fix_verified=False, source_fix_supported_by_main_repeat=True,
                      original_first_failure_exception_retroactively_established=False, full_development_complete=False,
                      freeze_eligible=False, capability_eligible=False)
        return result


def create(out, binding, *, execution_kind="native_local_browser"):
    out = scoped_path(out)
    plan = make_plan(binding, output_relative=out.relative_to(ROOT).as_posix(), execution_kind=execution_kind)
    out.mkdir(parents=True, exist_ok=False)
    exclusive_receipt(out / "plan.json", plan)
    (out / "slots").mkdir()
    for slot in plan["slots"]: (out / "slots" / slot["slot_id"]).mkdir()
    ledger = VerificationLedger(out, binding)
    ledger.write_report()
    return ledger


def future_development_plan(binding):
    """Frozen planning artifact only; no execution route for original pending slots."""
    profile = check_history()
    full = load("development-v2")
    slots = []
    for case in full["cases"]:
        for agent in AGENTS:
            ordinal = len(slots) + 1
            slots.append({"slot_id": f"corrected-dev-{ordinal:02d}-{agent}", "case_id": case["id"], "agent": agent,
                          "case_sha256": sha(case), "initial_state": "pending", "original_slot_id": f"{ordinal:02d}-{agent}",
                          "execution_id": f"details-development-v1/{case['id']}/{agent}",
                          "attempt_kind": "repeat_in_new_source_cohort" if ordinal <= 4 else "first_attempt_previously_pending_task_changed_source",
                          "migration_phase": "separate_repeat_gate" if ordinal <= 4 else "separate_pending_gate"})
    body = {"schema_version": 1, "purpose": "Future corrected-source full development plan; not executable by this candidate CLI",
            "execution_authorized": False, "source_cohort": "details-development-v1", "collector_version": VERSION,
            "source_binding_status": "Planning reference to collector candidate; executable orchestration must be separately sealed before dispatch",
            "source_binding": deepcopy(binding), "dataset_sha256": sha(full), "budgets": deepcopy(BUDGETS), "slots": slots,
            "intended_tasks_in_new_cohort": 12, "intended_runs_in_new_cohort": 24,
            "pending_migration_task_ids": [c["id"] for c in full["cases"][2:]], "pending_migration_runs": 20,
            "pending_migration_batches": [[c["id"] for c in full["cases"][start:start + 2]] for start in range(2, 12, 2)],
            "maximum_paired_tasks_per_future_lease": 2,
            "failure_rule": "Unknown/unsafe evidence stops dispatch; started/terminal slots never replayed; code drift creates a new cohort",
            "original_plan_sha256": profile["original_plan_sha256"], "original_frozen_pending_remain_unchanged": 20,
            "import_prior_results": False, "import_verification_repeat_results": False,
            "continuation_gate": "Collector pair independent review, separate source/cohort execution assignment and named leases",
            "native_freeze_gate": "All24 new-cohort slots independently audited at same source; baseline12safe postconditions; all policies attempted",
            "freeze_implemented_or_authorized": False, "capability_execution_authorized": False}
    return {**body, "plan_sha256": sha(body)}
