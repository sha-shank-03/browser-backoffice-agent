"""Injected observation/review/save contract. It cannot dispatch HTTP or browser work."""
from copy import deepcopy
import math
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse

from .common import ContractError, bounded_text, bytes_sha, canonical, exact_keys, hash_text, sha, strict_json, closed_errors
from .profile import MAPPING, SYSTEM_KEYS, mapped_values, preflight, validate_profile

SAVE_PATH = "/api/method/frappe.desk.form.save.savedocs"
CONTEXT_KEYS = {"site_id", "profile_sha256", "server_identity_sha256", "schema_sha256", "session_epoch", "principal_id", "csrf_sha256"}
OBSERVATION_KEYS = {"id", "revision", "context", "serialized_doc", "controls"}
CONTROL_KEYS = {"ref", "field", "role", "label", "value", "visible", "enabled", "options"}
STATE_KEYS = {"schema_version", "profile_sha256", "task_id", "request_sha256", "review", "approval", "intent_consumed", "injected_dispatch_count", "outcome"}
REVIEW_KEYS = {"schema_version","contract_version","action","task_id","request_sha256","profile_sha256","site_id","origin",
               "source_values","target_values","full_document","serialized_doc_sha256","wire_sha256","context","revision",
               "observation_sha256","email_storage_disclosure"}


def finite_time(value):
    if type(value) not in (int,float) or not math.isfinite(value) or value < 0:
        raise ContractError("invalid_approval_time")
    return value


def context_check(profile, context):
    exact_keys(context, CONTEXT_KEYS, "observation_context")
    expected = {"site_id":profile["site_id"], "profile_sha256":sha(profile),
                "server_identity_sha256":profile["server_identity_sha256"],
                "schema_sha256":profile["effective_schema_sha256"], "principal_id":profile["operator_scope"]["principal_id"]}
    if any(context[key] != value for key,value in expected.items()):
        raise ContractError("observation_identity_drift")
    bounded_text(context["session_epoch"], "session_epoch")
    hash_text(context["csrf_sha256"])


def validate_document(profile, request, document, principal):
    exact_keys(document, profile["document_keys"], "document_shape")
    if (document["doctype"] != "Supplier" or document["owner"] != principal
            or type(document["docstatus"]) is not int or document["docstatus"] != 0
            or any(type(document[key]) is not int or document[key] != 1 for key in ("__islocal","__unsaved","__run_link_triggers"))
            or not isinstance(document["name"],str) or not re.fullmatch(r"new-supplier-[a-z0-9-]{1,80}",document["name"])):
        raise ContractError("new_supplier_required")
    expected = {**profile["document_defaults"], **mapped_values(profile,request)}
    if any(canonical(document[key]) != canonical(value) for key,value in expected.items()):
        raise ContractError("business_payload_mismatch")
    return document


@closed_errors
def inspect_observation(profile, request, raw):
    exact_keys(raw, OBSERVATION_KEYS, "observation_keys")
    bounded_text(raw["id"], "observation_id")
    if type(raw["revision"]) is not int or raw["revision"] < 1:
        raise ContractError("observation_revision")
    context_check(profile,raw["context"])
    if not isinstance(raw["serialized_doc"],str):
        raise ContractError("serialized_document")
    document = strict_json(raw["serialized_doc"],32768)
    validate_document(profile,request,document,raw["context"]["principal_id"])
    controls = raw["controls"]
    if not isinstance(controls,list) or len(controls) != 6:
        raise ContractError("observation_controls")
    seen_fields, seen_refs = set(), set()
    expected = mapped_values(profile,request)
    for control in controls:
        exact_keys(control,CONTROL_KEYS,"control_keys")
        bounded_text(control["ref"],"observed_reference",80)
        bounded_text(control["label"],"observed_label",120)
        field = control["field"]
        if (field not in MAPPING or field in seen_fields or control["ref"] in seen_refs
                or control["visible"] is not True or control["enabled"] is not True
                or control["role"] != ("link_combobox" if field in {"country","category","payment_terms"} else "textbox")
                or control["value"] != expected[MAPPING[field]]):
            raise ContractError("observed_control_contract")
        if (not isinstance(control["options"],list) or any(not isinstance(o,str) or len(o)>120 for o in control["options"])
                or (field in {"country","category","payment_terms"} and control["value"] not in control["options"])
                or len(canonical(control["options"]).encode())>4096):
            raise ContractError("observed_link_option")
        seen_fields.add(field)
        seen_refs.add(control["ref"])
    return deepcopy(raw)


def public_observation(raw):
    # Raw document names, target mapping/schema, operator identity and CSRF fingerprint stay private.
    return {"id":raw["id"], "revision":raw["revision"], "controls":[
        {k:deepcopy(control[k]) for k in ("ref","role","label","value","options")} for control in raw["controls"]]}


