"""Only the pinned completed05/unknown06 boundary permits untouched07..24.

The existing engine and its default unknown barrier remain unchanged. All reads
of the preserved interruption are file/receipt hashes, never SQLite connections.
"""
from argparse import ArgumentParser
import ast
from copy import deepcopy
import hashlib
import json
import time
from types import SimpleNamespace

from durable_eval.ledger import execute_first_slice, replace_projection
from diagnostic_eval.repeat import tree
from fresh_eval.cases import sha
from fresh_eval.reporting import summarize
import remaining_eval as engine

VERSION = "preserved-dev03-continuation.1"
SEAL = engine.ROOT / "u2b-preserved-continuation-source-manifest.json"
SOURCES = ("remaining_continue.py", "remaining_continue_tests.py")
PROJECTION = "continuation-report.json"


def seal_data():
    return json.loads(SEAL.read_text(encoding="utf-8"))


def source_check():
    seal = seal_data()
    changed = []
    for name in SOURCES:
        path = engine.ROOT / name
        ast.parse(path.read_text(encoding="utf-8"), filename=name)
        if hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest() != seal["files"].get(name): changed.append(name)
    if set(seal["files"]) != set(SOURCES) or len(seal["preserved_repo_files"]) != 250: changed.append("source_inventory")
    for name, digest in seal["preserved_repo_files"].items():
        path = engine.ROOT / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest: changed.append(name)
    for name, expected in seal["history_trees"].items():
        if tree(engine.ROOT / name) != expected: changed.append(name)
    if len(seal["history_trees"]) != 4 or sum(len(v["files"]) for v in seal["history_trees"].values()) != 83:
        changed.append("historical_inventory")
    if sha(seal["boundary"]) != seal["boundary_sha256"] or sha(engine.source_binding()) != seal["boundary"]["engine_source_binding_sha256"]:
        changed.append("boundary_or_engine_binding")
    return {"passed": not changed, "version": VERSION, "files": 2, "changed_files": changed,
            "preserved_repo_files": 250, "older_native_files": 83, "pinned_dev03_files": 21,
            "native_execution": False, "quality_acceptance": False, "native_collector_fix_verified": False}


def actual_binding():
    if not source_check()["passed"]: raise ValueError("continuation_source_or_boundary_drift")
    seal = seal_data()
    return {**engine.source_binding(), "continuation_version": VERSION,
            "continuation_source_manifest_sha256": hashlib.sha256(SEAL.read_bytes()).hexdigest(),
            "preserved_boundary_sha256": seal["boundary_sha256"]}


def verify_boundary(out, plan, boundary):
    """Frozen old bytes plus declared new07..24 paths; no repair or mutation."""
    if boundary["plan_sha256"] != plan["plan_sha256"] or boundary["allowed_slot_ids"] != [s["slot_id"] for s in plan["slots"][2:]]:
        raise ValueError("exact_original_continuation_scope_required")
    if (boundary["completed_slot_id"], boundary["unknown_slot_id"]) != ("05-semantic-rules-v2", "06-local-double"):
        raise ValueError("only_reviewed_dev03_boundary_allowed")
    frozen = boundary["preserved_tree"]
    if len(frozen["files"]) != 21 or "runs/local-double/u2b-dev-03/workflow-v2.db-journal" not in frozen["files"]:
        raise ValueError("complete_hot_journal_boundary_required")
    current = tree(out)
    if any(current["files"].get(name) != digest for name, digest in frozen["files"].items()) or not set(frozen["directories"]).issubset(current["directories"]):
        raise ValueError("preserved_dev03_bytes_or_directories_changed")
    allowed = plan["slots"][2:]
    claim_files = {f"slots/{slot['slot_id']}/{name}" for slot in allowed for name in ("STARTED.json", "TERMINAL.json")}
    run_roots = [slot["run_dir"] for slot in allowed]
    for name in current["files"]:
        if name not in frozen["files"] and name != PROJECTION and name not in claim_files and not any(name.startswith(root + "/") for root in run_roots):
            raise ValueError("new_file_outside_untouched_original_intentions")
    for name in current["directories"]:
        if name not in frozen["directories"] and not any(name == root or name.startswith(root + "/") for root in run_roots):
            raise ValueError("new_directory_outside_untouched_original_intentions")
    if any((out / name).is_symlink() for name in list(current["files"]) + current["directories"]):
        raise ValueError("sidecar_symlink_not_allowed")
    return current


