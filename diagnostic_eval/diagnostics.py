"""Bounded fixed-category diagnostics. Never persist exception strings or UI text."""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from industry_backoffice.protocol import Halt
from . import VERSION

NAME = "evaluation-diagnostic.jsonl"
MAX_RECORDS = 82
MAX_BYTES = 131072
PATHS = {"/login", "/vendors", "/vendors/new", "/vendors/validation", "/vendors/review", "/vendors/detail"}
FIELDS = {"legal_name", "registration_ref", "country", "contact_email", "category", "payment_terms"}
TOOLS = {"fill_from_request", "choose_from_request", "click"}
ROLES = {"textbox", "combobox", "button", "link"}
TAGS = {"INPUT", "SELECT", "BUTTON", "A", "SUMMARY"}
DOM_PROBE = """el => {
 let closed=false;
 for(let p=el.parentElement;p;p=p.parentElement){
  if(p.tagName==='DETAILS'&&!p.open){
   const summary=Array.from(p.children).find(c=>c.tagName==='SUMMARY');
   if(!summary||!(summary===el||summary.contains(el))) closed=true;
  }
 }
 return {tag:el.tagName,closed_details_content:closed,
         has_client_rects:!!el.getClientRects().length,
         style_visibility_hidden:getComputedStyle(el).visibility==='hidden',
         check_visibility:typeof el.checkVisibility==='function'?el.checkVisibility():null};
}"""


def error_category(error):
    from playwright.sync_api import Error, TimeoutError as BrowserTimeout
    if isinstance(error, BrowserTimeout): return "playwright_timeout"
    if isinstance(error, Error): return "playwright_error"
    if isinstance(error, Halt): return "typed_halt"
    if isinstance(error, TimeoutError): return "builtin_timeout"
    if isinstance(error, ValueError): return "value_error"
    if isinstance(error, OSError): return "os_error"
    if isinstance(error, (KeyboardInterrupt, SystemExit)): return "interruption"
    return "unclassified_exception"


def action_metadata(browser, decision):
    arguments = decision.arguments
    item = browser.refs.get(arguments.get("ref"), {})
    index = item.get("index")
    try:
        path = urlparse(browser.page.url).path
    except Exception:
        path = None
    return {"path": path if path in PATHS else "outside_or_unavailable",
            "tool": decision.tool if decision.tool in TOOLS else "other",
            "request_field": arguments.get("field") if arguments.get("field") in FIELDS else None,
            "control_index": index if type(index) is int and 0 <= index < 4096 else None,
            "control_role": item.get("role") if item.get("role") in ROLES else None}


def safe_metadata(value):
    def member(key, allowed):
        item = value.get(key)
        return item if type(item) is str and item in allowed else None
    index = value.get("control_index")
    return {"path": member("path", PATHS) or "outside_or_unavailable", "tool": member("tool", TOOLS) or "other",
            "request_field": member("request_field", FIELDS), "control_role": member("control_role", ROLES),
            "control_index": index if type(index) is int and 0 <= index < 4096 else None}


def safe_probe(value):
    return {"probe_status": "observed" if value.get("probe_status") == "observed" else "unavailable",
            "snapshot_timing": "after_exception",
            "tag": value.get("tag") if type(value.get("tag")) is str and value.get("tag") in TAGS else None,
            **{key: value.get(key) if type(value.get(key)) is bool else None
               for key in ("closed_details_content", "has_client_rects", "style_visibility_hidden", "check_visibility")}}


def probe_control(browser, index):
    # One read-only probe after failure, bounded to 200ms; never re-resolve/click/fill.
    empty = {"probe_status": "unavailable", "tag": None, "closed_details_content": None,
             "has_client_rects": None, "style_visibility_hidden": None, "check_visibility": None}
    if index is None: return empty
    try:
        from fresh_eval.browser import SELECTOR
        result = browser.page.locator(SELECTOR).nth(index).evaluate(DOM_PROBE, timeout=200)
        if not isinstance(result, dict): return empty
        return {"probe_status": "observed", "tag": result.get("tag") if result.get("tag") in TAGS else None,
                **{key: result.get(key) if type(result.get(key)) is bool else None
                   for key in empty if key not in {"probe_status", "tag"}}}
    except Exception:
        return empty


class Writer:
    def __init__(self, run):
        self.path = Path(run) / NAME
        self.records, self.bytes = 0, 0

    def emit(self, stage, metadata, *, error=None, probe=None):
        if stage not in {"before_interact", "interaction_error"} or self.records >= MAX_RECORDS:
            return False
        record = {"schema_version": 1, "diagnostic_version": VERSION, "seq": self.records + 1,
                  "stage": stage, **safe_metadata(metadata), "exception_category": error_category(error) if error is not None else None}
        if probe is not None: record["control_probe"] = safe_probe(probe)
        payload = (json.dumps(record, sort_keys=True, allow_nan=False) + "\n").encode()
        if len(payload) > 2048 or self.bytes + len(payload) > MAX_BYTES: return False
        try:
            with self.path.open("xb" if self.records == 0 else "ab") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            self.records += 1
            self.bytes += len(payload)
            return True
        except OSError:
            return False  # Instrumentation never masks or changes the original action result.


def descriptor(run):
    path = Path(run) / NAME
    if not path.exists(): return {"status": "absent", "path": NAME}
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        return {"status": "unavailable", "path": NAME}
    payload = path.read_bytes()
    return {"status": "retained", "path": NAME, "bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
