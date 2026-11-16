Le regole del progetto stanno in `AGENTS.md`: leggile per prime (autenticazione, loopback, dispositivo esplicito, niente JavaScript remoto arbitrario, niente token o contenuti di pagina nei log).

## Test

La procedura è nel `README.md`, sezione «Build e test». In una copia nuova o in un worktree genera prima i pacchetti con `python3 build.py` (alcuni test usano `android-browser-mcp.pyz`, ignorato da git), poi lancia i test dei file che tocchi, per esempio `python3 -m unittest -v test_bridge.py`.

## Rilascio

Vedi `docs/RELEASE_GATE.md` e `RELEASE_NOTES.md`.

## Come leggere le mie richieste (dal 16/11/2026)

- Scrivo in fretta e impreciso. Ricostruisci l'obiettivo, non eseguire le parole.
- Prima di un lavoro grande scrivi in poche righe: cosa hai capito, cosa è ambiguo, cosa contraddice decisioni già prese.
- Se un'ambiguità cambia il risultato, fermati e chiedi. Una domanda alla volta, la più importante per prima. Se non lo cambia, scegli tu, dillo in una riga e vai.
- Non fermarti alla prima soluzione che soddisfa le parole (minimo locale). Cerca la migliore raggiungibile con il tempo macchina e gli strumenti che hai.
- Prima di chiudere chiediti: cosa resta aperto? cosa avevo proposto e non ho fatto? c'è una strada che dà di più? Elenca quello che resta, non solo quello che hai fatto.
- Ogni punto che proponi finisce fatto, in una voce con data, o in una domanda per me. Mai lasciato a metà in chat.
- I token non sono un limite: lavoro lungo, sotto-agenti (rispettando il carico della macchina), prove e riletture sono voluti quando migliorano il risultato.
- Confine: vale quando ti scrivo io in chat. Un agente lanciato dal loop, o la chat del loop, non fa domande che aspettano: scrive il dubbio nel rapporto o in una voce e va avanti con il resto.
