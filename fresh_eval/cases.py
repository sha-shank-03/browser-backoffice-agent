"""Exposed authored dataset validation. Never imported by either acting policy."""
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ("layout","semantic_labels","validation","session","duplicate_uncertainty","injection_authority")
COUNTS = {"development-v2":{"created":8,"existing":1,"handoff":3},"capability-v2":{"created":16,"existing":2,"handoff":6}}
BUDGETS = {"decisions":40,"active_seconds":300,"context_bytes":65536,"reply_bytes":32768,"output_tokens_per_request":512,
           "configured_output_tokens_per_request":128,"output_tokens_per_run":8192,"automatic_retries":0}


def sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def load(suite):
    if suite not in COUNTS:
        raise ValueError("only_worker_exposed_suites")
    value = json.loads((ROOT/"fresh_eval_data"/(suite+".json")).read_text(encoding="utf-8"))
    cases = value["cases"]
    if (value["suite"] != suite or value["exposure"] != "worker_authored_exposed" or value["budgets"] != BUDGETS
            or dict(Counter(c["expected"] for c in cases)) != COUNTS[suite]
            or dict(Counter(c["family"] for c in cases)) != {f:2 if suite=="development-v2" else 4 for f in FAMILIES}
            or len({c["id"] for c in cases}) != len(cases) or len({sha(c["request"]) for c in cases}) != len(cases)
            or any(c["template_sha256"] != sha(c["fixture"]) for c in cases)):
        raise ValueError("dataset_contract")
    return value


def disjoint():
    dev,cap = load("development-v2"),load("capability-v2")
    return (not {sha(c["request"]) for c in dev["cases"]}&{sha(c["request"]) for c in cap["cases"]}
            and not {c["template_sha256"] for c in dev["cases"]}&{c["template_sha256"] for c in cap["cases"]})
