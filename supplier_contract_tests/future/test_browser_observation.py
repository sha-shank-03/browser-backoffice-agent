"""Authored future Chromium observation double; no Desk or Save dispatch."""
from copy import deepcopy
import html
import os
from pathlib import Path
import unittest

from supplier_contract_tests.fixtures import REQUEST,authored_fixture,observation
from supplier_contract_tests.future.support import loopback_server,require_lease
from supplier_sandbox.common import ContractError,sha
from supplier_sandbox.gate import MemoryJournal,SupplierGate,inspect_observation,public_observation,resolve_request_proposal


def fixture_html(observed):
    parts = ['<!doctype html><html><head><link rel="icon" href="data:,"></head><body><h1>Fictional Supplier review fixture</h1>']
    for c in observed["controls"]:
        attr = f'id="{c["ref"]}" data-field="{c["field"]}" data-role="{c["role"]}"'
        parts.append(f'<label for="{c["ref"]}">{html.escape(c["label"])}</label>')
        if c["role"] == "link_combobox":
            options = ''.join(f'<option{(" selected" if o==c["value"] else "")}>{html.escape(o)}</option>' for o in c["options"])
            parts.append(f'<select {attr}>{options}</select>')
        else:
            parts.append(f'<input {attr} value="{html.escape(c["value"],quote=True)}">')
    parts.append('</body></html>')
    return ''.join(parts).encode()


class BrowserObservationTests(unittest.TestCase):
    def test_current_dom_references_bind_review_while_dispatch_stays_disabled(self):
        require_lease()
        expected_cache = Path(__file__).resolve().parents[2] / ".cache" / "ms-playwright"
        if Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH","missing")).resolve() != expected_cache.resolve():
            self.fail("Use only the existing pinned repository browser cache")
        from playwright.sync_api import sync_playwright
        profile,evidence = authored_fixture()
        authored = observation(profile)
        rejected_requests = []
        with loopback_server(html=fixture_html(authored)) as server:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(service_workers="block")
                    def route_guard(route):
                        if route.request.method == "GET" and route.request.url == server["origin"]+"/fixture":
                            route.continue_()
                        else:
                            rejected_requests.append(route.request.method)
                            route.abort()
                    context.route("**/*",route_guard)
                    page = context.new_page()
                    page.goto(server["origin"]+"/fixture",timeout=10000)
                    controls = page.locator("input, select").evaluate_all("""els => els.map(e => ({
                        ref:e.id,field:e.dataset.field,role:e.dataset.role,label:e.labels[0].textContent,
                        value:e.value,visible:e.getClientRects().length>0,enabled:!e.disabled,
                        options:e.tagName==='SELECT'?Array.from(e.options).map(o=>o.value):[]
                    }))""")
                    fresh = {**deepcopy(authored),"controls":controls}
                    inspect_observation(profile,REQUEST,fresh)
                    gate = SupplierGate(profile,REQUEST,"future-fictional-browser",evidence,MemoryJournal())
                    review = gate.review(fresh)
                    gate.approve_injected(sha(review),now=100)
                    visible = public_observation(fresh)
                    copied = resolve_request_proposal(profile,REQUEST,fresh,
                        {"tool":"choose_from_request","observation_id":visible["id"],"ref":"o2","field":"country"},fresh)
                    self.assertEqual(copied["copied_value"],"India")
                    with self.assertRaises(ContractError) as caught:
                        gate.dispatch_network()
                    self.assertEqual(caught.exception.code,"sandbox_dispatch_disabled")
                    self.assertFalse(gate.state["intent_consumed"])
                    context.close()
                finally:
                    browser.close()
            self.assertEqual(server["seen"],["/fixture"])
            self.assertEqual(server["blocked_writes"],[])
        self.assertEqual(rejected_requests,[])
