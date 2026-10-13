"""A narrow adapter over the frozen ledger and evaluator, with no raw recovery."""
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace

from durable_eval.ledger import ROOT, exclusive_receipt, execute_first_slice, scoped_path
from diagnostic_eval.repeat import tree
from details_eval.repeat import VerificationLedger, check_history
from details_eval.source_check import binding as prior_binding
from fresh_eval.cases import load, sha
from . import VERSION

PROFILE = ROOT / "details_continuation_data/provenance.json"
PARTIAL = ROOT / "work/u2b-dev02-details-verification-v1"
OUTPUT = "work/u2b-dev02-details-local-continuation-v1"
EXECUTION = "dev02-details-local-continuation-01"
RETAINED = "retained-01-semantic-rules-v2"
TARGET = "continuation-02-local-double"


def check_provenance():
    """Read bytes/receipts only. Never recover or refresh the archived projection."""
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    check_history()
    if tree(PARTIAL) != profile["partial_tree"]:
        raise ValueError("partial_raw_claim_state_or_directory_drift")
    if prior_binding() != profile["partial_source_binding"]:
        raise ValueError("retained_actor_collector_source_drift")
    for name, digest in profile["prior_repo_pins"].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError("main_reviewed_source_or_history_drift")
    archived = VerificationLedger(PARTIAL, profile["partial_source_binding"])
    report = archived.report()
    if report["plan_sha256"] != profile["partial_plan_sha256"] or report["accounting_states"] != {
            "pending": 1, "completed": 0, "failed": 0, "interrupted_unknown": 1}:
        raise ValueError("only_original_unknown_and_never_started_pair_allowed")
    first, second = report["rows"]
    if (first["agent"], first["accounting_state"], first["attempted"],
            second["agent"], second["accounting_state"], second["attempted"]) != (
            "semantic-rules-v2", "interrupted_unknown", True, "local-double", "pending", False):
        raise ValueError("attempted_unknown_or_target_alias")
    return profile, archived


def make_plan(binding, *, output_relative=None, execution_kind="native_local_browser"):
    relative = OUTPUT if output_relative is None else output_relative
    if relative != OUTPUT or scoped_path(ROOT / relative).relative_to(ROOT).as_posix() != relative:
        raise ValueError("single_fixed_fresh_continuation_output_required")
    if execution_kind not in {"native_local_browser", "pure_mocked_orchestration"}:
        raise ValueError("execution_kind")
    profile, archived = check_provenance()
    config = deepcopy(archived.plan["configuration"])
    config.update(output_relative=relative, continuation_version=VERSION, maximum_new_actor_starts=1)
    slots = deepcopy(archived.plan["slots"])
    for slot, slot_id in zip(slots, (RETAINED, TARGET)):
        slot.update(slot_id=slot_id, source_binding_sha256=sha(binding), configuration_sha256=sha(config),
                    partial_slot_id=slot["slot_id"], partial_execution_id=slot["execution_id"])
    slots[0].update(initial_state="interrupted_unknown", dispatch_allowed=False,
                    attempt_kind="retained_interrupted_unknown_never_replayed",
                    run_dir="retained/semantic-rules-v2/u2b-dev-02",
                    retained_source_binding_sha256=sha(profile["partial_source_binding"]))
    slots[1].update(dispatch_allowed=True, attempt_kind="continuation_of_never_started_slot",
                    execution_id=f"{EXECUTION}/local-double")
    body = {"schema_version": 1, "suite": "development-v2", "execution_kind": execution_kind,
            "execution_id": EXECUTION, "collector_version": profile["partial_source_binding"]["collector_version"],
            "continuation_version": VERSION, "source_binding": deepcopy(binding),
            "dataset_sha256": archived.plan["dataset_sha256"], "configuration": config, "slots": slots,
            "first_slice_case_ids": ["u2b-dev-02"], "dispatch_slot_ids": [TARGET], "maximum_new_actor_starts": 1,
            "partial_plan_sha256": profile["partial_plan_sha256"],
            "provenance_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
            "original_plan_sha256": archived.plan["original_plan_sha256"],
            "diagnostic_repeat_plan_sha256": archived.plan["diagnostic_repeat_plan_sha256"],
            "new_unique_tasks": 0, "original_policy_slots": 24, "original_terminal_slots": 4,
            "original_pending_slots": 20, "retained_partial_unknown_slots": 1,
            "retained_partial_pending_slots": 1, "reconciliation_intended_policy_slots": 2}
    return {**body, "plan_sha256": sha(body)}


