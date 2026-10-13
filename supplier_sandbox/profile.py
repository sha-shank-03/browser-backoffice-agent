"""Portable nonsecret site/schema/reference contract; no credential or site loader."""
from copy import deepcopy
import re
from urllib.parse import urlparse

from backoffice.domain import FIELDS, validate_request
from . import CONTRACT_VERSION
from .common import ContractError, bounded_text, canonical, exact_keys, hash_text, sha, closed_errors

MAPPING = {"legal_name":"supplier_name", "registration_ref":"custom_bb_registration_ref",
           "country":"country", "contact_email":"custom_bb_contact_email",
           "category":"supplier_group", "payment_terms":"payment_terms"}
REFERENCE_FIELDS = {"country":"Country", "category":"Supplier Group", "payment_terms":"Payment Terms Template"}
SYSTEM_KEYS = {"doctype", "name", "docstatus", "__islocal", "__unsaved", "owner", "__run_link_triggers"}
ZERO_FIELDS = {"is_transporter", "is_internal_supplier", "disabled", "warn_rfqs", "warn_pos",
               "prevent_rfqs", "prevent_pos", "on_hold", "is_frozen",
               "allow_purchase_invoice_creation_without_purchase_order", "allow_purchase_invoice_creation_without_purchase_receipt"}
EMPTY_FIELDS = {"default_bank_account", "tax_id", "tax_category", "tax_withholding_category", "represents_company",
                "image", "language", "default_currency", "default_price_list", "hold_type", "release_date",
                "website", "supplier_details", "supplier_primary_contact", "mobile_no", "email_id",
                "primary_address", "supplier_primary_address"}
EMPTY_TABLES = {"companies", "accounts", "portal_users"}
SAFE_DEFAULTS = {**{k:0 for k in sorted(ZERO_FIELDS)}, **{k:"" for k in sorted(EMPTY_FIELDS)},
                 **{k:[] for k in sorted(EMPTY_TABLES)}, "supplier_type":"Company", "naming_series":"SUP-.YYYY.-"}
PROFILE_KEYS = {"schema_version", "contract_version", "site_id", "origin", "isolated", "purpose",
                "versions", "upstream_supplier_schema_sha256", "effective_schema_sha256", "server_identity_sha256",
                "site_config_sha256", "field_mapping", "reference_maps", "document_defaults", "document_keys",
                "operator_scope", "verifier_scope", "dispatch_enabled", "email_storage_disclosure"}


def server_fingerprint(profile):
    return sha({k:profile[k] for k in ("site_id", "origin", "versions", "site_config_sha256")})


@closed_errors
def validate_profile(raw):
    exact_keys(raw, PROFILE_KEYS, "profile_keys")
    if (type(raw["schema_version"]) is not int or raw["schema_version"] != 1
            or raw["contract_version"] != CONTRACT_VERSION or raw["isolated"] is not True
            or raw["purpose"] != "exclusive-disposable-Supplier-sandbox" or raw["dispatch_enabled"] is not False):
        raise ContractError("profile_scope")
    if raw["email_storage_disclosure"] != "custom_bb_contact_email stores onboarding correspondence only; creates no Contact or Address.":
        raise ContractError("email_disclosure")
    bounded_text(raw["site_id"], "site_identity")
    try:
        url = urlparse(raw["origin"])
        if (url.scheme != "https" or not url.hostname or url.username or url.password or url.path
                or url.query or url.fragment or raw["origin"] != "https://" + url.netloc
                or url.port not in (None,443) or not re.fullmatch(r"[a-z0-9.-]+", url.hostname)):
            raise ContractError("profile_origin")
    except ValueError:
        raise ContractError("profile_origin") from None
    exact_keys(raw["versions"], {"erpnext", "frappe"}, "server_versions")
    for version in raw["versions"].values():
        exact_keys(version, {"version", "commit"}, "server_versions")
        if not isinstance(version["version"], str) or not re.fullmatch(r"15\.\d+\.\d+", version["version"]):
            raise ContractError("server_versions")
        hash_text(version["commit"], 40)
    for key in ("upstream_supplier_schema_sha256", "effective_schema_sha256", "site_config_sha256", "server_identity_sha256"):
        hash_text(raw[key])
    if raw["server_identity_sha256"] != server_fingerprint(raw) or raw["field_mapping"] != MAPPING:
        raise ContractError("profile_binding")
    exact_keys(raw["reference_maps"], REFERENCE_FIELDS, "reference_maps")
    sources = {"country":{"IN","GB","US"}, "category":{"Office supplies","IT services"}, "payment_terms":{"NET30","NET60"}}
    for key, values in sources.items():
        exact_keys(raw["reference_maps"][key], values, "reference_maps")
        if len(set(raw["reference_maps"][key].values())) != len(values):
            raise ContractError("reference_maps")
        for name in raw["reference_maps"][key].values():
            bounded_text(name, "reference_value", 120)
    defaults = raw["document_defaults"]
    if (not isinstance(defaults, dict) or set(defaults) - set(SAFE_DEFAULTS)
            or any(canonical(value) != canonical(SAFE_DEFAULTS[key]) for key, value in defaults.items())
            or defaults.get("supplier_type") != "Company" or defaults.get("naming_series") != "SUP-.YYYY.-"):
        raise ContractError("unsafe_defaults")
    expected_keys = SYSTEM_KEYS | set(MAPPING.values()) | set(defaults)
    if (not isinstance(raw["document_keys"], list) or any(not isinstance(k,str) for k in raw["document_keys"])
            or len(raw["document_keys"]) != len(expected_keys) or set(raw["document_keys"]) != expected_keys):
        raise ContractError("document_shape")
    for role in ("operator_scope", "verifier_scope"):
        scope = raw[role]
        exact_keys(scope, {"principal_id", "permissions", "supplier_visibility"}, "scope_keys")
        bounded_text(scope["principal_id"], "scope_principal")
        expected = {"Supplier":["create","read"] if role == "operator_scope" else ["read"],
                    "Country":["read"], "Supplier Group":["read"], "Payment Terms Template":["read"]}
        if scope["permissions"] != expected or scope["supplier_visibility"] != "all-in-isolated-site":
            raise ContractError("permission_scope")
    if raw["operator_scope"]["principal_id"] == raw["verifier_scope"]["principal_id"]:
        raise ContractError("separate_principals_required")
    if len(canonical(raw).encode()) > 32768:
        raise ContractError("profile_bound")
    return deepcopy(raw)


