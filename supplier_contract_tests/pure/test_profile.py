from copy import deepcopy
from pathlib import Path

from supplier_contract_tests.fixtures import authored_fixture
from supplier_contract_tests.pure_support import PureTestCase
from supplier_sandbox.common import ContractError, sha, strict_json
from supplier_sandbox.profile import preflight, validate_profile


class ProfileTests(PureTestCase):
    def setUp(self):
        super().setUp()
        self.profile,self.evidence = authored_fixture()

    def test_valid_injected_preflight_stays_disabled(self):
        report = preflight(self.profile,self.evidence)
        self.assertFalse(report["dispatch_enabled"])
        self.assertEqual(report["profile_sha256"],sha(self.profile))

    def test_checked_in_example_profile_matches_reproducible_fictional_evidence(self):
        path = Path(__file__).resolve().parents[2] / "sandbox_profiles/erpnext-v15-supplier.profile.example.json"
        example = strict_json(path.read_bytes(),32768)
        self.assertEqual(example,self.profile)
        self.assertTrue(example["origin"].endswith(".invalid"))
        report = preflight(example,self.evidence)
        self.assertFalse(report["dispatch_enabled"])

    def test_nonsecret_profile_rejects_credential_and_unknown_keys(self):
        for key in ("api_key","api_secret","cookie","password","headers","selector"):
            with self.subTest(key=key),self.assertRaises(ContractError) as caught:
                validate_profile({**self.profile,key:"SECRET-MARKER"})
            self.assertNotIn("SECRET-MARKER",str(caught.exception))

    def test_wrong_origin_shared_site_or_enabling_dispatch_fails(self):
        variants = [{**self.profile,"origin":origin} for origin in (
            "http://supplier-sandbox.invalid","https://secret@site.invalid","https://site.invalid?key=SECRET-MARKER",
            "https://site.invalid/", "https://site.invalid:444")]
        variants += [{**self.profile,"isolated":False},{**self.profile,"dispatch_enabled":True}]
        for value in variants:
            with self.assertRaises(ContractError):
                validate_profile(value)

    def test_site_origin_config_and_exact_version_drift_fail(self):
        for key,value in (("site_id","another-site"),("origin","https://another.invalid"),("site_config_sha256","a"*64)):
            evidence = {**self.evidence,key:value}
            with self.subTest(key=key),self.assertRaises(ContractError):
                preflight(self.profile,evidence)
        evidence = deepcopy(self.evidence)
        evidence["versions"]["frappe"]["commit"] = "f"*40
        with self.assertRaises(ContractError):
            preflight(self.profile,evidence)

    def test_schema_drift_even_in_unconsumed_metadata_is_rejected(self):
        evidence = deepcopy(self.evidence)
        evidence["effective_schema"]["fields"][0]["label"] = "Changed metadata"
        with self.assertRaises(ContractError) as caught:
            preflight(self.profile,evidence)
        self.assertEqual(caught.exception.code,"schema_drift")

    def test_unique_required_custom_reference_semantics_cannot_be_relaxed(self):
        for key,value in (("unique",0),("reqd",0),("read_only",1),("is_custom",0),("hidden",1)):
            evidence = deepcopy(self.evidence)
            field = next(f for f in evidence["effective_schema"]["fields"] if f["fieldname"]=="custom_bb_registration_ref")
            field[key] = value
            profile = {**self.profile,"effective_schema_sha256":sha(evidence["effective_schema"])}
            with self.subTest(key=key),self.assertRaises(ContractError):
                preflight(profile,evidence)

    def test_onboarding_email_is_disclosed_custom_field_not_contact(self):
        for key,value in (("fieldtype","Read Only"),("options","Contact"),("fetch_from","supplier_primary_contact.email_id")):
            evidence = deepcopy(self.evidence)
            field = next(f for f in evidence["effective_schema"]["fields"] if f["fieldname"]=="custom_bb_contact_email")
            field[key] = value
            profile = {**self.profile,"effective_schema_sha256":sha(evidence["effective_schema"])}
            with self.assertRaises(ContractError):
                preflight(profile,evidence)
        with self.assertRaises(ContractError):
            validate_profile({**self.profile,"email_storage_disclosure":"Native contact creation"})

    def test_company_and_safe_defaults_are_fixed(self):
        for key,value in (("supplier_type","Individual"),("is_internal_supplier",1),("accounts",[{"account":"Cash"}]),
                          ("companies",[{"company":"Other"}]),("portal_users",[{"user":"other"}]),("default_bank_account","Bank")):
            profile = deepcopy(self.profile)
            profile["document_defaults"][key] = value
            with self.subTest(key=key),self.assertRaises(ContractError):
                validate_profile(profile)

    def test_extra_default_and_document_keys_are_rejected(self):
        for key in ("flags","__newname","tax_certificate","purchase_invoice","contact","address"):
            profile = deepcopy(self.profile)
            profile["document_defaults"][key] = ""
            profile["document_keys"].append(key)
            with self.assertRaises(ContractError):
                validate_profile(profile)

    def test_host_reference_records_must_match_enabled_leaf_links(self):
        for key,value in (("doctype","Company"),("enabled",False),("is_group",True),("name","Unapproved Reference")):
            evidence = deepcopy(self.evidence)
            evidence["reference_records"]["category"][0][key] = value
            with self.assertRaises(ContractError):
                preflight(self.profile,evidence)

    def test_operator_verifier_are_separate_and_have_no_other_write_scope(self):
        variants = []
        same = deepcopy(self.profile)
        same["verifier_scope"]["principal_id"] = same["operator_scope"]["principal_id"]
        variants.append(same)
        for role in ("operator_scope","verifier_scope"):
            for doctype,permissions in (("Supplier",["read","write","delete"]),("Contact",["create"]),("Purchase Invoice",["create"])):
                value = deepcopy(self.profile)
                value[role]["permissions"][doctype] = permissions
                variants.append(value)
        for profile in variants:
            with self.assertRaises(ContractError):
                validate_profile(profile)

    def test_conditional_required_field_or_autoname_change_fails(self):
        for mutation in ("conditional","autoname"):
            evidence = deepcopy(self.evidence)
            if mutation == "conditional":
                evidence["effective_schema"]["fields"][0]["mandatory_depends_on"] = "eval:doc.website"
            else:
                evidence["effective_schema"]["doctype_properties"]["autoname"] = "field:supplier_name"
            profile = {**self.profile,"effective_schema_sha256":sha(evidence["effective_schema"])}
            with self.assertRaises(ContractError):
                preflight(profile,evidence)

    def test_wrong_wire_shape_and_field_mapping_fails(self):
        evidence = deepcopy(self.evidence)
        evidence["wire_contract"]["argument_keys"] = ["doc","action","cmd"]
        with self.assertRaises(ContractError):
            preflight(self.profile,evidence)
        profile = deepcopy(self.profile)
        profile["field_mapping"]["contact_email"] = "email_id"
        with self.assertRaises(ContractError):
            validate_profile(profile)

    def test_malformed_profiles_fail_with_fixed_redacted_code(self):
        for profile in ([],None,{**self.profile,"reference_maps":None},{**self.profile,"versions":{"frappe":[]}},
                        {**self.profile,"document_keys":[{"password":"SECRET-MARKER"}]}):
            with self.assertRaises(ContractError) as caught:
                validate_profile(profile)
            self.assertNotIn("SECRET-MARKER",str(caught.exception))
