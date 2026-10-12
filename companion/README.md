# Optional Android companion (experimental)

The Firefox extension remains independent and requires neither this app nor
Accessibility. This companion supplies a **separate native device** using the
existing broker pairing/poll/result protocol. It does not pretend that Android
app controls are Firefox DOM nodes or that clicking a control verifies a save.

**Status:** Kotlin source has compiled successfully with JVM policy tests and
Android lint. A development APK and a separately publisher-signed, non-debuggable
release candidate are available locally. Release unit tests, lint, APK signature
verification and physical-device runtime are separate gates; see the local build
verification records. On the physical tablet, version 0.1.1 pairing, capabilities,
foreground-package diagnostics and an allowed Firefox native read succeeded.
Version 0.1.2 semantic name lookup succeeded. On version 0.1.3, a locally approved
native click succeeded; the Firefox extension independently verified the fixture
counter changing from 2 to 3. Earlier unapproved requests expired without action.
Version 0.1.4 session approval was verified with two subsequent native clicks
without another approval prompt (176 ms and 173 ms); the Firefox DOM independently
confirmed counter changes 4→5→6. These are two observed operations, not a full
benchmark. No marketplace publication is claimed. This is an experimental optional component.

### Version 0.2.x behaviour

- **Apps screen:** pick the apps the server may use (*Allow*) and, per app, *Always*
  to approve writes permanently. Permanent approval is stored on the device, survives
  STOP and restarts, and can only be changed in this app (never through MCP).
  Without it, each write asks once / 10 minutes / always via notification.
- **Which window:** `args.package` if given, else the focused allowed app, else the
  only visible allowed app. Split screen with a focused terminal works.
- **Automatic foreground:** an allowed app that is not on screen is opened with its
  launcher intent. The `foreground` operation does this explicitly.
- **Tap fallback:** controls without a clickable ancestor (or `force:true`) are tapped
  at their visible centre unless another window covers that point.
- **Verification:** writes return `verified` and `effect` from comparing the screen
  before and after (500 ms). `verified:false` means no visible change was observed;
  read before repeating.
- **Operations:** capabilities, read, locate, inspect, click, fill, scroll, back,
  foreground. Arguments: package, ref, name, label, role, textQuery, exact, value, force,
  y, textLimit, maxElements.

## Build and verification

Use JDK 21 (tested), Gradle 8.9 and Android SDK platform 35 with build tools 35.0.0. Set
`ANDROID_HOME` to that SDK (or put `sdk.dir` in private `local.properties`). The
pinned Android Gradle plugin is 8.7.3 and the Kotlin plugin is 2.0.21. Dependencies
come from Google's Maven repository and Maven Central; no runtime cloud service
is required. No Gradle wrapper binary is supplied: invoke an installed Gradle.

From this directory:

```sh
gradle :app:testDebugUnitTest :app:lintDebug :app:assembleDebug
```

The resulting development APK is at
`app/build/outputs/apk/debug/app-debug.apk`. Android's debug keystore is only for
local development. A release build uses an independently managed publisher
signing key; no key or signing credentials belong in this repository.

### Signed release candidate and future updates

Build `:app:testReleaseUnitTest :app:lintRelease :app:assembleRelease`, align the
unsigned APK with Android SDK `zipalign`, then sign it with `apksigner` using a
private release keystore. Pass passwords through protected files or environment
references supported by the signing tools, never command-line literal secrets.
Verify the result with `apksigner verify --verbose --print-certs` and check that
`aapt dump badging` does not report `application-debuggable`.

The current candidate uses a dedicated publisher certificate, separate from the
Android debug certificate. Public APK and certificate SHA-256 fingerprints are
recorded alongside the local artifact. This is a signed candidate, not proof of
Android runtime validation or a store release.

Verified candidate `browser-bridge-companion-0.1.5-release.apk` (669,080 bytes):

