"""Every pure test fails immediately on socket/process/browser creation."""
from contextlib import ExitStack
import unittest
from unittest.mock import patch


class PureTestCase(unittest.TestCase):
    def setUp(self):
        self.forbidden_calls = []
        def forbidden(*args,**kwargs):
            self.forbidden_calls.append("forbidden_socket_process_or_browser_creation")
            raise AssertionError("Pure contract test attempted socket/process/browser creation")
        self.safety = ExitStack()
        self.addCleanup(self.safety.close)
        self.addCleanup(lambda:self.assertEqual(self.forbidden_calls,[]))
        for target in ("socket.socket","socket.create_connection","subprocess.Popen","os.system","os.spawnv","os.spawnve",
                       "urllib.request.urlopen","http.client.HTTPConnection.connect","http.client.HTTPSConnection.connect",
                       "playwright.sync_api.sync_playwright","playwright.sync_api.BrowserType.launch","playwright.sync_api.BrowserType.launch_persistent_context"):
            self.safety.enter_context(patch(target,side_effect=forbidden))