class ContinuationLedger(engine.RemainingLedger):
    def __init__(self, out):
        self.actual_binding = actual_binding()
        self.boundary = seal_data()["boundary"]
        self.allowed = set(self.boundary["allowed_slot_ids"])
        super().__init__(out, engine.source_binding())
        verify_boundary(self.out, self.plan, self.boundary)

    def envelope(self, slot):
        result = super().envelope(slot)
        if slot["slot_id"] in self.allowed:
            result.update(continuation_source_binding_sha256=sha(self.actual_binding),
                          preserved_boundary_sha256=self.actual_binding["preserved_boundary_sha256"])
        return result

    def start(self, slot):
        if slot["slot_id"] not in self.allowed or actual_binding() != self.actual_binding:
            raise ValueError("only_untouched_original_continuation_claims_allowed")
        verify_boundary(self.out, self.plan, self.boundary)
        return super().start(slot)

    def terminal(self, slot, state, row, code):
        if slot["slot_id"] not in self.allowed: raise ValueError("preserved_boundary_terminal_write_forbidden")
        return super().terminal(slot, state, {**row, "continuation_execution_binding": deepcopy(self.actual_binding)}, code)

    def project_slot(self, slot):
        row = super().project_slot(slot)
        if slot["slot_id"] in self.allowed:
            if row["accounting_state"] == "completed" and row.get("continuation_execution_binding") != self.actual_binding:
                raise ValueError("actual_continuation_execution_binding_drift")
            row["execution_source_binding"] = deepcopy(self.actual_binding)
        return row

    def report(self):
        if actual_binding() != self.actual_binding: raise ValueError("current_continuation_source_required")
        verify_boundary(self.out, self.plan, self.boundary)
        result = super().report()
        first, unknown = result["rows"][:2]
        if (first["accounting_state"], first["verification"].get("safe"), first["verification"].get("expected_matched"),
                unknown["accounting_state"], unknown["verification"].get("safe"), unknown["verification"].get("actual_outcome")) != (
                "completed", True, True, "interrupted_unknown", None, None):
            raise ValueError("completed05_and_permanent_unknown06_required")
        if unknown["verification"].get("transport_requests") is not None or unknown["verification"].get("cost_inr") is not None:
            raise ValueError("unknown06_metrics_must_remain_unknown")
        # The existing scorer is used only for the homogeneous new18 slice.
        result.update(summary=None, source_binding=None, accounting_source_binding=self.binding,
                      evaluation_scope="same_original_twenty_with_explicit_preserved_dev03_boundary",
                      summary_scope="No pooled mixed-source20/24 quality score; secondary summary only for new18",
                      policy_accounting_denominators={agent: 10 for agent in engine.AGENTS},
                      continuation_source_binding=self.actual_binding,
                      per_source_summary={"scope": "new18_dev04_through12", "source_binding": self.actual_binding,
                                          "summary": summarize({**self.full_manifest, "cases": self.full_manifest["cases"][3:]}, result["rows"][2:])},
                      preserved_boundary_sha256=self.actual_binding["preserved_boundary_sha256"],
                      preserved_starting_state_sha256=self.boundary["starting_state_sha256"],
                      full_development_complete=False, execution_complete=False, freeze_eligible=False, capability_eligible=False,
                      mixed_source_quality_summary=None, quality_acceptance=False, native_collector_fix_verified=False)
        return result

    def write_report(self):
        result = self.report()
        replace_projection(self.out / PROJECTION, result)
        return result


def state_sha256(ledger):
    ledger.report()
    view = tree(ledger.out)
    view["files"].pop(PROJECTION, None)  # The OLD report remains immutable and hash-bound.
    return sha({"plan_sha256": ledger.plan["plan_sha256"], "boundary_sha256": ledger.actual_binding["preserved_boundary_sha256"],
                "continuation_source_manifest_sha256": ledger.actual_binding["continuation_source_manifest_sha256"],
                "authoritative_sidecar_tree": view})


def next_pair(ledger, case_id):
    rows = ledger.report()["rows"][2:]
    if any(row["accounting_state"] not in {"pending", "completed"} or
           row["accounting_state"] == "completed" and row["verification"].get("safe") is not True for row in rows):
        raise ValueError("any_new_unknown_unsafe_or_incomplete_stops_continuation")
    for case in ledger.full_manifest["cases"][3:]:
        pair = [row for row in rows if row["case_id"] == case["id"]]
        if all(row["accounting_state"] == "completed" for row in pair): continue
        if case_id != case["id"] or len(pair) != 2 or not all(row["accounting_state"] == "pending" for row in pair):
            raise ValueError("only_next_fully_untouched_preserved_continuation_pair_allowed")
        selected = [slot for slot in ledger.plan["slots"] if slot["case_id"] == case_id]
        if [slot["agent"] for slot in selected] != list(engine.AGENTS) or not all(slot["slot_id"] in ledger.allowed for slot in selected):
            raise ValueError("original_policy_and_intention_order_required")
        return selected
    raise ValueError("no_untouched_continuation_pairs")


