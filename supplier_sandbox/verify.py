"""Data-only read verifier. No actor imports or network/credential dispatch.

An injected empty EOF page is required even after a short page. Five nonempty
pages, missing fields, unstable identity/visibility, or limits yield unknown.
"""
from copy import deepcopy
from dataclasses import dataclass
import time
from urllib.parse import quote, urlencode

from .common import ContractError, bounded_text, canonical, exact_keys, sha, strict_json
from .profile import SAFE_DEFAULTS, validate_profile

MAX_PAGES, PAGE_SIZE, MAX_BYTES, MAX_SECONDS, MAX_REQUESTS = 5, 50, 262144, 20.0, 255
TARGET_FIELDS = {"legal_name":"supplier_name", "registration_ref":"custom_bb_registration_ref", "country":"country",
                 "contact_email":"custom_bb_contact_email", "category":"supplier_group", "payment_terms":"payment_terms"}
SERVER_META = {"name","doctype","docstatus","owner","creation","modified","modified_by"}


@dataclass(frozen=True)
class ReadScope:
    site_id: str
    profile_sha256: str
    principal_id: str
    visibility: str
    isolated_snapshot_epoch: str


@dataclass(frozen=True)
class InjectedReply:
    expected_url: str
    scope: ReadScope
    body: bytes
    status: int = 200


class InjectedReadSource:
    """Closed in-memory reply sequence, not a callback that may access the network."""
    def __init__(self, replies):
        if not isinstance(replies,tuple) or any(type(r) is not InjectedReply for r in replies):
            raise ContractError("injected_replies_required")
        self.replies = replies
        self.index = 0
        self.requests = []

    def read(self, url):
        self.requests.append({"method":"GET","url":url})
        if self.index >= len(self.replies):
            raise ContractError("incomplete_injected_state")
        reply = self.replies[self.index]
        self.index += 1
        if reply.expected_url != url:
            raise ContractError("read_route_mismatch")
        return reply


def list_url(profile, offset):
    if type(offset) is not int or not 0 <= offset <= PAGE_SIZE * MAX_PAGES:
        raise ContractError("pagination_offset")
    query = {"fields":canonical(["name","custom_bb_registration_ref"]),"filters":"[]","order_by":"name asc",
             "limit_start":str(offset),"limit_page_length":str(PAGE_SIZE)}
    return profile["origin"] + "/api/resource/Supplier?" + urlencode(query)


def detail_url(profile, name):
    bounded_text(name,"supplier_record_name",140)
    return profile["origin"] + "/api/resource/Supplier/" + quote(name,safe="")


def unknown(code, *, pages=0, requests=0, body_bytes=0, records=0):
    return {"status":"unknown","complete":False,"code":code,"pages":pages,"requests":requests,
            "body_bytes":body_bytes,"records_seen":records,"records":None,"evidence_kind":"injected_read_api_contract",
            "external_site_verified":False,"database_or_cross_doctype_audit":False}


def inspect_record(profile, record):
    # Independent of write approval/normalization; inspect the full known business surface.
    if not isinstance(record,dict) or set(record) != SERVER_META | set(TARGET_FIELDS.values()) | set(SAFE_DEFAULTS):
        raise ContractError("incomplete_or_extra_supplier_fields")
    if record["doctype"] != "Supplier" or type(record["docstatus"]) is not int or record["docstatus"] != 0:
        raise ContractError("wrong_supplier_record")
    for key in SERVER_META - {"docstatus","doctype"}:
        bounded_text(record[key],"server_record_metadata",140)
    for target in TARGET_FIELDS.values():
        bounded_text(record[target],"supplier_record_value",120)
    for key,value in SAFE_DEFAULTS.items():
        actual = record[key]
        # Frappe may serialize an empty nullable value as null; nonempty/default effects are forbidden.
        if value == "" and actual is None:
            continue
        if canonical(actual) != canonical(value):
            raise ContractError("unapproved_supplier_effect")
    return deepcopy(record)


