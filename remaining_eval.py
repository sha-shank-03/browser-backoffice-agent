"""Linked original slots05..24; one reviewed untouched pair per main lease.

The original four receipts and all dev02 reruns remain separate and immutable.
Only the existing ledger, dispatcher, evaluator and DETAILS collector are used.
"""
from argparse import ArgumentParser
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import time
from types import SimpleNamespace

from durable_eval.ledger import ROOT, Ledger, encoded, exclusive_receipt, execute_first_slice, scoped_path, unknown_row
from diagnostic_eval.repeat import tree
from fresh_eval.cases import BUDGETS, load, sha
from fresh_eval.lease import require_lease
from fresh_eval.reporting import AGENTS

VERSION = "original-remaining-details.1"
OUTPUT = "work/u2b-remaining-details-v1"
ORIGINAL = ROOT / "work/u2b-first-slice-accounting-v1"
SEAL = ROOT / "u2b-remaining-source-manifest.json"
SOURCES = ("remaining_eval.py", "remaining_eval_tests.py")
LEASE_ENV = "BB_U2B_REMAINING_LEASE_NAME"


def source_check():
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    actual = {name: hashlib.sha256((ROOT / name).read_bytes().replace(b"\r\n", b"\n")).hexdigest() for name in SOURCES}
    for name in SOURCES: ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
    changed = sorted(name for name in SOURCES if seal["files"].get(name) != actual[name])
    if set(seal["files"]) != set(SOURCES): changed.append("source_inventory")
    for name, digest in seal["preserved_repo_files"].items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            changed.append(name)
    for name, expected in seal["history_trees"].items():
        if tree(ROOT / name) != expected: changed.append(name)
    expected_trees = {"work/u2b-first-slice-accounting-v1": 42, "work/u2b-dev02-diagnostic-repeat-v1": 22,
                      "work/u2b-dev02-details-verification-v1": 7, "work/u2b-dev02-details-local-continuation-v1": 12}
    if len(seal["preserved_repo_files"]) != 247 or {name: len(value["files"]) for name, value in seal["history_trees"].items()} != expected_trees:
        changed.append("preservation_denominator")
    if sha(load("development-v2")) != seal["dataset_sha256"]: changed.append("development_dataset")
    return {"passed": not changed, "version": VERSION, "files": 2, "changed_files": changed,
            "preserved_repo_files": 247, "history_files": 83, "native_execution": False,
            "native_collector_fix_verified": False, "quality_acceptance": False}


def source_binding():
    if not source_check()["passed"]: raise ValueError("remaining_source_data_or_history_drift")
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    return {**seal["actor_base_binding"], "remaining_version": VERSION,
            "remaining_source_manifest_sha256": hashlib.sha256(SEAL.read_bytes()).hexdigest()}


def original_plan():
    return json.loads((ORIGINAL / "plan.json").read_text(encoding="utf-8"))


def fixed_output(out):
    path = scoped_path(out)
    if path.relative_to(ROOT).as_posix() != OUTPUT: raise ValueError("fixed_remaining_sidecar_output_required")
    return path


def make_plan(binding=None, *, execution_kind="native_local_browser"):
    current = source_binding()
    if binding is not None and binding != current: raise ValueError("current_remaining_binding_required")
    if execution_kind not in {"native_local_browser", "pure_mocked_orchestration"}: raise ValueError("execution_kind")
    old, full = original_plan(), load("development-v2")
    config = deepcopy(old["configuration"])
    config.update(output_relative=OUTPUT, paired_task_limit=1, phase_seconds=900, maximum_actor_starts_per_batch=2,
                  collector_version=current["collector_version"], remaining_version=VERSION)
    if config["budgets"] != BUDGETS or old["dataset_sha256"] != sha(full): raise ValueError("unchanged_original_data_budgets_required")
    slots = []
    for old_slot in old["slots"][4:]:
        slot = deepcopy(old_slot)
        slot.update(original_slot_id=old_slot["slot_id"], original_slot_sha256=sha(old_slot),
                    original_intention_source_binding_sha256=old_slot["source_binding_sha256"],
                    original_intention_configuration_sha256=old_slot["configuration_sha256"],
                    source_binding_sha256=sha(current), configuration_sha256=sha(config),
                    execution_id=f"{VERSION}/{old_slot['slot_id']}",
                    attempt_kind="first_attempt_original_pending_intention_changed_collector")
        slots.append(slot)
    body = {"schema_version": 1, "suite": "development-v2", "execution_kind": execution_kind,
            "remaining_version": VERSION, "source_binding": current, "dataset_sha256": sha(full),
            "configuration": config, "slots": slots, "first_slice_case_ids": [c["id"] for c in full["cases"][2:]],
            "lease_name_template": "browser-main-remaining-{case_id}",
            "original_plan_sha256": old["plan_sha256"], "original_policy_slots": 24,
            "original_retained_terminal_slots": 4, "remaining_original_policy_slots": 20, "new_unique_tasks": 0}
    return {**body, "plan_sha256": sha(body)}


