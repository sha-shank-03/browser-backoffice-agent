# ERPNext Supplier U2-A contract

`erpnext-supplier-u2a.1` is an additive, data-only contract for a future isolated ERPNext/Frappe v15 Supplier sandbox. It does not launch a browser, open a socket, load credentials, or dispatch a Save or read request. `dispatch_network()` always raises `sandbox_dispatch_disabled`; verifier input must be a closed sequence of injected replies. U2-A does not add evaluator, baseline, crash recovery, or live-model work. Accepted v1/U1 code and manifests remain unchanged.

The example profile uses `https://supplier-sandbox.invalid` and fictional principals, links, schema metadata, and configuration. It is unprovisioned. Its schema hash describes an authored fixture; it is not evidence of a genuine site or a server metadata export.

## Pinned primary evidence

Public version-15 research on 2026-10-12 found ERPNext 15.122.0 at `bfd8100d42162048248b7b947f2e21fdf7999a91` and Frappe 15.122.0 at `b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4`. These pins are the researched example, not an assertion that a future site runs them. The exact URLs, retrieval times, raw body SHA-256 values, and version findings are in `sandbox_profiles/erpnext-v15-sources.json`. Any site profile must name its actual patch versions and commits and undergo fresh review if they change. [ERPNext version source](https://raw.githubusercontent.com/frappe/erpnext/bfd8100d42162048248b7b947f2e21fdf7999a91/erpnext/__init__.py), [Frappe version source](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/__init__.py).

The pinned Supplier schema makes native `email_id` a read-only value fetched from the primary Contact. `payment_terms` links to Payment Terms Template and Supplier type defaults to Company. This adapter requires Company and a disclosed custom onboarding email. It creates no Contact or Address. [Supplier schema](https://raw.githubusercontent.com/frappe/erpnext/bfd8100d42162048248b7b947f2e21fdf7999a91/erpnext/buying/doctype/supplier/supplier.json).

Desk sends the document and `action=Save` to `frappe.desk.form.save.savedocs`. Frappe's generic endpoint supports broader actions and verbs, so this contract admits only an exact reviewed new Supplier POST. The client removes `cmd` when it uses the `/api/method/` route and supplies a CSRF header. New-document construction also applies user/site defaults. Actual bytes, full document shape, and defaults must therefore be checked on the authorized site before implementing dispatch. [Desk save client](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/public/js/frappe/form/save.js), [request client](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/public/js/frappe/request.js), [new-document construction](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/public/js/frappe/model/create_new.js), [savedocs server](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/desk/form/save.py).

REST detail reads can expose a `run_method` query in the v15 API. The verifier constructs only fixed Supplier list GETs and percent-encoded detail GETs with no detail query. It never accepts a generic RPC/read URL from an actor. [v15 REST source](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/api/v1.py), [list implementation](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/frappe/client.py), [REST documentation](https://docs.frappe.io/framework/user/en/api/rest).

No upstream runtime implementation is bundled. ERPNext is a separately installed GPL-3.0 server and Frappe is a separately installed MIT framework; this authored Python adapter and fictional tests use this repository's MIT license. Upstream is attributed through the source ledger. [ERPNext license](https://raw.githubusercontent.com/frappe/erpnext/bfd8100d42162048248b7b947f2e21fdf7999a91/license.txt), [Frappe license](https://raw.githubusercontent.com/frappe/frappe/b0b5b99a1d9d2cb3d54b32293d3854bf2c15f4a4/LICENSE).

## Reviewed portable profile

The profile has no credential, cookie, API key/secret, CSRF token, environment loader, or authorization-header field. Its explicit identity includes an HTTPS origin, isolated site identifier, exclusive disposable Supplier purpose, exact two-app version/commit records, raw upstream Supplier schema hash, full effective metadata hash, nonsecret reviewed site-configuration hash, and a derived server identity hash. These are comparison bindings to owner-supplied evidence, not cryptographic attestation of a running server.

| Immutable request field | Host-owned target | Required treatment |
|---|---|---|
| `legal_name` | `supplier_name` | Copy the validated fictional name |
| `registration_ref` | `custom_bb_registration_ref` | Required unique custom Data field; `DEMO-V-` request |
| `country` | `country` | Country Link; host maps IN/GB/US to reviewed records |
| `contact_email` | `custom_bb_contact_email` | Required custom Data/Email; `.example` correspondence only |
| `category` | `supplier_group` | Supplier Group Link; reviewed enabled leaf records |
| `payment_terms` | `payment_terms` | Payment Terms Template Link; reviewed NET30/NET60 records |

Custom fields must be provisioned by the site owner before this adapter operates. U2-A does not install or edit them. Native `email_id`, primary Contact/Address links and child tables remain empty. The custom email disclosure appears in the profile and exact review. [Custom Field documentation](https://docs.frappe.io/erpnext/custom-field).

The owner must supply the full effective metadata export, including all field dictionaries and document properties, in the explicit wrapper `doctype`, `fields`, `source_sha256`, `doctype_properties`. Semantic flags omitted from native metadata must be explicitly normalized to their reviewed empty/zero values, while retaining other native metadata attributes. Canonical JSON hashes bind the entire supplied wrapper; the validator does not fetch metadata and cannot establish that an owner export is complete. Changes to unused metadata also fail the existing profile hash. It rejects missing/changed mapped fields, relaxed uniqueness, native/contact email substitution, unsupported required fields, conditional mandatory fields, and incompatible naming/document properties.

`document_keys` binds the full observed new-document key set, including only seven system keys, six mapped values, and explicitly reviewed defaults. It requires a new temporary name, draft status, local/unsaved/link-trigger flags, the operator owner, Company and `SUP-.YYYY.-`. Safe optional defaults may appear only as zero flags, empty known optional values, or empty `companies`, `accounts`, `portal_users`. A profile may review a subset that matches its actual new-document export, but must not infer omitted server defaults as safe. No extra custom fields, child rows, `__newname`, permission flags, populated Contact/Address/accounting/default effects, or unreviewed form keys are admitted. An unfamiliar actual shape requires another source/profile review, not automatic acceptance.

The operator has Supplier create/read and read access to the three Link doctypes. A distinct verifier has only read access to those four doctypes. The profile allows no other write permission. Site ownership, isolation, effective permissions, reference availability, server hooks and complete visibility are owner-supplied prerequisites; these pure comparisons do not discover effective server permissions or exclude hook side effects.

## Injected observation and Save boundary

The observation seam is review-ready: a host supplies the exact serialized full document and six current visible/enabled controls, with revision, observation identity and nonsecret session/CSRF fingerprints. It is not a production Desk collector or a draft-filling integration. The public observation projects current refs, roles, labels, values and observed Link choices. It omits target-field mapping, raw document, schema, principal and session fingerprints. Proposals contain only the observed ref, observation id, request-field enum and allowed request-copy tool. Fresh host evidence must match before copying an immutable mapped value; no arbitrary selector, value or RPC is accepted.

Review binds task, validated request, site/profile/server/schema, full source/target values, full document, exact serialized document bytes, exact URL-encoded body bytes, observation revision and session context. An injected operator approval is expressly `simulated_operator`, bound to the review digest and a finite five-minute expiry. It is not human approval. The only eligible shape is POST to the exact origin plus `/api/method/frappe.desk.form.save.savedocs`, form content type, exactly `doc` and `action=Save`, exact fresh context and unchanged reviewed bytes. Alternate serialization/order also fails, even if semantically similar. Actual browser encoding may differ from this authored example and must be reconciled by explicit review before any dispatcher is added.

`consume_injected_once()` models committing consumed authority before a possible Save. Its closed in-memory journal does not perform IO or implement crash durability. Ambiguous results retain consumed authority and `unknown`; restored bound state cannot replay. A received response remains `response_received`, never a creation claim. Public events contain hashes and fixed codes/status, while private review state contains fictional full values. There is no generic RPC update/delete, create Contact/Address, accounting operation, or connection path.

## Independent bounded read comparison

The verifier uses neither gate approvals nor actor completion text. It compares closed injected read replies under the distinct verifier identity and owner-provided all-Supplier visibility. It requests at most five pages of fifty rows, at most 255 requests, at most 64 KiB per body and 256 KiB total, within twenty monotonic seconds. It fetches full known Supplier records, requires the complete allowed business surface plus server metadata, and rejects extras or nonempty effects. Empty optional native fields may read as null; this does not loosen write approval.

It advances by actual returned row count and requires an observed empty final page, even after a short page. A missing EOF, five nonempty pages, denial, duplicate names/references, truncated/oversize response, wrong URL/identity, missing fields or exhausted bound produces `unknown` with no partial records offered as complete. Permission-limited results can still conceal rows; the owner must establish complete visibility independently. The `isolated_snapshot_epoch` is an injected exclusive observation/lease marker. It is not a Frappe database snapshot, native API header or concurrency guarantee.

Before/after complete injected scans must share that scope marker. The verifier independently resolves the six immutable source values, checks all pre-existing Supplier records unchanged, unique refs, and exactly one new matching Supplier. Every success remains labeled `injected_read_api_contract`, `external_site_verified=false`, `database_or_cross_doctype_audit=false`. Genuine read state needs a separately authorized fetcher/site test. Claims about all database effects, hooks, Contact/Address or other doctypes need owner audit/export evidence beyond this projection.

## Validation and future batch

Run only the pure suite for this source slice:

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s supplier_contract_tests/pure -v
& ./.venv/Scripts/python.exe -m supplier_contract_tests.source_check --check
```

The 50 authored pure methods cover reproducible fictional profile export, profile/schema/reference drift, extra arguments/doc keys/defaults, authority and expiry, ambiguous non-replay, independent scope/pagination/byte/time bounds, and redacted errors/events. Each test installs guards against socket, process and Playwright creation. Retained attempts record the source stages, starting with 47 and then 49 methods; no native/browser or genuine site result is inferred.

`supplier_contract_tests/future_batch.json` specifies three future commands: a metadata check and exactly two named local-double methods. The read test captures three loopback GET replies; the Chromium test reads six controls from an authored fictional page and proves actual dispatch stays disabled. Both are unexecuted source. Their guard requires a new main lease sentinel before creating a server or browser. Requested envelope: five minutes, 768 MiB RAM, 32 MiB added disk, one Python process, one browser, one Playwright driver, one owned loopback listener, no package/browser download, model or actual-site calls, and no automatic retry. The main executor must impose timeouts, record resources including gaps, retain failures, and verify owned cleanup. An environment sentinel by itself grants no authority.

Actual-site prerequisites remain pending: isolated disposable site and owner authority; exact reviewed server/configuration/schema/new-document/wire export; preprovisioned unique reference/custom email and Link records; a main-owned operator browser session and separate securely held verifier credentials; fresh source review, a distinct genuine integration lease, and human review of the concrete Save. U2-A stops at the source/pure handoff.
