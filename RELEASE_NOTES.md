# 0.2.4 development — automatic Codex setup and browser intent routing

One command, python3 install.py --codex, discovers existing authorized Browser
Bridge settings, creates a private connection profile, installs/registers the
MCP and installs a discoverable browser skill plus managed global instructions.
No machine IP, port, device ID or credential path is required in the agent prompt.
Other servers, native helper bindings and user instructions are preserved with
private backups. A new machine still needs authorization; credentials are not
invented or public. Profile-based clients share one broker without restarting it.

Browser task routing is semantic and language-independent, including browser
steps implicit in broader tasks. Actual model/tool-selection tests are reported
separately. Extension 0.2.1 is unchanged; no Android reinstall is required.

Verified with real Codex on arvos-next: repo-only automatic installation, natural
Italian and English browser requests, and actual Android operations with remote
medians 118–147 ms. See docs/VALIDATION.md for scope and measurements. Custom
private profile filenames now also support cold bootstrap and owner restart.