class ContinuationLedger(VerificationLedger):
    def __init__(self, out, binding):
        self.out = scoped_path(out)
        self.plan = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        if self.plan != make_plan(binding, output_relative=self.out.relative_to(ROOT).as_posix(),
                                  execution_kind=self.plan["execution_kind"]):
            raise ValueError("immutable_continuation_plan_or_denominator_drift")
        self.full_manifest = load("development-v2")
        self.manifest = {**self.full_manifest, "cases": [c for c in self.full_manifest["cases"] if c["id"] == "u2b-dev-02"]}
        self.binding = deepcopy(binding)
        self.index = {s["slot_id"]: s for s in self.plan["slots"]}
        self.validate_layout()

    def validate_layout(self):
        super().validate_layout()
        if any(self.slot_path(self.index[RETAINED]).iterdir()) or (self.out / self.index[RETAINED]["run_dir"]).exists():
            raise ValueError("retained_unknown_must_not_acquire_new_claim_or_raw_files")

    def start(self, slot):
        if slot != self.index[TARGET]:
            raise ValueError("only_exact_never_started_local_double_slot_allowed")
        check_provenance()
        self.validate_layout()
        return super().start(slot)

    def terminal(self, slot, state, row, code):
        if slot != self.index[TARGET]:
            raise ValueError("retained_unknown_must_not_be_rewritten")
        return super().terminal(slot, state, row, code)

    def project_slot(self, slot):
        if slot["slot_id"] == RETAINED:
            self.slot_path(slot)
            _, archived = check_provenance()
            row = archived.project_slot(archived.plan["slots"][0])
            return {**row, "retained_from_partial": True, "provider_requests": None,
                    "partial_plan_sha256": self.plan["partial_plan_sha256"]}
        return super().project_slot(slot)

    def report(self):
        result = super().report()
        result.update(execution_id=EXECUTION, continuation_version=VERSION,
                      evaluation_scope="never_started_local_double_continuation_with_retained_unknown",
                      summary_scope="Same two dev02 policy intentions: archived baseline unknown plus sole local-double continuation",
                      partial_plan_sha256=self.plan["partial_plan_sha256"],
                      retained_partial_accounting_states={"pending": 1, "completed": 0, "failed": 0, "interrupted_unknown": 1},
                      maximum_new_actor_starts=1, new_task_population=False, native_collector_fix_verified=False,
                      quality_acceptance=False, full_development_complete=False, freeze_eligible=False, capability_eligible=False)
        # Preserve the existing denominator/scorer; unknown baseline evidence cannot establish a comparison.
        result["summary"]["complete"] = False
        for pair in result["summary"]["pairs"]:
            pair.update(tie=None, winner=None, comparison_eligible=False)
        return result

    def recover(self, **kwargs):
        raise ValueError("no_recovery_or_archived_raw_rewrite_route")


def create(out, binding, *, execution_kind="native_local_browser"):
    out = scoped_path(out)
    plan = make_plan(binding, output_relative=out.relative_to(ROOT).as_posix(), execution_kind=execution_kind)
    out.mkdir(parents=True, exist_ok=False)
    exclusive_receipt(out / "plan.json", plan)
    (out / "slots").mkdir()
    for slot in plan["slots"]: (out / "slots" / slot["slot_id"]).mkdir()
    ledger = ContinuationLedger(out, binding)
    ledger.write_report()
    return ledger


def execute_pending(ledger, executor, *, clock=time.monotonic):
    """Only the target reaches the existing single-use dispatch seam."""
    check_provenance()
    ledger.validate_layout()
    dispatch = SimpleNamespace(out=ledger.out, manifest=ledger.manifest,
                               plan={**ledger.plan, "slots": [ledger.index[TARGET]]},
                               slot_path=ledger.slot_path, start=ledger.start,
                               terminal=ledger.terminal, write_report=ledger.write_report)
    return execute_first_slice(dispatch, executor, clock=clock)


def evaluate(out, binding, expected_plan_sha256):
    from fresh_eval.lease import require_lease
    require_lease()
    from .source_check import binding as current_binding
    if binding != current_binding(): raise ValueError("current_continuation_source_binding_required")
    relative = scoped_path(out).relative_to(ROOT).as_posix()
    if make_plan(binding, output_relative=relative)["plan_sha256"] != expected_plan_sha256:
        raise ValueError("reviewed_one_slot_continuation_plan_required")
    ledger = create(out, binding)
    runtime_binding = {**binding, "evaluation_plan_sha256": ledger.plan["plan_sha256"],
                       "evaluation_configuration_sha256": ledger.index[TARGET]["configuration_sha256"],
                       "execution_id": EXECUTION, "attempt_kind": "continuation_of_never_started_slot",
                       "partial_plan_sha256": ledger.plan["partial_plan_sha256"],
                       "original_plan_sha256": ledger.plan["original_plan_sha256"]}
    def executor(case, agent, row, deadline):
        from details_eval.native import bind_collector
        from fresh_eval.native import run_one
        if agent != "local-double": raise ValueError("local_double_only")
        with bind_collector(): return run_one(case, agent, row, runtime_binding, ledger.full_manifest, deadline)
    return execute_pending(ledger, executor)
