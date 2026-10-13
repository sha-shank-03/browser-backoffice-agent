"""Authored fictional contract data; no ERPNext site or upstream executable code."""
from copy import deepcopy

from supplier_sandbox import CONTRACT_VERSION
from supplier_sandbox.common import canonical, sha
from supplier_sandbox.profile import MAPPING, REFERENCE_FIELDS, SAFE_DEFAULTS, SYSTEM_KEYS, server_fingerprint
from supplier_sandbox.verify import ReadScope, InjectedReply, InjectedReadSource, list_url, detail_url

REQUEST = {"legal_name":"Cedar U2A Fiction", "registration_ref":"DEMO-V-U2A", "country":"IN",
           "contact_email":"orders@cedar-u2a.example", "category":"IT services", "payment_terms":"NET30"}
UPSTREAM_SCHEMA = "ad5f518acc5c2f95a5d42114451291e8b9f5c61b11e5d62b1ff0cce3560bcd39"
VERSIONS = {"erpnext":{"version":"15.122.0","commit":"bfd8100d42162048248b7b947f2e21fdf7999a91"},
            "frappe":{"version":"15.122.0","commit":"b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4"}}


def authored_fixture():
    def field(name,kind="Data",options="",reqd=0,unique=0,read_only=0,fetch_from="",is_custom=0):
        return dict(fieldname=name,fieldtype=kind,options=options,reqd=reqd,unique=unique,read_only=read_only,fetch_from=fetch_from,is_custom=is_custom)
    fields = [field("supplier_name",reqd=1),field("country","Link","Country"),field("supplier_group","Link","Supplier Group"),
              field("payment_terms","Link","Payment Terms Template"),field("custom_bb_registration_ref",reqd=1,unique=1,is_custom=1),
              field("custom_bb_contact_email",options="Email",reqd=1,is_custom=1),
              field("supplier_type","Select","Company\nIndividual\nPartnership",reqd=1)]
    for name,value in SAFE_DEFAULTS.items():
        if name == "supplier_type":
            continue
        fields.append(field(name,"Table" if isinstance(value,list) else "Check" if type(value) is int else "Select" if name=="naming_series" else "Data"))
    # Fictional complete metadata projection: real owner must supply its actual full metadata/default export.
    schema = {"doctype":"Supplier","fields":fields,"source_sha256":UPSTREAM_SCHEMA,
              "doctype_properties":{"autoname":"naming_series:","is_submittable":0,"issingle":0,"istable":0,"is_virtual":0,"fixture_only":True}}
    reference_maps = {"country":{"IN":"India","GB":"United Kingdom","US":"United States"},
                      "category":{"Office supplies":"Demo Office Supplies","IT services":"Demo IT Services"},
                      "payment_terms":{"NET30":"Demo Net 30","NET60":"Demo Net 60"}}
    base_permissions = {"Country":["read"],"Supplier Group":["read"],"Payment Terms Template":["read"]}
    profile = {"schema_version":1,"contract_version":CONTRACT_VERSION,"site_id":"unprovisioned-fictional-supplier-site",
               "origin":"https://supplier-sandbox.invalid","isolated":True,"purpose":"exclusive-disposable-Supplier-sandbox",
               "versions":deepcopy(VERSIONS),"upstream_supplier_schema_sha256":UPSTREAM_SCHEMA,"effective_schema_sha256":sha(schema),
               "site_config_sha256":sha({"fixture_only":True,"server_hooks_verified":False}),"server_identity_sha256":"0"*64,
               "field_mapping":dict(MAPPING),"reference_maps":reference_maps,"document_defaults":deepcopy(SAFE_DEFAULTS),
               "document_keys":sorted(SYSTEM_KEYS | set(MAPPING.values()) | set(SAFE_DEFAULTS)),
               "operator_scope":{"principal_id":"fictional-supplier-operator","permissions":{"Supplier":["create","read"],**base_permissions},"supplier_visibility":"all-in-isolated-site"},
               "verifier_scope":{"principal_id":"fictional-supplier-verifier","permissions":{"Supplier":["read"],**base_permissions},"supplier_visibility":"all-in-isolated-site"},
               "dispatch_enabled":False,"email_storage_disclosure":"custom_bb_contact_email stores onboarding correspondence only; creates no Contact or Address."}
    profile["server_identity_sha256"] = server_fingerprint(profile)
    evidence = {k:deepcopy(profile[k]) for k in ("site_id","origin","versions","site_config_sha256","operator_scope","verifier_scope","isolated")}
    evidence["effective_schema"] = schema
    evidence["reference_records"] = {source:[{"doctype":doctype,"name":name,"enabled":True,"is_group":False} for name in mapping.values()]
        for source,doctype in REFERENCE_FIELDS.items() for mapping in [reference_maps[source]]}
    evidence["wire_contract"] = {"method":"POST","path":"/api/method/frappe.desk.form.save.savedocs", "content_type":"application/x-www-form-urlencoded","argument_keys":["doc","action"],"action":"Save"}
    return profile,evidence


