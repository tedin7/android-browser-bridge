# Installazione tramite un LLM in chat

Copia il testo seguente in un assistente che può eseguire comandi sul tuo Linux.
Il collegamento pubblico al repository è sufficiente: non serve caricare file
locali. L'installazione è per il TUO browser e il TUO Linux.

```text
Installa Android Browser Bridge da
https://github.com/tedin7/android-browser-bridge

Leggi README.md, AGENTS.md e docs/NETWORKING.md prima di agire.
Se voglio riusare il browser già abbinato da più terminali o macchine, leggi
anche docs/MULTICLIENT.md: installa --attach con URL e file token già provisionati,
non creare un secondo broker e non richiedere un nuovo abbinamento.
Per Codex leggi docs/CODEX.md; per Claude Code leggi docs/CLAUDE_CODE.md.
Esegui tu discovery, clone, build, test e configurazione MCP sul mio Linux.
Non usare ADB, VPN obbligatorie, Cloudflare, relay o tunnel esterni.
Non sovrascrivere altri server MCP, configurazioni, certificati o firewall.

Per Codex esegui python3 install.py --codex: rileva la connessione già
configurata, migra le credenziali in un profilo privato e registra il MCP con
skill e istruzioni per usare il browser in modo implicito in qualsiasi lingua.
Non chiedermi IP o percorsi se sono già rilevabili; non inserirli nel codice.
Preserva gli altri MCP e le istruzioni AGENTS esistenti.

Per verificare la checkout, esegui prima python3 build.py, poi:
python3 -m unittest -v test_bridge.py test_navigation.py test_attach.py test_setup.py
python3 smoke_mcp.py
Se Node è disponibile esegui node test_extension.js.

Se non c’è una connessione Browser Bridge autorizzata, non inventare credenziali.
Prepara il broker locale e determina la raggiungibilità Android seguendo
NETWORKING.md. Usa solo connessioni fidate: HTTPS su Internet, HTTP soltanto in
LAN fidata o loopback con trasporto SSH cifrato già autorizzato. Se mancano
indirizzo di rete o autorizzazione, spiega il requisito concreto.
L’XPI è non firmato: non dichiarare installabilità normale su Firefox stabile.
Se l’estensione 0.2.1 è già installata, aggiorna soltanto il Linux.
Completa autonomamente i passaggi Android quando hai strumenti per controllarne
l’interfaccia; altrimenti indica soltanto il consenso/installazione indispensabili.
Non presentare foreground come controllo dell’installer.

Solo per un primo abbinamento, dopo installazione e controllo abilitato, usa
browser_pair con il nome scelto per il dispositivo. Per un collegamento esistente
usa browser_devices e non revocare/rifare l’abbinamento. Dammi la stringa BB1 da incollare entro
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
