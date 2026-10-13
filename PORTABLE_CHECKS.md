# Standalone upgrade checks — version standalone-unit-packaging.1

The frozen historical diagnostic/DETAILS tests assumed local saved evaluation
artifacts. Main's clean-index export exposed five diagnostic test errors on
13 October 2026. This additive correction keeps every older source/test/manifest
byte and historical failure intact. Use the explicit public package below from
a fresh checkout. Historical native report/source commands still require their
original captures and refuse absent or changed history; their checks are unchanged.

With the existing Python3.11 environment and pinned `requirements.lock` installed:

```powershell
.venv/Scripts/python.exe -B -m portable_checks source-check
.venv/Scripts/python.exe -B -m portable_checks test
.venv/Scripts/python.exe -B -m unittest portable_checks_tests -v
.venv/Scripts/python.exe -B -m portable_checks demo
```

Linux uses `.venv/bin/python`. No private coordination, saved local evaluation,
browser binary, site, credentials or model access is needed. The exact JavaScript
collector controls use the Node executable already bundled with the pinned
Playwright Python wheel. No extra runtime/dependency or browser download is added.

`test` executes the unchanged U1 unit, U2-A pure, fresh/durable evaluation,
diagnostic, DETAILS, one-slot continuation and remaining/continuation unit suites.
`--suite diagnostic_eval_tests` (or another listed suite) selects a bounded group.
No contracts are skipped. Each run supplies explicit authored synthetic history
in isolated temporary scratch, then restores all module path constants. Genuine
work roots, profiles, manifests and Git index are never changed. Actual checksum,
raw-tamper, interrupted/pending denominator, stale-reference and approval contracts
execute against those fixture bytes. Fixture generators call only pure callback
seams; SQL/socket/browser/child-actor creation is forbidden.

Synthetic42/22/7-file history shapes and219 unit pins reproduce legacy contract
inputs. They are NOT the historical first runs, database state, real approvals,
native execution, model quality or extra tasks. Opaque `.db` path fixtures explicitly
contain non-SQLite marker text and are never opened as SQL. Current-observation
policy controls are derived anew from the unchanged exact JavaScript DOM doubles.

`source-check` verifies exact prior shipping bytes and normalized new correction
hashes, including all prior
manifests and test bytes. It explicitly reports historical native artifact
verification as **not performed**. This is a separate public-source contract;
it cannot satisfy a native source/evidence gate or freeze. No historical native
manifest is regenerated or converted into a source-only success.

`demo` shows only the two unchanged policies' next decisions on authored collapsed
DETAILS controls: the baseline chooses the visible summary and the historical
local-double hands off for insufficient evidence. It performs no browser action,
HTTP request, SQL write or model inference and claims no business completion.
Original browser/approval demos and all native/source-report commands remain
available under their existing prerequisites and separate review/lease gates.

The additive `u2b-portable-source-manifest.json` versions this correction, while
the earlier manifests retain their original identities. The new portable CI job
runs these public source/unit/demo commands without a browser installation.
The extra packaging controls verify source tamper detection, scoped fixture
restoration and rejection of missing native history outside the unit context.
