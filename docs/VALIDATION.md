# Verified validation — 2026-10-11

## Actual Android verification: MCP 0.2.2 and extension 0.2.1

The extension was installed and explicitly enabled in Firefox Android Nightly on
an actual OnePlus Pad 3. A persistent MCP stdio session controlled that browser
through the authenticated loopback broker. Generated local fixture pages were
used for the interaction tests; no accounts, payments or personal page contents
were required.

The full suite passed all **30 fixed operations**:

- Device discovery, tabs and capabilities using the existing opt-in pairing.
- Open, navigate, back, forward, reload, activate, foreground and close.
- Read, inspect, semantic locate and paginated large-page results.
- Click, double click, hover, focus, fill, type, clear, press, select and check.
- Document/container scrolling and element waits.
- Frames, open shadow roots, coordinate clicks, dragging and actual PNG screenshots.
- Ordered batches, stopping at the first failure, and completed-result reporting.

The fixture also verified input events, selection-aware keyboard editing,
password-value omission, stale references and refusal of disabled, read-only,
hidden, covered or ambiguous targets. Two simultaneous MCP requests established
that reading page B completes before page A's element wait times out.

The explicitly configured Termux-local foreground helper requested a Nightly
launch successfully on this tablet. A subsequent full interaction suite with a
rendered viewport passed. A successful launch request alone is not reported as
proof that Android made the app visible; agents can inspect `read.viewport`.
The helper requires the MCP to run on that Android, a bound device name, a
loopback broker and an allowed Firefox package. It is not a remote Android
control API and does not install applications or extensions.

A repeated 0.2.1 run exposed an Android history-navigation completion timeout.
MCP 0.2.2 now submits the navigation once and verifies a completed document/URL
transition using fixed, read-only snapshots instead of depending solely on
Firefox's event order. The final actual Android full suite passed with this
verifier, including back/forward and concurrent pages. The installed extension
stayed at 0.2.1: this fix requires updating the Linux MCP, not reinstalling the
Android extension. Compound MCP commands preserve same-page order and device
barriers while independent pages can run concurrently.

## Actual Android measured latency

Twelve sequential samples per operation used the persistent MCP, actual Android
Firefox, a small local fixture and authenticated loopback HTTP. The baseline
used extension 0.1.2; the final optimized measurement used MCP 0.2.2 with
extension 0.2.1. Both include the tool,
transport and browser action. Aggregate results only were saved.

| Operation | Baseline median ms | Final median ms | Baseline p95 ms | Final p95 ms |
| --- | ---: | ---: | ---: | ---: |
| tabs | 935.05 | 6.24 | 1241.22 | 7.63 |
| read | 935.07 | 12.32 | 1240.55 | 16.31 |
| click | 935.26 | 7.41 | 1255.16 | 10.12 |
| fill | 940.27 | 8.42 | 1243.44 | 15.41 |

Version 0.2 removes the fixed one-second extension delay and broker sleep polling,
uses a resident fixed-operation page engine, and reports completed actions while
the next long poll is waiting. Optimizing the backend alone did not improve the
old extension. These are measured results on one tablet and a small local page,
not guarantees for every website, network or Android device. Twelve samples are
a small sample; here the reported p95 is the largest observed sample.

## Real Firefox Linux integration

`python3 test_firefox.py` passed against Firefox **140.16.0 ESR** in the tablet's
Linux/PRoot environment, with a freshly created temporary profile and Mozilla
`web-ext`. Only the test copy bootstraps consent automatically. The packaged MCP,
actual JSON-RPC stdio, authenticated HTTP and actual WebExtension APIs were used.
No existing user profile, cookies, passwords, history or tabs were used.

The rebuilt MCP 0.2.2 package with extension 0.2.1 passed the same 30-operation
fixture suite and actual
cross-page concurrency. Screenshots were checked for PNG/JPEG bytes, not merely
a MIME declaration. Desktop tests complement the separate actual Android run.

Earlier version 0.2.0 desktop measurements used 12 samples per operation:

| Operation | Median ms | p95 ms |
| --- | ---: | ---: |
| tabs | 30.62 | 167.37 |
| read | 57.37 | 323.51 |
| locate | 29.00 | 106.97 |
| click | 24.22 | 50.14 |
| fill | 21.81 | 108.86 |
| batch (fill + inspect) | 19.12 | 29.92 |

These earlier desktop timings are separate from the Android comparison above.

## Recovery and regression tests

Thirty-four Python tests passed (`test_bridge.py` and `test_navigation.py`),
covering authenticated HTTP, device isolation,
one-use pairing, expiry, revocation, private persistence, connection policy,
structured errors, conservative uncertain outcomes and `browser_status`.
Navigation regressions cover BFCache, same-URL reloads, fragments, stale complete
snapshots, transient read failure, preconditions before actions and exactly one
navigation submission on timeout. Mixed batches stop before later actions on a
navigation failure; coordinator tests cover ordering, concurrency and cleanup.
The fixed Android helper was tested with a mocked subprocess: allowed package,
bound device, loopback URL and explicit argument vector without a shell.

Node regressions passed for static engine injection, address failover, foreground
API support/fallback, invisible screenshots, navigation completion, same-tab
FIFO, global barriers, four-command concurrency and queued cancellation.
A suspended page's response deadline releases later scheduling barriers. Late
receiver failures or engine replacement cannot dispatch another action after
that deadline. Uncertain actions are not automatically replayed.

Earlier packaged smoke tests passed for local/direct HTTP and verified TLS using
a test certificate and a simulated browser. They are not Android network tests.

## Mozilla package lint

Mozilla `web-ext` 10 lint of extension **0.2.1** reported **0 errors, 0 notices,
0 warnings**. Desktop minimum 140 and Android minimum 142 match the built-in data
consent requirements. The manifest and included privacy policy disclose browsing,
website content/activity and authentication data permissions.

Passing lint does not establish Mozilla signing or marketplace approval. No AMO
submission or signing has been performed by this validation run.

## Remaining limitations and installation work

- Android suspension and changing networks remain device-dependent. The project
  has no verified 24/7 guarantee or completed multi-network endurance test.
- Mozilla authentication, signing and marketplace review remain pending; current
  development artifacts are unsigned and require the documented Nightly setup.
- The installed extension has no automatic-update bootstrap configured. A future
  `update_url` would require installing a version that declares it first; it
  cannot make the currently installed build update retroactively.
- `foreground` brings a configured Firefox session forward; it cannot operate
  Android's installer or Firefox's extension-installation settings. No automated
  Android installer is available in this tested setup; ADB listed no devices.
  Installation and upgrades currently require the documented user steps.
- Internal browser pages, native Android UI and closed shadow roots remain
  outside the supported page-operation surface. Some sites require trusted events.
