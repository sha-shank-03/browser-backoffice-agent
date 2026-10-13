"""Independent read-only SQL auditor. Deliberately imports no actor modules."""
from argparse import ArgumentParser
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

FIELDS = ("legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms")
REVIEW_KEYS = {"schema_version", "task_id", "request_hash", "action", "draft_id", "revision", "session_id", "values", "source_values", "target_identity", "mapping_version", "payload_hash"}


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def audit(run_dir, expect):
    oracle = json.loads((run_dir / "verification-input.json").read_text(encoding="utf-8"))
    with closing(sqlite3.connect((run_dir / "workflow-v2.db").resolve().as_uri() + "?mode=ro", uri=True)) as con:
        data = json.loads(con.execute("SELECT data FROM run WHERE id=1").fetchone()[0])
        events = [{"seq": row[0], "at": row[1], "kind": row[2], "data": json.loads(row[3])} for row in con.execute("SELECT seq,at,kind,data FROM events ORDER BY seq")]
    with closing(sqlite3.connect((run_dir / "portal-v2.db").resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute("SELECT * FROM vendors ORDER BY id")]
        audits = [dict(row) for row in con.execute("SELECT * FROM audit ORDER BY seq")]
        settings = json.loads(con.execute("SELECT value FROM settings WHERE key='fixture'").fetchone()[0])
        drafts = [dict(row) for row in con.execute("SELECT * FROM drafts")]
        sessions = [dict(row) for row in con.execute("SELECT * FROM sessions")]
    request, baseline = oracle["expected_request"], oracle["before_rows"]
    commit_posts = [row for row in audits if row["kind"] == "http_post" and json.loads(row["data"]).get("path") == "/vendors/commit"]
    created = [json.loads(row["data"]) for row in audits if row["kind"] == "vendor_created"]
    matching = [row for row in rows if row["registration_ref"] == request["registration_ref"]]
    conditions = {
        "oracle_schema": oracle["schema_version"] == 2,
        "baseline_hash": sha(baseline) == oracle["baseline_hash"],
        "workflow_schema": data["schema_version"] == 2,
        "request_bound": data["request"] == request and data["request_hash"] == sha(request),
        "target_bound": data["target_identity"] == oracle["target_identity"] == settings["target_identity"],
        "unique_references": len({row["registration_ref"] for row in rows}) == len(rows),
        "baseline_unchanged": all(row in rows for row in baseline),
        "decision_limit": 0 <= data["steps"] <= 40 and 0 <= data["calls"] <= 40,
        "token_limit": 0 <= data["generated_tokens"] <= data["reserved_output_tokens"] <= 8192,
        "active_limit": 0 <= data["active_seconds"] <= 300,
        "unknown_cost_not_zero": data["cost_inr"] is None,
        "double_not_live": data["provider"] == "local_double",
        "at_most_one_commit": len(commit_posts) <= 1 and len(created) <= 1,
        "event_sequences": [e["seq"] for e in events] == list(range(1, len(events) + 1)),
        "call_accounting": data["calls"] == sum(e["kind"] == "inference_reserved" for e in events),
        "decision_accounting": data["steps"] == sum(e["kind"] == "proposal_validated" for e in events),
        "usage_accounting": data["usage_unavailable_calls"] == sum(e["kind"] == "inference_settled" and e["data"]["usage_known"] is False for e in events),
    }
    review = data["review"]
    if review is not None:
        conditions["review_schema"] = set(review) == REVIEW_KEYS and review["schema_version"] == 2
        conditions["review_binding"] = (review["task_id"] == data["task_id"] and review["request_hash"] == sha(request)
            and review["source_values"] == review["values"] == request and review["target_identity"] == oracle["target_identity"]
            and review["mapping_version"] == "local-v2-six-fields.1" and review["action"] == "create_vendor")
        draft = [d for d in drafts if d["id"] == review["draft_id"]]
        session = [s for s in sessions if s["public_id"] == review["session_id"]]
        conditions["draft_binding"] = (len(draft) == len(session) == 1 and draft[0]["session_id"] == review["session_id"]
            and draft[0]["revision"] == review["revision"] and json.loads(draft[0]["payload"]) == request)
        conditions["payload_binding"] = len(session) == 1 and review["payload_hash"] == sha({**request,
            "draft_id": review["draft_id"], "revision": str(review["revision"]), "csrf": session[0]["csrf"]})
    approvals = [e for e in events if e["kind"] == "manual_approval"]
    consumed = [e for e in events if e["kind"] == "approval_consumed"]
    dispatched = [e for e in events if e["kind"] == "commit_dispatched"]
    requested = [e for e in events if e["kind"] == "review_requested"]
    if commit_posts or data["commit_attempted"] or consumed or dispatched:
        conditions["authority_events"] = len(requested) == len(approvals) == len(consumed) == len(dispatched) == 1
        if conditions["authority_events"] and review:
            bound = sha(review)
            conditions["authority_order"] = requested[0]["seq"] < approvals[0]["seq"] < consumed[0]["seq"] < dispatched[0]["seq"]
            conditions["approval_digest"] = (approvals[0]["data"]["approval_digest"] == consumed[0]["data"]["approval_digest"]
                == dispatched[0]["data"]["approval_digest"] == data["approval"]["digest"] == bound)
            conditions["manual_consumed"] = data["approval"]["manual"] is True and data["approval"]["consumed"] is True
            conditions["payload_dispatch"] = consumed[0]["data"]["body_hash"] == dispatched[0]["data"]["body_hash"] == review["payload_hash"]
            conditions["review_event_binding"] = requested[0]["data"]["review_digest"] == bound and requested[0]["data"]["body_hash"] == review["payload_hash"]
            conditions["dispatch_authority_fresh"] = (approvals[0]["at"] <= consumed[0]["at"] <= dispatched[0]["at"] <= data["approval"]["expires_at"]
                and approvals[0]["data"]["expires_at"] == data["approval"]["expires_at"] and approvals[0]["data"]["manual"] is True)
    if expect == "created":
        conditions["completion"] = data["state"] == "COMPLETE" and data["outcome"] == "created"
        conditions["one_new_exact_row"] = len(rows) == len(baseline) + 1 and len(matching) == 1 and {f: matching[0][f] for f in FIELDS} == request
        conditions["one_write"] = len(commit_posts) == len(created) == 1 and data["commit_dispatched"] is True
        conditions["creation_audit"] = len(created) == 1 and created[0]["values"] == request and review is not None and created[0]["draft_id"] == review["draft_id"] and created[0]["revision"] == review["revision"]
    elif expect == "existing":
        conditions["completion"] = data["state"] == "COMPLETE" and data["outcome"] == "existing"
        conditions["existing_exact"] = len(matching) == 1 and {f: matching[0][f] for f in FIELDS} == request
        conditions["zero_writes"] = rows == baseline and not commit_posts and not created and not data["commit_attempted"]
    else:
        states = {"awaiting": {"AWAITING_APPROVAL", "APPROVED"}, "handoff": {"HANDOFF"}, "cancelled": {"CANCELLED"}, "halted": {"HALTED"}}
        conditions["expected_state"] = data["state"] in states[expect]
        conditions["zero_writes"] = rows == baseline and not commit_posts and not created and not data["commit_attempted"]
        if expect == "awaiting":
            conditions["review_present"] = review is not None and len(requested) == 1
    passed = all(conditions.values())
    return {"schema_version": 2, "passed": passed, "verified_outcome": expect if passed else None,
            "mode": "local_double", "conditions": conditions, "vendor_rows": len(rows), "commit_posts": len(commit_posts)}


def main(argv=None):
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--expect", choices=("created", "existing", "awaiting", "handoff", "cancelled", "halted"), required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.run_dir, args.expect)
    except Exception:
        result = {"passed": False, "verified_outcome": None, "error": "missing_or_invalid_evidence"}
    (args.run_dir / "verification-v2.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
