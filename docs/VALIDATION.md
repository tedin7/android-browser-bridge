# Verified validation — 2026-10-11

## Real browser integration

Executed `python3 test_firefox.py` on the tablet's Linux/PRoot environment using
Firefox **140.16.0 ESR** and a freshly created temporary browser profile.
The real extension was loaded with Mozilla `web-ext` in that isolated profile.
An automated test-only bootstrap paired it with the packaged stdio MCP and
enabled control over a generated local fixture. No user browser profiles,
cookies, stored passwords, browsing history or existing tabs were used.

Passed:
- One-use pairing and live device polling.
- Real `tabs` and `read` via Firefox extension APIs.
- DOM click that changed the fixture page's text.
- Input fill with quotes and Unicode, with real input event handling.
- CSS selectors returned by `read`.
- Scroll, activate, open, reload and close.
- Device revocation.

The test used the packaged MCP over actual JSON-RPC stdio, authenticated HTTP
between the broker and extension, and actual Firefox APIs. It was not the earlier
mock-browser test. It does not establish Android-native Firefox compatibility,
background reliability, consent UX, marketplace acceptance, or a Mozilla signature.

## Version 0.2.0 expanded real Firefox verification

The rebuilt packaged MCP and resident extension passed the fixture suite on real
Firefox Linux: all 29 fixed operations, forms, keyboard editing, hidden/disabled/
readonly/covered/ambiguous errors, stale references, frame targeting, open shadow
DOM, semantic locators, large-DOM pagination, PNG screenshot bytes, coordinate
clicks and dragging, navigation history and batch failure boundaries.

Two concurrent JSON-RPC requests verified that reading page B completes before
page A's 1.2-second element wait times out. Mocked scheduler/transport tests also
verified same-page FIFO, global barriers, maximum four executing commands,
disabling queued work, and immediate result delivery during a waiting long poll.

## Version 0.2.0 measured desktop latency

Measured 12 sequential samples per operation using a persistent packaged MCP,
real Firefox Linux in a temporary isolated profile, authenticated loopback HTTP
and the generated interaction fixture. Aggregate results only were saved.

| Operation | Median ms | p95 ms |
| --- | ---: | ---: |
| tabs | 30.62 | 167.37 |
| read | 57.37 | 323.51 |
| locate | 29.00 | 106.97 |
| click | 24.22 | 50.14 |
| fill | 21.81 | 108.86 |
| batch (fill + inspect) | 19.12 | 29.92 |

These measurements include tool and transport latency and use a small fixture.
They are not Android measurements or a controlled cross-browser speedup claim.
Cold execution and host scheduling affect p95; larger pages need separate profiling.

## Actual Android verification of version 0.1.2

Firefox Android Nightly on the OnePlus Pad 3 was manually paired and opted in.
The persistent stdio MCP profiler passed open, tabs, read, click, fill, scroll,
activate, reload and close using only generated local fixture pages.
Twelve samples per operation measured baseline median latency: tabs 935 ms,
read 935 ms, click 935 ms, fill 940 ms; p95 approximately 1240–1255 ms.
Backend-only optimization did not improve this baseline with the old extension;
the fixed one-second browser delay remained. Version 0.2.0 removes that delay,
but its full Android suite and measured speedup remain pending installation.

## Mozilla package lint

Executed Mozilla `web-ext` 10 lint against extension version **0.2.0**.
Result: **0 errors, 0 notices, 0 warnings**.

The initial package omitted `data_collection_permissions`; this was corrected.
Minimum versions now match built-in data consent: desktop 140 and Android 142.
The manifest declares website content, browsing activity, website activity and
authentication information. An explicit privacy disclosure and local privacy
page are included in the extension; the repository includes `PRIVACY.md`.

Passing lint does not equal Mozilla signing or manual-review approval.

## Other tests

Fourteen Python tests passed, including actual HTTP authentication, device isolation,
one-use pairing, expiry, revocation, persistence and connection policy.
JavaScript tests passed with mocked WebExtension APIs, including address failover.
Earlier packaged smoke tests passed for local HTTP, direct HTTP and verified TLS
with a test certificate. They used a simulated browser.

## Current remaining work

- Upgrade Android to extension 0.2.0 and run all 29 actions plus timing comparison.
- Confirm Android network changes and suspension behavior on real devices.
- Authenticate to Mozilla AMO and submit the package for signing/review.
- Replace unsigned release links with signed artifacts only after receiving them.

No AMO submission or signing has been performed by this validation run.
