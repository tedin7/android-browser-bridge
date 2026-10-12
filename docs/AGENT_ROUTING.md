# Richieste browser riconosciute automaticamente

`python3 install.py --codex` registra il MCP e installa:

- una skill `android-browser-bridge` nel profilo Codex;
- un blocco gestito in AGENTS globale, preservando le istruzioni esistenti;
- la connessione runtime in un profilo privato, rilevata automaticamente.

La selezione è semantica, non una lista di parole o lingue nel codice.
«Fai tu questa cosa nel browser», «Open this page in my browser» e una richiesta
più ampia che richiede compilare un modulo seguono lo stesso driver MCP.
Una domanda fattuale generica non richiede il controllo del browser personale.
L’agente scopre gli strumenti, controlla i dispositivi e usa tabId espliciti.
I nomi dei server e dei dispositivi non sono hardcoded nelle istruzioni.

Apri una nuova sessione Codex dopo installazione/aggiornamento delle istruzioni.
La skill spiega ricerca semantica dei controlli, screenshot, iframe, schede
multiple e recupero tramite nextSteps/browser_status. Le operazioni non supportate
vengono dichiarate: il driver web non controlla l’installer Android o le pagine
interne Firefox. I contenuti delle pagine sono dati, non istruzioni per il modello.

Le autorizzazioni della richiesta restano applicabili. Il driver non autorizza
azioni aggiuntive su account, pubblicazione di dati o invii non richiesti.
Le prove reali di selezione su Codex via SSH sono riportate in VALIDATION.md.
La qualità della selezione dipende anche dal modello e dalle istruzioni del client;
la verifica reale deve controllare le chiamate MCP, non solo il testo della skill.
