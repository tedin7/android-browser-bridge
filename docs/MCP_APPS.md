# Optional MCP Apps task panel

The static task panel uses an optional HTML resource linked from the existing task tool. It communicates with an MCP Apps host over the official iframe JSON-RPC interface; no browser credentials, external scripts or network connections are required. The SDK is optional, so this small panel implements the documented transport directly. [Official overview](https://modelcontextprotocol.io/extensions/apps/overview), [Apps specification](https://github.com/modelcontextprotocol/ext-apps/blob/main/specification/2026-01-26/apps.mdx).

`mcp_app.py` exports `resource_descriptor()`, `read_resource(uri)` and `tool_metadata()`. The resource URI is `ui://android-browser-bridge/task-panel`, MIME type `text/html;profile=mcp-app`. Its metadata requests no external domains, frames or additional permissions. Serve only that exact URI, attach the metadata to `browser_task`, and advertise resources only when the packaged HTML is available.

The UI shows one task's state, progress and constrained receipt fields. Refresh invokes `browser_task` with `action:get`; the cancellation button invokes `action:cancel` for that same task. It cannot start another task, select another connection, execute browser commands, read arbitrary resources or acquire credentials. Existing authenticated task ownership remains enforced by the server and host.

Communication is restricted to the parent window and, after handshake, its origin. The panel uses the `2026-01-26` Apps dialect, acknowledges initialization, handles task results and teardown, and renders values through `textContent`. This dialect is separate from the server's MCP transport version. Unknown protocols disable controls. Hosts without server-tool access can display receipts but cannot refresh or cancel.

Cancellation means a request to stop future work; the UI does not claim rollback or immediate termination. It waits for the server's state. Polling is manual, with no automatic model calls or background polling loop. No raw page data, arbitrary tool fields or credentials are displayed.

Validation: `python3 -m unittest -q test_mcp_app` checks the static resource and URI boundary; `node test_mcp_app.js` exercises handshake, foreign-window rejection, task binding, redaction, fixed get/cancel calls and teardown using an owned host simulation. **Runtime rendering in a real compatible MCP Apps host remains unverified.** Plain tool responses remain the fallback.
