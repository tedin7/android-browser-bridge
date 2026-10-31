This project controls a user-authorized Firefox browser through an opt-in extension.
Keep authentication, loopback defaults, explicit device selection and fixed commands.
Never add arbitrary remote JavaScript execution. Do not log tokens or page contents.

## Test in una copia (worktree)

I test usano `android-browser-mcp.pyz` (ignorato da git): prima `python3 build.py`. Tre test di installazione riconoscono il ponte solo se la cartella si chiama `android-browser-bridge`: in un worktree con altro nome falliscono per ambiente. Usa una cartella con quel nome.
