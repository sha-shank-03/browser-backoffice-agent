from copy import deepcopy
from urllib.parse import urlencode

from supplier_contract_tests.fixtures import REQUEST,authored_fixture,observation
from supplier_contract_tests.pure_support import PureTestCase
from supplier_sandbox.common import ContractError,canonical,sha
from supplier_sandbox.gate import MemoryJournal,SAVE_PATH,SupplierGate,public_observation,resolve_request_proposal


class GateTests(PureTestCase):
    def setUp(self):
        super().setUp()
        self.profile,self.evidence = authored_fixture()
        self.observation = observation(self.profile)
        self.journal = MemoryJournal()
        self.gate = SupplierGate(self.profile,REQUEST,"fixture-task",self.evidence,self.journal)

    def args(self, *, doc=None, action="Save", **extra):
        serialized = self.observation["serialized_doc"] if doc is None else canonical(doc)
        return ["POST",self.profile["origin"]+SAVE_PATH,"application/x-www-form-urlencoded",
                urlencode({"doc":serialized,"action":action,**extra}).encode(),self.observation["context"],self.observation]

    def approved(self):
        review = self.gate.review(self.observation)
        self.gate.approve_injected(sha(review),now=100)
        return review

    def test_complete_review_binds_profile_request_session_revision_and_payload(self):
        review = self.approved()
        self.assertEqual(review["source_values"],REQUEST)
        self.assertEqual(review["profile_sha256"],sha(self.profile))
        self.assertEqual(review["full_document"]["supplier_type"],"Company")
        checked = self.gate.inspect_injected_save(*self.args(),now=101)
        self.assertTrue(checked["would_allow_injected_shape"])
        self.assertFalse(checked["actual_dispatch_enabled"])
        self.assertFalse(self.gate.state["intent_consumed"])

    def test_actual_dispatch_always_disabled_and_never_consumes_authority(self):
        self.approved()
        with self.assertRaises(ContractError) as caught:
            self.gate.dispatch_network(*self.args())
        self.assertEqual(caught.exception.code,"sandbox_dispatch_disabled")
        self.assertFalse(self.gate.state["intent_consumed"])

    def test_unapproved_wrong_digest_and_expired_save_fail(self):
        self.gate.review(self.observation)
        with self.assertRaises(ContractError):
            self.gate.inspect_injected_save(*self.args(),now=101)
        with self.assertRaises(ContractError):
            self.gate.approve_injected("bad",now=100)
        self.gate.approve_injected(sha(self.gate.state["review"]),now=100)
        with self.assertRaises(ContractError):
            self.gate.inspect_injected_save(*self.args(),now=401)
        with self.assertRaises(ContractError):
            self.gate.inspect_injected_save(*self.args(),now=400)

    def test_revision_observation_session_csrf_and_schema_drift_fail(self):
        self.approved()
        for key,value in (("revision",2),("id","new-observation")):
            args = self.args()
            args[-1] = {**self.observation,key:value}
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*args,now=101)
        for key,value in (("session_epoch","changed"),("csrf_sha256","a"*64),("schema_sha256","b"*64),("profile_sha256","c"*64)):
            args = self.args()
            args[-2] = {**self.observation["context"],key:value}
            args[-1] = {**self.observation,"context":args[-2]}
            with self.subTest(key=key),self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*args,now=101)
        self.assertFalse(self.gate.state["intent_consumed"])

    def test_only_new_supplier_post_savedocs_save_is_eligible(self):
        self.approved()
        for method in ("GET","PUT","DELETE"):
            args = self.args()
            args[0] = method
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*args,now=101)
        for path in ("/api/resource/Supplier","/api/method/frappe.client.insert","/api/method/frappe.client.delete",SAVE_PATH+"?run_method=delete"):
            args = self.args()
            args[1] = self.profile["origin"]+path
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*args,now=101)
        for action in ("Submit","Update","Cancel","Amend"):
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*self.args(action=action),now=101)

    def test_wrong_target_existing_name_or_creation_flags_fail(self):
        self.approved()
        doc = deepcopy(self.gate.state["review"]["full_document"])
        for key,value in (("doctype","Contact"),("name","SUP-2026-00001"),("__islocal",0),("docstatus",1),("owner","another-principal")):
            with self.subTest(key=key),self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*self.args(doc={**doc,key:value}),now=101)

    def test_extra_rpc_doc_fields_and_changed_defaults_fail(self):
        self.approved()
        for key,value in (("cmd","frappe.client.delete"),("doctype","Supplier"),("api_key","SECRET-MARKER")):
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*self.args(**{key:value}),now=101)
        doc = self.gate.state["review"]["full_document"]
        for key,value in (("flags",{"ignore_permissions":True}),("__newname","existing"),("email_id","native@contact.example"),
                          ("supplier_type","Individual"),("accounts",[{"account":"Cash"}]),("custom_extra",1)):
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*self.args(doc={**doc,key:value}),now=101)

    def test_duplicate_form_arguments_and_serialization_drift_fail(self):
        self.approved()
        args = self.args()
        args[3] += b'&action=Save'
        with self.assertRaises(ContractError):
            self.gate.inspect_injected_save(*args,now=101)
        args = self.args()
        args[3] = urlencode({"action":"Save","doc":self.observation["serialized_doc"]}).encode()
        with self.assertRaises(ContractError) as caught:
            self.gate.inspect_injected_save(*args,now=101)
        self.assertEqual(caught.exception.code,"save_payload_changed")

    def test_ambiguous_consumed_save_cannot_replay_after_state_restore(self):
        self.approved()
        self.gate.consume_injected_once(*self.args(),now=101)
        self.gate.mark_injected_response(False)
        self.assertEqual(self.gate.state["outcome"],"unknown")
        restored = SupplierGate(self.profile,REQUEST,"fixture-task",self.evidence,MemoryJournal(),restored_state=self.journal.entries[-1]["state"])
        with self.assertRaises(ContractError) as caught:
            restored.consume_injected_once(*self.args(),now=102)
        self.assertEqual(caught.exception.code,"save_replay_forbidden")
        self.assertEqual(restored.state["injected_dispatch_count"],1)

    def test_received_response_is_not_a_verified_creation_claim(self):
        self.approved()
        self.gate.consume_injected_once(*self.args(),now=101)
        self.gate.mark_injected_response(True)
        self.assertEqual(self.gate.state["outcome"],"response_received")
        self.assertNotIn("created",self.gate.state.values())

    def test_restored_approval_cannot_change_review_or_consumption_binding(self):
        self.approved()
        approved = deepcopy(self.gate.state)
        variants = []
        for key,value in (("kind","human_operator"),("review_sha256","a"*64),("consumed",True),("expires_at",float("nan")),("extra","SECRET-MARKER")):
            state = deepcopy(approved)
            state["approval"][key] = value
            variants.append(state)
        state = deepcopy(approved)
        state["review"]["full_document"]["supplier_type"] = "Individual"
        variants.append(state)
        state = deepcopy(approved)
        state["intent_consumed"] = True
        variants.append(state)
        for state in variants:
            with self.assertRaises(ContractError) as caught:
                SupplierGate(self.profile,REQUEST,"fixture-task",self.evidence,MemoryJournal(),restored_state=state)
            self.assertNotIn("SECRET-MARKER",str(caught.exception))

    def test_invalid_injected_clock_cannot_bypass_expiry(self):
        review = self.gate.review(self.observation)
        for now in (float("nan"),float("inf"),-1,True,"SECRET-MARKER"):
            with self.assertRaises(ContractError):
                self.gate.approve_injected(sha(review),now=now)
        self.gate.approve_injected(sha(review),now=100)
        for now in (float("nan"),float("inf"),-1,True,"SECRET-MARKER"):
            with self.assertRaises(ContractError):
                self.gate.inspect_injected_save(*self.args(),now=now)

    def test_atomic_injected_journal_failure_prevents_consumption(self):
        self.approved()
        before = deepcopy(self.gate.state)
        def failed_commit(*args):
            raise RuntimeError("Injected journal failure")
        self.journal.commit = failed_commit
        with self.assertRaises(RuntimeError):
            self.gate.consume_injected_once(*self.args(),now=101)
        self.assertEqual(self.gate.state,before)

    def test_provider_projection_omits_host_mapping_session_and_schema(self):
        visible = public_observation(self.observation)
        self.assertEqual(set(visible),{"id","revision","controls"})
        for control in visible["controls"]:
            self.assertNotIn("field",control)
        for hidden in ("serialized_doc","csrf_sha256","principal_id","profile_sha256","field_mapping"):
            self.assertNotIn(hidden,canonical(visible))

    def test_fresh_reference_and_field_enum_copy_host_owned_link(self):
        proposal = {"tool":"choose_from_request","observation_id":self.observation["id"],"ref":"o2","field":"country"}
        copied = resolve_request_proposal(self.profile,REQUEST,self.observation,proposal,self.observation)
        self.assertEqual(copied["copied_value"],"India")
        self.assertFalse(copied["network_dispatch_enabled"])
        for mutation in ({"field":"legal_name"},{"ref":"#hidden"},{"value":"arbitrary"},{"selector":"#hidden"}):
            with self.assertRaises(ContractError):
                resolve_request_proposal(self.profile,REQUEST,self.observation,{**proposal,**mutation},self.observation)
        with self.assertRaises(ContractError):
            resolve_request_proposal(self.profile,REQUEST,self.observation,proposal,{**self.observation,"id":"new"})

    def test_redacted_events_exclude_body_principal_csrf_and_arbitrary_errors(self):
        self.approved()
        self.gate.consume_injected_once(*self.args(),now=101)
        self.gate.mark_injected_response(False)
        events = canonical([entry["event"] for entry in self.journal.entries])
        for value in (REQUEST["legal_name"],REQUEST["contact_email"],self.profile["operator_scope"]["principal_id"],"fictional-csrf-only","serialized_doc"):
            self.assertNotIn(value,events)
        args = self.args(api_key="SECRET-MARKER")
        with self.assertRaises(ContractError) as caught:
            self.gate.inspect_injected_save(*args,now=102)
        self.assertNotIn("SECRET-MARKER",str(caught.exception))

    def test_profile_or_immutable_request_drift_fails(self):
        self.gate.request["country"] = "GB"
        with self.assertRaises(ContractError):
            self.gate.review(self.observation)
        self.gate.request = deepcopy(REQUEST)
        self.gate.profile["site_id"] = "other"
        with self.assertRaises(ContractError):
            self.gate.review(self.observation)

    def test_malformed_json_duplicate_keys_and_oversize_fail(self):
        for raw in ('{"doctype":"Supplier","doctype":"Contact"}', '"'+'x'*32768+'"', '['*14+'0'+']'*14):
            with self.assertRaises(ContractError):
                self.gate.review({**self.observation,"serialized_doc":raw})
