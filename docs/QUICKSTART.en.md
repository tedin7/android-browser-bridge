# Connect your Firefox Android to your Linux assistants

Browser Bridge has no central account or relay service. Each person runs their
own broker; one extension can connect to up to sixteen independent servers.

1. Install the development extension from the [release](https://github.com/tedin7/android-browser-bridge/releases/tag/v0.3.1-dev).
   It is currently unsigned; follow the [Firefox development guide](FIREFOX.md).
2. Give your Linux assistant the repository URL and ask it to follow
   [INSTALL_WITH_LLM.md](INSTALL_WITH_LLM.md). In Codex, `python3 install.py --codex`
   installs and registers the client and browser instructions.
3. Make the broker reachable from your tablet. Different networks require a
   reachable HTTPS endpoint with a valid certificate. See [NETWORKING.md](NETWORKING.md).
   The tablet connects outwards; no incoming Android port, ADB or VPN is required.
4. Ask your assistant to pair the browser. It returns a single-use `BB1.…` code
   valid for five minutes.
5. In Firefox, open Extensions → Browser Bridge. Under **Add a connection**, paste
   the code, optionally name the server, check **I authorize this connection**,
   and select **Connect this browser**. Wait for **Connected**.

Repeat pairing for another independent server without replacing the first.
Multiple terminals sharing one broker instead reuse an authorized connection
profile and do not need another Firefox pairing. All enabled servers can access
the same tabs; use distinct tabs for parallel work.

Pause one connection from its card or use **Pause all**. Removing a connection
removes its local credential; `browser_revoke` invalidates it at the server too.
An action already started may still complete. An unreachable server does not
block the other connections. If Android suspends Firefox, reopen it.

Upgrade the extension to 0.3.1 for the new interface and independent servers.
The existing single-server pairing is preserved. This build has been tested on
real desktop Firefox; see [VALIDATION.md](VALIDATION.md) for the separate Android
and remote-host evidence. Store publication and signing remain pending.
