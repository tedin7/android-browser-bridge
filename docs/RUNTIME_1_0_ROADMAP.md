# Browser Bridge 1.0 implementation roadmap

This records the approved direction and acceptance gates. It is **not a claim that Browser Bridge 1.0 is implemented**. The existing fixed-operation browser engine remains the baseline. Update completion markers only with implementation and verification evidence; publishing this document does not satisfy a gate.

## Current candidate evidence

The source candidate implements the phase-1 queue/recovery/control fixes and the operation registry, authenticated client credentials, durable action identities, extension tab leases, bounded `browser_step`, DOM field projection and observation snapshots/deltas. This is source implementation status, **not deployment or release promotion**.

The integration run of `test_firefox.py` passed on actual desktop Firefox, including lease acquisition, fill-and-verify through `browser_step` and observation deltas, alongside the existing browser suite. Unit/regression tests separately cover action-store restart/expiry, private result recovery, bounded control scheduling and HTTP authentication. `test_broker_security.py` verifies scoped ownership, queued revocation, device revocation uncertainty, private native sharing and explicit transport deadlines using a disposable local HTTP server.

Generated browser operation lists and input validation now execute before dispatch, including validation of an entire batch before its first action. Raw Firefox output schemas and explicit validators cover all 35 operations; diagnostic/site-defined output remains extensible as documented. Native capabilities are separate and do not imply Firefox schema support.

The MCP adapter supports explicit legacy negotiation and a verified modern discovery/tools/resources subset. Opted-in modern clients can use polling Tasks with durable private result recovery. There are no subscription or full-conformance claims. The task UI is served as a bundled MCP Apps resource; a real supporting host remains unverified.

The optional companion has passed release compilation, JVM policy tests, Android lint and APK v2 signing verification; it is non-debuggable. Physical companion 0.1.1 pairing, capabilities and authorized Firefox native reads are verified; a native write approval expired without executing the action. WebMCP detection/permission/fallback and fixed CDP diagnostics are implemented; native WebMCP availability on Android and a live Chromium diagnostic run are not established.

Physical Android extension 1.0.0 has now passed the focused workflow/delta/reconnected-task check. The native APK is installed, paired and Accessibility-authorized. Split-screen native reads work when Firefox owns Android input focus; a visible Firefox pane alone does not establish that focus. The candidate has not completed the 16 live-model benchmark episodes, the full Android regression matrix, Mozilla signing or marketplace review. The final local broker and remote Codex/Claude MCP clients report 1.0.0, with a successful scoped remote Android workflow check. Existing downloadable release links intentionally remain 0.3.1-dev. The CLI/harness do not assert that Arvos/Fabric is already configured on a remote server.

## Goal and boundaries

Reduce model round trips and ambiguity per **completed, verified task**, while preserving per-user pairing, explicit authority, direct connections and a lightweight runtime. Python remains the core, fixed JavaScript commands execute in Firefox, and an optional Kotlin companion handles native Android capabilities. No mandatory cloud, VPN, root or ADB. MCP and CLI should use the same core; an external agent or Arvos/Fabric retains planning and budgets.

Four target contracts:

- **Capability:** backend, version, supported operations, authority and actual limits.
- **Observation:** document, revision, region, references, completeness and provenance.
- **Action:** caller-created identity, destination, preconditions, deadline and requested verification.
- **Receipt:** accepted, executed, effect observed, application outcome verified, remaining uncertainty and artifact references.

Do not infer saved application state from a successful click. Different servers connected to one Firefox share tabs and authenticated sessions; scheduling does not isolate profiles. Do not add arbitrary remote JavaScript or export cookies as an integration mechanism.

## Phase 1: reliable queueing and recovery

- [x] Separate active commands from retained results. Initial configurable limits: 256 active globally, 32 per authenticated client; history at most 1,000 results, 64 MiB and ten minutes. History eviction must not reject otherwise admissible active work.
- [x] Attribute quotas to authenticated credentials, never arbitrary caller labels. Preserve existing clients during migration.
- [x] Distinguish retryable delivery failure, permanently expired command and revoked credentials. Remove terminally rejected results from the reporter queue with an observable diagnostic; never replay the browser action.
- [x] Apply one result serialization policy to immediate responses and `browser_status`: compact/full/fields, uncertainty markers and image attachments remain consistent.
- [x] Separate control-plane processing from command execution and long status waits. Discovery, metrics and revocation remain responsive while command workers are blocked.

