# 1.0 runtime candidate — not promoted

This checkout adds bounded active queues independent of retained history,
client-scoped credentials, durable action identities, compact result recovery,
separate MCP control workers and extension-enforced tab workflow leases.
`browser_step` combines fixed actions with explicit verification;
`browser_observe` returns bounded region snapshots/deltas; `browser_task`
persists cancellable workflows and private selected results.

A generated registry supplies input validation before browser dispatch and raw
Firefox output contracts. Observed references reject changed role/name/type;
optional document preconditions reject navigation changes before action.
DOM projection avoids unrequested descriptors and metadata-only enumeration.

Optional adapters include versioned MCP discovery, opt-in polling Tasks,
MCP Apps task status/cancel, JSON CLI with private artifact downloads,
disabled-by-default WebMCP, and local fixed CDP diagnostics. The separate Android
companion has a signed non-debuggable release candidate; native permissions and
one-use mutation approvals remain under local user control.

The release gate has concrete fixtures, independent state verification, actual
client usage parsers and bounded Codex/Claude launchers. No token-savings claim
or stable 1.0 promotion is made before the complete live benchmark and Android
candidate validation. Mozilla signing/marketplace, real MCP Apps host and native
physical-runtime validation remain separate gates. See docs/VALIDATION.md,
docs/RUNTIME_1_0_ROADMAP.md and companion/README.md.

The installer backs up the previous package and supports explicit package-only
rollback. Pairing is preserved. Existing running MCP processes load new tool
schemas only after their host reconnects/restarts them; replacing a package does
not restart another user's session.

# 0.3.1 development — lean MCP responses and fixed desktop layout audits

Compact browser_command responses are now the default: read starts at 2,000
text characters and 20 controls, locate at 20 controls, preserving refs, counts,
truncation, document/viewport evidence and safety metadata. Explicit limits win;
full restores the previous output and fields selects top-level properties.
Duplicate labels and long attributes/frame URLs are reduced with explicit flags.
Screenshot results in batches become MCP images rather than base64 inside JSON.

Updated agent guidance favors targeted DOM operations, confirmed devices and tab
IDs, batches and proportionate verification. Screenshots remain available when
visual evidence is required. Raw logs/HTML/tables should stay in evidence files.
Text response optimization also works with older installed Android extensions.

Extension 0.3.1 adds optional fixed inspect layout metadata and a desktop-only
viewport command. desktop_audit.py uses Firefox plus our MCP in a temporary
profile, without Playwright or arbitrary page JavaScript, and no screenshots
unless requested. Measured viewport matching and explicit limits prevent
claiming Android rendering or requested sizes that were not actually observed.

See docs/TOKEN_EFFICIENCY.md, docs/DESKTOP_AUDIT.md and docs/VALIDATION.md for
usage and measured verification. The XPI remains unsigned; no AMO approval.
