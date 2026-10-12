# Experimental WebMCP adapter

`extension/webmcp_adapter.js` is an optional consumer adapter, disabled by default.
It uses the documented `document.modelContext.getTools()` and
`document.modelContext.executeTool(tool, input, {signal})` APIs. It does not
install a page shim or execute caller-supplied JavaScript.

Create the adapter inside the target content-script frame using
`createWebMCPAdapter(document, window, trustedConfiguration)`. Configuration must
come from extension settings, never remote command arguments. Enabling it
requires exact `allowedOrigins` and `allowedToolNames` lists. Tools must belong
to that document origin and frame. Page annotations do not grant authority.
Discovery returns bounded untrusted descriptors. Invocation requires the exact
previously observed input schema, checks a deliberately limited JSON Schema
subset, and refuses unsupported keywords. There are no automatic retries.
Timeouts or navigation may leave an uncertain outcome; inspect before acting
again. A successful invocation does not verify an application transaction.

`probe()` reports API presence separately from configuration authorization.
When the native API is absent, use the existing fixed DOM operations. The
adapter's unit tests use mocked native APIs; they do not establish support in
Firefox Android or real Chrome. The extension exposes fixed `webmcp_discover` and `webmcp_invoke` operations,
with explicit tab/frame selection and the existing workflow lease checks.
Use the dedicated WebMCP section in extension options to enable exact origins
and tool names. Invocation rechecks local authorization immediately before
calling the native API. Remote command arguments cannot change these settings.
`webmcp_discover` returns an empty tool list plus the DOM fallback when disabled
or unsupported. `webmcp_invoke` takes `toolName`, `input`, `expectedSchema` and an
optional timeout of at most 15 seconds.

Sources checked on 2026-10-12:

- [Chrome WebMCP imperative consumer APIs](https://developer.chrome.com/docs/ai/webmcp/imperative-api).
- [WebMCP browser implementation status](https://github.com/webmachinelearning/webmcp/blob/main/implementation-status.md): Firefox lists tracking references, not a confirmed supported release.