- APK SHA-256: `899f83e9aa1790cb04533fdace490efb5b9964de4774f4266399c8f719307a4e`
- Publisher certificate SHA-256: `ffdfbb15acdfbb73abc91c0ee3f95073e14adf3446ac0bd18a80001940f9b5a6`
- APK signature v2 verified; manifest is not debuggable; all nineteen release unit tests and
  release lint passed. This candidate's Android runtime remains unverified.

Keep the keystore and its password outside the checkout with owner-only access.
Maintain a verified, encrypted backup on independent storage; a private sibling
copy on the build server protects against accidental edits but **not** server or
disk loss. Do not commit or upload signing material. Preserve this exact signing
identity for updates and increment `versionCode` for each new release. Losing the
key prevents normal updates to installations signed with it.

Android cannot update a debug-signed installation with this publisher-signed APK
under the same application ID. If the debug app is already installed, explicitly
uninstall it before installing the release candidate; this deletes its pairing
and settings, so enroll a fresh native device afterward. Keep the existing
Firefox extension and its separate pairing intact. Do not automate uninstalling
an existing installation or assume that its data transfers across signing keys.

## Updating an existing publisher-signed installation

Version 0.1.5 uses `versionCode=6` and the same publisher certificate as earlier release candidates.
Install it as a normal update; **do not uninstall or clear app data**. Existing
pairing and the exact package allowlist are retained. Check the permission status
shown in the app and explicitly enable control again if Android stopped the
service during the update. No package is automatically added to the allowlist.

Version 0.1.2 fixes native accessible names when Android supplies an empty or
whitespace-only content description: use the first nonblank description, text,
or hint, still capped at 512 characters. This improves semantic `name` matching
without changing package, permission or node checks.

Capabilities and `PACKAGE_NOT_ALLOWED` diagnostics now report `foregroundPackage`
and `allowedPackages`. These are package identifiers only: controls and text from
an unauthorized active window are never returned. A system overlay may own the
active window even when Firefox is visible underneath. Dismiss the overlay or
bring an already allowed app forward; do not broaden the allowlist automatically.

Selecting consent clears an obsolete consent warning but does not enable control.
Unchecking consent immediately stops control and clears pending approval. The UI
reports Android's service-enabled status and notification permission independently
from the broker connection; Enable explains which permission is missing.

### Version 0.1.3 approval visibility and focus

STOP remains on a persistent control notification. One-use approvals use a
separate high-importance **One-use action approvals** notification channel with
Approve once / This app: 10 min / STOP actions (Deny remains in companion details). Android can still suppress heads-up display (for
example under Do Not Disturb); companion details show the same pending request
and countdown. The app checks global notifications and both channels. If a
channel is blocked, the status identifies it; the notification settings button
opens Android settings when notification permission is already granted.

Authorization still expires 30 seconds after the request. Approve early, then
return immediately to the originally approved allowed app. The runtime samples
the active package on the main thread for up to five seconds after approval,
without extending the original expiry. It does not launch apps, choose background
windows, or replay actions. Approved details remain visible until the request
finishes. STOP, denied approval, changed connection, expired approval, removed
allowlist membership or missing original focus prevents execution.

After approval and focus recovery, the companion calls the authenticated
`/api/native-preflight` endpoint with the device and pending command ID. A rejected
or unavailable check fails closed before action. The broker must support this
endpoint; upgrade it before installing 0.1.3. Local authorization, connection,
expiry and focus are checked again immediately before execution. Revocation after
that last broker check still has an unavoidable race; this is not a claim of
instantaneous revocation or exactly-once application effects.

### Version 0.1.4: approve one app session

For a pending write, explicitly select **Approve this app for 10 minutes** in the
companion, or **This app: 10 min** in its notification. That local gesture permits
subsequent fixed native writes only in the pending request's exact app package
and current connection, for ten minutes. It does not add packages to the allowlist
or grant control of this companion or Android system UI. MCP cannot grant this
session. **Approve once** remains available; **Deny this action** remains in the app.

