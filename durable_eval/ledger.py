"""Immutable full intentions and single-use filesystem attempt receipts.

File flush/fsync precedes actor dispatch. This establishes process-interruption
accounting, not Windows power-loss durability or actual crash evidence.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
import uuid

from fresh_eval.cases import BUDGETS, load, sha
from fresh_eval.reporting import AGENTS, summarize
from . import VERSION

ROOT = Path(__file__).resolve().parents[1]
TERMINAL_STATES = {"completed", "failed", "interrupted_unknown"}
RAW_NAMES = ("workflow-v2.db", "workflow-v2.db-wal", "workflow-v2.db-shm",
             "portal-v2.db", "portal-v2.db-wal", "portal-v2.db-shm",
             "events-v2.jsonl", "actor-result-v2.json", "review-v2.json",
             "evaluation-oracle.json", "reviewer-decision.json", "independent-evaluation.json")


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def exclusive_receipt(path, value):
    """Never replace a claim/terminal record, even if a write was interrupted."""
    path = Path(path)
    with path.open("xb") as output:
        output.write(encoded(value))
        output.flush()
        os.fsync(output.fileno())


def replace_projection(path, value):
    """Reports are disposable projections; intentions and receipts are not."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    exclusive_receipt(temporary, value)
    os.replace(temporary, path)


def scoped_path(raw):
    path = Path(raw).resolve()
    if not path.is_relative_to((ROOT / "work").resolve()) or path == (ROOT / "work").resolve():
        raise ValueError("repository_work_output_required")
    return path


def make_plan(binding, *, paired_tasks=2, phase_seconds=900, execution_kind="native_local_browser",
              output_relative="work/u2b-first-slice-accounting-v1"):
    if type(paired_tasks) is not int or paired_tasks not in (1, 2):
        raise ValueError("at_most_two_paired_development_tasks")
    if phase_seconds not in (900, 1800):
        raise ValueError("bounded_phase_seconds")
    if execution_kind not in ("native_local_browser", "pure_mocked_orchestration"):
        raise ValueError("execution_kind")
    output = scoped_path(ROOT / output_relative)
    if output.relative_to(ROOT).as_posix() != output_relative:
        raise ValueError("canonical_relative_plan_output_required")
    manifest = load("development-v2")
    config = {"agents": list(AGENTS), "budgets": deepcopy(BUDGETS), "phase_seconds": phase_seconds,
              "output_relative": output_relative,
              "paired_task_limit": paired_tasks, "automatic_retries": 0,
              "model_config": {"mode": "local_double", "model": "fixture/local-double-v1",
                               "max_output_tokens": 128, "attempt_seconds": 20,
                               "endpoint": "fresh_loopback_local_double_or_unused_baseline_endpoint"}}
    slots = []
    for case in manifest["cases"]:
        for agent in AGENTS:
            slots.append({"slot_id": f"{len(slots) + 1:02d}-{agent}", "case_id": case["id"], "agent": agent,
                          "case_sha256": sha(case), "run_dir": f"runs/{agent}/{case['id']}",
                          "initial_state": "pending", "dataset_sha256": sha(manifest),
                          "source_binding_sha256": sha(binding), "configuration_sha256": sha(config)})
    body = {"schema_version": 1, "accounting_version": VERSION, "suite": "development-v2",
            "execution_kind": execution_kind, "source_binding": deepcopy(binding),
            "dataset_sha256": sha(manifest), "configuration": config, "slots": slots,
            "first_slice_case_ids": [c["id"] for c in manifest["cases"][:paired_tasks]]}
    return {**body, "plan_sha256": sha(body)}


def create_plan(out, binding, **options):
    out = scoped_path(out)
    plan = make_plan(binding, **options, output_relative=out.relative_to(ROOT).as_posix())
    # A fresh directory is mandatory. A partial initialization is never reused.
    out.mkdir(parents=True, exist_ok=False)
    exclusive_receipt(out / "plan.json", plan)
    (out / "slots").mkdir()
    for slot in plan["slots"]:
        (out / "slots" / slot["slot_id"]).mkdir()
    ledger = Ledger(out, binding)
    ledger.write_report()
    return ledger


