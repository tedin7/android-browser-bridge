This project controls a user-authorized Firefox browser through an opt-in extension.
Keep authentication, loopback defaults, explicit device selection and fixed commands.
Never add arbitrary remote JavaScript execution. Do not log tokens or page contents.

## Test in una copia (worktree)

I test usano `android-browser-mcp.pyz` (ignorato da git): prima `python3 build.py`. Dal 192c5d0 i test di installazione riconoscono il ponte dal manifest, non dal nome della cartella: un worktree con qualsiasi nome va bene.