@closed_errors
def validate_effective_schema(profile, schema):
    if not isinstance(schema, dict) or sha(schema) != profile["effective_schema_sha256"]:
        raise ContractError("schema_drift")
    exact_keys(schema, {"doctype", "fields", "source_sha256", "doctype_properties"}, "schema_keys")
    if schema["doctype"] != "Supplier" or schema["source_sha256"] != profile["upstream_supplier_schema_sha256"]:
        raise ContractError("schema_target")
    if not isinstance(schema["fields"], list):
        raise ContractError("schema_fields")
    properties = schema["doctype_properties"]
    if (not isinstance(properties,dict) or properties.get("autoname") != "naming_series:"
            or any(properties.get(key,0) != 0 for key in ("is_submittable","issingle","istable","is_virtual"))
            or len(canonical(schema).encode()) > 65536):
        raise ContractError("doctype_properties")
    fields = {}
    for field in schema["fields"]:
        if not isinstance(field,dict) or not {"fieldname", "fieldtype", "options", "reqd", "unique", "read_only", "fetch_from", "is_custom"} <= set(field):
            raise ContractError("schema_fields")
        bounded_text(field["fieldname"], "schema_field_name")
        if field["fieldname"] in fields or any(type(field[key]) is not int or field[key] not in (0,1) for key in ("reqd","unique","read_only","is_custom")):
            raise ContractError("schema_fields")
        fields[field["fieldname"]] = field
    specifications = {
        "supplier_name": ("Data","",1,0), "country":("Link","Country",0,0),
        "supplier_group":("Link","Supplier Group",0,0), "payment_terms":("Link","Payment Terms Template",0,0),
        "custom_bb_registration_ref":("Data","",1,1), "custom_bb_contact_email":("Data","Email",1,0),
        "supplier_type":("Select","Company\nIndividual\nPartnership",1,0),
    }
    for key, (kind, options, required, unique) in specifications.items():
        field = fields.get(key)
        if (not field or field["fieldtype"] != kind or field["options"] != options or field["reqd"] != required
                or field["unique"] != unique or field["read_only"] or field["fetch_from"]
                or field.get("hidden",0) != 0
                or field["is_custom"] != int(key.startswith("custom_"))):
            raise ContractError("required_field_contract")
    if any(f["reqd"] and key not in profile["document_keys"] for key,f in fields.items()):
        raise ContractError("unsupported_required_field")
    if any(f.get("mandatory_depends_on") for f in fields.values()):
        raise ContractError("conditional_required_field")
    for key, value in profile["document_defaults"].items():
        field = fields.get(key)
        if not field or (isinstance(value,list) and field["fieldtype"] != "Table"):
            raise ContractError("default_schema_shape")
    return fields


def mapped_values(profile, request):
    try:
        request = validate_request(request)
    except Exception:
        raise ContractError("request_contract") from None
    return {target: profile["reference_maps"][source][request[source]] if source in REFERENCE_FIELDS else request[source]
            for source,target in MAPPING.items()}


@closed_errors
def preflight(raw_profile, evidence):
    profile = validate_profile(raw_profile)
    exact_keys(evidence, {"site_id","origin","versions","site_config_sha256","effective_schema","reference_records",
                          "operator_scope","verifier_scope","wire_contract","isolated"}, "preflight_evidence")
    for key in ("site_id","origin","versions","site_config_sha256","operator_scope","verifier_scope","isolated"):
        if canonical(evidence[key]) != canonical(profile[key]):
            raise ContractError("identity_or_scope_drift")
    validate_effective_schema(profile, evidence["effective_schema"])
    exact_keys(evidence["reference_records"], REFERENCE_FIELDS, "reference_evidence")
    for source, doctype in REFERENCE_FIELDS.items():
        records = evidence["reference_records"][source]
        if (not isinstance(records,list) or len(records) != len(profile["reference_maps"][source])
                or any(not isinstance(r,dict) or set(r) != {"doctype","name","enabled","is_group"} for r in records)
                or {r["name"] for r in records} != set(profile["reference_maps"][source].values())
                or any(r["doctype"] != doctype or r["enabled"] is not True or r["is_group"] is not False for r in records)):
            raise ContractError("reference_evidence")
    if evidence["wire_contract"] != {"method":"POST","path":"/api/method/frappe.desk.form.save.savedocs",
                                    "content_type":"application/x-www-form-urlencoded","argument_keys":["doc","action"],"action":"Save"}:
        raise ContractError("wire_contract_unreviewed")
    return {"profile_sha256":sha(profile), "site_id":profile["site_id"], "schema_sha256":profile["effective_schema_sha256"],
            "server_identity_sha256":profile["server_identity_sha256"], "dispatch_enabled":False}