The session lives only in process memory and expires using Android's monotonic
elapsed-realtime clock. STOP, withdrawing consent, changed allowlist, connection
replacement, detected broker authorization rejection, explicit **Revoke app session
approval**, expiry or process restart discards it. The UI shows the package and
remaining duration. Each write still requires current allowed-app focus, existing
node/permission checks and broker preflight; failures never replay the action.

After the local session-approval button is pressed, the companion tries to resume
only that pending app through Android's own package launcher. This is tied to the
explicit user gesture, not a remote launch command. If Android provides no launcher
or refuses the transition, return manually immediately. The original request's
30-second deadline and five-second focus-return bound still apply. Notification
approval does not launch anything. A session does not keep commands alive, extend
node references, bypass stale-ref checks, or promise instantaneous remote revocation.

### Version 0.1.5: composed controls

Empty clickable/checkable container names can be derived from visible non-password
descendant labels within the same package and window. Traversal is bounded to
32 descendants, depth three and 512 characters. Derived names can match both a
container and a child: disambiguate with observed role/ref rather than guessing.

Clicking a uniquely selected non-clickable leaf resolves its nearest clickable
ancestor, at most four levels up. Every node along that path must remain visible,
enabled, non-password, and in the same authorized package/window. The leaf and
resolved target are refreshed, semantic fingerprints rechecked, and the ancestor
path resolved again before action. Results indicate `resolvedAncestor` and
`ancestorDepth`; unsuccessful resolution gives `TARGET_NOT_ACTIONABLE` without an
action. A platform action returning false is reported separately and requires
inspection before retry. Zero matches return `TARGET_NOT_FOUND`, distinct from
`TARGET_NOT_UNIQUE`.

Descriptors include bounded screen `rect` and `checked` for checkable controls.
Capabilities expose session `active`, `targetPackage` and `remainingSeconds`,
without connection identifiers. Android manifest visibility is limited to normal
MAIN/LAUNCHER activities so the explicit local approval gesture can find app
launchers; no `QUERY_ALL_PACKAGES` permission or remote-launch operation is added.

## Explicit installation and pairing

1. Install the locally built APK using Android's installer.
2. Enroll a **new device ID**, for example `tablet-native`, using `browser_pair`.
   Keep your Firefox device enrolled separately. Reusing its ID requires revoking
   it and would disrupt the browser connection.
3. Paste the new `BB1` string in the companion. Enter exact allowed Android app
   package names, such as the package of your own test app. Wildcards are refused.
4. Read and select the authorization checkbox, then tap **Pair server**. Pairing
   is one-use. If the result is uncertain, create a new enrollment rather than
   automatically replaying the pairing request.
5. Use **Open Android Accessibility settings** and enable this service yourself.
   Android may require you to approve restricted settings for a sideloaded app.
   This application does not enable that permission or bypass its confirmation.
6. Allow the control notification, then tap **Enable remote control**. The
   persistent notification and app both provide a **STOP** control. Open the
   allowed target app yourself; this version has no remote app-launch operation.
7. Call `browser_devices`, select the new native device ID explicitly and inspect
   its `capabilities` before issuing native commands.
8. A native write requires one-use approval or an active, locally granted
   ten-minute session for that exact app and connection. Pending approval
   expires after 30 seconds. STOP, revoked
   consent, a changed app, or a replaced connection prevents the action. Opening
   the details screen may invalidate a node ref; in that case the agent must
   observe again, rather than rebinding a stale ref silently.

The broker must be reachable by the tablet. HTTPS is required except for explicit
`http://127.0.0.1`/`http://localhost` origins; TLS verification and hostname checks
are never disabled. Redirects are not followed with pairing codes or tokens.
A remote server's `127.0.0.1` is not the tablet's loopback address: use reachable
HTTPS or an already established local forwarding route. The companion does not
create a VPN, tunnel or NAT traversal service.

