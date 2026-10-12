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


## Remote Codex automatic installation and intent routing (2026-10-12)

A real Codex CLI session on the owned SSH host `arvos-next` cloned public main
`8c8dcad` and ran `python3 install.py --codex`. Its prompt contained only the
repository and installation instructions, with no broker URL, credential path
or device ID. The installer migrated the existing authorized connection,
registered MCP 0.2.4 and installed the skill/global instructions while preserving
unrelated MCP servers and instructions. This tests reuse of an authorized
connection, not first authorization of an unknown machine.

Two subsequent fresh Codex sessions received natural browser requests in Italian
and English. Both selected `android-browser` automatically, opened example.org,
read "Example Domain" and closed only their newly created tab. This is observed
behavior for these sessions, not a guarantee for every model or language.

The remote installed client then operated a disposable fixture in actual Android
Firefox through the existing encrypted SSH forward. Twelve samples per operation:

| Operation | Median ms | p95 ms |
| --- | ---: | ---: |
| tabs | 136.65 | 182.27 |
| read | 147.35 | 307.46 |
| click | 128.42 | 143.35 |
| fill | 117.55 | 313.14 |

A tablet-local MCP independently verified the remote fill and exactly twelve
clicks in the same fixture. Only the created fixture tab was closed afterwards.
These measure persistent MCP operation latency, excluding model thinking, startup
and website navigation. This connection depends on the running SSH forward;
network-independent or permanent availability was not established.

Final regression verification: 49 Python tests passed, including custom profile
filename bootstrap, alias regeneration without a second owner, and restart.


## 0.3.0 independent servers and connection interface

The new background transport passed the existing Node dispatcher, scheduling,
navigation and deadline suites, plus a dedicated multi-server suite. The latter
checks simultaneous polls, independent tokens/devices and results (including
identical command IDs), offline isolation, per-server disable/removal, global
pause, legacy settings and redacted status.

A real isolated Firefox desktop profile connected simultaneously to two owned
HTTP brokers, each accessed through a packaged MCP client. Broker A filled a
fixture tab and broker B read that value. Concurrent cross-broker reading and
clicking succeeded; revoking A left B operational. Only temporary test profiles,
servers and fixture pages were used. The full existing real Firefox page-action
suite also passed with the new extension.

The 49 Python regression tests passed. These tests do not establish installation
of extension 0.3.0 on Android: the user's installed Android extension remains
0.2.1 until explicitly updated through Firefox. Prior Android benchmarks refer
to that older extension. The new UI and independent-broker behavior require
the new XPI; no AMO signing or marketplace approval is claimed.

The settings UI passed dedicated Node tests for adding a second server while
preserving the legacy connection and explicit global pause, legacy token cleanup,
duplicate confirmation/replacement, consent, invalid codes, network recovery
messages, per-server/global pause and removal. Tokens were absent from rendered
text and form values. Desktop and 390px layouts were rendered by actual headless
Firefox and visually inspected using inert demo profiles; these screenshots are
illustrative UI previews, not real tablet connections. Final Mozilla web-ext lint
reported zero errors, notices and warnings for extension 0.3.0.


## 0.3.1 compact response evidence (2026-10-12)

The installed Android extension 0.2.1 was operated by MCP 0.3.1 against owned
lab and large-DOM fixtures, comparing resultMode full with omitted/default
compact. Only created tabs were closed afterwards; no screenshots were taken.
Counts, documentId/URL/textLength and actionable refs were verified.

| Android fixture / operation | Full UTF-8 text bytes | Compact bytes | Reduction |
| --- | ---: | ---: | ---: |
| Lab read | 7,700 | 3,343 | 56.58% |
| Lab locate | 3,287 | 1,537 | 53.24% |
| Large DOM read | 46,014 | 4,886 | 89.38% |
| Large DOM locate | 27,300 | 2,176 | 92.03% |

A separate real isolated Firefox desktop benchmark measured lab read
7,524→3,352 bytes and locate 3,088→1,419; large-DOM read 46,189→4,894 and
locate 27,454→2,164. Byte/character reductions are not tokenizer counts or
subscription quota percentages. Full preserves exact values; fields and
truncation markers make reduced outputs explicit.

65 Python tests passed, including 10 response-policy and 5 Claude setup tests.
Node regressions cover normal dispatch/scheduling/navigation, multiple servers,
settings consent/preservation, optional CSS layout and desktop viewport limits.

## 0.3.1 desktop audit on SSH arvos-next

The new runner used Firefox ESR 153.4.0 and Browser Bridge MCP 0.3.1 on an
owned fixture, without Playwright or screenshots. Requested 1280×720 and
500×844 were measured exactly, with fixed-position layout and successful
center hit-tests. A 390×844 request on a separate probe measured 500×844 and
reported matched:false: Firefox desktop window constraints were not hidden.
A local Firefox 140 fixture also verified a covered target via occluded:true.

Temporary Firefox pairing follows the actual browser-side /api/pair flow;
profile/admin credentials remain private and the temporary browser/broker are
closed on exit. Normal runner startup does not disable browser sandboxes.
These desktop checks do not establish installation of extension 0.3.1 on the
user's tablet. Computed layout needs the new engine; compact text works with
the older installed extension.
