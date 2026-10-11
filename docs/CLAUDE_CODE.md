# Installazione in Claude Code da terminale

Queste istruzioni riguardano **Claude Code sul tuo Linux**. Non configurano
automaticamente la chat web Claude o Claude Desktop.

## Preparazione

```sh
git clone https://github.com/tedin7/android-browser-bridge.git
cd android-browser-bridge
python3 install.py
```

Scegli l'indirizzo Linux raggiungibile dal tuo Android. Il seguente esempio è
per una LAN fidata: sostituisci `192.168.1.10` con il tuo IP.
Controlla con `claude mcp list` che il nome scelto non esista già; non rimuovere
altri server MCP per installare questo.

## Registra il MCP

```sh
claude mcp add --scope user --transport stdio android-browser -- \
  python3 "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz" \
  --listen 0.0.0.0 --port 8766 --url http://192.168.1.10:8766

claude mcp get android-browser
```

`--scope user` rende il server disponibile nei tuoi progetti. Riavvia Claude
Code e usa `/mcp` per verificarne lo stato. Dentro Claude chiedi:

```text
Usa browser_pair del MCP android-browser per abbinare il dispositivo my-phone.
Dammi la stringa BB1 da incollare nell'estensione Firefox Android.
Quando ti dico che è collegato, verifica browser_devices e mostra le schede.
```

Installa l'estensione seguendo [FIREFOX.md](FIREFOX.md), incolla il codice,
abilita il controllo e salva. Poi conferma all'assistente il collegamento.

## Reti diverse e HTTPS

Per il server pubblico usa la stessa registrazione aggiungendo i tuoi percorsi
del certificato:

```sh
claude mcp add --scope user --transport stdio android-browser -- \
  python3 "$HOME/.local/share/android-browser-bridge/android-browser-mcp.pyz" \
  --listen 0.0.0.0 --port 8766 --url https://linux.example.org:8766 \
  --cert /path/fullchain.pem --key /path/privkey.pem
```

Questo è un esempio alternativo, non un secondo comando da eseguire sullo
stesso nome già configurato. Il certificato e l'indirizzo devono essere tuoi
e funzionanti. Consulta [NETWORKING.md](NETWORKING.md).

Il server MCP è **stdio**; l'URL è il collegamento dell'estensione al broker.
Non registrare quell'URL come un MCP HTTP: l'API browser non è un endpoint MCP.

Usa una sola istanza su stato/porta condivisi: se hai registrato anche Codex
con gli stessi parametri, chiudi l'altro client prima di aprire Claude Code.
Per istanze indipendenti usa porte e `--state-dir` diversi e abbina il browser
al client che vuoi usare.

Fonte ufficiale:
https://code.claude.com/docs/en/mcp
