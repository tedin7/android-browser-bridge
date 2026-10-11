# Installazione in Codex da terminale

Queste istruzioni riguardano **Codex CLI sul tuo Linux**, che avvia il MCP locale.

## Preparazione

```sh
git clone https://github.com/tedin7/android-browser-bridge.git
cd android-browser-bridge
python3 install.py
```

Scegli l'indirizzo Linux raggiungibile dal tuo Android. Il seguente esempio è
per una LAN fidata: sostituisci `192.168.1.10` con il tuo IP.
Controlla con `codex mcp list` che il nome non sia già configurato.

## Registra il MCP

```sh
codex mcp add android-browser -- \
  python3 "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz" \
  --listen 0.0.0.0 --port 8766 --url http://192.168.1.10:8766

codex mcp get android-browser
```

Il comando aggiunge il server alla configurazione Codex, preservando gli altri
server. Riavvia la sessione Codex e controlla gli strumenti MCP disponibili.
Poi chiedi:

```text
Usa browser_pair del MCP android-browser per abbinare il dispositivo my-phone.
Dammi la stringa BB1 da incollare nell'estensione Firefox Android.
Quando ti dico che è collegato, verifica browser_devices e mostra le schede.
```

Segui [FIREFOX.md](FIREFOX.md), incolla il codice nell'estensione, abilita il
controllo e salva. Conferma quindi il collegamento a Codex.

## Reti diverse e HTTPS

Alternativa per un server pubblico raggiungibile:

```sh
codex mcp add android-browser -- \
  python3 "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz" \
  --listen 0.0.0.0 --port 8766 --url https://linux.example.org:8766 \
  --cert /path/fullchain.pem --key /path/privkey.pem
```

Non eseguire entrambe le registrazioni sullo stesso nome. Usa un certificato
valido per il tuo indirizzo, insieme alla raggiungibilità descritta in
[NETWORKING.md](NETWORKING.md). `--fallback-url` può aggiungere indirizzi
alternativi del medesimo broker.

Il MCP è **stdio**. L'URL del broker per Android non è un server MCP HTTP:
non passarlo a `codex mcp add ... --url`.

Se l'ambiente gestito Codex vieta server MCP personalizzati o connessioni di
rete, la policy dell'ambiente resta applicabile; questa configurazione non
la aggira. Usa una sola istanza con la stessa porta/stato: chiudi Claude Code
se usa la medesima configurazione, oppure assegna istanze indipendenti.

Fonte ufficiale:
https://learn.chatgpt.com/docs/extend/mcp?surface=cli

## Collegarsi al browser già abbinato da più sessioni o macchine

Segui [MULTICLIENT.md](MULTICLIENT.md) e usa la modalità client `--attach`.
Ogni Codex può avviare il proprio processo stdio senza avviare un nuovo broker:

```sh
codex mcp add android-browser -- \
  python3 "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz" \
  --attach http://127.0.0.1:8766 \
  --token-file "$HOME/.local/state/android-browser-bridge/token"
```

Sostituisci URL e percorso token con quelli del broker già attivo. Il token va
provisionato tramite un canale cifrato e non incollato nel prompt. Se il nome
MCP esiste già, conserva la configurazione e scegli un nome distinto per la prova.
Non ripetere browser_pair per un dispositivo già abbinato.
