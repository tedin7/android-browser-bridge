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
