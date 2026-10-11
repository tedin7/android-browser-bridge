# 0.2.3 development — multiple MCP clients, extension unchanged at 0.2.1

Adds packaged --attach URL --token-file FILE client mode and --broker-only owner
mode. Multiple Codex/Claude sessions or machines can share one paired browser
through one broker. Attached clients never bind a listener, create broker state,
or shut down the shared broker on exit. The installer preserves unrelated MCP
configuration and makes private backups.

Three packaged multi-client regressions passed: simultaneous clients complete
commands through one actual HTTP broker and a simulated browser, closing one
leaves the other running, invalid credentials fail without fallback, and no
listener or new broker state is created. Use explicit tabIds for concurrent work;
compound navigation ordering is per MCP process, so coordinate writers sharing
the same page across clients. No Android extension reinstall is required.

The 0.2.2 Android navigation fix, 30 verified Android operations and measured
6–13 ms local-fixture median latency remain. Mozilla signing and native installer
control remain pending. Remote Codex live installation is tested separately.
