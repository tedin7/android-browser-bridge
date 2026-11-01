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
- Mozilla signing of extension 1.0.0 for **unlisted** distribution is complete
  (see below). Listed marketplace publication and review remain pending.
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

A real Codex CLI session on an owned remote SSH host cloned public main
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

## 0.3.1 desktop audit on a remote SSH host

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


## Runtime 1.0 candidate, 2026-10-12

The candidate passed 167 Python unit/integration tests, all 12 JavaScript/Node
suites, generated-contract drift checking, and packaged stdio MCP smoke testing.
A fresh desktop Firefox profile with the real extension passed the interaction
suite (forms, blocked controls, references, Shadow DOM, frames, screenshots,
navigation, concurrent pages), plus leased `browser_step`, observation deltas,
broker-owned tasks, modern MCP Tasks completion/result recovery and resources.
Mozilla web-ext 10 lint reported zero errors, notices and warnings.

These tests do not prove Android execution of the candidate. Live discovery on
the user's tablet still reported extension 0.3.1 before the requested update.
The candidate XPI was placed in Android Downloads; its installation prompt is
outside the extension's page-control surface. A Mozilla Developer Hub tab was
opened, but Firefox returned “Missing host permission for the tab” when asked
to read it. No authenticated AMO signing or marketplace submission is claimed.

The companion passed Android release compilation, JVM policy tests and lint,
then APK v2 signature verification and a non-debuggable manifest check. Its
public certificate and artifact hashes are in companion/README.md. Physical
installation, Accessibility consent and native runtime tests remain pending.

The fixed CDP adapter passed protocol tests. The local owned Chromium process
exited with SIGTRAP in this environment, so live Chromium diagnostics are not
claimed. MCP Apps passed a host-protocol simulation; no real supporting host is
claimed. WebMCP permission/fallback tests passed; Firefox Android native WebMCP
availability is not assumed.

Concrete benchmark fixtures and launchers exist for Codex and Claude. The lost
response fixture commits a controlled application effect and closes its HTTP
response; this is application-response loss, not an MCP network fault. No paid
16-episode baseline/candidate matrix or measured token-saving percentage is
claimed. Candidate promotion remains blocked until the explicit release gates
are satisfied.


### Physical Android extension confirmation

After the user installed the candidate, live MCP discovery confirmed Firefox
Android extension **1.0.0**. On the owned local interaction fixture,
`validate_runtime.py` passed leased fill-and-verify, a region observation delta,
and modern MCP Tasks completion after closing and reopening the MCP client.
The single local workflow sample was 103.35 ms; this is a single sample, not a
latency benchmark or a model-token measurement. WebMCP returned disabled and
native-consumer-API unavailable with a DOM fallback, as expected for this device.

The previous standalone fixture server on port 18973 had exited: an HTTP probe
returned connection refused. Restarting it and reloading the same tab restored
readability. The candidate now packages `/fixture` and `/frame` directly in the
broker so the standard interaction lab shares the broker's lifetime. A server's
loopback address still refers to that server; use the tablet-reachable broker
origin. Firefox error pages themselves reject extension injection, which can
surface as a host-permission error; recovery guidance now distinguishes this.

The native companion was installed and paired by the user, but Accessibility
was blocked by Android restricted settings at this point. Pairing is not a
claim of active native control or a passed native-runtime test.


### Live model connectivity smoke on the remote agent host

Two read-only model sessions called device discovery and capabilities against
the real paired Firefox: Codex CLI 0.162.1 with gpt-6.1-sol, and Claude Code
2.1.296 with the configured opus alias. Each emitted two completed tool calls.
Codex reported 87,999 inclusive input tokens (65,280 cached) and 141 output;
Claude reported 25,449 inclusive input (12,369 cache reads) and 204 output.
These are whole-client counters, not MCP-only usage and not a matched benchmark.
The per-client smoke input budget was exceeded because counters arrived only
at turn completion; both process groups were then stopped and not retried.
Claude's final output included the observed 1.0.0 version; the smoke collector
did not confirm Codex's final text. This is not a passed release gate.

