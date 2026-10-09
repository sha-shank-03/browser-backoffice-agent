"""Durable bounded decision loop; authority lives outside provider output."""
from __future__ import annotations

import json
from pathlib import Path
import time
from urllib.parse import urlparse

from .browser import BrowserController, PortalProcess
from .domain import Cancelled, Interrupted, ProtocolError, WorkflowError, digest, review_contract
from .policy import check_budget, track_progress, validate_approval
from .providers import ScriptedProvider, ask
from .store import Store, run_lock

TERMINALS = {"ACTOR_DONE": 0, "HANDOFF": 20, "FAILED": 30, "CANCELLED": 30}


def approve(run_dir: Path, supplied_digest: str, kind="manual_cli"):
    with run_lock(run_dir):
        store = Store(run_dir)
        try:
            if (run_dir / "cancel.request").exists():
                raise WorkflowError("Cancellation is pending")
            if store.data["state"] != "AWAITING_APPROVAL" or not store.data["review"] or store.data["commit_attempted"]:
                raise WorkflowError("Run is not awaiting fresh approval")
            expected = digest(store.data["review"])
            if supplied_digest != expected:
                raise WorkflowError("Approval digest does not match the complete review")
            grant(store, kind)
            store.export()
        finally:
            store.close()


def grant(store, kind):
    expected = digest(store.data["review"])
    now = time.time()
    store.data["approval"] = {"digest": expected, "approved_at": now, "expires_at": now + 900,
                              "kind": kind, "consumed": False}
    store.data["state"] = "APPROVED"
    store.save("approval_granted", {"digest": expected, "kind": kind})


def handoff(store, reason):
    store.data.update(state="HANDOFF", reason=reason)
    store.save("handoff", {"reason": reason})
    return 20


def cancellation(store):
    if (store.run_dir / "cancel.request").exists():
        raise Cancelled("operator_cancelled")


