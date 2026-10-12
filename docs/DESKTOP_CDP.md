# Optional desktop Chrome/CDP diagnostics

`desktop_cdp.mjs` attaches only when explicitly invoked with a loopback debugger endpoint and the exact URL of one already-open page. It does not start Chrome, discover other machines, open pages, navigate, reload, run page scripts, read cookies or collect request headers/bodies. It is **desktop-only**, separate from Firefox Android and the default MCP connection.

Node with its built-in `WebSocket` is required (tested here with Node 24.20.0). No Playwright dependency is used. Start an isolated debugging browser yourself using your platform's supported Chrome/Chromium setup, then run:

```sh
node desktop_cdp.mjs \
  --endpoint http://127.0.0.1:9222 \
  --tab-url https://your-owned-fixture.example/ \
  --duration-ms 1000 \
  --output /private/location/new-desktop-audit.json
```

Only loopback HTTP endpoints with an explicit port are accepted. Tab URL matching is exact; no match or multiple matching pages fails. The target WebSocket must remain on the same loopback endpoint. Output must name a new file: existing files and symlinks are not overwritten.

The fixed CDP method allowlist comprises enable/disable for Runtime, Log, Network and Performance, plus `Performance.getMetrics`. `Runtime.evaluate`, arbitrary method invocation, script arguments, response bodies and browser-wide target control are absent. Enabling Runtime captures console events; it does not evaluate page expressions.

Sampling duration is 1–10,000 ms, default 1,000. Discovery, WebSocket connection and each command have three-second deadlines. Up to 100 console and 100 network records are retained, with bounded strings; omitted records are counted. Metrics are bounded to 256 finite numeric values. Network records contain request URL/method, response status/MIME type and failure summaries, never headers or payload bodies. Console strings and URLs may still contain sensitive page data, so the artifact is private and should not be dumped wholesale into a model context.

Stdout contains only backend/platform, artifact path and aggregate counts. The JSON artifact is created with mode 0600; newly created directories use 0700. The caller owns cleanup and retention. This module does not implement a new broker, authority scope or MCP remote protocol.

Validation: `node test_desktop_cdp.mjs` exercises the fixed protocol with an owned fake, rejects cross-host target sockets and arbitrary methods, checks bounded capture and private artifact output. An attempted isolated local Chromium integration could not complete: Chromium exited with SIGTRAP shortly after announcing its debugging port in this PRoot environment. Therefore real Chrome/CDP behavior is **not yet validated here**, and no Android result is implied. The existing Firefox desktop driver remains separately tested.
