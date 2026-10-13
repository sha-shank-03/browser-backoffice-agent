"""Authored future read-only HTTP double; NOT an ERPNext site test."""
import unittest
from urllib.parse import urlsplit
from urllib.request import build_opener,ProxyHandler

from supplier_contract_tests.fixtures import REQUEST,authored_fixture,read_source,scope,supplier_record
from supplier_contract_tests.future.support import loopback_server
from supplier_sandbox.verify import InjectedReply,InjectedReadSource,scan,verify_one_new


class LocalDoubleTests(unittest.TestCase):
    def test_bounded_supplier_reads_capture_exact_urls_and_empty_eof(self):
        profile,_ = authored_fixture()
        record = supplier_record(profile)
        scripted = read_source(profile,[record])
        captured = []
        with loopback_server(replies=scripted.replies) as server:
            opener = build_opener(ProxyHandler({}))
            for planned in scripted.replies:
                parsed = urlsplit(planned.expected_url)
                path = parsed.path + ("?"+parsed.query if parsed.query else "")
                with opener.open(server["origin"]+path,timeout=2) as response:
                    body = response.read(65537)
                    self.assertLessEqual(len(body),65536)
                    captured.append(InjectedReply(planned.expected_url,planned.scope,body,response.status))
            self.assertEqual(len(server["seen"]),3)
            self.assertEqual(server["blocked_writes"],[])
            self.assertEqual(server["remaining"],[])
        before = scan(profile,scope(profile),read_source(profile,[]))
        after = scan(profile,scope(profile),InjectedReadSource(tuple(captured)))
        self.assertEqual(after["code"],"complete_empty_eof_observed")
        result = verify_one_new(profile,REQUEST,before,after)
        self.assertTrue(result["one_exact_new_supplier"])
        self.assertFalse(result["external_site_verified"])