Subsequently, progressive tool-schema disclosure reduced serialized discovery
from 10,440 to approximately 9,016 bytes while preserving operation contracts
on demand. This byte comparison is not a token-saving estimate; no further
paid model runs were performed to claim a measured token improvement.


### Final local candidate deployment and native scope check

The final Python regression run passed **171 tests**. Generated operation
contracts and `git diff --check` also passed. The action journal now leaves
ordinary observations unjournaled unless an explicit action identity is supplied;
mutations retain deduplication identities and reject full capacity before
dispatch. Regression checks cover read traffic at capacity and client quotas.

The local installed MCP package and persistent broker were upgraded with a
private stopped-broker state backup. Health reports 1.0.0 and the broker-owned
`/fixture` returns HTTP 200. The existing Android fixture tab was migrated to
that origin. A fresh installed MCP client again passed leased fill/verification,
observation delta and durable task recovery after client reconnection. The
single workflow sample was 161 ms, not a latency benchmark.

Companion 0.1.1 was physically installed, paired and Accessibility-authorized.
An actual native read returned the Firefox fixture with package
`org.mozilla.fenix` while the user used split screen (Termux left, Firefox right).
A visible pane and Android active-window input focus are different: the same
policy correctly refused reads while Termux had that focus. A single native
click request for the fixture button expired waiting for local approval and
returned `APPROVAL_REQUIRED`, `actionMayHaveOccurred:false`; no retry was made.
Native mutation success is therefore not claimed. Empty accessibility
descriptions were found to hide nonempty node text; the source fix uses the
first nonblank description, text or hint and preserves package restrictions.

The final remote installation on the agent host updated both Codex and Claude
registrations. Fresh stdio sessions using each registration reported 1.0.0 and
ten tools; separate private scoped profiles were retained. A single workflow
validation from that server through the Codex scoped profile passed on the real
Android fixture: verified step (567 ms single sample), delta observation and
verified durable task after client reconnection. No model invocation was used
for this final deployment check.

Companion 0.1.2/code 3 packages the accessibility label fix. Six release JVM tests
passed with no failures, errors or skips; lint and release compilation passed.
APK v2 signing and non-debuggable status were verified, using the same signing
certificate. The APK is ready in Android Downloads; installation and physical
verification of this label fix remain pending.


### Physical companion 0.1.3 approved write

After a user-confirmed update to companion 0.1.3, capabilities reported
`0.1.3-experimental`. The approved native `Click fixture` action returned
`executed:true, verified:false`. An independent Firefox DOM read on the owned
fixture confirmed `clicks:2` before and `clicks:3` after, establishing one actual
effect. Earlier attempts returned no-action errors for changed focus or missing
controls; none was treated as successful or replayed while uncertain.

The companion also physically read the signed-in Mozilla developer agreement
page through Android Accessibility, despite Firefox's protected-domain DOM
restriction. This establishes native observation of that page, not submission,
acceptance of the agreement, API authentication or Mozilla signing.

A new authenticated native preflight endpoint checks a device-bound dispatched
command and originating-client validity before an approved write. Eleven focused
broker security/fixture tests passed, including wrong-device, queued command and
revocation rejection. The local broker was backed up while stopped and upgraded
before companion 0.1.3 verification. This check does not promise atomicity between
a server-side revocation and a later Android UI effect.


### User-requested native session approval candidate

Companion 0.1.4 adds a local user choice to approve an exact app and broker
connection for ten minutes. The grant uses monotonic time and process memory;
STOP, consent withdrawal, allowlist change, connection replacement, revocation,
expiry and process restart invalidate it. Each write still passes broker
preflight and final context checks; no MCP operation can grant this approval.
The local button attempts returning to the approved app using its own launcher.
Thirteen JVM tests passed (eight policy and five session tests), along with lint,
release compilation, APK v2 verification and non-debuggable manifest checks.
The APK keeps the publisher certificate and increments versionCode to 5.
Physical 0.1.4 installation is now confirmed. After local session approval, two consecutive native fixture clicks completed without new approval prompts (single call samples 176 and 173 ms). Independent Firefox DOM evidence showed clicks:4, then clicks:5 and clicks:6. These are focused functional samples, not a latency benchmark. The earlier 0.1.3 single-write result remains separately recorded.


