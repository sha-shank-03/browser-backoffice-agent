from copy import deepcopy
from dataclasses import replace

from supplier_contract_tests.fixtures import REQUEST,authored_fixture,scope,supplier_record,read_source
from supplier_contract_tests.pure_support import PureTestCase
from supplier_sandbox.common import canonical
from supplier_sandbox.verify import InjectedReply,InjectedReadSource,detail_url,list_url,scan,verify_one_new


class VerificationTests(PureTestCase):
    def setUp(self):
        super().setUp()
        self.profile,self.evidence = authored_fixture()
        self.scope = scope(self.profile)
        self.record = supplier_record(self.profile)

    def report(self,records):
        return scan(self.profile,self.scope,read_source(self.profile,records))

    def test_empty_complete_state_requires_observed_empty_page(self):
        report = self.report([])
        self.assertEqual(report["status"],"verified")
        self.assertTrue(report["complete"])
        self.assertEqual(report["records"],[])
        self.assertEqual(report["requests"],1)
        self.assertFalse(report["external_site_verified"])

    def test_actual_read_dispatch_disabled_and_arbitrary_fetch_callbacks_rejected(self):
        for source in (None,lambda *args:self.fail("Network callback invoked")):
            report = scan(self.profile,self.scope,source)
            self.assertEqual(report["status"],"unknown")
            self.assertEqual(report["code"],"readonly_network_dispatch_disabled")
            self.assertEqual(report["requests"],0)

    def test_one_exact_new_supplier_preserves_unrelated_record(self):
        old = supplier_record(self.profile,{**REQUEST,"registration_ref":"DEMO-V-OLD","legal_name":"Existing Fiction"},name="SUP-OLD")
        before = self.report([old])
        after = self.report([old,self.record])
        report = verify_one_new(self.profile,REQUEST,before,after)
        self.assertEqual(report["status"],"verified")
        self.assertTrue(report["one_exact_new_supplier"])
        self.assertFalse(report["database_or_cross_doctype_audit"])

    def test_short_page_without_empty_eof_remains_unknown(self):
        report = scan(self.profile,self.scope,read_source(self.profile,[self.record],eof=False))
        self.assertEqual(report["status"],"unknown")
        self.assertFalse(report["complete"])
        self.assertIsNone(report["records"])

    def test_service_page_cap_uses_actual_returned_length_and_empty_eof(self):
        second = supplier_record(self.profile,{**REQUEST,"registration_ref":"DEMO-V-SECOND"},name="SUP-SECOND")
        source = read_source(self.profile,[],pages=[[self.record],[second]])
        report = scan(self.profile,self.scope,source)
        self.assertTrue(report["complete"])
        self.assertEqual(report["pages"],3)
        self.assertEqual(report["requests"],5)
        self.assertEqual(source.requests[2]["url"],list_url(self.profile,1))

    def test_five_nonempty_pages_cannot_be_labeled_complete(self):
        groups = [[supplier_record(self.profile,{**REQUEST,"registration_ref":f"DEMO-V-P{i}"},name=f"SUP-P{i}")] for i in range(5)]
        source = read_source(self.profile,[],pages=groups,eof=False)
        report = scan(self.profile,self.scope,source)
        self.assertEqual(report["status"],"unknown")
        self.assertEqual(report["code"],"pagination_incomplete_at_bound")
        self.assertEqual(report["pages"],5)

    def test_repeated_name_or_reference_detects_unstable_pagination(self):
        for second in (self.record,{**self.record,"name":"OTHER"}):
            report = scan(self.profile,self.scope,read_source(self.profile,[],pages=[[self.record],[second]]))
            self.assertEqual(report["status"],"unknown")
            self.assertEqual(report["code"],"duplicate_or_unstable_pagination")

    def test_read_reply_identity_scope_or_snapshot_changes_fail(self):
        for changed in (replace(self.scope,site_id="other"),replace(self.scope,principal_id="other"),
                        replace(self.scope,isolated_snapshot_epoch="other")):
            source = InjectedReadSource((InjectedReply(list_url(self.profile,0),changed,b'{"data":[]}'),))
            report = scan(self.profile,self.scope,source)
            self.assertEqual(report["code"],"read_identity_or_snapshot_changed")
            self.assertFalse(report["complete"])

    def test_operator_scope_cannot_substitute_for_independent_verifier(self):
        report = scan(self.profile,replace(self.scope,principal_id=self.profile["operator_scope"]["principal_id"]),read_source(self.profile,[]))
        self.assertEqual(report["code"],"verifier_scope")
        self.assertEqual(report["requests"],0)

    def test_missing_extra_or_unapproved_record_fields_do_not_pass(self):
        missing = deepcopy(self.record)
        del missing["email_id"]
        variants = [missing,{**self.record,"extra_business_field":"secret"},{**self.record,"doctype":"Contact"},
                    {**self.record,"accounts":[{"account":"Cash"}]},{**self.record,"email_id":"native@contact.example"}]
        for record in variants:
            report = self.report([record])
            self.assertEqual(report["status"],"unknown")
            self.assertFalse(report["complete"])

    def test_null_empty_optional_value_is_read_representation_only(self):
        report = self.report([{**self.record,"email_id":None}])
        self.assertTrue(report["complete"])
        self.assertEqual(report["records"][0]["email_id"],None)

    def test_body_page_and_total_byte_bounds_are_not_truncation_success(self):
        giant = InjectedReadSource((InjectedReply(list_url(self.profile,0),self.scope,b'x'*65537),))
        self.assertEqual(scan(self.profile,self.scope,giant)["code"],"read_body_bound")
        many = [{"name":f"SUP-{i}","custom_bb_registration_ref":f"DEMO-V-{i}"} for i in range(51)]
        source = InjectedReadSource((InjectedReply(list_url(self.profile,0),self.scope,canonical({"data":many}).encode()),))
        self.assertEqual(scan(self.profile,self.scope,source)["code"],"pagination_page_shape")
        second = supplier_record(self.profile,{**REQUEST,"registration_ref":"DEMO-V-TWO"},name="SUP-TWO")
        original = read_source(self.profile,[],pages=[[self.record],[second]])
        padded = tuple(replace(r,body=r.body+b' '*(65536-len(r.body))) for r in original.replies[:-1])+(original.replies[-1],)
        report = scan(self.profile,self.scope,InjectedReadSource(padded))
        self.assertEqual(report["code"],"read_total_body_bound")
        self.assertFalse(report["complete"])

    def test_total_monotonic_read_time_bound(self):
        moments = iter([0.0,0.0,21.0])
        report = scan(self.profile,self.scope,read_source(self.profile,[]),clock=lambda:next(moments))
        self.assertEqual(report["code"],"read_time_or_request_bound")
        self.assertEqual(report["requests"],1)

    def test_errors_and_denials_do_not_echo_raw_body(self):
        source = InjectedReadSource((InjectedReply(list_url(self.profile,0),self.scope,b'SECRET-MARKER',status=403),))
        report = scan(self.profile,self.scope,source)
        self.assertEqual(report["code"],"read_http_unknown")
        self.assertNotIn("SECRET-MARKER",canonical(report))
        malformed = InjectedReadSource((InjectedReply(list_url(self.profile,0),self.scope,b'{"data":[],"data":[]}'),))
        self.assertEqual(scan(self.profile,self.scope,malformed)["code"],"duplicate_json_key")

    def test_list_detail_mismatch_and_route_injection_are_rejected(self):
        source = read_source(self.profile,[self.record])
        wrong = replace(source.replies[1],body=canonical({"data":{**self.record,"name":"WRONG"}}).encode())
        injected = InjectedReadSource((source.replies[0],wrong,source.replies[2]))
        self.assertEqual(scan(self.profile,self.scope,injected)["code"],"list_detail_mismatch")
        encoded = detail_url(self.profile,"SUP?run_method=delete/../name")
        self.assertNotIn("?run_method",encoded)
        self.assertIn("%3F",encoded)
        self.assertIn("%2F",encoded)

    def test_false_completion_extra_supplier_or_changed_baseline_is_mismatch(self):
        empty = self.report([])
        self.assertEqual(verify_one_new(self.profile,REQUEST,empty,empty)["status"],"mismatch")
        extra = supplier_record(self.profile,{**REQUEST,"registration_ref":"DEMO-V-EXTRA"},name="SUP-EXTRA")
        self.assertEqual(verify_one_new(self.profile,REQUEST,empty,self.report([self.record,extra]))["status"],"mismatch")
        old = supplier_record(self.profile,{**REQUEST,"registration_ref":"DEMO-V-OLD"},name="SUP-OLD")
        changed = {**old,"country":"United Kingdom"}
        self.assertEqual(verify_one_new(self.profile,REQUEST,self.report([old]),self.report([changed,self.record]))["status"],"mismatch")

    def test_incomplete_before_after_or_changed_read_scope_stays_unknown(self):
        before,after = self.report([]),self.report([self.record])
        self.assertEqual(verify_one_new(self.profile,REQUEST,{**before,"complete":False},after)["status"],"unknown")
        self.assertEqual(verify_one_new(self.profile,REQUEST,before,{**after,"scope_sha256":"different"})["status"],"unknown")
