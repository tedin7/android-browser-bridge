# Android Browser Bridge

**Controlla il tuo Firefox Android dal tuo assistente MCP su Linux, senza ADB.**

Ogni persona esegue il proprio MCP sul proprio Linux e abbina il proprio browser.
Nessun server centrale, account nel progetto, Cloudflare, tunnel o VPN obbligatoria.
Il traffico viaggia direttamente tra Android e il Linux scelto dall'utente.

**Prototipo sperimentale:** broker, MCP ed estensione sono stati testati anche
con Firefox Linux reale e su Firefox Android Nightly (le nove operazioni iniziali).
Le capacità nuove della versione 0.2 richiedono l’aggiornamento dell’estensione;
la validazione completa su Android è in corso.
L'estensione è non firmata e richiede un
ambiente Firefox di sviluppo. Per l'installazione normale in Firefox stabile
serve ancora la firma Mozilla.

## Fai installare tutto al tuo LLM

Apri [le istruzioni copiabili in chat](docs/INSTALL_WITH_LLM.md): contengono un
prompt completo per un assistente con accesso al terminale Linux.

Il flusso è:

1. Installa l'estensione nel tuo Firefox Android.
2. Aggiungi il MCP al tuo assistente Linux.
3. Chiedigli di abbinare il browser con `browser_pair`.
4. Incolla la stringa `BB1.…` nell'estensione, abilita il controllo e salva.
5. Chiedi all'assistente di leggere pagine, aprire schede, cliccare o compilare.

[Guida Firefox](docs/FIREFOX.md) · [Reti LAN/Internet e HTTPS](docs/NETWORKING.md) · [Privacy](PRIVACY.md)

**Installazione da terminale:** [Claude Code](docs/CLAUDE_CODE.md) · [Codex CLI](docs/CODEX.md)