The local Android foreground helper previously launched the broker health URL
through a package-scoped VIEW intent. On this split-screen tablet that did not
reliably transfer Android input focus. An explicit fixed Firefox launcher alias
with activity reorder-to-front succeeded; native capabilities then reported
`org.mozilla.fenix`. The helper now uses that alias for the same three whitelisted
Firefox packages and preserves the selected browser tab. Twenty MCP/helper
regression tests passed. Android activity launch acceptance still does not by
itself prove foreground focus on every device.


### Mozilla unlisted signing of extension 1.0.0

Extension 1.0.0 (id `android-browser-bridge@local.invalid`) was signed by Mozilla
for unlisted distribution; the signed XPI contains Mozilla signature files. This
is not a listed marketplace publication. The signed file is a private release
artifact and is not committed.

### Companion 0.2.x: owner-chosen permanent approval, split screen, tap fallback, verification

Companion 0.2.0/0.2.1 changes, all local to the owner's device:

- **Permanent per-app approval.** The app lists launchable apps with *Allow* and
  *Always* switches. *Always* (also offered on the approval notification) skips the
  approval prompt for that allowed app; it persists across STOP and restarts, but
  STOP still halts all control and writes still pass broker preflight. It cannot be
  granted or changed through MCP.
- **Target selection without focus.** With `flagRetrieveInteractiveWindows`, the
  target is `args.package`, else the focused allowed app, else the single visible
  allowed app. In split screen a focused terminal no longer blocks Firefox actions.
  `back` still requires real focus and the companion requests it.
- **Automatic foreground.** If the target app is not on screen, the companion opens
  it with its launcher intent (allowed apps only) and waits up to 4 s. A new
  `foreground` native operation does the same explicitly.
- **Tap fallback.** A matched control without a safe clickable ancestor (or with
  `force:true`) is tapped at the centre of its visible part with an accessibility
  gesture, refused when a higher window covers that point; failures report the reason.
- **Post-action verification.** After a write the companion compares the window list,
  the target window tree and the target node with evidence taken just before the action.
  `verified:true` with `effect` (`value_matches`, `window_changed`,
  `target_state_changed`, `screen_changed`) reports an observed change; it is not a
  claim about application semantics.

The broker validates native-device arguments (including `package`) with a separate
native contract, leaving the Firefox catalog and the signed extension unchanged.

Physical results on the OnePlus Pad 3 with 0.2.0: an MCP read with
`package: org.mozilla.fenix` while another app was in front launched Firefox and
returned its controls (`autoForeground.launched:true`, 424 ms). With *Always* set for
Firefox, a native click on the tab strip label switched tabs without an approval
prompt and returned `verified:true, effect:screen_changed`; the Firefox extension
independently reported the new active tab. A forced screen tap on another tab
label was refused with `tap_point_unavailable` (fail-closed); 0.2.1 adds the
refusal diagnostics. Companion 0.2.1 also fixes the in-app Accessibility indicator
on ColorOS, which omitted the running service from the manager list. Release builds
passed 24 JVM tests and lint and were signed with the same publisher certificate.


### Extension 1.0.1: select options in read/locate

Read and locate now include a select control's options (value, text when it differs,
selected/disabled flags; at most 25, then `optionsTruncated`) whenever the `type` field
is returned, which the compact MCP defaults already request. `options` is also an
explicit descriptor field. An observed Claude form episode spent a separate inspect
turn only to discover option values; this removes that turn without any MCP change,
so a newer MCP still works with extension 1.0.0. Node suites, the new
`test_select_options.js` and web-ext lint (0 errors, 0 warnings) passed. Version 1.0.1
is Mozilla-signed for unlisted distribution; installation on the tablet is pending.

### Release gate run, 12 October 2026 (baseline 0.3.1 vs candidate 1.0.1)

