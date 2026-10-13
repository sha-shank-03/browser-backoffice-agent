"""Both policies use this collector; every trusted gate is inherited unchanged."""
from pathlib import Path
from diagnostic_eval.browser import DiagnosticBrowser
from fresh_eval.browser import SELECTOR

EXTRACTOR = Path(__file__).with_name("collector.js").read_text(encoding="utf-8").strip()


class DetailsBrowser(DiagnosticBrowser):
    def _controls(self):
        return self.page.locator(SELECTOR).evaluate_all(EXTRACTOR)