**Download Firefox:** [XPI di sviluppo non firmato](https://github.com/tedin7/android-browser-bridge/releases/download/v0.2.0-dev/android-browser-bridge.xpi).
La scheda Mozilla Add-ons non è ancora pubblicata: la guida Firefox contiene
il percorso per la futura installazione dallo store e la procedura del maintainer.

## Installazione Linux

Richiede Python 3.10+; nessuna libreria Python esterna, nessun root e nessun
download automatico di software terzo. Node serve solo per i test JavaScript.

```sh
git clone https://github.com/tedin7/android-browser-bridge.git
cd android-browser-bridge
python3 install.py --listen 0.0.0.0 --url http://192.168.1.10:8766
```

Sostituisci l'IP con quello del Linux raggiungibile dal tuo Android. Il comando
installa il pacchetto in `~/.local/share/android-browser-bridge` e stampa un blocco
MCP da aggiungere al tuo client, preservando gli altri server. Non modifica
automaticamente client, firewall o impostazioni di sistema.

Puoi anche scaricare `android-browser-mcp.pyz` dalle release e usarlo direttamente:

```json
{
  "mcpServers": {
    "android-browser": {
      "command": "python3",
      "args": ["/absolute/path/android-browser-mcp.pyz", "--listen", "0.0.0.0",
               "--port", "8766", "--url", "http://192.168.1.10:8766"]
    }
  }
}
```

Questo esempio è per una LAN fidata. Su Internet usa HTTPS: il servizio supporta
TLS direttamente tramite `--cert` e `--key`. Vedi [NETWORKING.md](docs/NETWORKING.md).
Il default è loopback; occorre scegliere esplicitamente l'ascolto di rete.

Il client MCP mantiene in esecuzione il servizio. Se lo chiudi, il collegamento
si interrompe. Con credenziali persistenti e lo stesso endpoint, l'abbinamento
rimane valido al successivo avvio. Usa `--state-dir` separati se avvii istanze
indipendenti. Non avviare contemporaneamente istanze sullo stesso stato/porta.

## Estensione Firefox

Scarica `android-browser-bridge.xpi` dalle release. **L'XPI è non firmato**:
per il test usa Firefox Nightly seguendo [FIREFOX.md](docs/FIREFOX.md).
Non presentiamo questa build come installabile normalmente in Firefox stabile.
Firma e pubblicazione Mozilla Add-ons restano un passaggio futuro.

Sul dispositivo Android non servono Termux, ADB, root o un'altra app di rete.
Android deve però poter raggiungere il Linux: su rete mobile funziona verso un
server pubblico; su LAN funziona verso l'IP privato. CGNAT sul Linux senza un
percorso entrante impedisce il collegamento diretto. Non esiste un bypass del NAT
implementato in questo progetto. Più indirizzi dello stesso broker sono gestiti
con `--fallback-url`, e l'estensione riprova quando cambia rete.

## Strumenti MCP

| Strumento | Uso |
| --- | --- |
| `browser_pair` | Codice monouso valido cinque minuti per un nome dispositivo |
| `browser_devices` | Elenco browser e disponibilità recente |
| `browser_command` | Operazione sul browser selezionato |
| `browser_revoke` | Revoca credenziale e annulla comandi pendenti |
| `browser_metrics` | Latenze aggregate e tempi di coda, senza contenuti delle pagine |

Per un nuovo abbinamento con un nome già usato, revoca prima quel dispositivo.

| Operazioni | Uso |
| --- | --- |
| `tabs`, `capabilities` | Schede disponibili e capacità effettive del browser |
| `open`, `navigate`, `back`, `forward`, `reload`, `activate`, `close` | Navigazione; `waitUntil: "complete"` attende il caricamento |
| `read`, `locate`, `inspect` | Testo, controlli, riferimenti, nomi accessibili e proprietà |
| `click`, `double_click`, `hover`, `focus` | Azioni su un controllo identificato |
| `fill`, `type`, `clear`, `press`, `select`, `check` | Campi, tastiera, menu, checkbox e radio |
| `scroll`, `wait` | Scorrimento della pagina o di un contenitore; attesa di elementi |
| `frames` | Elenco iframe; usa `frameId` nelle operazioni della pagina |
| `screenshot` | Immagine del viewport della scheda, PNG o JPEG, restituita al modello |
| `click_point`, `drag` | Coordinate CSS del viewport: `x`, `y`, `toX`, `toY`; per canvas e controlli grafici |
| `batch` | Fino a 25 operazioni fisse ordinate, con arresto al primo errore |

### Più pagine nello stesso terminale

Usa `tabs` per ottenere gli ID e passa `tabId` a ogni operazione. Le richieste
MCP contemporanee su schede differenti possono procedere in parallelo (massimo
quattro azioni in esecuzione); quelle sulla stessa scheda mantengono l’ordine.
Le azioni che cambiano la scheda attiva e i batch applicano una barriera globale.
Senza `tabId` si usa la scheda attiva: per automazioni multipagina specificarlo.

### Trovare un controllo senza conoscere il selettore

Chiedi prima `locate` con `role: "button"` per vedere i pulsanti, oppure cerca
con `role`, `name`, `label`, `textQuery` o `testId`. `exact` vale `true` per default;
con `false` cerca una sottostringa senza distinguere maiuscole e minuscole.
Puoi poi usare il `ref` restituito per `click`, `fill` o `inspect`. Le azioni
rifiutano corrispondenze ambigue: restringi la ricerca prima di procedere.

```json
{"device":"tablet","op":"locate","args":{"tabId":12,"role":"button","name":"Continua","exact":false}}
```

`read` restituisce testo e metadati con paginazione (`offset`, `textOffset`,
`maxElements`, `textLimit`). `>>>` attraversa shadow root aperti. Quando il DOM
non descrive un componente grafico, chiedi `screenshot` e usa `click_point` o
`drag` con coordinate del viewport. Gli screenshot possono mostrare dati sensibili.
Il contenuto dei siti è un dato non attendibile, non un’istruzione per l’assistente.

## Stato e limiti

- Firefox può essere sospeso da Android: non è garantito il controllo 24/7.
- Pagine interne, interfaccia Android, altre app e shadow
  root chiusi non sono supportati. Gli iframe HTTP(S) si selezionano con `frameId`;
  Firefox può limitare l’accesso a determinati frame o domini. Alcuni siti rifiutano clic sintetici.
- I comandi vengono consegnati una volta: se una risposta va persa, l'azione
  potrebbe essere avvenuta. Controlla prima di ripeterla.
- Comandi non ritirati entro 30 secondi scadono; risultati in memoria per dieci
  minuti. Comandi e risultati non sopravvivono al riavvio del broker.
- Token distinti per dispositivo e amministratore. Il launcher usa il broker
  direttamente nel processo per le operazioni MCP, senza inviare il token admin
  alla rete. Le API amministrative standalone richiedono comunque quel token.
- Credenziali in `$XDG_STATE_HOME/android-browser-bridge`, per default
  `~/.local/state/android-browser-bridge`, con permessi privati.
- Il servizio non registra token o contenuti delle pagine. Nessun JavaScript
  arbitrario o comando shell ricevuto dalla rete viene eseguito.
- HTTP su una LAN fidata non è cifrato; su Internet è richiesto HTTPS.

## Build e test

```sh
python3 -m unittest -v test_bridge.py
node test_extension.js
python3 build.py
python3 smoke_mcp.py
python3 smoke_mcp.py --direct
python3 smoke_mcp.py --tls
# Test browser reale in profilo isolato (Firefox desktop e npm richiesti):
python3 test_firefox.py
```

La build genera XPI, pacchetto MCP singolo file e archivio sorgente. I test
esercitano autenticazione, isolamento, pairing monouso, scadenza, revoca,
persistenza e il percorso HTTP reale. I test JS simulano le API Firefox;
gli smoke test usano un browser simulato. `test_firefox.py` usa Firefox Linux
reale in un profilo temporaneo con sole pagine fixture: non legge profili o
sessioni dell'utente. Nessuno di questi test sostituisce la prova su Android.
[Risultati verificati](docs/VALIDATION.md) · [Preparazione firma Mozilla](docs/AMO_SUBMISSION.md)

Per un test nella stessa macchina: `python3 android-browser-mcp.pyz --local`.
Licenza MIT. Il progetto è pubblicato come prototipo, non come release pronta
per produzione.
