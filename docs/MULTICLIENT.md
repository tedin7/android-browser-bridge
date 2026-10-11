# Più terminali e macchine sullo stesso Firefox Android

Un browser si abbina a **un broker**. Qualsiasi numero di client MCP autorizzati
può collegarsi a quel broker: non avviare un broker nuovo per ogni terminale e
non ripetere l’abbinamento Firefox.

## 1. Mantieni un solo broker in esecuzione

Se il broker è già attivo, riusalo. Per avviarlo separatamente dai client:

```sh
python3 android-browser-mcp.pyz --broker-only --local --port 8766
```

Per un altro Android, scegli l’endpoint effettivamente raggiungibile dal browser,
ascolto LAN esplicito oppure HTTPS pubblico come in [NETWORKING.md](NETWORKING.md).
Il processo broker deve restare attivo. Il suo token amministrativo è in
`~/.local/state/android-browser-bridge/token`, con permessi privati.

## 2. Installa un client in ciascun terminale o macchina

Dopo aver clonato il repository:

```sh
python3 install.py --attach http://127.0.0.1:8766 \
  --token-file "$HOME/.local/state/android-browser-bridge/token"
```

Questa modalità installa il client e genera la configurazione MCP senza avviare
un secondo broker. Il comando MCP corrispondente è:

```sh
python3 "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz" \
  --attach http://127.0.0.1:8766 \
  --token-file "$HOME/.local/state/android-browser-bridge/token"
```

Puoi usare questo stesso comando in più sessioni Codex o Claude. Chiudere uno dei
client non ferma il broker o gli altri client. Non usare `--local` insieme ad
`--attach`: `--local` appartiene al processo broker.

## 3. Client su un’altra macchina

Il client usa l’URL del broker raggiungibile **da quella macchina**. Su Internet
usa HTTPS. Su una LAN fidata puoi usare l’IP privato; HTTP non cifra le credenziali.
Un inoltro SSH loopback già autenticato è un’altra possibilità opzionale: non è
richiesto per il prodotto e non serve un tunnel o servizio di terzi.

Trasferisci il token tramite un canale cifrato sul tuo host fidato e conserva il
file con permessi 600. Il token concede accesso amministrativo al broker, inclusi
contenuti del browser, abbinamento e revoca: non condividerlo con persone o
macchine non autorizzate, né inserirlo nel prompt o nella chat.

Se l’URL visto dal client differisce da quello visto da Android, passa anche
`--url INDIRIZZO_RAGGIUNGIBILE_DA_ANDROID`. Serve per eventuali nuovi codici di
abbinamento; il browser già abbinato resta collegato al suo endpoint attuale.

```sh
python3 install.py --attach https://mio-linux.example:8766 \
  --token-file "$HOME/.local/state/android-browser-bridge/token"
```

Per Codex registra il comando stdio nella configurazione esistente, preservando
gli altri server, come in [CODEX.md](CODEX.md). Poi apri una nuova sessione Codex,
usa `browser_devices`, seleziona il dispositivo già abbinato e prova `tabs`.

## Coordinazione delle pagine

Tutti i client vedono le stesse schede. Usa sempre un `tabId` esplicito; assegna
schede distinte ai lavori contemporanei. Le azioni sulla stessa pagina condividono
lo stato e possono interferire fra client: coordinare flussi complessi è
responsabilità dei client. Il broker non crea copie separate del browser.
Nessun client può controllare l’installer Android tramite le operazioni web.