Full 16-episode matrix on the OnePlus Pad 3 Firefox Nightly, agents on the owned
SSH host: Codex CLI 0.162.1 (`gpt-6.1-sol`, low effort, read-only sandbox, only the
bridge MCP pre-approved, isolated home) and Claude Code 2.1.296 (`claude-opus-5-5`,
strict MCP config, bridge tools only). All 16 episodes verified independently;
`promotable: true`, `baselineUnverified: 0`.

| Client | Baseline input | Candidate input | Change | Tool calls (b → c) |
|---|---|---|---|---|
| Codex | 452,706 | 429,184 | −5.2% | 21 → 15 |
| Claude | 252,612 | 241,785 | −4.3% | 22 → 22 |
| Total | 705,318 | 670,969 | −4.9% | 43 → 37 |

One sample per cell; the same candidate scenario varied by up to ~25% between runs,
so these differences are within run-to-run noise except the call-count reduction.
The 30% target is not met by this run.

Fixes found while preparing it: the lost-response fixture caused Firefox to resend
the POST (fixed with a 504 reply); the gate stopped on baseline failures (baseline
is now recorded); limits are whole-matrix caps. After the run, usage rules moved
into the browser_command description and the Codex skill became a pointer, removing
the per-session skill-reading turn. Targeted Codex re-runs then measured form
79.3k (baseline run 137.0k) and two tabs 79.8k (baseline run 75.8k) input tokens,
both verified; these are single samples, not a new full matrix.

### Extension 1.0.2: click effects, clear batch errors, app-shell scrolling

Reviewed a real Claude session that tried to switch Search Console's "Rows per page"
menu to 500 rows. It spent about twenty calls and gave up with 10 URLs per reason:

- the menu ignores synthetic events, yet every click returned `ok:true`;
- a `press` step without a target failed as `ACTION_ERROR: args: invalid alternatives`
  with `actionMayHaveOccurred:true`, naming neither the step nor the missing field;
- the page scrolls an inner element, so `scroll` reported `maxY:0` and moved nothing.

Changes:

- `click`, `double_click`, `click_point` and `press` now report `effect`
  (`navigation`, `target_state_changed`, `dom_changed`, `no_visible_change`) and
  `verified`. Styling changes on the control itself (focus, ripple) are ignored. On
  `no_visible_change` a `hint` says not to repeat the action and to use a native
  companion device for a real tap. Observation waits one frame, plus 200 ms only when
  nothing changed yet.
- Validation errors name the batch step and the accepted target fields
  (`steps[1] press: args: needs one of selector, ref, role, …`). The broker rejects
  them as `INVALID_ARGUMENT` before queueing, and the MCP reports
  `actionMayHaveOccurred:false`.
- `scroll` without a target moves the largest visible inner scroller when the window
  cannot scroll; `intoView` reports the container that actually moved. Both return
  `container` with its ref.
- The `browser_command` rules explain `no_visible_change`.

The real Firefox suite (`test_firefox.py`) gained a button that ignores untrusted
clicks, an inner `intoView` case and an app-shell page; it passed together with all
Node and Python suites and web-ext lint (0 errors, 0 warnings). Version 1.0.2 is
Mozilla-signed for unlisted distribution
(`ee57848410b94cbe8c82-1.0.2.xpi`, SHA-256 `bd9f26c3…0a48b05`).

### Companion 0.2.2: taps through transparent Open Canvas windows

On the OnePlus Pad 3 in split screen, OnePlus Open Canvas keeps a full-screen
`com.oplus.pscanvas` window above every app. The companion counted it as covering
every tap point and refused all gesture taps (`tap_point_unavailable`, reason
`covered`). A higher window now blocks a tap only when its accessibility tree shows
a visible labelled or interactive node at that point; a dialog, shade, keyboard or
bubble still blocks, and a window whose tree cannot be read (or exceeds 3000 nodes)
still blocks. On the tablet, `force:true` taps then opened Search Console's URL
filter menu, which had reported `no_visible_change` to the extension's synthetic
click (extension 1.0.2 on the device). The MCP rules now say to retry such a control
through the companion with `args.force:true`. Unit tests (25) and lint passed; the
APK is signed with the existing publisher certificate (versionCode 9, SHA-256
`31550cb6…cf414b`).