Acceptance: completed history cannot exhaust active capacity; a stale first result cannot block the next; recovered screenshots do not become JSON base64; four waiting actions cannot starve control requests. Retention must bound memory including results, not only object counts.

## Phase 2: operation contracts and protocol compatibility

Initial source files now exist: `operations.json`, `operation_registry.py`, a deterministic generator, generated JavaScript catalog and operation documentation. They provide metadata and per-operation **input** contracts for the browser command catalog (including the new lease operations). This is a partial foundation, not complete cross-backend enforcement or output schemas.

- [x] Source registry with engine, effect, ordering, platforms, tested baseline and input schema.
- [x] Dependency-free Python structural validator, including validation of all batch steps before dispatch.
- [x] Deterministic generated catalog/documentation and drift checks against existing broker/MCP/extension declarations.
- [x] Registry is integrated in Python admission, MCP contracts, build and generated extension operation lists. Generated Firefox input validation is active before dispatch; native uses its own policy.
- [x] Generate raw Firefox output schemas and input validators; maintain target/actionability checks. Output conformance is explicit, never a post-mutation retry trigger.
- [x] Centralize product version without conflating it with internal wire protocol or MCP protocol version.
- [x] Replace version echoing with explicitly supported, tested legacy MCP negotiation. Preserve the client versions verified with Codex and Claude.
- [x] Independently verify the referenced MCP 2026-07-28 specification and implement its adapter only against confirmed official content and conformance tests. A date/string is not evidence that a protocol exists or is supported.
- [x] Keep internal broker HTTP distinct from remote MCP transport. Unsupported mixed versions must fail before browser mutation with clear upgrade guidance.

`baselineVersion` is a conservative catalog baseline, not a historical feature-introduction claim. Runtime capability detection remains authoritative. Run `python3 generate_operations.py --check` and `python3 -m unittest -q test_operation_registry` to detect registry drift.

## Phase 3: stable action identity and workflow ownership

- [x] Caller-created `actionId` before transmission; authenticated client plus identifier is the deduplication key. Different payload under the same identity is a conflict.
- [x] SQLite local journal persists identity before acknowledging acceptance. Preserve minimal identity/outcome for 24 hours; page content and artifacts have separate shorter retention policies.
- [x] Recover dispatched actions with missing outcomes as `unknown`, never automatically resend. Once identity retention expires, explicitly report reconciliation unavailable.
- [x] Extension-enforced temporary per-tab workflow ownership across brokers, with expiry and generation/fencing checks immediately before execution. Expired owners cannot continue after takeover.
- [x] Cancellation/revocation prevents subsequent steps and reports already-produced effects. It cannot undo clicks or remote application writes.
- [x] Recheck optional document identity and observed role/type/name on references, plus workflow preconditions. This guards the observed semantics, not every hidden application state.

Acceptance: lost responses reconcile without duplicate actions; competing brokers cannot interleave protected workflows; restart, expiry and ownership transfer preserve uncertainty. No promise of universal exactly-once effects on third-party applications.

## Phase 4: action plus verification

- [x] Add `browser_step`: context/preconditions, fixed actions, bounded wait, requested verification and selected output.
- [x] Initial synchronous limits: 25 steps, 60 seconds, no arbitrary code or unbounded loops. Support prior-step references and declarative presence/value/text/URL conditions. General control-state conditions remain pending.
- [x] Receipt distinguishes `executed`, `verified`, `verification_failed` and `unknown`; normal output contains final evidence. Explicit selected task output is retained privately; arbitrary intermediate page contents are not persisted.
- [x] Keep `browser_command` for simple operations and compatibility.
- [x] Longer work uses persisted recoverable tasks, acknowledged only after storage; integrate MCP Tasks only for actually supported client/protocol versions.

Acceptance: equivalent controlled tasks need at least 30% fewer model calls without lower observed success; uncertainty never triggers automatic mutation replay.

## Phase 5: less DOM work and less context