def mapped(profile,request=REQUEST):
    return {target:profile["reference_maps"][source][request[source]] if source in REFERENCE_FIELDS else request[source] for source,target in MAPPING.items()}


def observation(profile,request=REQUEST):
    context = {"site_id":profile["site_id"],"profile_sha256":sha(profile),"server_identity_sha256":profile["server_identity_sha256"],
               "schema_sha256":profile["effective_schema_sha256"],"session_epoch":"fictional-session-epoch-1", "principal_id":profile["operator_scope"]["principal_id"],"csrf_sha256":sha("fictional-csrf-only")}
    document = {**deepcopy(profile["document_defaults"]),**mapped(profile,request),"doctype":"Supplier","name":"new-supplier-u2a-fiction",
                "docstatus":0,"__islocal":1,"__unsaved":1,"owner":context["principal_id"],"__run_link_triggers":1}
    labels = {"legal_name":"Supplier Name","registration_ref":"Demo Registration Reference","country":"Country",
              "contact_email":"Onboarding Email (custom)","category":"Supplier Group","payment_terms":"Default Payment Terms Template"}
    controls = [{"ref":f"o{i}","field":source,"role":"link_combobox" if source in REFERENCE_FIELDS else "textbox",
                 "label":labels[source],"value":document[target],"visible":True,"enabled":True,
                 "options":list(profile["reference_maps"][source].values()) if source in REFERENCE_FIELDS else []}
                for i,(source,target) in enumerate(MAPPING.items())]
    return {"id":"fixture-observation-1","revision":1,"context":context,"serialized_doc":canonical(document),"controls":controls}


def scope(profile):
    return ReadScope(profile["site_id"],sha(profile),profile["verifier_scope"]["principal_id"],"all-in-isolated-site","fictional-exclusive-observation-epoch")


def supplier_record(profile,request=REQUEST,name="SUP-2026-00001"):
    return {**deepcopy(SAFE_DEFAULTS),**mapped(profile,request),"name":name,"doctype":"Supplier","docstatus":0,
            "owner":"fictional-supplier-operator","creation":"2026-10-12 10:00:00.000000", "modified":"2026-10-12 10:00:00.000000","modified_by":"fictional-supplier-operator"}


def read_source(profile,records,pages=None,*,eof=True):
    replies = []
    offset = 0
    grouped = pages if pages is not None else [records] if records else []
    for group in grouped:
        projection = [{"name":r["name"],"custom_bb_registration_ref":r["custom_bb_registration_ref"]} for r in group]
        replies.append(InjectedReply(list_url(profile,offset),scope(profile),canonical({"data":projection}).encode()))
        for record in group:
            replies.append(InjectedReply(detail_url(profile,record["name"]),scope(profile),canonical({"data":record}).encode()))
        offset += len(group)
    if eof:
        replies.append(InjectedReply(list_url(profile,offset),scope(profile),b'{"data":[]}'))
    return InjectedReadSource(tuple(replies))
