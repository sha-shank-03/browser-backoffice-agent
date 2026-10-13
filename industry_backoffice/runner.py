"""Bounded proposal loop. Approval and SQL evidence stay outside the provider."""
from __future__ import annotations

from dataclasses import asdict
import time
from urllib.parse import urlparse, parse_qs

from backoffice.domain import canonical, digest
from . import VERSION
from .browser import SemanticPortalProcess, V2Browser
from .protocol import Halt, PROMPT_VERSION, parse_reply, request_body, public_observation
from .state import ActiveClock, reserve_call, settle_call, consume_approval
from .transport import exchange

EXITS = {"COMPLETE": 0, "AWAITING_APPROVAL": 10, "HANDOFF": 20, "CANCELLED": 21, "HALTED": 30}


def execute(store, config, transport=exchange, clock=None):
    """Real-browser entry point; must not run before a heavy lease."""
    config.validate()
    data = store.data
    if config.mode != "local_double":
        raise Halt("live_dispatch_disabled", sent=False)
    # A loopback port is transient; all other config is immutable across approval/resume.
    stable = lambda cfg: {k: v for k, v in cfg.items() if k != "endpoint"}
    if (stable(asdict(config)) != stable(data["config"]) or data["code_version"] != VERSION
            or data["prompt_version"] != PROMPT_VERSION or digest(data["request"]) != data["request_hash"]):
        raise Halt("resume_version_or_config_changed")
    if data["state"] in EXITS:
        store.export()
        return EXITS[data["state"]]
    clock = clock or ActiveClock(store)
    try:
        if data["pending_transport"]:
            # Never replay an inference whose completion was not durably observed.
            clock.base += data["pending_transport"]["reserved_seconds"]
            raise Halt("ambiguous_inference_requires_operator", sent=None)
        if clock.remaining() < 60:
            raise Halt("startup_budget")
        clock.checkpoint()
        with SemanticPortalProcess(store.run_dir / "portal-v2.db") as portal:
            clock.checkpoint()
            with V2Browser(portal.origin, store) as browser:
                while True:
                    clock.checkpoint()
                    # Clip Playwright action/navigation timeouts to remaining active budget.
                    millis = max(1, int(min(5, clock.remaining()) * 1000))
                    browser.page.set_default_timeout(millis)
                    browser.page.set_default_navigation_timeout(max(1, int(min(10, clock.remaining()) * 1000)))
                    observed = browser.observe()
                    observation = public_observation(observed)
                    parsed = urlparse(observed["url"])
                    search_complete = (parsed.path == "/vendors" and
                                       parse_qs(parsed.query).get("q") == [data["request"]["registration_ref"]])
                    if search_complete and not observation["records"]:
                        data["absence_observed"] = True
                    context = {"approval_state": data["state"], "search_complete": search_complete,
                               "commit_dispatched": data["commit_dispatched"]}
                    body = request_body(config, data["request"], observation, context, data["history"])
                    reserve_call(store, config, clock)
                    try:
                        raw = transport(config, body, min(time.monotonic() + config.attempt_seconds,
                                        time.monotonic() + max(0, clock.remaining() - 1)),
                                        lambda: (store.run_dir / "cancel.request").exists())
                        decision, assistant, tokens = parse_reply(raw, observation, config.max_output_tokens)
                    except Halt as exc:
                        settle_call(store, None, exc.sent)
                        raise
                    settle_call(store, tokens, True)
                    call_id = assistant["tool_calls"][0]["id"]
                    if call_id in data["call_ids"]:
                        raise Halt("duplicate_function_id")
                    data["call_ids"].append(call_id)
                    data["steps"] += 1
                    store.save("proposal_validated", {"tool": decision.tool, "call_id": call_id,
                               "observation_hash": digest(observation), "decision_hash": digest(asdict(decision))})
                    clock.checkpoint()
                    result = apply_action(store, browser, decision, observation)
                    # Keep one complete assistant/tool pair, matching call id; prior observations are discarded.
                    data["history"] = [assistant, {"role": "tool", "tool_call_id": call_id,
                                       "content": canonical({"status": result, "tool": decision.tool})}]
                    store.save("tool_completed", {"tool": decision.tool, "call_id": call_id, "status": result})
                    if data["state"] in EXITS:
                        break
    except Halt as exc:
        data["state"] = "CANCELLED" if exc.code == "cancelled" else "HALTED"
        data["reason"] = exc.code
        store.save("typed_halt", {"code": exc.code, "sent": exc.sent, "cost_inr": None})
    except Exception:
        # Never persist arbitrary browser/provider exception strings, which may contain secrets.
        data["state"], data["reason"] = "HALTED", "browser_or_local_failure"
        store.save("typed_halt", {"code": data["reason"], "cost_inr": None})
    finally:
        clock.persist()
        store.export()
    return EXITS[data["state"]]


def apply_action(store, browser, decision, observation):
    data, tool = store.data, decision.tool
    path = observation["path"]
    if tool in {"fill_from_request", "choose_from_request", "click"}:
        control = next(c for c in observation["controls"] if c["ref"] == decision.arguments["ref"])
        if tool == "click" and control["label"] == "Register a vendor" and not data.get("absence_observed"):
            raise Halt("duplicate_search_required")
        if data["commit_attempted"]:
            raise Halt("commit_authority_consumed")
        browser.interact(decision, data["request"])
        return "applied"
    if tool == "observe":
        return "reobserve"
    if tool == "request_review":
        if data["commit_attempted"] or data["approval"] or not data.get("absence_observed"):
            raise Halt("review_state")
        data["review"] = browser.read_review()
        data["state"] = "AWAITING_APPROVAL"
        store.save("review_requested", {"review_digest": digest(data["review"]), "body_hash": data["review"]["payload_hash"]})
        return "awaiting_manual_approval"
    if tool == "submit_approved":
        fresh = browser.refresh_review()
        consume_approval(store, fresh)
        try:
            browser.arm_and_submit(fresh)
        except Exception:
            # A possibly dispatched commit cannot be retried automatically, even on resume.
            data["state"], data["reason"] = "HANDOFF", "uncertain_commit"
            store.save("commit_uncertain", {"reason": "uncertain_commit"})
            return "operator_reconciliation_required"
        data["state"] = "CONFIRMING"
        return "submitted_once"
    if tool == "finish":
        expected = decision.arguments["outcome"]
        if observation["records"] != [data["request"]]:
            raise Halt("completion_evidence")
        if expected == "created" and (path != "/vendors/detail" or not data["commit_dispatched"]):
            raise Halt("creation_evidence")
        if expected == "existing" and (path != "/vendors" or data["commit_attempted"]):
            raise Halt("existing_evidence")
        data["state"], data["outcome"] = "COMPLETE", expected
        store.save("actor_completed", {"outcome": expected})
        return expected
    if tool == "handoff":
        data["state"], data["outcome"], data["reason"] = "HANDOFF", "handoff", decision.arguments["reason"]
        store.save("operator_handoff", {"reason": data["reason"]})
        return "handoff"
    raise Halt("unknown_action")
