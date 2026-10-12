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
A write attempt expired waiting for approval and reported `APPROVAL_REQUIRED`
with `actionMayHaveOccurred:false`; no successful native write is claimed.
The 0.1.2 label fix has not yet been verified on the tablet. No marketplace
publication is claimed. This is an experimental optional component.

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

Verified candidate `browser-bridge-companion-0.1.2-release.apk` (656,792 bytes):

- APK SHA-256: `db6f8531f38d6f610985270696161706d261f729ce19132df757dddc4e0a0a4a`
- Publisher certificate SHA-256: `ffdfbb15acdfbb73abc91c0ee3f95073e14adf3446ac0bd18a80001940f9b5a6`
- APK signature v2 verified; manifest is not debuggable; all six release unit tests and
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

Version 0.1.2 uses `versionCode=3` and the same publisher certificate as 0.1.0/0.1.1.
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
8. Each native write requires your one-use approval from the notification or
   companion details screen. Approve/deny expires after 30 seconds. STOP, revoked
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

The current app supports one broker connection, a package allowlist, per-action
approval and explicit sharing. It does **not** capture the screen, launch apps
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