## Current fixed capabilities

- `read`: bounded visible text and up to 50 actionable controls, with incomplete
  and truncation indicators. No targeted read; use `locate` and `inspect`.
- `locate`: semantic `name`, `label`, `role`, `textQuery`, `exact`, or a confirmed
  `ref`. Roles currently distinguish textbox, checkbox, button and element.
- `inspect`: one confirmed visible enabled non-password control.
- `click`, `fill`, `scroll`: accessible control actions; inspect afterward to
  verify the application's outcome. Fill values over 10,000 characters fail.
- `back`: Android's native back action, gated by the foreground package allowlist.
- `capabilities`: explicitly reports the native backend and absent browser tabs,
  screenshots and targeted reads.

Example tool arguments after inspecting capabilities:

```json
{"device":"tablet-native","op":"locate","args":{"role":"textbox","name":"Search","exact":true}}
```

Then use the returned `ref` with `fill` and `inspect`. Do not include `tabId`,
`frameId` or CSS selectors: those belong to the Firefox backend. Password fields
are excluded. Observations traverse at most 1,000 accessible nodes. If that bound
prevents proving target uniqueness, mutations require a previously returned ref.
Refs are invalidated by a window change and checked against refreshed node
identity before use; they are not durable selectors.

Every mutation returns `executed` and `verified:false`; it never claims that
an application saved data or completed an external transaction. Errors contain
`nextSteps`. A callback timeout reports uncertainty and does not repeat the action.
Result delivery retries the stored result, never the underlying command. Terminal
rejections release the result queue; revoked connections disable control.

## Data, stop behavior and limitations

Pairing credentials are encrypted with Android Keystore, app backup is disabled,
and no page contents or credentials are logged. One bounded result can be held
in app-private preferences until delivery. It is cleared after delivery or a
terminal rejection. Stopping disables new actions; a stored result may still be
delivered to reconcile an action that already occurred.

The current app supports one broker connection, a package allowlist, one-use
or scoped app-session approval and explicit sharing. It does **not** capture the screen, launch apps
remotely, run a shell, execute JavaScript or provide durable multi-step native
workflows. Those remain separate future capabilities.

Use Android Share or the app's text/URL field and document picker to select one
item. Selection does not send anything. **Review and send** shows the exact
paired server, file name/type/size or a text preview; **Send this item** is a
separate explicit confirmation. Files are limited to 1 MiB, text to 64 KiB. The
paired-device `/api/native-share` endpoint stores an artifact server-side and
returns its identifier and byte size. No file base64 is returned to the model.
Sharing can be used while native remote control is stopped. Failed transfers
remain selected and are never retried automatically; repeating the same selection
within the app uses the same share ID. The receiver must support that endpoint;
older brokers return a failure and are not reported as having accepted the item.
Accessibility lifecycle and network connectivity depend on Android; a connected
broker must not be described as permanently available. Full native-control runtime
verification remains required beyond the limited 0.1.1 checks described above.

Before release, verify explicit permission activation, two separate device IDs,
correct allowlist gating, denied notification consent, STOP during an in-flight
poll, stale references, password exclusion, ambiguous controls, delivery failure,
process death, reconnection and revocation. Verify packet/result contents against
these claims using a controlled app, not personal pages or credentials.

Build compatibility references: [AGP 8.7 requirements](https://developer.android.com/build/releases/agp-8-7-0-release-notes) and [official Android SDK tools](https://developer.android.com/studio#command-line-tools-only).


### Android restricted settings

If Android says access was denied while enabling Accessibility, open Android
Settings → Apps → Browser Bridge Companion → More (⋮) → Allow restricted
settings, confirm locally, then return to Accessibility. Availability and labels
can vary by device; do not bypass system policy if the option is unavailable.
This is the [official Android user-controlled flow](https://support.google.com/android/answer/12623953).
Pairing remains valid while this permission is pending. Firefox extension
control does not depend on enabling the companion.
