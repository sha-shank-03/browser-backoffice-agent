"""Trusted browser gate adds ReviewV2 without changing frozen v1 sources."""
from queue import Queue, Empty
import subprocess
import sys
from threading import Thread

from backoffice.browser import BrowserController, PortalProcess, ROOT
from backoffice.domain import FIELDS, digest
from .protocol import Halt
from .state import make_review


class SemanticPortalProcess(PortalProcess):
    def __enter__(self):
        self.stderr_handle = (self.database.parent / "portal-v2-stderr.log").open("a", encoding="utf-8")
        self.process = subprocess.Popen([sys.executable, "-m", "industry_backoffice.fixture", "--db", str(self.database.resolve())],
                                        cwd=ROOT, stdout=subprocess.PIPE, stderr=self.stderr_handle, text=True)
        lines = Queue()
        Thread(target=lambda: lines.put(self.process.stdout.readline()), daemon=True).start()
        try:
            self.origin = lines.get(timeout=10).strip()
            from .protocol import ModelConfig
            ModelConfig("local_double", "fixture/local-double-v1", self.origin + "/v1/chat/completions").validate()
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise Halt("portal_startup") from None


class V2Browser(BrowserController):
    def _block(self, route, request, reason):
        from urllib.parse import urlparse
        path = urlparse(request.url).path
        allowed = {"/login", "/vendors", "/vendors/new", "/vendors/validation", "/vendors/review", "/vendors/detail", "/session/open", "/vendors/draft", "/vendors/ack", "/vendors/commit"}
        detail = {"method": request.method if request.method in {"GET", "POST"} else "OTHER",
                  "path": path if path in allowed else "outside_allowlist", "reason": reason}
        self.blocked.append(detail)
        self.store.save("route_blocked", detail)
        route.abort("blockedbyclient")

    def observe(self):
        # Zero automatic inference retries and no read retry inherited from v1 here.
        return self._observe_once()

    def read_review(self):
        draft = super().read_review()
        target = self.page.locator("[data-target-identity]")
        if target.count() != 1 or target.get_attribute("data-target-identity") != self.store.data["target_identity"]:
            raise Halt("target_identity_changed")
        form = self.page.locator('form[action="/vendors/commit"]')
        if form.count() != 1:
            raise Halt("commit_form")
        pairs = form.locator("input").evaluate_all("els => els.map(el => [el.name, el.value])")
        actual = dict(pairs)
        if (len(pairs) != len(actual) or set(actual) != set(FIELDS) | {"draft_id", "revision", "csrf"}
                or not actual["csrf"] or {f: actual[f] for f in FIELDS} != draft["values"]
                or actual["draft_id"] != draft["draft_id"] or actual["revision"] != str(draft["revision"])):
            raise Halt("review_payload")
        return make_review(self.store.data["task_id"], self.store.data["request"], draft,
                           self.store.data["target_identity"], digest(actual))

    def arm_and_submit(self, review):
        if digest(self.read_review()) != digest(review):
            raise Halt("payload_changed_before_dispatch")
        return super().arm_and_submit(review)
