# Installazione automatica in Claude Code

Dalla checkout del repository sul tuo Linux:

```sh
python3 install.py --claude
```

Oppure configura entrambi i client in una sola esecuzione:

```sh
python3 install.py --codex --claude
```

L’installer rileva la connessione privata autorizzata, registra il processo
MCP stdio in Claude Code a livello utente e installa la skill browser con un
blocco gestito in ~/.claude/CLAUDE.md. Preserva altri MCP, progetti e impostazioni,
con backup privati. Se il nome android-browser appartiene a un altro progetto,
usa un nome disponibile senza sovrascriverlo. Non stampa credenziali.

Apri una nuova sessione Claude Code e usa /mcp per verificarne la presenza.
Richieste browser naturali usano la skill e il driver; la qualità della selezione
dipende dal modello e dal contesto. Non serve lanciare un modello per verificare
la registrazione: il client può essere inizializzato direttamente via stdio.

## Macchine con un wrapper nella riga MCP

Se in ~/.claude.json la riga `android-browser` non lancia direttamente il pacchetto
ma passa da un wrapper (sul Linux di Arvos: `mcp_pigro.py`, che avvia il server
solo quando serve), `install.py --claude` va evitato:

- il programma di installazione riconosce il ponte solo se un argomento è un file
  chiamato `android-browser-mcp.pyz`. Con un pacchetto rinominato (per esempio
  `android-browser-mcp-1.0.5-t6528.pyz`) crea una seconda riga `android-browser-2`
  accanto al wrapper; con il nome standard fonde i campi e **sostituisce `command` e
  `args`**, cioè toglie il wrapper;
- riscrive anche il blocco gestito in ~/.claude/CLAUDE.md.

Su queste macchine il rilascio di un cambio al pacchetto (guida, strumenti) è la sola
sostituzione del file in uso:

1. `python3 build.py` dal ramo principale;
2. copia di sicurezza del `.pyz` installato (`cp -p` con suffisso `.bak-AAAAMMGGTHHMMZ-CODICE`);
3. sostituisci il file letto dalla riga di ~/.claude.json (il percorso sta negli `args`);
4. prova: `python3 <pyz> --help` esce 0 e lo zip contiene il testo nuovo;
5. i processi MCP già aperti tengono il vecchio file in memoria: il cambio vale dalla
   prossima sessione o dal riavvio del server.

Non toccare la riga in ~/.claude.json. Il ritorno indietro è la copia di sicurezza
(o `--rollback-package`, vedi UPGRADE_ROLLBACK.md).

## Primo browser e macchine aggiuntive

Una nuova macchina deve essere autorizzata: il repository non inventa segreti.
Per un primo browser usa browser_pair e incolla BB1 in Firefox → Browser Bridge
→ Aggiungi un collegamento, con consenso esplicito. La connessione deve essere
raggiungibile da Android; su Internet usa HTTPS come in NETWORKING.md.

Più sessioni Codex e Claude possono condividere il broker persistente senza
rifare l’abbinamento né chiudere l’altro client. Mantieni tabId espliciti e
assegna schede diverse ai lavori paralleli. Per più server indipendenti leggi
[MULTICLIENT.md](MULTICLIENT.md). Non usare l’URL del broker come un server MCP
HTTP: il nostro adattatore è stdio.

Questa procedura configura Claude Code nel terminale. Non modifica Claude Web
né l’app Claude Desktop. Per risposte compatte e uso proporzionato delle
immagini leggi [TOKEN_EFFICIENCY.md](TOKEN_EFFICIENCY.md).

Riferimento CLI del prodotto: https://code.claude.com/docs/en/mcp