def unknown_row(ledger, slot, code):
    return {"case_id": slot["case_id"], "agent": slot["agent"], "attempted": True,
            "run_dir": str(ledger.out / slot["run_dir"]), "wall_seconds": None,
            "verification": {"status": "unknown", "safe": None, "expected_matched": False, "code": code,
                             "unsafe_attempts": None, "unsafe_effects": None, "cost_inr": None, "usage_tokens": None,
                             "live_model": False, "external_site_verified": False}}


def raw_evidence(run):
    """Hash retained raw files without opening SQL or exporting their contents."""
    files, unavailable = [], []
    for name in RAW_NAMES:
        path = run / name
        try:
            if not path.exists():
                unavailable.append(name)
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError("raw_evidence_not_regular_file")
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    size += len(chunk)
            files.append({"name": name, "bytes": size, "sha256": digest.hexdigest()})
        except (OSError, ValueError):
            unavailable.append(name)
    return {"kind": "filesystem_hash_inventory_only", "sql_read": False,
            "files": files, "unavailable": unavailable, "full_sql_verification": "not_performed_by_accounting"}


def retained_evidence_matches(run, receipt):
    expected = receipt["files"]
    names = [f["name"] for f in expected]
    if len(names) != len(set(names)) or not set(names).issubset(RAW_NAMES):
        raise ValueError("raw_receipt_shape")
    actual = {f["name"]: f for f in raw_evidence(run)["files"]}
    return all(actual.get(f["name"]) == f for f in expected)


