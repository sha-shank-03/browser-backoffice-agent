"""External reviewer and fault barriers. Never exposed as acting tools."""
from contextlib import closing
import json
import sqlite3
from urllib.parse import urlparse

from backoffice.domain import Interrupted
from backoffice.providers import FixedMacroProvider, ScriptedProvider
from backoffice.runner import run


def execute(run_dir, case, agent="reactive-scripted", provider_factory=None):
    provider_type = provider_factory or {"reactive-scripted": ScriptedProvider, "fixed-macro": FixedMacroProvider}[agent]
    fired = False

    def hook(stage, store):
        nonlocal fired
        if fired:
            return
        name = case.get("barrier")
        if name == "interrupt_after_draft" and stage == "after_tool" and urlparse(store.data["resume_path"]).path in {"/vendors/review", "/vendors/validation"}:
            fired = True
            raise Interrupted("Authored orderly restart after draft navigation")
        if name == "interrupt_before_commit" and stage == "before_commit_request":
            fired = True
            raise Interrupted("Authored interruption after consumed intent before request")
        if name == "interrupt_after_commit" and stage == "after_commit":
            fired = True
            raise Interrupted("Authored restart after received commit response")
        if name in {"stale_approval", "expire_approval"} and stage == "after_approval":
            fired = True
            with closing(sqlite3.connect(run_dir / "portal.db")) as con, con:
                if name == "stale_approval":
                    con.execute("UPDATE drafts SET revision=revision+1 WHERE id=?", (store.data["review"]["draft_id"],))
                else:
                    con.execute("DELETE FROM sessions WHERE public_id=?", (store.data["review"]["session_id"],))
            store.save("fixture_barrier", {"name": name})

    reviewer = lambda review: case.get("reviewer", "approve") == "approve"
    codes = [run(run_dir, provider_type(), fixture_approval=reviewer, hook=hook)]
    if codes[-1] == 11:
        # A new runner owns a fresh portal process/browser, with persisted request/authority.
        codes.append(run(run_dir, provider_type(), fixture_approval=reviewer, hook=hook))
    (run_dir / "harness.json").write_text(json.dumps({"raw_actor_exits": codes, "restart_count": len(codes) - 1}, indent=2), encoding="utf-8")
    return codes
