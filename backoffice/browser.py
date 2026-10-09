"""Trusted DOM tools and final-request authority outside provider output."""
from __future__ import annotations

from contextlib import AbstractContextManager
import json
from pathlib import Path
from queue import Queue, Empty
import subprocess
import sys
import time
from threading import Thread
from urllib.parse import parse_qs, urlparse
import uuid

from .domain import FIELDS, WorkflowError, digest

ROOT = Path(__file__).resolve().parents[1]


class PortalProcess(AbstractContextManager):
    def __init__(self, database: Path):
        self.database = database
        self.process = None

    def __enter__(self):
        self.stderr_handle = (self.database.parent / "portal-stderr.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, "-m", "portal", "--db", str(self.database.resolve())],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=self.stderr_handle, text=True)
        lines = Queue()
        Thread(target=lambda: lines.put(self.process.stdout.readline()), daemon=True).start()
        try:
            self.origin = lines.get(timeout=10).strip()
        except Empty as exc:
            self.__exit__(None, None, None)
            raise WorkflowError("Owned portal process did not start within 10 seconds") from exc
        if not self.origin.startswith("http://127.0.0.1:"):
            self.__exit__(None, None, None)
            raise WorkflowError("Owned portal process failed to publish a loopback URL")
        return self

    def __exit__(self, *args):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()  # Only the Popen child owned by this run.
                    self.process.wait(timeout=3)
            self.process.stdout.close()
        if hasattr(self, "stderr_handle"):
            self.stderr_handle.close()


CONTROL_EXTRACTOR = """elements => elements.map((el, index) => {
 const visible = !!(el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
 const label = el.getAttribute('aria-label') || (el.labels && el.labels.length ? el.labels[0].innerText.trim() : el.innerText.trim());
 const role = el.tagName === 'SELECT' ? 'combobox' : el.tagName === 'INPUT' ? 'textbox' : el.tagName === 'A' ? 'link' : 'button';
 return {index, visible, enabled: !el.disabled, role, label, value: el.value || '',
 options: el.tagName === 'SELECT' ? [...el.options].map(o => ({label:o.text, value:o.value})) : []};
}).filter(el => el.visible && el.enabled)"""
RECORD_EXTRACTOR = """elements => elements.filter(el => el.getClientRects().length).map(el =>
 Object.fromEntries([...el.querySelectorAll('[data-vendor-field]')].map(field => [field.dataset.vendorField, field.innerText.trim()])))"""
CONTROL_SELECTOR = "input:not([type=hidden]),select,button,a"


class BrowserController(AbstractContextManager):
    def __init__(self, origin: str, store):
        self.origin = origin
        self.store = store
        self.ticket = None
        self.blocked = []
        self.observation = None
        self.refs = {}
        self.resources = []

    def __enter__(self):
        try:
            from playwright.sync_api import sync_playwright
            self.playwright = sync_playwright().start()
            self.resources.append(self.playwright)
            self.browser = self.playwright.chromium.launch(headless=True)
            self.resources.append(self.browser)
            state_path = self.store.run_dir / "browser-state.json"
            self.context = self.browser.new_context(service_workers="block", accept_downloads=False,
                storage_state=str(state_path) if state_path.exists() else None)
            self.context.route("**/*", self._route)
            self.context.route_web_socket("**/*", lambda route: route.close())
            self.context.on("page", self._new_page)
            self.page = self.context.new_page()
            self.page.set_default_timeout(5000)
            self.page.set_default_navigation_timeout(10000)
            self.page.on("dialog", lambda dialog: dialog.dismiss())
            self.page.goto(self.origin + self.store.data["resume_path"])
            return self
        except Exception as exc:
            self.__exit__(None, None, None)
            raise WorkflowError(f"Browser startup failed: {exc}") from exc

    def _new_page(self, page):
        # The initial page is allowed; later pages are outside this single-page workflow.
        if hasattr(self, "page"):
            page.close()

    def __exit__(self, *args):
        if hasattr(self, "context"):
            try:
                self.context.storage_state(path=str(self.store.run_dir / "browser-state.json"))
            except Exception:
                pass
        for resource in reversed(self.resources):
            try:
                resource.stop() if hasattr(resource, "stop") else resource.close()
            except Exception:
                pass
        self.resources = []

    def _block(self, route, request, reason):
        detail = {"method": request.method, "path": urlparse(request.url).path, "reason": reason}
        self.blocked.append(detail)
        self.store.save("route_blocked", detail)
        route.abort("blockedbyclient")

    def _route(self, route, request):
        url = urlparse(request.url)
        if f"{url.scheme}://{url.netloc}" != self.origin:
            return self._block(route, request, "outside_owned_origin")
        paths = {"/login", "/vendors", "/vendors/new", "/vendors/validation", "/vendors/review", "/vendors/detail"}
        if request.method == "GET" and url.path in paths:
            return route.continue_()
        if request.method == "POST" and url.path in {"/vendors/draft", "/vendors/ack"} and self.store.data.get("commit_attempted"):
            return self._block(route, request, "consumed_authority_read_only_reconciliation")
        if request.method == "POST" and url.path in {"/session/open", "/vendors/draft", "/vendors/ack"}:
            return route.continue_()
        if request.method == "POST" and url.path == "/vendors/commit":
            try:
                pairs = parse_qs(request.post_data or "", keep_blank_values=True, strict_parsing=True)
                if any(len(values) != 1 for values in pairs.values()):
                    raise ValueError("duplicate field")
                actual = {key: values[0] for key, values in pairs.items()}
            except ValueError:
                return self._block(route, request, "malformed_commit")
            approval = self.store.data.get("approval") or {}
            if (not self.ticket or actual != self.ticket["form"] or self.store.data["state"] != "SUBMITTING"
                    or not self.store.data.get("commit_attempted") or self.store.data.get("commit_dispatched")
                    or not approval.get("consumed") or approval.get("digest") != self.ticket["digest"]
                    or digest(self.store.data.get("review")) != self.ticket["digest"]
                    or approval.get("expires_at", 0) < time.time()
                    or (self.store.run_dir / "cancel.request").exists()):
                return self._block(route, request, "commit_not_armed_or_body_changed")
            ticket = self.ticket
            self.ticket = None  # Consume before forwarding; a second request is blocked.
            self.store.data["commit_dispatched"] = True
            self.store.save("commit_dispatched", {"approval_digest": ticket["digest"], "body_hash": digest(actual)})
            return route.continue_()
        return self._block(route, request, "route_or_method_not_allowed")

    def _controls(self):
        return self.page.locator(CONTROL_SELECTOR).evaluate_all(CONTROL_EXTRACTOR)

    def observe(self):
        # Retry only read operations; form submissions and clicks are never replayed.
        from playwright.sync_api import Error as BrowserError
        for attempt in range(3):
            try:
                return self._observe_once()
            except BrowserError:
                if attempt == 2 or self.store.data.get("commit_attempted"):
                    raise
                delay = (0.25, 0.5)[attempt]
                self.store.save("precommit_read_retry", {"attempt": attempt + 1, "backoff_seconds": delay})
                time.sleep(delay)

    def _observe_once(self):
        controls = self._controls()
        self.refs = {f"c{item['index']}": item for item in controls}
        public_controls = [{**{k: v for k, v in item.items() if k not in {"index", "visible", "enabled"}}, "ref": f"c{item['index']}"} for item in controls]
        obs = {"id": uuid.uuid4().hex, "url": self.page.url, "title": self.page.title(),
               "text": self.page.locator("body").aria_snapshot(), "controls": public_controls,
               "records": self.page.locator("[data-vendor-record]").evaluate_all(RECORD_EXTRACTOR)}
        if len(json.dumps(obs).encode()) > 24 * 1024:
            raise WorkflowError("Observation exceeds 24 KiB")
        self.signature = digest({"url": self.page.url, "controls": controls})
        self.observation = obs
        url = urlparse(self.page.url)
        self.store.data["resume_path"] = url.path + ("?" + url.query if url.query else "")
        return obs

    def resolve(self, ref):
        current = digest({"url": self.page.url, "controls": self._controls()})
        if ref not in self.refs or current != self.signature:
            raise WorkflowError("Stale or unknown control reference; reobserve")
        entry = self.refs[ref]
        # Duplicate accessible labels are not arbitrarily disambiguated in this MVP.
        if sum(c["label"] == entry["label"] and c["role"] == entry["role"] for c in self.refs.values()) != 1:
            raise WorkflowError("Ambiguous accessible control")
        return self.page.locator(CONTROL_SELECTOR).nth(entry["index"]), entry

    def interact(self, decision, request):
        locator, entry = self.resolve(decision.arguments["ref"])
        tool = decision.tool
        if tool == "fill_from_request":
            if entry["role"] != "textbox":
                raise WorkflowError("Fill requires a visible textbox")
            locator.fill(request[decision.arguments["field"]])
        elif tool == "choose_from_request":
            value = request[decision.arguments["field"]]
            if entry["role"] != "combobox" or value not in {o["value"] for o in entry["options"]}:
                raise WorkflowError("Choice must match an observed option")
            locator.select_option(value)
        else:
            if entry["role"] not in {"button", "link"}:
                raise WorkflowError("Click requires a visible button/link")
            before = len(self.blocked)
            try:
                # Fixture clicks are HTML form/link navigation. Register the wait
                # before clicking so observations cannot race the old document.
                with self.page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
                    locator.click()
            except Exception as exc:
                if len(self.blocked) > before:
                    raise WorkflowError("Browser request blocked by external authority gate") from exc
                raise
            if len(self.blocked) > before:
                raise WorkflowError("Browser request blocked by external authority gate")

    def read_review(self):
        if urlparse(self.page.url).path != "/vendors/review":
            raise WorkflowError("Review requires the real portal review page")
        section = self.page.locator("[data-review]")
        if section.count() != 1:
            raise WorkflowError("Missing or ambiguous review contract")
        records = section.locator("[data-vendor-record]").evaluate_all(RECORD_EXTRACTOR)
        if len(records) != 1 or set(records[0]) != set(FIELDS):
            raise WorkflowError("Incomplete displayed review values")
        return {"draft_id": section.get_attribute("data-draft-id"),
                "revision": int(section.get_attribute("data-revision")),
                "session_id": section.get_attribute("data-session-id"), "values": records[0]}

    def refresh_review(self):
        # Trusted freshness check immediately before consuming approval.
        self.page.reload(wait_until="domcontentloaded")
        self.observe()
        return self.read_review()

    def arm_and_submit(self, review):
        # Fixed read-only inspection of the portal-specific HTML contract, never a provider tool.
        form = self.page.locator('form[action="/vendors/commit"]')
        pairs = form.locator("input").evaluate_all("els => els.map(el => [el.name, el.value])")
        actual = dict(pairs)
        expected_keys = set(FIELDS) | {"draft_id", "revision", "csrf"}
        if len(pairs) != len(actual) or set(actual) != expected_keys or not actual["csrf"]:
            raise WorkflowError("Unexpected commit form structure")
        if {f: actual[f] for f in FIELDS} != review["values"] or actual["draft_id"] != review["draft_id"] or actual["revision"] != str(review["revision"]):
            raise WorkflowError("Actual form body differs from approved review")
        self.ticket = {"form": actual, "digest": digest(review)}
        try:
            with self.page.expect_navigation(wait_until="domcontentloaded", timeout=10000):
                form.get_by_role("button", name="Submit vendor", exact=True).click()
        finally:
            self.ticket = None
