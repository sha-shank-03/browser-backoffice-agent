"""Capability scoring needs complete native development controls and unchanged source."""
import json
from pathlib import Path
from .cases import sha,load
from .reporting import AGENTS


def validate_development(report,current_binding):
    dev = load("development-v2")
    if report["suite"]!="development-v2" or report["source_binding"]!=current_binding or report["dataset_sha256"]!=sha(dev):
        raise ValueError("development_source_binding")
    rows = report["rows"]
    expected = {(a,c["id"]) for a in AGENTS for c in dev["cases"]}
    if len(rows)!=len(expected) or {(r["agent"],r["case_id"]) for r in rows}!=expected:
        raise ValueError("development_denominator")
    baseline = [r for r in rows if r["agent"]=="semantic-rules-v2"]
    if any(not r["attempted"] or r["verification"].get("evidence_kind")!="native_local_browser_full_sql"
           or not r["verification"].get("expected_matched") or not r["verification"].get("safe") for r in baseline):
        raise ValueError("native_baseline_development_controls_required")
    # Provider development losses remain in the report; no comparator success is fabricated.
    if any(not r["attempted"] for r in rows):
        raise ValueError("development_runs_incomplete")
    return {"schema_version":1,"source_binding":current_binding,"development_report_sha256":sha(report),
            "development_dataset_sha256":sha(dev),"capability_dataset_sha256":sha(load("capability-v2")),
            "agents":list(AGENTS),"baseline_native_controls":12,"blind_evidence":False,"post_score_tuning_allowed":False}


def check_freeze(frozen,current_binding):
    if frozen["source_binding"]!=current_binding or frozen["capability_dataset_sha256"]!=sha(load("capability-v2")):
        raise ValueError("scored_source_or_dataset_drift")
    if frozen["baseline_native_controls"]!=12 or frozen["agents"]!=list(AGENTS) or frozen["post_score_tuning_allowed"] is not False:
        raise ValueError("capability_freeze_contract")
    return True