def dispatch(ledger, case_id, plan_sha256, boundary_sha256, source_sha256, expected_state, executor, *, clock=time.monotonic):
    engine.require_pair_lease(case_id)
    if actual_binding() != ledger.actual_binding: raise ValueError("reviewed_current_continuation_source_required")
    ledger.validate_layout()
    if (plan_sha256, boundary_sha256, source_sha256, expected_state) != (
            ledger.plan["plan_sha256"], ledger.actual_binding["preserved_boundary_sha256"],
            ledger.actual_binding["continuation_source_manifest_sha256"], state_sha256(ledger)):
        raise ValueError("exact_reviewed_continuation_plan_boundary_source_state_required")
    selected = next_pair(ledger, case_id)
    facade = SimpleNamespace(out=ledger.out, manifest=ledger.manifest,
                             plan={**ledger.plan, "slots": selected, "first_slice_case_ids": [case_id]},
                             slot_path=ledger.slot_path, start=ledger.start, terminal=ledger.terminal, write_report=ledger.write_report)
    ledger._dispatch_slots = tuple(slot["slot_id"] for slot in selected)
    try: return execute_first_slice(facade, executor, clock=clock)
    finally: ledger._dispatch_slots = ()


def evaluate(out, case_id, plan_sha256, boundary_sha256, source_sha256, expected_state):
    engine.require_pair_lease(case_id)  # No actor import or projection write before guards.
    ledger = ContinuationLedger(out)
    runtime_binding = {**ledger.actual_binding, "evaluation_plan_sha256": ledger.plan["plan_sha256"],
                       "continuation_source_binding_sha256": sha(ledger.actual_binding),
                       "evaluation_configuration_sha256": ledger.plan["slots"][0]["configuration_sha256"],
                       "original_plan_sha256": ledger.plan["original_plan_sha256"]}
    def executor(case, agent, row, deadline):
        from details_eval.native import bind_collector
        from fresh_eval.native import run_one
        slot = next(s for s in ledger.plan["slots"] if (s["case_id"], s["agent"]) == (case["id"], agent))
        actual = {**runtime_binding, "original_slot_id": slot["original_slot_id"], "execution_id": slot["execution_id"],
                  "attempt_kind": slot["attempt_kind"]}
        with bind_collector(): return run_one(case, agent, row, actual, ledger.full_manifest, deadline)
    return dispatch(ledger, case_id, plan_sha256, boundary_sha256, source_sha256, expected_state, executor)


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("source-check")
    commands.add_parser("derive-dev04")
    report = commands.add_parser("report"); report.add_argument("--out", required=True)
    run = commands.add_parser("run-next")
    for name in ("out", "case-id", "plan-sha256", "boundary-sha256", "source-sha256", "state-sha256"):
        run.add_argument("--" + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "source-check":
            result = source_check(); print(json.dumps(result, indent=2)); return 0 if result["passed"] else 1
        if args.command == "derive-dev04":
            ledger = ContinuationLedger(engine.ROOT / engine.OUTPUT)
            slots = next_pair(ledger, "u2b-dev-04")
            print(json.dumps({"plan_sha256": ledger.plan["plan_sha256"], "boundary_sha256": ledger.actual_binding["preserved_boundary_sha256"],
                              "source_sha256": ledger.actual_binding["continuation_source_manifest_sha256"], "state_sha256": state_sha256(ledger),
                              "selected_original_slot_ids": [s["slot_id"] for s in slots], "sidecar_mutated": False}, indent=2)); return 0
        if args.command == "report":
            ledger = ContinuationLedger(args.out)
            print(json.dumps({"report": ledger.report(), "state_sha256": state_sha256(ledger)}, indent=2)); return 0
        result = evaluate(args.out, args.case_id, args.plan_sha256, args.boundary_sha256, args.source_sha256, args.state_sha256)
        print(json.dumps(result, indent=2))
        pair = [row for row in result["rows"] if row["case_id"] == args.case_id]
        return 0 if len(pair) == 2 and all(r["accounting_state"] == "completed" and r["verification"].get("safe") is True for r in pair) else 1
    except Exception:
        print(json.dumps({"passed": False, "code": "invalid_or_unauthorized_preserved_continuation", "native_collector_fix_verified": False})); return 1


if __name__ == "__main__": raise SystemExit(main())