### Companion 0.2.3: Enter for fields that ignore synthetic keys

Search Console's URL inspection box starts only on a real Enter; the extension's
synthetic key submits the surrounding form, which reloads the overview instead.
The companion gains `press` (key Enter only) for the field that has input focus in
an allowed, focused app: first the Android 11+ editor action `ACTION_IME_ENTER`,
then, with `force:true` or when the field lacks that action, a real tap on the
on-screen keyboard's action key (matched by label or `ime_action` resource id).
The broker accepts `press` and `key` for companion devices. Unit tests (26) and lint
passed; versionCode 10, same publisher certificate (SHA-256 `19e19207…49625`).

### Companion 0.2.4–0.2.5: Enter with a physical keyboard attached

Firefox exposes no `ACTION_IME_ENTER` on web fields, and with a physical keyboard
attached Gboard shrinks to a toolbar without an Enter key (0.2.4 reports the visible
key labels when the key is not found, never typed text). 0.2.5 declares
`flagInputMethodEditor` and, on Android 13+, sends a real Enter through the
accessibility service's own input connection to the focused editor. On the tablet
this started Search Console's URL inspection, which then accepted "Request
indexing" (the inspection page uses an opaque id, so its URL cannot be built
directly). versionCode 12, same publisher certificate (SHA-256 `9b8f2f07…a67b9c`).

### Token and round-trip reductions from a real Search Console session (1.0.3)

Measured while requesting indexing through Search Console on the tablet:

- Companion `read`/`locate` (compact): Firefox exposes containers as buttons whose
  names concatenate their children and repeats nested copies of the same control.
  The MCP keeps the innermost node per role and name, drops merged containers and
  null fields, and reports `duplicatesOmitted`. A real Search Console `read` went
  from 12,010 to 4,539 bytes (50 → 34 elements).
- Companion `click`/`fill` by name/role: the MCP locates, deduplicates and acts in one
  call, retrying a stale reference (nothing ran) with a fresh lookup. Before, agents
  needed locate + click and often hit `STALE_REFERENCE`.
- Verified native writes drop the verification notes and follow-up advice (about
  600 → 150 characters); `wait` returns only ref, tag, role and name.
- Extension 1.0.3: an app rewriting its own URL encoding (`%3A` → `:`) is no longer
  reported as `navigation`; `locate` with a CSS selector skips hidden copies unless
  `includeHidden` (Search Console keeps several hidden tables).

All Node and Python suites, the real Firefox suite (new hidden-selector case) and
web-ext lint passed. 1.0.3 is Mozilla-signed (`ee57848410b94cbe8c82-1.0.3.xpi`,
SHA-256 `0547b858…`).


## 1.0.4: fixed keyboard codes, timed input and SVG activation

The game-input fixture verifies Space/KeyW and explicit ShiftRight location through the packaged MCP, real Firefox and the resident extension. A 100ms key hold and 120ms drag are checked against event timestamps recorded by the page. SVG group activation completes without calling a nonexistent .click() method. The complete existing Firefox interaction/task suite passed after the change, preserving form editing, native HTML control defaults, navigation and recovery. This is desktop Firefox evidence, not Android runtime evidence.

All 187 Python tests passed with the Linux interpreter (one existing skip); all 13 Node test suites and web-ext lint passed (zero errors/notices/warnings). The targeted Node input test additionally checks release after visibility/pagehide cancellation and rejects out-of-range durations before keydown. A test fixture formerly hardcoded engine version1.0.3 now obtains the loaded version, retaining the version handshake rather than rejecting every later release.

Synthetic input remains untrusted. There is no claim of native Android keyboard expansion, autonomous canvas targeting, simultaneous multi-key steering or guaranteed release after browser process death. See GAME_INPUT.md for supported arguments and limits. Signing, installed extension version and remote agent activation must be verified independently from these tests.