def run(run_dir: Path, provider=None, fixture_approval=False, *, hook=None):
    """hook is trusted harness code at named barriers; never a provider tool."""
    provider = provider or ScriptedProvider()
    with run_lock(run_dir):
        store = Store(run_dir)
        started = time.monotonic()

        def barrier(stage):
            if hook:
                hook(stage, store)
            cancellation(store)

        def budget():
            size = sum(p.stat().st_size for p in run_dir.iterdir() if p.is_file())
            check_budget(store.data, time.monotonic() - started, size)

        def usage_count():
            usage = getattr(provider, "last_usage", {})
            store.data["generated_tokens"] = store.data.get("generated_tokens", 0) + (usage.get("eval_count") or 0)
            if store.data["live_provider"] and usage.get("eval_count") is None:
                store.data["usage_unavailable_calls"] = store.data.get("usage_unavailable_calls", 0) + 1
            if store.data["generated_tokens"] > 8192:
                raise WorkflowError("Reported generation token budget exhausted")
            return usage

        try:
            if not store.data:
                raise WorkflowError("Missing initialized run")
            if digest(store.data["request"]) != store.data["request_hash"]:
                raise WorkflowError("Immutable request hash changed")
            if store.data["state"] in TERMINALS:
                store.save("terminal_replayed", {"state": store.data["state"]})
                return TERMINALS[store.data["state"]]
            cancellation(store)
            if store.data["state"] == "AWAITING_APPROVAL":
                return 10
            if store.data["steps"] == 0:
                store.data["provider"] = provider.identity
                store.data["live_provider"] = provider.identity.startswith("ollama:")
            elif store.data["provider"] != provider.identity:
                raise WorkflowError("Resume requires the original provider identity")
            if store.data["state"] == "INTERRUPTED" and not store.data["commit_attempted"]:
                store.data["state"] = store.data.get("resume_state", "CREATED")
            if store.data["commit_attempted"]:
                store.data.update(state="RECONCILING", resume_path="/vendors")
                store.save("reconciliation_started", {"policy": "visible_ui_search_only_no_resubmit"})
            budget()
            with PortalProcess(run_dir / "portal.db") as portal, BrowserController(portal.origin, store) as browser:
                while True:
                    barrier("before_observation")
                    budget()
                    observation = browser.observe()
                    path = urlparse(observation["url"]).path
                    if path == "/login" and store.data.get("session_opened"):
                        if store.data.get("approval") and not store.data["commit_attempted"]:
                            return handoff(store, "approval_invalidated")
                        if store.data["reauth_attempts"] >= 1:
                            return handoff(store, "reauthentication_exhausted")
                    context = {"schema_version": 1, "request": dict(store.data["request"]),
                               "state": store.data["state"], "observation": observation,
                               "remaining_steps": 40 - store.data["steps"],
                               "last_result": store.data.get("last_result")}
                    store.data["steps"] += 1
                    try:
                        decision = ask(provider, context)
                    except ProtocolError as exc:
                        usage = usage_count()
                        store.data["protocol_errors"] = store.data.get("protocol_errors", 0) + 1
                        store.data["last_result"] = {"status": "protocol_error", "error": str(exc)[:200]}
                        store.save("provider_protocol_rejected", {**store.data["last_result"], "usage": usage})
                        if store.data["protocol_errors"] > 1:
                            raise WorkflowError("Protocol correction budget exhausted") from exc
                        continue
                    usage = usage_count()
                    track_progress(store.data, observation, decision)
                    store.save("decision", {"provider": provider.identity, "tool": decision.tool,
                                            "arguments": decision.arguments, "observation": observation, "usage": usage})
                    if store.data["commit_attempted"] and decision.tool not in {"observe", "fill_from_request", "click", "finish", "handoff"}:
                        raise WorkflowError("Consumed authority permits only UI reconciliation")
                    if store.data["commit_attempted"] and decision.tool in {"fill_from_request", "click"}:
                        control = next(c for c in observation["controls"] if c["ref"] == decision.arguments["ref"])
                        permitted = path == "/vendors" and control["label"] in {"Registration reference search", "Search", "Inspect matching vendor"}
                        permitted |= path == "/login" and control["label"] == "Open fictional operator session"
                        if not permitted or (decision.tool == "fill_from_request" and decision.arguments["field"] != "registration_ref"):
                            raise WorkflowError("Reconciliation permits only reference search and reauthentication")
                    if decision.tool == "observe":
                        store.data["last_result"] = {"status": "observed"}
                        continue
                    if decision.tool in {"fill_from_request", "choose_from_request", "click"}:
                        if path == "/login" and decision.tool == "click":
                            if store.data.get("session_opened"):
                                store.data["reauth_attempts"] += 1
                                store.save("reauthentication_attempted", {"attempt": store.data["reauth_attempts"]})
                        browser.interact(decision, store.data["request"])
                        if path == "/login":
                            store.data["session_opened"] = True
                        browser.observe()  # Persist the destination before an orderly restart barrier.
                        store.data["last_result"] = {"status": "completed", "tool": decision.tool}
                        store.save("tool_completed", store.data["last_result"])
                        barrier("after_tool")
                    elif decision.tool == "request_review":
                        review = review_contract(store.data["task_id"], store.data["request"], browser.read_review())
                        store.data.update(review=review, state="AWAITING_APPROVAL")
                        store.save("review_ready", {"digest": digest(review)})
                        (run_dir / "review.json").write_text(json.dumps({"review": review, "digest": digest(review)}, indent=2), encoding="utf-8")
                        if not fixture_approval:
                            return 10
                        accepted = fixture_approval(review) if callable(fixture_approval) else True
                        if not accepted:
                            return handoff(store, "approval_denied")
                        grant(store, "simulated_fixture")
                        store.data["last_result"] = {"status": "approved_for_current_review"}
                        barrier("after_approval")
                    elif decision.tool == "submit_approved":
                        try:
                            current = review_contract(store.data["task_id"], store.data["request"], browser.refresh_review())
                            validate_approval(store.data, current, time.time())
                        except WorkflowError:
                            store.save("approval_invalidated")
                            return handoff(store, "approval_invalidated")
                        barrier("before_commit_intent")
                        budget()
                        store.data["approval"]["consumed"] = True
                        store.data.update(state="SUBMITTING", commit_attempted=True)
                        store.save("commit_intent", {"approval_digest": store.data["approval"]["digest"]})
                        barrier("before_commit_request")
                        try:
                            browser.arm_and_submit(current)
                        except Exception as exc:
                            cancellation(store)
                            raise Interrupted("Commit response unavailable; resume with UI reconciliation") from exc
                        store.data["state"] = "RECONCILING"
                        browser.observe()
                        store.data["last_result"] = {"status": "commit_returned_requires_visible_verification"}
                        store.save("commit_returned")
                        barrier("after_commit")
                    elif decision.tool == "finish":
                        outcome = decision.arguments["outcome"]
                        allowed = {"/vendors/detail"} if outcome == "created" and store.data["commit_attempted"] else {"/vendors"}
                        if path not in allowed or observation["records"] != [store.data["request"]] or (outcome == "created" and not store.data["commit_attempted"]) or (outcome == "existing" and store.data["commit_attempted"]):
                            raise WorkflowError("Completion requires an exact visible vendor record and matching write history")
                        store.data.update(state="ACTOR_DONE", outcome=outcome, reason=None)
                        store.save("actor_done", {"outcome": outcome})
                        return 0
                    else:
                        return handoff(store, decision.arguments["reason"])
        except (KeyboardInterrupt, Cancelled):
            store.data.update(state="CANCELLED", reason="operator_cancelled")
            store.save("cancelled", {"write_outcome": "unknown" if store.data.get("commit_attempted") else "not_attempted"})
            return 30
        except Interrupted as exc:
            store.data["resume_state"] = store.data["state"]
            store.data.update(state="INTERRUPTED", reason=str(exc)[:500])
            store.save("interrupted", {"reason": store.data["reason"], "commit_attempted": store.data["commit_attempted"]})
            return 11
        except Exception as exc:
            store.data.update(state="FAILED", reason=str(exc)[:500])
            store.save("run_failed", {"reason": store.data["reason"], "write_outcome": "unknown" if store.data.get("commit_attempted") else "not_attempted"})
            return 30
        finally:
            if store.data:
                store.data["active_seconds"] += time.monotonic() - started
                store.save("run_stopped", {"state": store.data["state"]})
                store.export()
            store.close()