class Ledger:
    def __init__(self, out, binding):
        self.out = scoped_path(out)
        self.plan = json.loads((self.out / "plan.json").read_text(encoding="utf-8"))
        config = self.plan["configuration"]
        if config["output_relative"] != self.out.relative_to(ROOT).as_posix():
            raise ValueError("plan_output_directory_binding")
        expected = make_plan(binding, paired_tasks=config["paired_task_limit"], phase_seconds=config["phase_seconds"],
                             execution_kind=self.plan["execution_kind"], output_relative=config["output_relative"])
        if self.plan != expected:
            raise ValueError("immutable_plan_source_data_config_or_denominator_drift")
        self.manifest = load("development-v2")
        self.binding = deepcopy(binding)
        self.index = {s["slot_id"]: s for s in self.plan["slots"]}
        self.validate_layout()

    def validate_layout(self):
        if json.loads((self.out / "plan.json").read_text(encoding="utf-8")) != self.plan:
            raise ValueError("immutable_plan_changed")
        directories = self.out / "slots"
        if directories.is_symlink() or {p.name for p in directories.iterdir()} != set(self.index):
            raise ValueError("slot_directory_omission_or_duplicate")
        for slot in self.plan["slots"]:
            path = self.slot_path(slot)
            if path.is_symlink() or not path.is_dir() or any(p.name not in {"STARTED.json", "TERMINAL.json"} for p in path.iterdir()):
                raise ValueError("unexpected_or_duplicate_slot_record")

    def slot_path(self, slot):
        if self.index.get(slot["slot_id"]) != slot:
            raise ValueError("unplanned_slot")
        return self.out / "slots" / slot["slot_id"]

    def envelope(self, slot):
        return {"schema_version": 1, "plan_sha256": self.plan["plan_sha256"], "slot_sha256": sha(slot),
                "source_binding_sha256": sha(self.binding), "dataset_sha256": self.plan["dataset_sha256"],
                "configuration_sha256": sha(self.plan["configuration"])}

    def read_receipt(self, path, slot):
        if path.is_symlink() or not path.is_file():
            raise ValueError("receipt_not_regular_file")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            return None  # A partial exclusive record is a spent slot, never pending.
        if not isinstance(record, dict) or any(record.get(k) != v for k, v in self.envelope(slot).items()):
            raise ValueError("receipt_binding_drift")
        if record.get("receipt_sha256") != sha({k: v for k, v in record.items() if k != "receipt_sha256"}):
            raise ValueError("receipt_content_drift")
        return record

    def start(self, slot):
        directory = self.slot_path(slot)
        if any(directory.iterdir()) or (self.out / slot["run_dir"]).exists():
            raise ValueError("started_terminal_or_historical_slot_must_not_replay")
        receipt = {**self.envelope(slot), "state": "STARTED", "started_at": now(),
                   "run_dir": slot["run_dir"], "automatic_retries": 0}
        receipt["receipt_sha256"] = sha(receipt)
        # O_EXCL refuses concurrent claims. Dispatch happens only after fsync.
        exclusive_receipt(directory / "STARTED.json", receipt)
        return receipt

    def terminal(self, slot, state, row, code):
        if state not in TERMINAL_STATES:
            raise ValueError("terminal_state")
        directory = self.slot_path(slot)
        started = directory / "STARTED.json"
        if not started.exists():
            raise ValueError("terminal_without_start")
        if (row["case_id"], row["agent"], row["attempted"], row["run_dir"]) != (
                slot["case_id"], slot["agent"], True, str(self.out / slot["run_dir"])):
            raise ValueError("terminal_row_binding")
        evidence = raw_evidence(self.out / slot["run_dir"])
        core = {"workflow-v2.db", "portal-v2.db", "evaluation-oracle.json", "independent-evaluation.json"}
        if state == "completed" and self.plan["execution_kind"] == "native_local_browser" and (
                row["verification"].get("evidence_kind") != "native_local_browser_full_sql"
                or not core.issubset({f["name"] for f in evidence["files"]})):
            state, code = "failed", "native_raw_evidence_unavailable"
            row = unknown_row(self, slot, code)
        record = {**self.envelope(slot), "state": state, "code": code, "finished_at": now(),
                  "started_receipt_sha256": hashlib.sha256(started.read_bytes()).hexdigest(),
                  "row": deepcopy(row), "raw_evidence": evidence}
        record["receipt_sha256"] = sha(record)
        exclusive_receipt(directory / "TERMINAL.json", record)
        return record

    def project_slot(self, slot):
        directory = self.slot_path(slot)
        start, terminal = directory / "STARTED.json", directory / "TERMINAL.json"
        if not start.exists():
            if terminal.exists():
                raise ValueError("terminal_start_receipt_omitted")
            row = {"case_id": slot["case_id"], "agent": slot["agent"], "attempted": False,
                   "run_dir": str(self.out / slot["run_dir"]), "wall_seconds": None,
                   "verification": {"status": "not_attempted", "expected_matched": False,
                                    "code": "outside_first_slice_or_prior_stop"}}
            if (self.out / slot["run_dir"]).exists():
                raise ValueError("raw_state_without_start_receipt")
            return {**row, "accounting_state": "pending", "terminal_receipt": None}
        start_record = self.read_receipt(start, slot)
        if start_record is not None and (start_record.get("state") != "STARTED" or start_record.get("run_dir") != slot["run_dir"]):
            raise ValueError("start_state_or_run_binding")
        if not terminal.exists():
            return {**unknown_row(self, slot, "start_without_terminal"), "accounting_state": "interrupted_unknown",
                    "terminal_receipt": None, "started_receipt_valid": start_record is not None}
        record = self.read_receipt(terminal, slot)
        if record is None:
            return {**unknown_row(self, slot, "partial_terminal_receipt"), "accounting_state": "interrupted_unknown",
                    "terminal_receipt": "partial", "started_receipt_valid": start_record is not None}
        if record.get("state") not in TERMINAL_STATES or record.get("started_receipt_sha256") != hashlib.sha256(start.read_bytes()).hexdigest():
            raise ValueError("terminal_state_or_start_receipt_drift")
        row = record["row"]
        if (row["case_id"], row["agent"], row["attempted"], row["run_dir"]) != (
                slot["case_id"], slot["agent"], True, str(self.out / slot["run_dir"])):
            raise ValueError("terminal_row_binding")
        if record["state"] == "completed" and not retained_evidence_matches(self.out / slot["run_dir"], record["raw_evidence"]):
            return {**unknown_row(self, slot, "retained_raw_evidence_changed_or_unavailable"),
                    "accounting_state": "interrupted_unknown", "recorded_terminal_state": record["state"],
                    "terminal_receipt": f"slots/{slot['slot_id']}/TERMINAL.json", "started_receipt_valid": start_record is not None}
        if start_record is None or record["state"] != "completed":
            row = unknown_row(self, slot, record["code"])
        return {**row, "accounting_state": record["state"] if start_record is not None else "interrupted_unknown",
                "terminal_receipt": f"slots/{slot['slot_id']}/TERMINAL.json", "started_receipt_valid": start_record is not None}

    def report(self):
        self.validate_layout()
        rows = [self.project_slot(slot) for slot in self.plan["slots"]]
        states = {state: sum(r["accounting_state"] == state for r in rows)
                  for state in ("pending", "completed", "failed", "interrupted_unknown")}
        return {"schema_version": 1, "accounting_version": VERSION, "suite": "development-v2",
                "plan_sha256": self.plan["plan_sha256"], "source_binding": self.binding,
                "dataset_sha256": self.plan["dataset_sha256"], "configuration": self.plan["configuration"],
                "rows": rows, "summary": summarize(self.manifest, rows), "accounting_states": states,
                "full_plan_runs": len(rows), "first_slice_case_ids": self.plan["first_slice_case_ids"],
                "execution_complete": states["completed"] == len(rows), "freeze_eligible": False,
                "capability_eligible": False,
                "native_execution_requested": self.plan["execution_kind"] == "native_local_browser",
                "native_execution": self.plan["execution_kind"] == "native_local_browser" and any(
                    r["verification"].get("evidence_kind") == "native_local_browser_full_sql" for r in rows),
                "actual_human_approval": False, "live_model": False, "external_site_verified": False,
                "durability_scope": "flushed files and process interruption; Windows power loss not demonstrated"}

    def write_report(self):
        report = self.report()
        replace_projection(self.out / "report.json", report)
        return report

    def recover(self, *, owner_stopped=False):
        if owner_stopped is not True:
            raise ValueError("stopped_owner_declaration_required")
        for slot in self.plan["slots"]:
            directory = self.slot_path(slot)
            if (directory / "STARTED.json").exists() and not (directory / "TERMINAL.json").exists():
                self.read_receipt(directory / "STARTED.json", slot)
                self.terminal(slot, "interrupted_unknown", unknown_row(self, slot, "recovered_start_without_terminal"),
                              "recovered_start_without_terminal")
        return self.write_report()