@closed_errors
def resolve_request_proposal(profile, request, observation, proposal, fresh_observation):
    inspect_observation(profile,request,observation)
    inspect_observation(profile,request,fresh_observation)
    exact_keys(proposal,{"tool","observation_id","ref","field"},"proposal_keys")
    if sha(observation) != sha(fresh_observation) or proposal["observation_id"] != fresh_observation["id"]:
        raise ContractError("stale_observed_reference")
    controls = [c for c in fresh_observation["controls"] if c["ref"] == proposal["ref"]]
    if len(controls) != 1 or proposal["field"] not in MAPPING or controls[0]["field"] != proposal["field"]:
        raise ContractError("request_field_reference")
    tool = "choose_from_request" if controls[0]["role"] == "link_combobox" else "fill_from_request"
    if proposal["tool"] != tool:
        raise ContractError("request_tool_role")
    value = mapped_values(profile,request)[MAPPING[proposal["field"]]]
    if tool == "choose_from_request" and value not in controls[0]["options"]:
        raise ContractError("unobserved_link_choice")
    return {"ref":controls[0]["ref"], "copied_value":value, "network_dispatch_enabled":False}


class MemoryJournal:
    """Injected atomic journal double; no filesystem, network, process or crash implementation."""
    def __init__(self):
        self.entries = []

    def commit(self,event,state):
        self.entries.append({"event":deepcopy(event),"state":deepcopy(state)})