def original_rows():
    plan = original_plan()
    archived = Ledger(ORIGINAL, plan["source_binding"])
    rows = [archived.project_slot(slot) for slot in plan["slots"][:4]]
    if any(row["accounting_state"] != "completed" for row in rows): raise ValueError("original_four_terminal_rows_required")
    return [{**row, "original_slot_id": slot["slot_id"], "execution_source_binding": deepcopy(plan["source_binding"]),
             "provenance": "immutable_original_receipt"} for slot, row in zip(plan["slots"], rows)]


class RemainingLedger(Ledger):
    def __init__(self, out, binding):
        self.out = fixed_output(out)
        self.plan = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        if self.plan != make_plan(binding, execution_kind=self.plan["execution_kind"]):
            raise ValueError("immutable_remaining_twenty_plan_binding_or_denominator_drift")
        self.full_manifest = load("development-v2")
        self.manifest = {**self.full_manifest, "cases": self.full_manifest["cases"][2:]}
        self.binding = deepcopy(binding)
        self.index = {slot["slot_id"]: slot for slot in self.plan["slots"]}
        self._dispatch_slots = ()
        self.validate_layout()

    def start(self, slot):
        if slot["slot_id"] not in self._dispatch_slots or source_binding() != self.binding:
            raise ValueError("reviewed_pair_dispatch_context_required")
        return super().start(slot)

    def terminal(self, slot, state, row, code):
        row = {**row, "retained_run_tree": tree(self.out / slot["run_dir"])}
        return super().terminal(slot, state, row, code)

    def project_slot(self, slot):
        row = super().project_slot(slot)
        if row["accounting_state"] == "completed" and row.get("retained_run_tree") != tree(self.out / slot["run_dir"]):
            row = {**unknown_row(self, slot, "retained_run_tree_changed"), "accounting_state": "interrupted_unknown"}
        return {**row, "original_slot_id": slot["original_slot_id"], "execution_id": slot["execution_id"],
                "execution_source_binding": deepcopy(self.binding),
                "execution_source_binding_status": "executed" if row["attempted"] else "planned",
                "provenance": "linked_original_pending_intention"}

    def report(self):
        if source_binding() != self.binding: raise ValueError("remaining_execution_source_drift")
        result = super().report()
        inventory = original_rows() + result["rows"]
        result.update(evaluation_scope="original_remaining_twenty_only", summary_scope="dev03..12 at the separately sealed execution source; N10 per actor",
                      original_plan_sha256=self.plan["original_plan_sha256"], original_policy_slots=24,
                      original_raw_accounting_states={"completed": 4, "pending": 20, "failed": 0, "interrupted_unknown": 0},
                      logical_inventory=inventory, logical_policy_denominator=24, logical_inventory_kind="mixed_source_read_only_accounting",
                      mixed_source_quality_summary=None, included_diagnostic_or_alias_rows=0, new_unique_tasks=0,
                      full_development_complete=False, freeze_eligible=False, capability_eligible=False,
                      native_collector_fix_verified=False, quality_acceptance=False)
        return result

    def recover(self, **kwargs):
        raise ValueError("no_remaining_recovery_or_replay_route")


def initial_state_sha256(plan):
    view = {"files": {"plan.json": hashlib.sha256(encoded(plan)).hexdigest()},
            "directories": sorted(["slots"] + ["slots/" + slot["slot_id"] for slot in plan["slots"]])}
    return sha({"plan_sha256": plan["plan_sha256"], "sidecar_tree_without_report": view})


def state_sha256(ledger):
    ledger.report()  # Validate every receipt/raw tree, source and historical attribution.
    view = tree(ledger.out)
    view["files"].pop("report.json", None)  # Projection bytes are not authoritative claims.
    return sha({"plan_sha256": ledger.plan["plan_sha256"], "sidecar_tree_without_report": view})


def next_pair(ledger, case_id):
    rows = ledger.report()["rows"]
    if any(r["accounting_state"] not in {"pending", "completed"} or
           r["accounting_state"] == "completed" and r["verification"].get("safe") is not True for r in rows):
        raise ValueError("unknown_unsafe_or_incomplete_remaining_evidence_stops_dispatch")
    for case in ledger.manifest["cases"]:
        selected = [slot for slot in ledger.plan["slots"] if slot["case_id"] == case["id"]]
        pair = [row for row in rows if row["case_id"] == case["id"]]
        if all(row["accounting_state"] == "completed" for row in pair): continue
        if case_id != case["id"] or len(pair) != 2 or not all(row["accounting_state"] == "pending" for row in pair):
            raise ValueError("only_next_fully_untouched_original_pair_allowed")
        if [slot["agent"] for slot in selected] != list(AGENTS): raise ValueError("original_policy_order_required")
        return selected
    raise ValueError("no_untouched_original_pairs")


