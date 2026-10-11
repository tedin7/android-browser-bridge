# Installazione tramite un LLM in chat

Copia il testo seguente in un assistente che può eseguire comandi sul tuo Linux.
Il collegamento pubblico al repository è sufficiente: non serve caricare file
locali. L'installazione è per il TUO browser e il TUO Linux.

```text
Installa Android Browser Bridge da
https://github.com/tedin7/android-browser-bridge

Leggi README.md, AGENTS.md e docs/NETWORKING.md prima di agire.
Per Codex leggi docs/CODEX.md; per Claude Code leggi docs/CLAUDE_CODE.md.
Esegui tu discovery, clone, build, test e configurazione MCP sul mio Linux.
Non usare ADB, VPN obbligatorie, Cloudflare, relay o tunnel esterni.
Non sovrascrivere altri server MCP, configurazioni, certificati o firewall.

Determina l'indirizzo Linux raggiungibile dal mio Android:
- stessa LAN: IP privato e porta 8766, HTTP solo su rete fidata;
- reti diverse: indirizzo pubblico raggiungibile e HTTPS;
- Linux dietro NAT: verifica port forwarding o IPv6 pubblico;
- se Linux è dietro CGNAT senza accesso entrante, spiega il blocco concreto:
  non fingere che l'estensione possa attraversarlo automaticamente.
Se non puoi sapere in quale rete è Android, chiedimelo.

Clona il repository in una nuova directory, poi esegui:
python3 -m unittest -v test_bridge.py
python3 build.py
python3 smoke_mcp.py
Se Node è disponibile, esegui anche node test_extension.js.

Usa install.py per installare il pacchetto nel mio utente e generare il blocco
MCP. Per HTTPS diretto usa launcher.py con --cert e --key già disponibili;
non disabilitare la verifica TLS e non esporre HTTP su Internet.
Inserisci il blocco nel mio client MCP preservando gli altri server, se il
client è identificabile; altrimenti forniscimi il blocco pronto da copiare.

Spiegami i passaggi manuali Firefox da docs/FIREFOX.md. L'XPI attuale è NON
firmato: non dichiarare che si installa normalmente in Firefox stabile.
L'installazione e il consenso nell'app Android devono essere fatti da me.
Dammi l'URL diretto di download XPI dalla release pubblica. Non inventare
un URL Mozilla Add-ons: la scheda del progetto non è ancora pubblicata.

Dopo che avrò installato e abilitato l'estensione, chiama browser_pair con
un nome per il mio dispositivo. Dammi la stringa BB1 da incollare entro
cinque minuti. Verifica browser_devices, quindi prova tabs e open su
https://example.org. Non automatizzare invii, acquisti o modifiche ad account
senza una mia istruzione. Riporta cosa hai verificato e cosa rimane da fare.
```

Il client MCP deve avviare il processo Linux e mantenerne aperto lo standard
input. La chiusura del client interrompe il servizio. Le credenziali persistono
nel profilo dell'utente; con gli stessi indirizzi l'abbinamento può essere
riutilizzato al prossimo avvio. Se è necessario un servizio indipendente dalla
vita del client, `bridge.py serve` è la base per un deployment separato, che
richiede una configurazione esplicita del servizio e del trasporto.
