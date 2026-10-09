# Sources, dependencies and data

All portal content, vendor requests, development cases and scripted policy were authored for this fictional demonstration. They use this project's MIT license. No upstream benchmark data, job-posting text, source code, model weights or browser binary is included in the repository.

| Component | Version | License | Official source |
| --- | --- | --- | --- |
| Playwright Python | 1.63.0 | Apache-2.0 | https://pypi.org/project/playwright/1.63.0/ |
| pyee | 13.0.0 | MIT | https://pypi.org/project/pyee/13.0.0/ |
| greenlet | 3.3.2 | MIT AND PSF-2.0 | https://pypi.org/project/greenlet/3.3.2/ |
| typing-extensions | 4.15.0 | PSF-2.0 | https://pypi.org/project/typing-extensions/4.15.0/ |
| Python runtime | 3.11 | PSF and bundled notices | https://docs.python.org/3.11/license.html |
| SQLite runtime | Python-bundled; measured version in evidence | Public-domain core | https://www.sqlite.org/copyright.html |
| Chromium headless shell | Pinned Playwright-installed revision | BSD-style and bundled third-party notices | https://chromium.googlesource.com/chromium/src/+/main/LICENSE |
| actions/checkout | v6.1.0 | MIT | https://github.com/actions/checkout/releases/tag/v6.1.0 |
| actions/setup-python | v6.3.0 | MIT | https://github.com/actions/setup-python/releases/tag/v6.3.0 |

Dependency installers retain their bundled license/notice files. Do not strip those notices if redistributing packages or browser binaries. `requirements.lock` covers permitted Windows x64 and Linux x64 wheels with official versioned PyPI SHA-256 hashes. Browser downloads use Playwright's official installer; this lock does not cover browser archives.

Research retrieved 2026-10-08: [Anthropic's computer-use engineering role](https://job-boards.greenhouse.io/anthropic/jobs/5238637008) illustrates employer interest in browser products, harness reliability and task-success evaluation. [Browser Use](https://github.com/browser-use/browser-use) and [WebArena](https://github.com/web-arena-x/webarena) are prior art. This project does not claim to replace those libraries or compare against their published scores. Employer requirements are a dated snapshot and do not imply endorsement.

Technical references: [Playwright locators](https://playwright.dev/python/docs/locators), [network interception](https://playwright.dev/python/docs/network), [browser installation](https://playwright.dev/python/docs/browsers), [Python's local HTTP server](https://docs.python.org/3.11/library/http.server.html), and [SQLite read-only URI connections](https://docs.python.org/3.11/library/sqlite3.html).

The optional stdlib provider adapter follows [Ollama's Chat API](https://docs.ollama.com/api/chat) and [tool calling protocol](https://docs.ollama.com/capabilities/tool-calling), researched 2026-10-08. No Ollama runtime or model is bundled, downloaded, or evaluated. A future user-supplied runtime/model requires its own version, digest and license record. All ten development and thirty held-out definitions, including adversarial text, are authored fiction under MIT.

The original freeze and additive acceptance harness/tests are also project-authored MIT code. Their case labels are authored engineering postconditions, not copied benchmark labels. The Windows installer also fetched its required FFmpeg revision 1011 and Winldd revision 1007 helpers. They remain ignored installer-managed tools; their binaries are not redistributed by this source repository. The installed headless shell retains `LICENSE.headless_shell`, including Chromium and bundled third-party notices. The lock pins wheels, not a complete browser/helper supply-chain manifest; preserve and review upstream notices before any binary redistribution.