def dispatch(ledger, case_id, expected_plan, expected_state, executor, *, clock=time.monotonic):
    require_pair_lease(case_id)
    if source_binding() != ledger.binding: raise ValueError("current_remaining_source_required")
    ledger.validate_layout()
    if expected_plan != ledger.plan["plan_sha256"] or expected_state != state_sha256(ledger):
        raise ValueError("exact_reviewed_plan_and_prebatch_state_required")
    selected = next_pair(ledger, case_id)
    facade = SimpleNamespace(out=ledger.out, manifest=ledger.manifest,
                             plan={**ledger.plan, "slots": selected, "first_slice_case_ids": [case_id]},
                             slot_path=ledger.slot_path, start=ledger.start, terminal=ledger.terminal, write_report=ledger.write_report)
    ledger._dispatch_slots = tuple(slot["slot_id"] for slot in selected)
    try: return execute_first_slice(facade, executor, clock=clock)
    finally: ledger._dispatch_slots = ()


def create_sidecar(out, binding):
    out = fixed_output(out)
    plan = make_plan(binding)
    out.mkdir(parents=True, exist_ok=False)
    exclusive_receipt(out / "plan.json", plan)
    (out / "slots").mkdir()
    for slot in plan["slots"]: (out / "slots" / slot["slot_id"]).mkdir()
    return RemainingLedger(out, binding)


def require_pair_lease(case_id):
    require_lease()
    if os.environ.get(LEASE_ENV) != f"browser-main-remaining-{case_id}":
        raise ValueError("exact_main_remaining_pair_lease_name_required")
    # Name/sentinel guard accidental dispatch; actual grant remains main's responsibility.


def evaluate(out, case_id, expected_plan, expected_state):
    require_pair_lease(case_id)  # No output or actor import before this guard.
    binding = source_binding()
    plan = make_plan(binding)
    path = fixed_output(out)
    if expected_plan != plan["plan_sha256"]: raise ValueError("reviewed_remaining_plan_required")
    if path.exists(): ledger = RemainingLedger(path, binding)
    else:
        if case_id != plan["first_slice_case_ids"][0] or expected_state != initial_state_sha256(plan):
            raise ValueError("reviewed_initial_dev03_state_required")
        ledger = create_sidecar(path, binding)
    runtime_binding = {**binding, "evaluation_plan_sha256": plan["plan_sha256"],
                       "evaluation_configuration_sha256": plan["slots"][0]["configuration_sha256"],
                       "original_plan_sha256": plan["original_plan_sha256"]}
    def executor(case, agent, row, deadline):
        from details_eval.native import bind_collector
        from fresh_eval.native import run_one
        slot = next(s for s in plan["slots"] if (s["case_id"], s["agent"]) == (case["id"], agent))
        actual = {**runtime_binding, "original_slot_id": slot["original_slot_id"], "execution_id": slot["execution_id"],
                  "attempt_kind": slot["attempt_kind"]}
        with bind_collector(): return run_one(case, agent, row, actual, ledger.full_manifest, deadline)
    return dispatch(ledger, case_id, expected_plan, expected_state, executor)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("source-check")
    commands.add_parser("derive-dev03")
    run = commands.add_parser("run-next")
    for name in ("out", "case-id", "plan-sha256", "state-sha256"): run.add_argument("--" + name, required=True)
    report = commands.add_parser("report"); report.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source-check":
            result = source_check(); print(json.dumps(result, indent=2)); return 0 if result["passed"] else 1
        if args.command == "derive-dev03":
            plan = make_plan()
            print(json.dumps({"plan": plan, "initial_state_sha256": initial_state_sha256(plan), "sidecar_created": False}, indent=2)); return 0
        if args.command == "report":
            ledger = RemainingLedger(args.out, source_binding())
            print(json.dumps({"report": ledger.report(), "state_sha256": state_sha256(ledger)}, indent=2)); return 0
        result = evaluate(args.out, args.case_id, args.plan_sha256, args.state_sha256)
        print(json.dumps(result, indent=2))
        pair = [row for row in result["rows"] if row["case_id"] == args.case_id]
        return 0 if len(pair) == 2 and all(r["accounting_state"] == "completed" and r["verification"].get("safe") is True for r in pair) else 1
    except Exception:
        print(json.dumps({"passed": False, "code": "invalid_or_unauthorized_remaining_command", "native_collector_fix_verified": False})); return 1


if __name__ == "__main__": raise SystemExit(main())
