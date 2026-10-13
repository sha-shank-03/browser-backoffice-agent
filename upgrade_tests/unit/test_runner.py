"""Pure runner checks with injected in-memory browser/transport objects."""
from contextlib import AbstractContextManager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backoffice.domain import canonical
from industry_backoffice.protocol import Halt, ModelConfig
from industry_backoffice.runner import execute
from industry_backoffice.state import Store
from upgrade_tests.unit.test_protocol import REQUEST, reply


class FakePage:
    def set_default_timeout(self, value):
        pass
    def set_default_navigation_timeout(self, value):
        pass


class FakePortal(AbstractContextManager):
    origin = "http://127.0.0.1:1"
    def __init__(self, *args):
        pass
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


class FakeBrowser(FakePortal):
    page = FakePage()
    def observe(self):
        return {"id": "fresh", "url": "http://127.0.0.1:1/vendors/new", "title": "Fake", "text": "authored",
                "records": [], "controls": [{"ref": "c9", "role": "textbox", "label": "Registered organisation", "value": "", "options": []}]}


class RunnerTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[2] / ".cache/u1-unit"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name))
        self.addCleanup(self.store.close)
        self.config = ModelConfig("local_double", "fixture/local-double-v1", "http://127.0.0.1:1/v1/chat/completions")
        self.store.initialize(REQUEST, "task", "target", self.config)
        self.patches = [patch("industry_backoffice.runner.SemanticPortalProcess", FakePortal),
                        patch("industry_backoffice.runner.V2Browser", FakeBrowser)]
        for mocked in self.patches:
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_transport_errors_are_never_retried_and_unknown_usage_is_persisted(self):
        for code in ("gateway_rate_limit", "gateway_server", "transport_deadline", "transport_io"):
            # Separate persisted workflow per error; these are pure injected errors, no HTTP calls.
            path = self.store.run_dir / code
            path.mkdir()
            store = Store(path)
            self.addCleanup(store.close)
            store.initialize(REQUEST, "task", "target", self.config)
            called = []
            def failed(*args, **kwargs):
                called.append(1)
                raise Halt(code, sent=None)
            with self.subTest(code=code):
                self.assertEqual(execute(store, self.config, transport=failed), 30)
                self.assertEqual(len(called), 1)
                self.assertEqual(store.data["calls"], 1)
                self.assertEqual(store.data["usage_unavailable_calls"], 1)
                self.assertIsNone(store.data["cost_inr"])
                self.assertEqual(store.data["reason"], code)
                self.assertEqual(execute(store, self.config, transport=failed), 30)
                self.assertEqual(len(called), 1)  # Halted resume does not repeat the inference.

    def test_cancel_after_response_prevents_action(self):
        def cancelled(*args):
            (self.store.run_dir / "cancel.request").touch()
            return canonical(reply()).encode()
        self.assertEqual(execute(self.store, self.config, transport=cancelled), 21)
        self.assertEqual(self.store.data["steps"], 1)
        self.assertFalse(self.store.data["commit_attempted"])

    def test_pending_inference_charges_time_and_never_calls_transport(self):
        self.store.data["pending_transport"] = {"reserved_seconds": 20, "reserved_tokens": 512}
        def forbidden(*args):
            self.fail("Ambiguous inference was replayed")
        self.assertEqual(execute(self.store, self.config, transport=forbidden), 30)
        self.assertGreaterEqual(self.store.data["active_seconds"], 20)
        self.assertEqual(self.store.data["reason"], "ambiguous_inference_requires_operator")

    def test_invalid_model_cannot_trigger_transport(self):
        config = ModelConfig("gateway", "openai/gpt-4.1-mini", "https://ai-gateway.vercel.sh/v1/chat/completions")
        def forbidden(*args):
            self.fail("Gateway inference attempted")
        with self.assertRaises(Halt) as caught:
            execute(self.store, config, transport=forbidden)
        self.assertEqual(caught.exception.code, "live_dispatch_disabled")
