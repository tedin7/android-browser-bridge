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

## Mozilla package lint

Executed Mozilla `web-ext` 10 lint against extension version **0.1.2**.
Result: **0 errors, 0 notices, 0 warnings**.

The initial package omitted `data_collection_permissions`; this was corrected.
Minimum versions now match built-in data consent: desktop 140 and Android 142.
The manifest declares website content, browsing activity, website activity and
authentication information. An explicit privacy disclosure and local privacy
page are included in the extension; the repository includes `PRIVACY.md`.

Passing lint does not equal Mozilla signing or manual-review approval.

## Other tests

Ten Python tests passed, including actual HTTP authentication, device isolation,
one-use pairing, expiry, revocation, persistence and connection policy.
JavaScript tests passed with mocked WebExtension APIs, including address failover.
Earlier packaged smoke tests passed for local HTTP, direct HTTP and verified TLS
with a test certificate. They used a simulated browser.

## Current remaining work

- Test on Android-native Firefox 142+ with manual installation and consent.
- Confirm Android network changes and suspension behavior on real devices.
- Authenticate to Mozilla AMO and submit the package for signing/review.
- Replace unsigned release links with signed artifacts only after receiving them.

No AMO submission or signing has been performed by this validation run.