- [x] Metadata-only reads skip control enumeration. Compute selectors and geometry only when requested.
- [ ] Progressive search stops when sufficient and labels partial counts accurately. Reuse geometry only within safe operation boundaries.
- [x] Region-scoped snapshot identities/deltas; gaps or navigation force a full resnapshot. General resolved-strategy caching remains a future optimization.
- [ ] Preserve detected blockers, errors, loading state and incomplete-result indicators in compact output.
- [x] Workflow selected output is bounded (14 KiB); task receipts and explicit native shares use private bounded/expiring artifacts.
- [ ] Profile bounded event coalescing and region-specific observation before introducing permanent whole-DOM indexes.
- [ ] Compare WebSocket only after measuring transport/queue/reconnect/Android cost. Long-poll timeout is not command latency.

Acceptance measures actual page work, bytes on each transport and client-reported tokens separately. Byte savings are not token or quota percentages.

## Phase 6: optional interchangeable integrations

- [x] **Arvos/Fabric contract:** `browser_cli.py` exposes workflows, task status/cancel and explicit private artifact download. Private orchestrator registration remains environment-specific. Public CLI JSON and MCP adapter for capability discovery, submit/status/cancel/artifact retrieval. Do not require the private `/root/arvos` checkout. Planning and budgets belong to the orchestrator; preserve distinct credentials across connected services.
- [x] **WebMCP implementation:** experimental, disabled by default, actual feature detection per browser; bind page tools to origin/frame/schema and bridge authority. Fall back to DOM when absent. Site-declared safety does not confer authorization; Firefox support is not assumed.
- [x] **Desktop diagnostic adapter:** retain Firefox audit backend; optional Chrome/CDP capability set for console, network and performance. Desktop evidence is never presented as Android evidence.
- [ ] **Android companion:** optional signed Kotlin APK with pairing, explicit URL/text/file sharing, approved app launches, approvals, local stop and authorized native accessibility controls. Prefer semantic nodes; serialize native control because one screen is shared. Accessibility activation and screen-capture consents remain native user steps; protected/unavailable screens return concrete limits. Browser operation remains usable without companion, ADB or root.
- [ ] **Interfaces:** extension/companion show connections, authorized scopes, activity, uncertainty and revoke. MCP Apps may expose the same controls on supporting hosts.

## Cross-cutting regression and agent benchmark gates

- [ ] Queue/history capacity and per-client fairness; stale delivery followed by valid delivery; revocation during report delivery.
- [ ] Compact recovered images; responsive controls under saturation; lost response/restart/deduplication; two brokers and expired tab ownership.
- [ ] Large/dynamic DOM, blockers, iframes, Shadow DOM, reused nodes, Android suspension and disconnected networks.
- [ ] Migration and downgrade preserve unrelated configuration and credentials; rollback is documented and tested.
- [ ] Run four controlled tasks (form, dynamic filter, concurrent tabs, uncertain-result recovery), baseline versus candidate on both Codex and Claude: 16 agent episodes per release.
- [ ] Freeze model/configuration/prompt in benchmark output. Initial run budget: 20 minutes, 300,000 total input tokens, 20,000 output tokens; stop at first limit. Report input/cache/output semantics explicitly to avoid double-counting cached input.
- [ ] Do not certify token cost if counters are absent. Exhausted budget or incomplete verification blocks promotion; do not automatically rerun costly agent tests.
- [ ] Record failures and timeouts, verified success, model calls, token categories, images, bytes and separate model/transport/broker/extension/page timing. Do not optimize only successful-request latency.

## Phase 7: distribution and rollout

- [ ] Prepare Mozilla signing and update paths early; use external private signing credentials. Native installation is not evidence of marketplace approval.
- [ ] Publish reproducible artifacts and signed companion APK; initial GitHub releases, marketplace publication only after real review/signing.
- [ ] Direct LAN/HTTPS first; optional self-hosted relay where direct reachability is absent. NAT/CGNAT traversal requires an actual network path; do not imply transport independence solves reachability.
- [x] Installer validates packages, backs up package/configuration changes and supports explicit package rollback. No destructive state migration is performed; rollback does not downgrade extension or journal schemas.
- [ ] Final integration test on the currently installed Android extension and Codex/Claude clients on arvos-next; mark native installation and live runtime separately.
- [ ] Publish commits, artifacts, compatibility matrix and aggregate evidence only. Never publish credentials, personal pages, raw screenshots/logs or private journals.

## Completion policy

This roadmap spans multiple releases. A checked implementation item still requires its acceptance gate before release promotion. Experimental backends must be labeled unavailable until runtime feature detection succeeds. Review source links/specifications live when implementing integrations; the proposal's external protocol/version claims are inputs to verify, not supported-capability declarations.
