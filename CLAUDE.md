Le regole del progetto stanno in `AGENTS.md`: leggile per prime (autenticazione, loopback, dispositivo esplicito, niente JavaScript remoto arbitrario, niente token o contenuti di pagina nei log).

## Test

La procedura è nel `README.md`, sezione «Build e test». In una copia nuova o in un worktree genera prima i pacchetti con `python3 build.py` (alcuni test usano `android-browser-mcp.pyz`, ignorato da git), poi lancia i test dei file che tocchi, per esempio `python3 -m unittest -v test_bridge.py`.

## Rilascio

Vedi `docs/RELEASE_GATE.md` e `RELEASE_NOTES.md`.
