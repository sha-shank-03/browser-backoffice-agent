from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from backoffice.browser import BrowserController
from backoffice.domain import digest, review_contract
from evaluation.fixtures import load_suite

ROOT = Path(__file__).resolve().parents[2]
REQUEST = load_suite()["cases"]["happy"]["request"]


class RequestGateContracts(unittest.TestCase):
    def test_valid_authority_forwards_once_and_persisted_dispatch_blocks_rearming(self):
        (ROOT / "work").mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / "work", prefix="gate-unit-") as tmp:
            review = review_contract("task", REQUEST, {"values": REQUEST, "draft_id": "draft", "session_id": "session", "revision": 1})
            form = {**REQUEST, "draft_id": "draft", "revision": "1", "csrf": "fictional-csrf"}
            store = Mock(run_dir=Path(tmp), data={"state": "SUBMITTING", "commit_attempted": True, "review": review,
                         "approval": {"consumed": True, "digest": digest(review), "expires_at": time.time() + 60}})
            browser = BrowserController("http://127.0.0.1:8000", store)
            request = Mock(url="http://127.0.0.1:8000/vendors/commit", method="POST", post_data=urlencode(form))
            first = Mock()
            browser.ticket = {"form": form, "digest": digest(review)}
            browser._route(first, request)
            first.continue_.assert_called_once()
            self.assertTrue(store.data["commit_dispatched"])
            second = Mock()
            browser.ticket = {"form": form, "digest": digest(review)}
            browser._route(second, request)
            second.continue_.assert_not_called()
            second.abort.assert_called_once()
            self.assertEqual(store.save.call_args_list[0].args[0], "commit_dispatched")

    def test_only_precommit_read_retries_are_bounded(self):
        from playwright.sync_api import Error
        store = Mock(data={"commit_attempted": False})
        browser = BrowserController("http://127.0.0.1:8000", store)
        browser._observe_once = Mock(side_effect=[Error("transient"), Error("transient"), {"id": "ok"}])
        with patch("backoffice.browser.time.sleep") as sleep:
            self.assertEqual(browser.observe(), {"id": "ok"})
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.25, 0.5])
        store.data["commit_attempted"] = True
        browser._observe_once = Mock(side_effect=Error("read failure"))
        with patch("backoffice.browser.time.sleep") as sleep, self.assertRaises(Error):
            browser.observe()
        sleep.assert_not_called()
        self.assertEqual(browser._observe_once.call_count, 1)
