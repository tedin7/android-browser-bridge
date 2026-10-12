# 0.3.0 development — one browser, multiple independent servers

A redesigned mobile-first Firefox settings page guides pairing with an explicit
consent step. Named connection cards show live state, endpoint, pause/resume and
removal; a global switch pauses every server. Italian and English interface text
follows the browser language. No credentials are rendered or placed in links.

Independent brokers now poll the same extension concurrently with isolated
credentials and result routing. An unreachable server does not block the others.
The tab scheduler remains shared across connections. All enabled servers control
the same tabs; this is not a per-server browsing sandbox. Legacy single-server
settings are migrated without requiring a new pairing.

Update the Firefox extension to 0.3.0 for these features. Existing MCP clients
remain compatible; automatic Codex setup remains available. The XPI is still
unsigned and AMO publication is pending. See docs/VALIDATION.md for the actual
scope of testing; previous Android tests do not establish this build’s installation.

For quick URL-opening requests, agent guidance now reuses a confirmed device,
queries capabilities only when needed, batches URL creation and limits final
verification. It distinguishes opened tabs from verified completed navigation.
49 Python tests, dedicated transport/UI Node suites, and real desktop Firefox
(two brokers plus full page operations) passed. Mozilla lint: zero findings.
