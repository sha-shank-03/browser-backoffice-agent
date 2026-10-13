"""A separate, bounded repeat identity; never amend the original 24-slot ledger."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from durable_eval.ledger import ROOT, Ledger, exclusive_receipt, scoped_path
from fresh_eval.cases import BUDGETS, load, sha
from fresh_eval.reporting import AGENTS
from . import VERSION
from .diagnostics import descriptor

PROFILE = ROOT / "diagnostic_eval_data/original_evidence_profile.json"
ORIGINAL = ROOT / "work/u2b-first-slice-accounting-v1"
EXECUTION = "dev02-diagnostic-repeat-01"


def tree(path):
    return {"files": {p.relative_to(path).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in sorted(path.rglob("*")) if p.is_file()},
            "directories": sorted(p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_dir())}


def check_original():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    if tree(ORIGINAL) != profile["tree"]:
        raise ValueError("original_four_attempts_or_twenty_pending_changed")
    return profile


def make_plan(binding, *, output_relative="work/u2b-dev02-diagnostic-repeat-v1", execution_kind="native_local_browser"):
    path = scoped_path(ROOT / output_relative)
    if path.relative_to(ROOT).as_posix() != output_relative or path.is_relative_to(ORIGINAL.resolve()):
        raise ValueError("distinct_canonical_repeat_output_required")
    if execution_kind not in {"native_local_browser", "pure_mocked_orchestration"}:
        raise ValueError("repeat_execution_kind")
    profile = check_original()
    manifest = load("development-v2")
    case = next(c for c in manifest["cases"] if c["id"] == "u2b-dev-02")
    config = {"output_relative": output_relative, "phase_seconds": 900, "paired_task_limit": 1,
              "budgets": deepcopy(BUDGETS), "automatic_retries": 0, "diagnostic_version": VERSION,
              "model_config": {"mode": "local_double", "model": "fixture/local-double-v1",
                               "max_output_tokens": 128, "attempt_seconds": 20,
                               "endpoint": "fresh_loopback_local_double_or_unused_baseline_endpoint"}}
    slots = [{"slot_id": f"repeat-{i + 1:02d}-{agent}", "case_id": case["id"], "agent": agent,
              "case_sha256": sha(case), "run_dir": f"runs/{agent}/{case['id']}", "initial_state": "pending",
              "dataset_sha256": sha(manifest), "source_binding_sha256": sha(binding), "configuration_sha256": sha(config),
              "execution_id": f"{EXECUTION}/{agent}", "attempt_kind": "repeat_of_same_exposed_task",
              "original_slot_id": f"{i + 3:02d}-{agent}"} for i, agent in enumerate(AGENTS)]
    body = {"schema_version": 1, "suite": "development-v2", "execution_kind": execution_kind,
            "diagnostic_version": VERSION, "execution_id": EXECUTION, "source_binding": deepcopy(binding),
            "dataset_sha256": sha(manifest), "configuration": config, "slots": slots,
            "first_slice_case_ids": [case["id"]], "original_plan_sha256": profile["original_plan_sha256"],
            "original_evidence_profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
            "original_intended_tasks": 12, "original_policy_slots": 24, "original_terminal_slots": 4,
            "original_pending_slots": 20, "new_unique_tasks": 0, "repeat_task_ids": 1}
    return {**body, "plan_sha256": sha(body)}


class RepeatLedger(Ledger):
    def __init__(self, out, binding):
        self.out = scoped_path(out)
        self.plan = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        expected = make_plan(binding, output_relative=self.out.relative_to(ROOT).as_posix(),
                             execution_kind=self.plan["execution_kind"])
        if self.plan != expected: raise ValueError("immutable_repeat_plan_drift")
        self.full_manifest = load("development-v2")
        self.manifest = {**self.full_manifest, "cases": [c for c in self.full_manifest["cases"] if c["id"] == "u2b-dev-02"]}
        self.binding = deepcopy(binding)
        self.index = {s["slot_id"]: s for s in self.plan["slots"]}
        self.validate_layout()

    def terminal(self, slot, state, row, code):
        row = {**row, "diagnostic_evidence": descriptor(self.out / slot["run_dir"])}
        return super().terminal(slot, state, row, code)

    def report(self):
        check_original()
        result = super().report()
        for slot, row in zip(self.plan["slots"], result["rows"]):
            row.update(attempt_kind=slot["attempt_kind"], execution_id=slot["execution_id"], original_slot_id=slot["original_slot_id"])
            terminal = self.slot_path(slot) / "TERMINAL.json"
            record = self.read_receipt(terminal, slot) if terminal.exists() else None
            pinned = record["row"].get("diagnostic_evidence") if record else None
            row["diagnostic_evidence"] = pinned
            row["diagnostic_receipt_unchanged"] = descriptor(self.out / slot["run_dir"]) == pinned if pinned else None
        result.update(diagnostic_version=VERSION, execution_id=EXECUTION, evaluation_scope="repeat_diagnostic_only",
                      summary_scope="Same dev02 task repeated; not added to original full-development first-attempt metrics",
                      original_plan_sha256=self.plan["original_plan_sha256"], original_intended_tasks=12,
                      original_policy_slots=24, original_terminal_slots=4, original_pending_slots=20,
                      new_unique_tasks=0, repeat_task_ids=1, full_development_complete=False,
                      root_cause_established=False, freeze_eligible=False, capability_eligible=False)
        return result


def create(out, binding, *, execution_kind="native_local_browser"):
    out = scoped_path(out)
    plan = make_plan(binding, output_relative=out.relative_to(ROOT).as_posix(), execution_kind=execution_kind)
    out.mkdir(parents=True, exist_ok=False)
    exclusive_receipt(out / "plan.json", plan)
    (out / "slots").mkdir()
    for slot in plan["slots"]: (out / "slots" / slot["slot_id"]).mkdir()
    ledger = RepeatLedger(out, binding)
    ledger.write_report()
    return ledger
