Initial experimental prototype: direct Firefox Android ↔ Linux MCP connection.

Includes source, unsigned development XPI, dependency-free Python MCP zipapp,
instructions to install with an LLM, Firefox setup and direct LAN/Internet TLS.
No Cloudflare, relay, mandatory VPN or ADB. Optional fallback addresses of the
same broker support network changes.

Broker and packaged MCP are tested with a simulated browser. Real Firefox
Android verification and Mozilla signing are still pending. The XPI is not a
normal stable-Firefox installation package. See the README and Firefox guide.