class SupplierGate:
    @closed_errors
    def __init__(self, profile, request, task_id, evidence, journal, *, restored_state=None):
        self.profile = validate_profile(profile)
        preflight(self.profile,evidence)
        self.request = deepcopy(request)
        mapped_values(self.profile,self.request)
        bounded_text(task_id,"task_id")
        if type(journal) is not MemoryJournal:
            raise ContractError("injected_journal_required")
        self.journal = journal
        initial = {"schema_version":1,"profile_sha256":sha(self.profile),"task_id":task_id,"request_sha256":sha(self.request),
                   "review":None,"approval":None,"intent_consumed":False,"injected_dispatch_count":0,"outcome":"not_attempted"}
        if restored_state is not None:
            exact_keys(restored_state,STATE_KEYS,"restored_state")
            if any(canonical(restored_state[k]) != canonical(initial[k]) for k in ("schema_version","profile_sha256","task_id","request_sha256")):
                raise ContractError("restored_state_binding")
            if (type(restored_state["intent_consumed"]) is not bool or type(restored_state["injected_dispatch_count"]) is not int
                    or restored_state["injected_dispatch_count"] not in (0,1) or restored_state["outcome"] not in {"not_attempted","unknown","response_received"}
                    or restored_state["injected_dispatch_count"] != int(restored_state["intent_consumed"])
                    or (restored_state["intent_consumed"] != (restored_state["outcome"] != "not_attempted"))):
                raise ContractError("restored_state_shape")
            initial = deepcopy(restored_state)
        self.state = initial
        self._state_binding()

    @closed_errors
    def _state_binding(self):
        review,approval = self.state["review"],self.state["approval"]
        if review is None:
            if approval is not None or self.state["intent_consumed"]:
                raise ContractError("restored_approval_without_review")
            return
        exact_keys(review,REVIEW_KEYS,"restored_review_shape")
        expected = {"schema_version":1,"contract_version":self.profile["contract_version"],"action":"new_supplier_savedocs_Save",
                    "task_id":self.state["task_id"],"request_sha256":sha(self.request),"profile_sha256":sha(self.profile),
                    "site_id":self.profile["site_id"],"origin":self.profile["origin"],"source_values":self.request,
                    "target_values":mapped_values(self.profile,self.request),"email_storage_disclosure":self.profile["email_storage_disclosure"]}
        if any(canonical(review[key]) != canonical(value) for key,value in expected.items()):
            raise ContractError("restored_review_binding")
        context_check(self.profile,review["context"])
        validate_document(self.profile,self.request,review["full_document"],review["context"]["principal_id"])
        if type(review["revision"]) is not int or review["revision"] < 1:
            raise ContractError("restored_review_binding")
        for key in ("serialized_doc_sha256","wire_sha256","observation_sha256"):
            hash_text(review[key])
        if approval is None:
            if self.state["intent_consumed"]:
                raise ContractError("restored_consumption_without_approval")
            return
        exact_keys(approval,{"review_sha256","expires_at","kind","consumed"},"restored_approval_shape")
        finite_time(approval["expires_at"])
        if (approval["review_sha256"] != sha(review) or approval["kind"] != "simulated_operator"
                or type(approval["consumed"]) is not bool or approval["consumed"] != self.state["intent_consumed"]):
            raise ContractError("restored_approval_binding")

    def _binding(self):
        if self.state["profile_sha256"] != sha(self.profile) or self.state["request_sha256"] != sha(self.request):
            raise ContractError("runtime_profile_or_request_drift")
        self._state_binding()

    def _save(self, kind, new_state, **metadata):
        allowed = {"review_sha256","payload_sha256","wire_sha256","status","code"}
        if set(metadata) - allowed:
            raise ContractError("event_metadata")
        event = {"kind":kind, "contract_version":self.profile["contract_version"], "evidence_kind":"injected_pure_contract",
                 "site_id_sha256":sha(self.profile["site_id"]),"profile_sha256":sha(self.profile),**metadata}
        self.journal.commit(event,new_state)
        self.state = new_state  # Only after the injected journal accepts the complete state/event.

    def review(self, observation):
        self._binding()
        if self.state["intent_consumed"] or self.state["approval"]:
            raise ContractError("save_authority_already_consumed")
        observation = inspect_observation(self.profile,self.request,observation)
        body = urlencode({"doc":observation["serialized_doc"],"action":"Save"}).encode()
        review = {"schema_version":1,"contract_version":self.profile["contract_version"],"action":"new_supplier_savedocs_Save",
                  "task_id":self.state["task_id"],"request_sha256":sha(self.request),"profile_sha256":sha(self.profile),
                  "site_id":self.profile["site_id"],"origin":self.profile["origin"],"source_values":deepcopy(self.request),
                  "target_values":mapped_values(self.profile,self.request),"full_document":strict_json(observation["serialized_doc"]),
                  "serialized_doc_sha256":bytes_sha(observation["serialized_doc"].encode()),"wire_sha256":bytes_sha(body),
                  "context":deepcopy(observation["context"]),"revision":observation["revision"],"observation_sha256":sha(observation),
                  "email_storage_disclosure":self.profile["email_storage_disclosure"]}
        next_state = {**deepcopy(self.state),"review":review}
        self._save("review_created",next_state,review_sha256=sha(review),payload_sha256=sha(review["full_document"]))
        return deepcopy(review)

    def approve_injected(self, review_digest, *, now=None):
        self._binding()
        now = finite_time(time.time() if now is None else now)
        if not self.state["review"] or self.state["approval"] or self.state["intent_consumed"] or review_digest != sha(self.state["review"]):
            raise ContractError("approval_binding")
        next_state = deepcopy(self.state)
        next_state["approval"] = {"review_sha256":review_digest,"expires_at":now+300,"kind":"simulated_operator","consumed":False}
        self._save("simulated_operator_approval",next_state,review_sha256=review_digest)

    def inspect_injected_save(self, method, url, content_type, body, context, fresh_observation, *, now=None):
        self._binding()
        now = finite_time(time.time() if now is None else now)
        if self.state["intent_consumed"] or self.state["injected_dispatch_count"]:
            raise ContractError("save_replay_forbidden")
        review, approval = self.state["review"],self.state["approval"]
        if (not review or not approval or approval["consumed"] or approval["expires_at"] <= now
                or approval["review_sha256"] != sha(review)):
            raise ContractError("unapproved_or_expired_save")
        if method != "POST" or url != self.profile["origin"] + SAVE_PATH or content_type != "application/x-www-form-urlencoded":
            raise ContractError("save_route_or_action")
        context_check(self.profile,context)
        fresh = inspect_observation(self.profile,self.request,fresh_observation)
        if context != review["context"] or sha(fresh) != review["observation_sha256"]:
            raise ContractError("stale_revision_session_or_profile")
        if not isinstance(body,bytes) or len(body) > 65536:
            raise ContractError("save_body_bound")
        try:
            pairs = parse_qsl(body.decode("utf-8"),strict_parsing=True,keep_blank_values=True)
            args = dict(pairs)
        except (UnicodeError,ValueError):
            raise ContractError("save_form_body") from None
        if len(pairs) != 2 or len(args) != 2 or set(args) != {"doc","action"} or args["action"] != "Save":
            raise ContractError("save_argument_shape")
        validate_document(self.profile,self.request,strict_json(args["doc"],32768),context["principal_id"])
        if (bytes_sha(body) != review["wire_sha256"] or bytes_sha(args["doc"].encode()) != review["serialized_doc_sha256"]
                or args["doc"] != fresh["serialized_doc"]):
            raise ContractError("save_payload_changed")
        return {"would_allow_injected_shape":True,"actual_dispatch_enabled":False,"review_sha256":sha(review)}

    def consume_injected_once(self, *args, **kwargs):
        checked = self.inspect_injected_save(*args,**kwargs)
        next_state = deepcopy(self.state)
        next_state["intent_consumed"] = True
        next_state["approval"]["consumed"] = True
        # Unknown until separate read-only reconciliation; zero network dispatch actually occurs.
        next_state["outcome"] = "unknown"
        next_state["injected_dispatch_count"] = 1
        self._save("simulated_single_save_intent",next_state,review_sha256=checked["review_sha256"],wire_sha256=self.state["review"]["wire_sha256"])
        return checked

    def mark_injected_response(self, received):
        self._binding()
        if not self.state["intent_consumed"] or type(received) is not bool:
            raise ContractError("response_state")
        next_state = deepcopy(self.state)
        next_state["outcome"] = "response_received" if received else "unknown"
        self._save("simulated_save_response",next_state,status=next_state["outcome"])

    def dispatch_network(self, *args, **kwargs):
        raise ContractError("sandbox_dispatch_disabled")
