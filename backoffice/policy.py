"""Host budgets and authority checks, independent of provider decisions."""
from .domain import WorkflowError, digest


def check_budget(data, elapsed, evidence_bytes=0):
    if data["steps"] >= 40:
        raise WorkflowError("40-step budget exhausted")
    limit = 300 if data.get("live_provider") else 120
    if data["active_seconds"] + elapsed >= limit:
        raise WorkflowError("Active wall-clock budget exhausted")
    if data.get("generated_tokens", 0) >= 8192:
        raise WorkflowError("Reported generation token budget exhausted")
    # Reserve 1 MiB for final failure/checkpoint/export records within the 20 MiB ceiling.
    if evidence_bytes >= 19 * 1024 * 1024:
        raise WorkflowError("Run evidence budget exhausted (20 MiB including shutdown reserve)")


def validate_approval(data, current, now):
    approval = data.get("approval")
    if (data["state"] != "APPROVED" or not approval or approval["consumed"]
            or approval["expires_at"] < now or current != data["review"]
            or digest(current) != approval["digest"]):
        raise WorkflowError("Missing, stale, expired or consumed exact approval")


def track_progress(data, observation, decision):
    signature = digest({"observation": {k: observation[k] for k in ("url", "text", "controls", "records")},
                        "tool": decision.tool,
                        "arguments": {k: v for k, v in decision.arguments.items() if k != "observation_id"}})
    data["unchanged_count"] = data.get("unchanged_count", 0) + 1 if data.get("last_signature") == signature else 1
    data["last_signature"] = signature
    if data["unchanged_count"] >= 3:
        raise WorkflowError("Three unchanged observation/action cycles")
