"""Accidental native execution guard; the sentinel is not authorization evidence."""
import os
from pathlib import Path

SENTINEL = "u2b-development-or-capability-explicit-main-lease"


def require_lease(*,browser=True):
    if os.environ.get("BB_U2B_EVALUATION_LEASE") != SENTINEL:
        raise ValueError("separate_main_u2b_lease_required")
    if browser:
        expected=Path(__file__).resolve().parents[1]/".cache/ms-playwright"
        if Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH","missing")).resolve()!=expected.resolve() or not expected.is_dir():
            raise ValueError("existing_pinned_browser_cache_required")