def execute_first_slice(ledger, executor, *, clock=time.monotonic):
    """Pure callback seam. Only the guarded native wrapper supplies real actors."""
    # There is no resume/retry path: any spent slot disqualifies this invocation.
    if any(any(ledger.slot_path(s).iterdir()) for s in ledger.plan["slots"]):
        raise ValueError("existing_attempts_must_not_replay")
    deadline = clock() + ledger.plan["configuration"]["phase_seconds"]
    cases = {c["id"]: c for c in ledger.manifest["cases"]}
    for slot in ledger.plan["slots"]:
        if slot["case_id"] not in ledger.plan["first_slice_case_ids"] or deadline - clock() < 60:
            continue
        ledger.start(slot)
        row = unknown_row(ledger, slot, "actor_not_returned")
        try:
            ledger.write_report()
            result = executor(cases[slot["case_id"]], slot["agent"], row, deadline)
            if result is not row:
                raise ValueError("executor_must_return_bound_row")
            verification = row["verification"]
            state = "completed" if verification.get("status") in ("verified", "mismatch") else "failed"
            if state == "failed":
                row = unknown_row(ledger, slot, "actor_evidence_unknown")
            receipt = ledger.terminal(slot, state, row, "actor_returned" if state == "completed" else "actor_evidence_unknown")
            state, row = receipt["state"], receipt["row"]
        except BaseException as error:
            state = "failed" if isinstance(error, Exception) else "interrupted_unknown"
            # If terminal persistence itself failed, preserve its exclusive claim.
            if not (ledger.slot_path(slot) / "TERMINAL.json").exists():
                ledger.terminal(slot, state, unknown_row(ledger, slot, "coordinator_exception"), "coordinator_exception")
            ledger.write_report()
            raise
        ledger.write_report()
        if state == "failed" or row["verification"].get("safe") is not True:
            break
    return ledger.write_report()