def scan(raw_profile, scope, source=None, *, clock=time.monotonic):
    pages = requests = total_bytes = 0
    records, names, references = [], set(), set()
    started = clock()
    try:
        profile = validate_profile(raw_profile)
        if (type(scope) is not ReadScope or scope.site_id != profile["site_id"] or scope.profile_sha256 != sha(profile)
                or scope.principal_id != profile["verifier_scope"]["principal_id"]
                or scope.principal_id == profile["operator_scope"]["principal_id"]
                or scope.visibility != "all-in-isolated-site"):
            raise ContractError("verifier_scope")
        bounded_text(scope.isolated_snapshot_epoch,"read_snapshot_epoch")
        if type(source) is not InjectedReadSource:
            raise ContractError("readonly_network_dispatch_disabled")

        def read(url):
            nonlocal requests,total_bytes
            if clock() - started >= MAX_SECONDS or requests >= MAX_REQUESTS:
                raise ContractError("read_time_or_request_bound")
            requests += 1
            reply = source.read(url)
            if clock() - started >= MAX_SECONDS:
                raise ContractError("read_time_or_request_bound")
            if reply.scope != scope:
                raise ContractError("read_identity_or_snapshot_changed")
            if reply.status != 200:
                raise ContractError("read_http_unknown")
            if not isinstance(reply.body,bytes) or len(reply.body)>65536:
                raise ContractError("read_body_bound")
            total_bytes += len(reply.body)
            if total_bytes > MAX_BYTES:
                raise ContractError("read_total_body_bound")
            value = strict_json(reply.body,65536)
            exact_keys(value,{"data"},"read_response_envelope")
            return value["data"]

        offset = 0
        while pages < MAX_PAGES:
            pages += 1
            page = read(list_url(profile,offset))
            if not isinstance(page,list) or len(page)>PAGE_SIZE:
                raise ContractError("pagination_page_shape")
            if not page:
                return {"status":"verified","complete":True,"code":"complete_empty_eof_observed",
                        "pages":pages,"requests":requests,"body_bytes":total_bytes,"records_seen":len(records),"records":records,
                        "scope_sha256":sha(scope.__dict__),"evidence_kind":"injected_read_api_contract","external_site_verified":False,
                        "database_or_cross_doctype_audit":False}
            for item in page:
                exact_keys(item,{"name","custom_bb_registration_ref"},"supplier_list_projection")
                bounded_text(item["name"],"supplier_record_name",140)
                bounded_text(item["custom_bb_registration_ref"],"supplier_record_reference",120)
                if item["name"] in names or item["custom_bb_registration_ref"] in references:
                    raise ContractError("duplicate_or_unstable_pagination")
                record = inspect_record(profile,read(detail_url(profile,item["name"])))
                if record["name"] != item["name"] or record["custom_bb_registration_ref"] != item["custom_bb_registration_ref"]:
                    raise ContractError("list_detail_mismatch")
                names.add(item["name"])
                references.add(item["custom_bb_registration_ref"])
                records.append(record)
            offset += len(page) # Handles a service-side page cap without silently assuming short-page EOF.
        raise ContractError("pagination_incomplete_at_bound")
    except ContractError as error:
        return unknown(error.code,pages=pages,requests=requests,body_bytes=total_bytes,records=len(records))
    except Exception:
        return unknown("invalid_or_unmeasured_read_state",pages=pages,requests=requests,body_bytes=total_bytes,records=len(records))


def verify_one_new(raw_profile, request, before, after):
    """Projected Supplier API state comparison; not a server audit or actor completion claim."""
    try:
        profile = validate_profile(raw_profile)
        if any(r.get("status") != "verified" or r.get("complete") is not True or not isinstance(r.get("records"),list) for r in (before,after)):
            return {"status":"unknown","complete":False,"code":"complete_before_after_required"}
        if before.get("scope_sha256") != after.get("scope_sha256"):
            return {"status":"unknown","complete":False,"code":"scope_or_snapshot_changed"}
        old = {r["name"]:inspect_record(profile,r) for r in before["records"]}
        new = {r["name"]:inspect_record(profile,r) for r in after["records"]}
        if len(old) != len(before["records"]) or len(new) != len(after["records"]):
            raise ContractError("duplicate_supplier_names")
        expected = {}
        exact_keys(request,TARGET_FIELDS,"verification_request")
        for source,target in TARGET_FIELDS.items():
            bounded_text(request[source],"verification_request",120)
            expected[target] = profile["reference_maps"][source][request[source]] if source in {"country","category","payment_terms"} else request[source]
        added = [r for name,r in new.items() if name not in old]
        unchanged = all(name in new and canonical(new[name]) == canonical(row) for name,row in old.items())
        refs = [r["custom_bb_registration_ref"] for r in new.values()]
        passed = (len(added)==1 and len(new)==len(old)+1 and unchanged and len(set(refs))==len(refs)
                  and all(added[0][target]==value for target,value in expected.items()))
        return {"status":"verified" if passed else "mismatch","complete":True,"one_exact_new_supplier":passed,
                "unrelated_suppliers_unchanged":unchanged,"external_site_verified":False,
                "evidence_kind":"injected_read_api_contract","database_or_cross_doctype_audit":False}
    except ContractError as error:
        return {"status":"unknown","complete":False,"code":error.code}
    except Exception:
        return {"status":"unknown","complete":False,"code":"invalid_verification_evidence"}
